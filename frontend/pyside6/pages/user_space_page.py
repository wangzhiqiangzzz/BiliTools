"""博主个人空间页：参照 B 站 space.bilibili.com/<mid>/upload/video 投稿页布局。

结构：
- 顶部：博主资料条（头像/昵称/签名/关注粉丝 Lv）+ 关注按钮
- 左侧：分类导航（视频 N / 图文 N / 音频 N）
- 右侧：「TA的视频」标题 + 排序切换（最新发布/最多播放/最多收藏）+ 视频网格卡片
  每张卡片显示封面、播放量、弹幕数、时长、标题、发布日期；点击进视频详情。

支持分页、关注/取消关注、返回上一页。
"""
import logging
import time

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget, QGridLayout, QMessageBox,
)

from src.models import MediaItem, UserInfo
from src.services.social import SocialService
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


class UserSpacePage(QWidget):
    """博主空间页（投稿视频）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MySpacePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._service = SocialService()
        self._loader = AvatarLoader(self)
        self._mid = 0
        self._pn = 1
        self._total = 0
        self._worker = None
        self._following = False
        self._order = "pubdate"  # pubdate / click / stow
        self._build()

    PS = 12  # 每行 4 个 × 3 行

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(10)

        # 顶部：返回 + 关注 + 打开 B 站空间
        top = QHBoxLayout()
        btn_back = QPushButton("‹ 返回")
        btn_back.setObjectName("NavItem")
        btn_back.clicked.connect(lambda: app_signals.goto_page.emit("myspace"))
        top.addWidget(btn_back)
        top.addStretch(1)
        self.btn_follow = QPushButton("+ 关注")
        self.btn_follow.clicked.connect(self._toggle_follow)
        top.addWidget(self.btn_follow)
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

        # 主体：左侧分类 + 右侧视频网格
        body = QHBoxLayout()
        body.setSpacing(12)

        left = QVBoxLayout()
        self.category = QListWidget()
        self.category.setFixedWidth(120)
        for text in ("视频", "图文", "音频"):
            item = QListWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.category.addItem(item)
        self.category.setCurrentRow(0)
        left.addWidget(self.category)
        left.addStretch(1)
        body.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(8)
        head = QHBoxLayout()
        self.section_title = QLabel("TA的视频")
        self.section_title.setObjectName("PageTitle")
        head.addWidget(self.section_title)
        head.addStretch(1)
        for text, order in (("最新发布", "pubdate"), ("最多播放", "click"), ("最多收藏", "stow")):
            btn = QPushButton(text)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setChecked(order == self._order)
            btn.clicked.connect(lambda _=False, o=order: self._set_order(o))
            head.addWidget(btn)
            setattr(self, f"_order_btn_{order}", btn)
        right.addLayout(head)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        right.addWidget(self.grid_host, 1)

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
        self.name.setText("加载中…")
        self.sign.setText("")
        self.stats.setText("")
        self.avatar.setPixmap(placeholder(56))
        self._load_profile()
        self._load_videos()

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
        self._pn = max(1, self._pn + delta)
        self._load_videos()

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

    def _toggle_follow(self):
        if self._following:
            ans = QMessageBox.question(self, "取消关注", f"确定取消关注 {self._name or '该博主'} 吗？")
            if ans != QMessageBox.StandardButton.Yes:
                return
        self._service.modify_relation(self._mid, 2 if self._following else 1)
        self._following = not self._following
        self.btn_follow.setText("+ 关注" if not self._following else "已关注")
