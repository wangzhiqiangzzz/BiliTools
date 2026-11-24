"""好友页：关注 / 粉丝列表，左侧关注分组页签，支持分页与点击博主进入空间。

复刻 downkyicore 的 FriendsViewModel + FollowingViewModel/FollowerViewModel。
"""
import logging
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from src.models import FollowGroup, RelationUser
from src.services.social import SocialService

from frontend.pyside6.avatar import AvatarLoader, placeholder
from frontend.pyside6.signals import app_signals
from frontend.pyside6.workers.social_worker import load_social

logger = logging.getLogger(__name__)


class _UserItem(QWidget):
    """关注/粉丝列表项：头像 + 昵称 + 签名。点击整项进入该博主空间。"""

    def __init__(self, user: RelationUser, avatar_loader: AvatarLoader, on_click, parent=None):
        super().__init__(parent)
        self.user = user
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(10)

        self.avatar = QLabel()
        self.avatar.setFixedSize(40, 40)
        self.avatar.setPixmap(placeholder(40))
        if user.face:
            avatar_loader.load(user.face, 40, self.avatar.setPixmap)
        lay.addWidget(self.avatar)

        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(user.name or "未命名")
        name.setObjectName("NameBig")
        sign = QLabel(user.sign or "")
        sign.setObjectName("Dim")
        info.addWidget(name)
        info.addWidget(sign)
        lay.addLayout(info, 1)

        self.mousePressEvent = lambda event: on_click(user.mid) if event.button() == Qt.MouseButton.LeftButton else None


class FriendsPage(QWidget):
    """关注 / 粉丝页。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MySpacePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._service = SocialService()
        self._avatar_loader = AvatarLoader(self)
        self._mid = 0
        self._tab = "following"  # following / follower
        self._group_id = -1  # -1 表示全部关注
        self._groups = []
        self._pn = 1
        self._total = 0
        self._worker = None
        self._build()

    PS = 20

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 12, 20, 12)
        outer.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(self._nav_btn("‹ 返回"))
        top.addStretch(1)
        title = QLabel("关注与粉丝")
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch(1)
        outer.addLayout(top)

        self.tabs = QListWidget()
        self.tabs.setFixedHeight(40)
        self.tabs.setFlow(QListWidget.Flow.LeftToRight)
        self.tabs.setWrapping(False)
        self.tabs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabs.currentRowChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs)

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

    def _nav_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("NavItem")
        btn.clicked.connect(lambda: app_signals.goto_page.emit("myspace"))
        return btn

    def load(self, mid: int, tab: str = "following"):
        """由个人中心/博主空间调用。"""
        self._mid = int(mid)
        self._tab = tab
        self._group_id = -1
        self._pn = 1
        self._load_groups()

    def _load_groups(self):
        def done(items, total, extra):
            self._groups = items
            self.tabs.clear()
            self.tabs.addItem("全部关注")
            for g in items:
                self.tabs.addItem(f"{g.name} ({g.count})")
            self.tabs.addItem("粉丝")
            self.tabs.setCurrentRow(0 if self._tab == "following" else len(items) + 1)
            self._load_list()

        load_social(partial(self._service.get_follow_groups), done, self._on_error)

    def _on_tab_changed(self, row: int):
        if row < 0 or not self._groups:
            return
        if row == 0:
            self._tab, self._group_id = "following", -1
        elif row <= len(self._groups):
            self._tab, self._group_id = "group", self._groups[row - 1].tag_id
        else:
            self._tab, self._group_id = "follower", -1
        self._pn = 1
        self._load_list()

    def _load_list(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1000)
        if self._tab == "following":
            loader = partial(self._service.get_following, self._mid, self._pn, self.PS)
        elif self._tab == "follower":
            loader = partial(self._service.get_followers, self._mid, self._pn, self.PS)
        else:
            loader = partial(self._service.get_group_members, self._group_id, self._pn, self.PS)
        self.list.clear()
        self.list.addItem(QListWidgetItem("加载中…"))
        self._worker = load_social(loader, self._on_list, self._on_error)

    def _on_list(self, items, total, extra):
        self.list.clear()
        self._total = total
        for user in items:
            item = QListWidgetItem(self.list)
            widget = _UserItem(user, self._avatar_loader, self._open_user)
            item.setSizeHint(widget.sizeHint())
            self.list.setItemWidget(item, widget)
        if not items:
            self.list.addItem(QListWidgetItem("暂无数据"))
        self.page_label.setText(f"第 {self._pn} 页 · 共 {total} 人")
        self.btn_prev.setEnabled(self._pn > 1)
        self.btn_next.setEnabled(self._pn * self.PS < total)

    def _turn_page(self, delta: int):
        self._pn = max(1, self._pn + delta)
        self._load_list()

    def _on_item_clicked(self, item):
        widget = self.list.itemWidget(item)
        if isinstance(widget, _UserItem):
            self._open_user(widget.user.mid)

    def _open_user(self, mid: int):
        app_signals.user_space_requested.emit(int(mid))

    def _on_error(self, message: str):
        self.list.clear()
        self.list.addItem(QListWidgetItem(f"加载失败：{message}"))
