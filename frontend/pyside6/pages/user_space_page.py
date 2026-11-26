"""博主个人空间页：参照 B 站 space.bilibili.com/<mid>/upload/video 投稿页布局。

结构：
- 顶部：博主资料条（头像/昵称/签名/关注粉丝 Lv）+ 在 B 站打开
- 左侧：分类导航（动态=全部/视频；投稿=视频/图文/音频；合集隐藏）
- 右侧：动态列表 / 投稿网格 / 合集列表，支持排序切换与分页

支持动态真分页、投稿/合集切换、返回上一页。
"""
import logging
import time

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget, QGridLayout,
)

from src.models import MediaItem, UserInfo
from src.services.social import SocialService
from src.services.archive import ArchiveService
from src.services.dynamic import DynamicService
from src.services.user import UserService
from src.api.auth import get_wbi
from src.urls.user_urls import UserUrls

from frontend.pyside6.avatar import AvatarLoader, placeholder, cover_placeholder
from frontend.pyside6.signals import app_signals
from frontend.pyside6.workers.social_worker import load_social

logger = logging.getLogger(__name__)

_COVER_W, _COVER_H = 190, 108


def _fmt_count(n: int) -> str:
    """播放量格式化：>=10000 显示 x.x万。"""
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


# 动态类型徽章：kind → (显示文案, 颜色)。颜色取主题强调色系，便于快速区分。
_DYN_KIND_BADGE = {
    "word": ("纯文字", "#8c8c8c"),
    "draw": ("图文", "#2e7d32"),
    "archive": ("视频", "#c62828"),
    "article": ("专栏", "#6a1b9a"),
    "live": ("直播", "#e65100"),
    "forward": ("转发", "#1565c0"),
    "music": ("音乐", "#00838f"),
    "pgc": ("剧集", "#ad1457"),
    "ugc_season": ("合集", "#4527a0"),
    "medialist": ("歌单", "#00695c"),
    "courses": ("课程", "#37474f"),
    "common": ("分享", "#5d4037"),
    "unknown": ("动态", "#8c8c8c"),
}


def _dyn_badge(info) -> tuple[str, str]:
    """根据 DynamicInfo 推导类型徽章；转发动态优先按原动态类型显示。"""
    kind = info.kind
    if kind == "forward" and info.forward and info.forward.orig:
        kind = info.forward.orig.kind or "forward"
    label, color = _DYN_KIND_BADGE.get(kind, (kind or "动态", "#8c8c8c"))
    # 有图片但类型为 word 的，标注为图文
    if kind == "word" and info.images:
        label, color = _DYN_KIND_BADGE["draw"]
    return label, color


class _VideoCard(QWidget):
    """视频卡片：封面 + 播放/弹幕/时长 + 标题 + 日期。"""

    def __init__(self, media: MediaItem, loader: AvatarLoader, on_click, parent=None):
        super().__init__(parent)
        self.media = media
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("VideoCard")

        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        self.cover = QLabel()
        self.cover.setFixedSize(_COVER_W, _COVER_H)
        self.cover.setPixmap(cover_placeholder(_COVER_W, _COVER_H))
        loader.load_cover(media.cover, _COVER_W, _COVER_H, self.cover.setPixmap)
        v.addWidget(self.cover)

        # 封面底部信息条：播放量 / 弹幕 / 时长
        info = ""
        if media.play:
            info += f"▶ {_fmt_count(media.play)}  "
        if media.danmaku:
            info += f"💬 {_fmt_count(media.danmaku)}  "
        if media.duration:
            m, s = divmod(media.duration, 60)
            info += f"{m:02d}:{s:02d}"
        bar = QLabel(info.strip())
        bar.setObjectName("Dim")
        v.addWidget(bar)

        title = QLabel(media.title or "无标题")
        title.setWordWrap(True)
        title.setFixedHeight(36)
        v.addWidget(title)

        if media.pubdate:
            date = QLabel(time.strftime("%Y-%m-%d", time.localtime(media.pubdate)))
            date.setObjectName("Dim")
            v.addWidget(date)

        self.mousePressEvent = lambda e: on_click(media) if e.button() == Qt.MouseButton.LeftButton else None


