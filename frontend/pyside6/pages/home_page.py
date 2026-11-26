"""首页：品牌标识 + 统一搜索框 + 四个功能入口。

搜索框只做输入识别与页面跳转，不发网络请求、不触发下载；
识别出的来源和原文通过 prefill_requested 交给下载页预填。
"""
from functools import lru_cache

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from src.config.path import ASSETS_DIR

from frontend.pyside6.avatar import AvatarLoader, placeholder
from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.theme import get_palette

_SVG_DIR = ASSETS_DIR / "imgs" / "svg"
_FALLBACK = {"search": "⌕", "settings": "⚙", "download": "⇩", "toolbox": "▣", "schedule": "◷"}


@lru_cache(maxsize=None)
def _svg_icon(name: str, color: str) -> QIcon:
    """把 SVG 的 currentColor 替换为指定颜色后渲染为 QIcon。"""
    path = _SVG_DIR / f"{name}.svg"
    if not path.exists():
        return QIcon()
    data = path.read_text(encoding="utf-8").replace("currentColor", color)
    pm = QPixmap()
    return QIcon(pm) if pm.loadFromData(data.encode("utf-8")) else QIcon()


def detect_source(text: str) -> str:
    """按输入文本判断落到下载页的哪个来源页签；纯字符串判断，不发网络请求。"""
    s = text.strip().lower()
    if "favlist" in s or "medialist" in s or "fid=" in s:
        return "fav"
    if "/lists/" in s or "sid=" in s:
        return "season"
    if "space.bilibili.com" in s:
        return "up"
    return "bv"


class HomePage(QWidget):
    """首页：搜索框跳转下载页，四个圆形入口分别通向设置/下载/工具箱/定时任务。"""

    prefill_requested = Signal(str, str)  # (原文, source)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._entry_buttons = {}
        self._user = None
        self._avatar_loader = AvatarLoader(self)
        self._build()
        app_signals.theme_changed.connect(self._on_theme_changed)
        app_signals.login_changed.connect(self._on_login_changed)
        self._apply_theme_icons()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(20, 10, 20, 0)
        top.addStretch(1)
        # 头像按钮：未登录显示占位头像 + "登录"，已登录显示真实头像 + 昵称。
        # 点击分流到登录页/个人中心页，与 downkyicore 的 IndexAccountButton 一致。
        self.btn_login = QPushButton()
        self.btn_login.setObjectName("HomeLogin")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setToolTip("登录 / 我的空间")
        self.btn_login.setIconSize(QSize(32, 32))
        self.btn_login.setIcon(QIcon(placeholder(32)))
        self.btn_login.setText("登录")
        self.btn_login.clicked.connect(self._on_account_clicked)
        top.addWidget(self.btn_login)
        outer.addLayout(top)

        outer.addStretch(2)

        center = QVBoxLayout()
        center.setSpacing(32)

        brand = QLabel("b站工具助手")
        brand.setObjectName("HomeBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(brand)

        # 搜索框整体是一个圆角容器：无边框输入框 + 内嵌在右端的搜索按钮。
        search_box = QWidget()
        search_box.setObjectName("HomeSearchBox")
        search_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        search_box.setFixedHeight(52)
        search_box.setFixedWidth(760)
        search_row = QHBoxLayout(search_box)
        search_row.setContentsMargins(20, 0, 8, 0)
        search_row.setSpacing(0)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("HomeSearch")
        self.search_edit.setPlaceholderText("请输入B站网址链接或av、BV号等……")
        self.search_edit.setFrame(False)
        self.search_edit.returnPressed.connect(self._on_search)
        self.btn_search = QPushButton()
        self.btn_search.setObjectName("HomeSearchBtn")
        self.btn_search.setFixedSize(38, 38)
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.setToolTip("跳转到下载页")
        self.btn_search.clicked.connect(self._on_search)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.btn_search)
        center.addWidget(search_box, 0, Qt.AlignmentFlag.AlignCenter)

        entries = QHBoxLayout()
        entries.setSpacing(80)
        entries.addStretch(1)
        for key, label, icon_name, slot in (
            ("settings", "设置", "settings", lambda: app_signals.goto_page.emit("settings")),
            ("download", "下载管理", "download", lambda: app_signals.goto_page.emit("download")),
            ("toolbox", "工具箱", "toolbox", self._on_toolbox),
            ("schedule", "定时任务", "schedule", self._on_schedule),
        ):
            item = QVBoxLayout()
            item.setSpacing(8)
            item.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn = QPushButton()
            btn.setObjectName("HomeEntryIcon")
            btn.setFixedSize(68, 68)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(label)
            btn.clicked.connect(slot)
            text = QLabel(label)
            text.setObjectName("HomeEntryText")
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item.addWidget(btn)
            item.addWidget(text)
            entries.addLayout(item)
            self._entry_buttons[(key, icon_name)] = btn
        entries.addStretch(1)
        center.addLayout(entries)

        outer.addLayout(center)
        outer.addStretch(3)

    def _on_search(self):
        text = self.search_edit.text().strip()
        if not text:
            app_signals.log_message.emit(LogCategory.WARN, "请输入 B 站链接、BV 号或 av 号")
            return
        app_signals.goto_page.emit("download")
        self.prefill_requested.emit(text, detect_source(text))

    def _on_toolbox(self):
        QMessageBox.information(self, "工具箱", "工具箱功能开发中，敬请期待。")

    def _on_schedule(self):
        QMessageBox.information(self, "定时任务", "定时任务功能开发中，敬请期待。")

    def _on_account_clicked(self):
        """头像点击：未登录去登录页，已登录去个人中心页。"""
        if self._user is not None and getattr(self._user, "is_login", False):
            app_signals.goto_page.emit("myspace")
        else:
            app_signals.goto_page.emit("login")

    def _on_login_changed(self, user):
        self._user = user
        if user is not None and getattr(user, "is_login", False):
            self.btn_login.setText(user.uname or "已登录")
            self.btn_login.setToolTip("我的空间")
            if getattr(user, "face", ""):
                self._avatar_loader.load(user.face, 32, lambda pm: self.btn_login.setIcon(QIcon(pm)))
            else:
                self.btn_login.setIcon(QIcon(placeholder(32)))
        else:
            self.btn_login.setText("登录")
            self.btn_login.setToolTip("登录 B 站账号")
            self.btn_login.setIcon(QIcon(placeholder(32)))

    def _apply_theme_icons(self):
        color = get_palette()["nav_active"]
        icon = _svg_icon("search", color)
        self.btn_search.setIcon(icon)
        self.btn_search.setIconSize(QSize(22, 22))
        self.btn_search.setText("" if not icon.isNull() else _FALLBACK["search"])
        for (key, name), btn in self._entry_buttons.items():
            icon = _svg_icon(name, color)
            btn.setIcon(icon)
            btn.setIconSize(QSize(34, 34))
            btn.setText("" if not icon.isNull() else _FALLBACK[key])

    def _on_theme_changed(self, _name):
        self._apply_theme_icons()
