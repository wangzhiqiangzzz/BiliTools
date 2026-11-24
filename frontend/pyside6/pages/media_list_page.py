"""通用媒体列表页：收藏夹 / 追番 / 稍后再看 / 历史记录。

复刻 downkyicore 的 MyFavorites / MyBangumiFollow / MyToViewVideo / MyHistory
共有的列表 + 分页 + 点击视频 + 批量选中/下载 结构。
"""
import logging
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from src.models import MediaItem
from src.services.social import SocialService

from frontend.pyside6.signals import app_signals
from frontend.pyside6.workers.social_worker import load_social

logger = logging.getLogger(__name__)


class MediaListPage(QWidget):
    """通用媒体列表页。kind 决定数据源与每页数量。"""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("MySpacePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._service = SocialService()
        self._mid = 0
        self._pn = 1
        self._total = 0
        self._worker = None
        self._media_id = 0  # 收藏夹专用
        self._items = []
        self._build()

    @property
    def PS(self) -> int:
        return 30 if self.kind == "history" else (15 if self.kind == "bangumi" else 20)

    @property
    def TITLE(self) -> str:
        return {
            "favorites": "我的收藏", "bangumi": "我的追番",
            "watch_later": "稍后再看", "history": "历史记录",
        }.get(self.kind, "列表")

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 12, 20, 12)
        outer.setSpacing(10)

        top = QHBoxLayout()
        btn_back = QPushButton("‹ 返回")
        btn_back.setObjectName("NavItem")
        btn_back.clicked.connect(lambda: app_signals.goto_page.emit("myspace"))
        top.addWidget(btn_back)
        top.addStretch(1)
        title = QLabel(self.TITLE)
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.btn_download = QPushButton("下载选中")
        self.btn_download.clicked.connect(self._download_selected)
        top.addWidget(self.btn_download)
        outer.addLayout(top)

        # 收藏夹专用：收藏夹选择列表
        self.folder_bar = QListWidget()
        self.folder_bar.setFixedHeight(36)
        self.folder_bar.setFlow(QListWidget.Flow.LeftToRight)
        self.folder_bar.setWrapping(False)
        self.folder_bar.itemClicked.connect(self._on_folder_clicked)
        self.folder_bar.setVisible(self.kind == "favorites")
        outer.addWidget(self.folder_bar)

        self.list = QListWidget()
        self.list.itemClicked.connect(self._on_item_clicked)
        outer.addWidget(self.list, 1)

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
        outer.addLayout(pager)

    def load(self, mid: int, media_id: int = 0):
        self._mid = int(mid)
        self._media_id = int(media_id)
        self._pn = 1
        if self.kind == "favorites":
            self._load_folders()
        else:
            self._load_list()

    def _load_folders(self):
        def done(items, total, extra):
            self.folder_bar.clear()
            for folder in items:
                item = QListWidgetItem(f"{folder.title} ({folder.media_count})")
                item.setData(Qt.ItemDataRole.UserRole, folder.media_id)
                self.folder_bar.addItem(item)
            if items:
                self.folder_bar.setCurrentRow(0)
                self._media_id = items[0].media_id
                self._load_list()
        load_social(partial(self._service.get_fav_folders, self._mid), done, self._on_error)

    def _on_folder_clicked(self, item):
        self._media_id = item.data(Qt.ItemDataRole.UserRole)
        self._pn = 1
        self._load_list()

    def _loader(self):
        s = self._service
        if self.kind == "favorites":
            return partial(s.get_fav_medias, self._media_id, self._pn, self.PS)
        if self.kind == "bangumi":
            return partial(s.get_bangumi_follow, self._mid, self._pn, self.PS)
        if self.kind == "watch_later":
            return partial(s.get_watch_later, self._pn, self.PS)
        if self.kind == "history":
            return partial(s.get_history, 0, 0, "", self.PS)
        raise ValueError(f"未知列表类型：{self.kind}")

    def _load_list(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1000)
        self.list.clear()
        self.list.addItem(QListWidgetItem("加载中…"))
        self._worker = load_social(self._loader(), self._on_list, self._on_error)

    def _on_list(self, items, total, extra):
        self.list.clear()
        self._items = items
        self._total = total
        for media in items:
            item = QListWidgetItem(self.list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            duration = f" {media.duration // 60}:{media.duration % 60:02d}" if media.duration else ""
            text = f"{media.title}{duration}"
            if media.author:
                text += f"  — {media.author}"
            if media.extra:
                text += f"  [{media.extra}]"
            item.setText(text)
            item.setData(Qt.ItemDataRole.UserRole, media)
        if not items:
            self.list.addItem(QListWidgetItem("暂无数据"))
        self.page_label.setText(f"第 {self._pn} 页 · 共 {total} 条")
        self.btn_prev.setEnabled(self._pn > 1)
        self.btn_next.setEnabled(self._pn * self.PS < total)

    def _turn_page(self, delta):
        self._pn = max(1, self._pn + delta)
        self._load_list()

    def _on_item_clicked(self, item):
        media = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(media, MediaItem) and media.bvid:
            app_signals.video_detail_requested.emit(media.bvid)

    def _download_selected(self):
        """把勾选的视频提交为下载任务（有 BV 号的）。"""
        count = 0
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                media = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(media, MediaItem) and media.bvid:
                    app_signals.prefill_requested.emit(media.bvid, "bv")
                    count += 1
        if count:
            app_signals.goto_page.emit("download")
            app_signals.log_message.emit(0, f"已加入 {count} 个视频到下载页")

    def _on_error(self, message: str):
        self.list.clear()
        self.list.addItem(QListWidgetItem(f"加载失败：{message}"))