class _ArchiveCard(QWidget):
    """合集卡片：封面 + 标题 + 视频数量。点击按 season_id 下载整个合集。"""

    def __init__(self, title: str, cover: str, total: int, loaded: int,
                 loader: AvatarLoader, on_click, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("VideoCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)
        self.cover = QLabel()
        self.cover.setFixedSize(_COVER_W, _COVER_H)
        self.cover.setPixmap(cover_placeholder(_COVER_W, _COVER_H))
        loader.load_cover(cover, _COVER_W, _COVER_H, self.cover.setPixmap)
        v.addWidget(self.cover)
        count = QLabel(f"共 {total} 个视频")
        count.setObjectName("Dim")
        v.addWidget(count)
        name = QLabel(title)
        name.setWordWrap(True)
        name.setFixedHeight(36)
        v.addWidget(name)
        self.mousePressEvent = lambda e: on_click() if e.button() == Qt.MouseButton.LeftButton else None


class _DynamicCard(QWidget):
    """动态卡片：头像 + 昵称 + 时间 + 正文 + 图片缩略（参照 B 站动态页）。"""

    def __init__(self, info, loader: AvatarLoader, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoCard")
        self.info = info
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        head = QHBoxLayout()
        avatar = QLabel()
        avatar.setFixedSize(36, 36)
        avatar.setPixmap(placeholder(36))
        if info.author.face:
            loader.load(info.author.face, 36, avatar.setPixmap)
        head.addWidget(avatar)
        meta = QVBoxLayout()
        meta.setSpacing(0)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name = QLabel(info.author.name or "动态")
        name.setObjectName("NameBig")
        name_row.addWidget(name)
        # 类型徽章：图文/视频/纯文字等，放在昵称右侧
        badge_text, badge_color = _dyn_badge(info)
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"color: #ffffff; background-color: {badge_color}; border-radius: 4px; "
            "padding: 1px 6px; font-size: 11px;"
        )
        name_row.addWidget(badge)
        name_row.addStretch(1)
        meta.addLayout(name_row)
        pub = QLabel(info.author.pub_time or "")
        pub.setObjectName("Dim")
        meta.addWidget(pub)
        head.addLayout(meta, 1)
        outer.addLayout(head)

        text = (info.content.text or "").strip()
        if text:
            body = QLabel(text[:500])
            body.setWordWrap(True)
            outer.addWidget(body)

        if info.images:
            # 最多显示前 3 张缩略图
            row = QHBoxLayout()
            row.setSpacing(6)
            for img in info.images[:3]:
                thumb = QLabel()
                thumb.setFixedSize(140, 90)
                thumb.setPixmap(cover_placeholder(140, 90))
                if img.url:
                    loader.load_cover(img.url, 140, 90, thumb.setPixmap)
                row.addWidget(thumb)
            row.addStretch(1)
            outer.addLayout(row)

        # 卡片类动态：显示来源标题（类型已由徽章标注，这里不再重复 kind）
        if info.cards:
            card = info.cards[0]
            if card.title:
                link = QLabel(card.title)
                link.setObjectName("Dim")
                link.setWordWrap(True)
                outer.addWidget(link)
        if info.forward and info.forward.orig:
            orig = QLabel(f"转发：{info.forward.orig.content.text[:80]}")
            orig.setObjectName("Dim")
            orig.setWordWrap(True)
            outer.addWidget(orig)


class UserSpacePage(QWidget):
    """博主空间页（投稿视频）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MySpacePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._service = SocialService()
        self._archive = ArchiveService()
        self._dynamic = DynamicService()
        self._loader = AvatarLoader(self)
        self._mid = 0
        self._pn = 1
        self._total = 0
        self._worker = None
        self._order = "pubdate"  # pubdate / click / stow
        self._view = "dynamics"  # dynamics / videos / archives / articles / audio
        self._dyn_filter = "all"  # all / video
        # 动态分页：offsets[i] 是第 i+1 页的起始游标，_dyn_page 从 1 开始。
        # 用游标栈支持真正的上一页/下一页（每页独立，不累加到一页）。
        self._dyn_page = 1
        self._dyn_offsets: list[str] = [""]
        self._dyn_has_more = True
        self._build()

    PS = 12  # 每行 4 个 × 3 行

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(10)

        # 顶部：返回 + 打开 B 站空间
        top = QHBoxLayout()
        btn_back = QPushButton("‹ 返回")
        btn_back.setObjectName("NavItem")
        btn_back.clicked.connect(lambda: app_signals.goto_page.emit("myspace"))
        top.addWidget(btn_back)
        top.addStretch(1)
        self.btn_open_web = QPushButton("在 B 站打开")
        self.btn_open_web.clicked.connect(self._open_in_browser)
        top.addWidget(self.btn_open_web)
        outer.addLayout(top)

        # 博主资料条
        card = QWidget()
        card.setObjectName("Card")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cv = QHBoxLayout(card)
        cv.setContentsMargins(14, 10, 14, 10)
        cv.setSpacing(12)
        self.avatar = QLabel()
        self.avatar.setFixedSize(56, 56)
        self.avatar.setPixmap(placeholder(56))
        cv.addWidget(self.avatar)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.name = QLabel("加载中…")
        self.name.setObjectName("NameBig")
        info.addWidget(self.name)
        self.sign = QLabel("")
        self.sign.setObjectName("Dim")
        info.addWidget(self.sign)
        self.stats = QLabel("")
        self.stats.setObjectName("Dim")
        info.addWidget(self.stats)
        cv.addLayout(info, 1)
        outer.addWidget(card)

        # 顶部导航：动态 / 投稿 / 合集和系列（参照 B 站空间页）
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self.tab_buttons = {}
        for key, text in (("dynamics", "动态"), ("videos", "投稿"), ("archives", "合集和系列")):
            btn = QPushButton(text)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setChecked(key == "dynamics")
            btn.clicked.connect(lambda _=False, k=key: self._switch_view(k))
            tabs.addWidget(btn)
            self.tab_buttons[key] = btn
        tabs.addStretch(1)
        outer.addLayout(tabs)

        # 主体：左侧分类 + 右侧内容
        body = QHBoxLayout()
        body.setSpacing(12)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 8, 0)
        self.category_buttons = {}
        # 动态栏目的分类：全部 / 视频；投稿栏目：视频 / 图文 / 音频
        for key, text in (("all", "全部"), ("video", "视频")):
            btn = QPushButton(text)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda _=False, k=key: self._switch_dyn_filter(k))
            left.addWidget(btn)
            self.category_buttons[f"dyn_{key}"] = btn
        self.dyn_category_buttons = [self.category_buttons[f"dyn_{k}"] for k in ("all", "video")]
        for key, text in (("videos", "视频"), ("articles", "图文"), ("audio", "音频")):
            btn = QPushButton(text)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setChecked(key == "videos")
            btn.clicked.connect(lambda _=False, k=key: self._switch_category(k))
            left.addWidget(btn)
            self.category_buttons[key] = btn
            btn.hide()
        left.addStretch(1)
        body.addLayout(left, 0)

        right = QVBoxLayout()
        right.setSpacing(8)
        head = QHBoxLayout()
        self.section_title = QLabel("TA的视频")
        self.section_title.setObjectName("PageTitle")
        head.addWidget(self.section_title)
        head.addStretch(1)
        self._order_buttons = []
        for text, order in (("最新发布", "pubdate"), ("最多播放", "click"), ("最多收藏", "stow")):
            btn = QPushButton(text)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setChecked(order == self._order)
            btn.clicked.connect(lambda _=False, o=order: self._set_order(o))
            head.addWidget(btn)
            setattr(self, f"_order_btn_{order}", btn)
            self._order_buttons.append(btn)
        right.addLayout(head)

        from PySide6.QtWidgets import QStackedWidget

        self.content_stack = QStackedWidget()
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.dynamics_host = QListWidget()
        self.dynamics_host.setSpacing(6)
        self.content_stack.addWidget(self.grid_host)
        self.content_stack.addWidget(self.dynamics_host)
        right.addWidget(self.content_stack, 1)

        pager = QHBoxLayout()
        self.btn_prev = QPushButton("上一页")
        self.btn_next = QPushButton("下一页")
        self.page_label = QLabel("第 1 页")
        self.btn_prev.clicked.connect(lambda: self._turn_page(-1))
        self.btn_next.clicked.connect(lambda: self._turn_page(1))
        pager.addStretch(1)
        pager.addWidget(self.btn_prev)
        pager.addWidget(self.page_label)
        pager.addWidget(self.btn_next)
        pager.addStretch(1)
        right.addLayout(pager)
        body.addLayout(right, 1)
        outer.addLayout(body, 1)

    def load(self, mid: int):
        self._mid = int(mid)
        self._pn = 1
        self._name = ""
        self._view = "dynamics"
        self._category = "videos"
        self._dyn_filter = "all"
        self._dyn_page = 1
        self._dyn_offsets = [""]
        self._dyn_has_more = True
        for key, btn in self.tab_buttons.items():
            btn.setChecked(key == "dynamics")
        for key, btn in self.category_buttons.items():
            btn.setChecked(key == "videos" or key == "dyn_all")
        self.name.setText("加载中…")
        self.sign.setText("")
        self.stats.setText("")
        self.avatar.setPixmap(placeholder(56))
        self._load_profile()
        self._load_content()

    def _switch_view(self, view: str):
        if view == self._view:
            return
        self._view = view
        for key, btn in self.tab_buttons.items():
            btn.setChecked(key == view)
        self._pn = 1
        self._load_content()

    def _switch_category(self, category: str):
        if category == self._category:
            return
        self._category = category
        for key, btn in self.category_buttons.items():
            if not key.startswith("dyn_"):
                btn.setChecked(key == category)
        self._pn = 1
        self._load_content()

    def _switch_dyn_filter(self, value: str):
        if value == self._dyn_filter:
            return
        self._dyn_filter = value
        for key, btn in self.category_buttons.items():
            if key.startswith("dyn_"):
                btn.setChecked(key == f"dyn_{value}")
        # 切换筛选=换数据流，分页游标全部作废，回到第 1 页
        self._dyn_page = 1
        self._dyn_offsets = [""]
        self._dyn_has_more = True
        self._load_content()

    def _load_content(self):
        """按当前视图与分类加载内容。"""
        is_dyn = self._view == "dynamics"
        show_order = self._view == "videos" and self._category == "videos"
        for btn in self._order_buttons:
            btn.setVisible(show_order)
        # 左侧分类组按视图互斥：动态=全部/视频，投稿=视频/图文/音频，合集=全部隐藏。
        # 原写法 `True if dyn_ else not is_dyn` 让 dyn_ 按钮永远可见，切到投稿后
        # 动态筛选残留（见截图）。
        show_dyn = self._view == "dynamics"
        show_post = self._view == "videos"
        for key, btn in self.category_buttons.items():
            is_dyn_btn = key.startswith("dyn_")
            btn.setVisible(show_dyn if is_dyn_btn else show_post)
        self.content_stack.setCurrentWidget(self.dynamics_host if is_dyn else self.grid_host)

        if is_dyn:
            self._load_dynamics()
        elif self._view == "archives":
            self._load_archives()
        elif self._category == "videos":
            self._load_videos()
        else:
            self._clear_grid()
            self.section_title.setText("图文 / 音频")
            self._add_message(f"{'图文' if self._category == 'articles' else '音频'}列表暂未接入，可点击「在 B 站打开」查看")

    def _load_profile(self):
        loader = lambda: ([UserService().fetch_info(self._mid)],)
        def done(items, total, extra):
            info = items[0] if items else None
            if not info:
                return
            self._name = info.name
            self.name.setText(info.name or "未命名")
            self.sign.setText(info.sign or "")
            self.stats.setText(f"关注 {info.num_following} · 粉丝 {info.num_follower} · Lv{info.level}")
            if info.face:
                self._loader.load(info.face, 56, self.avatar.setPixmap)
        load_social(loader, done, lambda e: self.name.setText(f"资料加载失败：{e}"))

    def _set_order(self, order: str):
        if order == self._order:
            return
        self._order = order
        for o in ("pubdate", "click", "stow"):
            getattr(self, f"_order_btn_{o}").setChecked(o == order)
        self._pn = 1
        self._load_videos()

    def _load_videos(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1000)

        def loader():
            params = {"mid": self._mid, "pn": self._pn, "ps": self.PS,
                      "order": self._order, "platform": "web"}
            get_wbi(params)  # 原地追加签名；返回值是 (wts, w_rid) 元组
            data = self._service.session.get(UserUrls.SPACE_ARC_SEARCH, params=params)
            vlist = (data.get("list") or {}).get("vlist") or []
            return [MediaItem.from_video_dict(x) for x in vlist], int((data.get("page") or {}).get("count") or 0), {}

        self._clear_grid()
        self._add_message("加载中…")
        self._worker = load_social(loader, self._on_videos, self._on_error)

    def _load_dynamics(self):
        """加载当前页的动态（全部 / 仅视频）。每页独立，不累加。"""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1000)
        self.dynamics_host.clear()  # 分页：只显示当前页
        feed_type = "video" if self._dyn_filter == "video" else "all"
        offset = self._dyn_offsets[self._dyn_page - 1]

        def loader():
            items, next_offset, has_more = self._dynamic.fetch_user_dynamic_page(
                self._mid, offset, feed_type=feed_type
            )
            return items, len(items), {"offset": next_offset, "has_more": has_more}

        self.section_title.setText("TA的动态" if feed_type == "all" else "TA的视频动态")
        self.page_label.setText(f"第 {self._dyn_page} 页 · 加载中…")
        self._worker = load_social(loader, self._on_dynamics, self._on_dyn_error)

    def _on_dynamics(self, items, total, extra):
        next_offset = extra.get("offset", "")
        self._dyn_has_more = bool(extra.get("has_more", False))
        # 下一页游标入栈：_dyn_offsets[page] 即第 page+1 页的起始游标
        if len(self._dyn_offsets) <= self._dyn_page:
            self._dyn_offsets.append(next_offset)
        else:
            self._dyn_offsets[self._dyn_page] = next_offset
        if not items:
            if self.dynamics_host.count() == 0:
                self.dynamics_host.addItem("暂无动态")
        for item in items:
            # 接口返回什么就展示什么：即使解析失败也不静默丢弃该条，
            # 用最小信息降级展示，避免充电专属等非常规动态"查不出来"。
            try:
                info = self._dynamic.parse_item(item)
            except Exception as e:
                logger.warning("[UserSpacePage] 动态解析失败，降级展示：%s", e)
                try:
                    from src.models.dynamic_model import DynamicInfo
                    info = DynamicInfo()
                    info.raw = item
                    info.id = int(str(item.get("id_str") or "0").strip() or 0)
                    info.type = str(item.get("type") or "")
                    info.author.pub_time = str(
                        ((item.get("modules") or {}).get("module_author") or {}).get("pub_time") or ""
                    )
                except Exception as e2:
                    logger.warning("[UserSpacePage] 动态降级展示仍失败：%s", e2)
                    continue
            try:
                widget = _DynamicCard(info, self._loader)
                list_item = QListWidgetItem(self.dynamics_host)
                list_item.setSizeHint(widget.sizeHint())
                self.dynamics_host.setItemWidget(list_item, widget)
            except Exception as e:
                logger.warning("[UserSpacePage] 动态卡片渲染失败：%s", e)
        self.page_label.setText(f"第 {self._dyn_page} 页 · {self.dynamics_host.count()} 条"
                                + (" · 有更多" if self._dyn_has_more else ""))
        self.btn_prev.setEnabled(self._dyn_page > 1)
        self.btn_next.setEnabled(self._dyn_has_more)

    def _on_dyn_error(self, message: str):
        if self.dynamics_host.count() == 0:
            self.dynamics_host.addItem(f"加载失败：{message}")
        self.page_label.setText("加载失败")

    def _load_archives(self):
        """加载用户的合集/系列列表。"""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1000)

        def loader():
            seasons = self._archive._list_seasons(self._mid, self._pn, self.PS)
            cards = []
            for season in seasons:
                meta = season.get("meta") or {}
                archives = season.get("archives") or []
                cover = meta.get("cover", "")
                title = meta.get("name") or meta.get("title") or "未命名合集"
                total = int(meta.get("total") or len(archives))
                cards.append((title, cover, total, len(archives), meta.get("season_id", 0)))
            return cards, len(cards), {}

        self._clear_grid()
        self._add_message("加载中…")
        self._worker = load_social(loader, self._on_archives, self._on_error)

    def _on_archives(self, items, total, extra):
        self._clear_grid()
        cols = 4
        for idx, (title, cover, total_videos, loaded, season_id) in enumerate(items):
            card = _ArchiveCard(title, cover, total_videos, loaded, self._loader,
                                lambda sid=season_id: self._open_archive(sid))
            self.grid.addWidget(card, idx // cols, idx % cols)
        if not items:
            self._add_message("该用户暂无合集/系列")
        self.section_title.setText(f"合集和系列 · 共 {total} 个")
        self.page_label.setText(f"第 {self._pn} 页")
        self.btn_prev.setEnabled(self._pn > 1)
        self.btn_next.setEnabled(self._pn * self.PS < total)

    def _open_archive(self, season_id: int):
        """点击合集：跳到下载页并按合集 sid 预填。"""
        if season_id:
            app_signals.prefill_requested.emit(str(season_id), "season")
            app_signals.goto_page.emit("download")

    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_message(self, text: str):
        label = QLabel(text)
        label.setObjectName("Dim")
        self.grid.addWidget(label, 0, 0, 1, 4)

    def _on_videos(self, items, total, extra):
        self._clear_grid()
        self._total = total
        cols = 4
        for idx, media in enumerate(items):
            card = _VideoCard(media, self._loader, self._open_video)
            self.grid.addWidget(card, idx // cols, idx % cols)
        if not items:
            self._add_message("暂无投稿视频")
        self.section_title.setText(f"TA的视频 · 共 {total} 个")
        self.page_label.setText(f"第 {self._pn} 页")
        self.btn_prev.setEnabled(self._pn > 1)
        self.btn_next.setEnabled(self._pn * self.PS < total)

    def _turn_page(self, delta):
        if self._view == "dynamics":
            # 动态页用游标栈做真分页：上一页回退、下一页前进，每页只显示该页。
            if delta > 0 and self._dyn_has_more:
                self._dyn_page += 1
                self._load_dynamics()
            elif delta < 0 and self._dyn_page > 1:
                self._dyn_page -= 1
                self._load_dynamics()
            return
        self._pn = max(1, self._pn + delta)
        self._load_content()

    def _open_video(self, media: MediaItem):
        if media.bvid:
            app_signals.video_detail_requested.emit(media.bvid)

    def _on_error(self, message: str):
        self._clear_grid()
        self._add_message(f"加载失败：{message}")

    def _open_in_browser(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(f"https://space.bilibili.com/{self._mid}/upload/video"))

