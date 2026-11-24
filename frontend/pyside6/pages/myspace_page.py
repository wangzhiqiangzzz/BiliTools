"""个人中心页：复刻 downkyicore 的「我的空间」，应用内自绘。

展示当前登录用户的头像/昵称/等级/大会员/签名、硬币与钱包、
邮箱手机绑定状态、等级进度、关注/粉丝/黑名单/信誉/禁言、
以及收藏/追番/稍后再看/历史/B 站动态入口和退出登录。

数据在后台线程加载，避免网络请求卡住 UI。
"""
import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)
from PySide6.QtWidgets import QMessageBox

from src.models import LoginUser, MySpaceProfile, MySpaceStats
from src.services.account import AccountManager
from src.services.myspace import MySpaceService

from frontend.pyside6.avatar import AvatarLoader, placeholder
from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.workers.login_worker import recheck_login

logger = logging.getLogger(__name__)

_AVATAR_SIZE = 72
_DYNAMICS_URL = "https://t.bilibili.com/"


class MySpaceLoadWorker(QThread):
    """后台加载个人资料与统计。"""

    result = Signal(object, object)  # (MySpaceProfile | None, MySpaceStats | None)
    error = Signal(str)

    def __init__(self, mid: int, parent=None):
        super().__init__(parent)
        self.mid = mid

    def run(self):
        try:
            service = MySpaceService()
            profile = service.get_profile(self.mid)
            stats = service.get_stats(self.mid)
            self.result.emit(profile, stats)
        except Exception as e:
            logger.warning("[MySpacePage] 个人中心加载失败：%s", e)
            self.error.emit(str(e))


class MySpacePage(QWidget):
    """应用内个人中心页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MySpacePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._worker = None
        self._avatar_loader = AvatarLoader(self)
        self._user = None
        self._build()
        app_signals.login_changed.connect(self._on_login_changed)

    # ---- UI 构建 ----

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(12)

        # 顶栏：返回 + 标题 + 退出登录
        top = QHBoxLayout()
        self.btn_back = QPushButton("‹ 返回")
        self.btn_back.setObjectName("NavItem")
        self.btn_back.clicked.connect(lambda: app_signals.goto_page.emit("home"))
        top.addWidget(self.btn_back)
        top.addStretch(1)
        title = QLabel("我的空间")
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.btn_logout = QPushButton("退出登录")
        self.btn_logout.clicked.connect(self._on_logout)
        top.addWidget(self.btn_logout)
        outer.addLayout(top)

        self.hint = QLabel("")
        self.hint.setObjectName("Dim")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.hint)

        # 主体左右两栏
        body = QHBoxLayout()
        body.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(12)
        right = QVBoxLayout()
        right.setSpacing(12)
        body.addLayout(left, 3)
        body.addLayout(right, 2)
        outer.addLayout(body, 1)

        # 左栏：身份卡
        card = QWidget()
        card.setObjectName("Card")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(20, 16, 20, 16)
        cv.setSpacing(8)

        self.avatar = QLabel()
        self.avatar.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setPixmap(placeholder(_AVATAR_SIZE))
        cv.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignCenter)

        self.name = QLabel("未登录")
        self.name.setObjectName("NameBig")
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(self.name)

        self.vip = QLabel("")
        self.vip.setObjectName("Dim")
        self.vip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(self.vip)

        self.sign = QLabel("")
        self.sign.setObjectName("Dim")
        self.sign.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sign.setWordWrap(True)
        cv.addWidget(self.sign)

        self.binding = QLabel("")
        self.binding.setObjectName("Dim")
        self.binding.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(self.binding)

        # 等级进度
        self.level_text = QLabel("等级 --")
        self.level_text.setObjectName("Dim")
        cv.addWidget(self.level_text)
        self.exp_bar = QProgressBar()
        self.exp_bar.setTextVisible(True)
        self.exp_bar.setFormat("%v / %m")
        cv.addWidget(self.exp_bar)

        # 硬币 / B 币
        self.balance = QLabel("硬币 0.0    B 币钱包 0.0")
        self.balance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(self.balance)
        left.addWidget(card)

        # 左栏下方：状态数据
        status = QWidget()
        status.setObjectName("Card")
        status.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sv = QVBoxLayout(status)
        sv.setContentsMargins(16, 12, 16, 12)
        sv.setSpacing(6)
        sv.addWidget(self._section_title("社交状态"))
        self.status_labels = {}
        for key, text in (
            ("following", "关注"), ("follower", "粉丝"), ("black", "黑名单"),
            ("moral", "信誉"), ("silence", "禁言状态"),
        ):
            row = QHBoxLayout()
            label = QLabel(text)
            label.setObjectName("Dim")
            value = QLabel("--")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(value)
            sv.addLayout(row)
            self.status_labels[key] = value
        left.addWidget(status)

        # 右栏：功能入口
        entries = QWidget()
        entries.setObjectName("Card")
        entries.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        ev = QVBoxLayout(entries)
        ev.setContentsMargins(16, 12, 16, 12)
        ev.setSpacing(8)
        ev.addWidget(self._section_title("我的内容"))
        for text, slot in (
            ("我的收藏", self._open_favorites),
            ("我的追番", self._open_bangumi),
            ("稍后再看", self._open_to_view),
            ("历史记录", self._open_history),
            ("B 站动态", self._open_dynamics),
        ):
            btn = QPushButton(text)
            btn.setObjectName("NavItem")
            btn.clicked.connect(slot)
            ev.addWidget(btn)
        ev.addStretch(1)
        right.addWidget(entries, 1)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    # ---- 登录态与数据加载 ----

    def load(self, user: LoginUser) -> None:
        """由 MainWindow 在跳转前调用，传入当前登录用户。"""
        self._user = user
        if user is None or not user.is_login or not user.mid:
            self.hint.setText("未登录，请先扫码登录")
            self.name.setText("未登录")
            return
        self.hint.setText("正在加载个人资料…")
        self.avatar.setPixmap(placeholder(_AVATAR_SIZE))
        self._avatar_loader.load(user.face, _AVATAR_SIZE, self.avatar.setPixmap)

        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)
        self._worker = MySpaceLoadWorker(user.mid, self)
        self._worker.result.connect(self._apply_data)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_login_changed(self, user) -> None:
        self._user = user
        if user is None or not getattr(user, "is_login", False):
            self.hint.setText("未登录，请先扫码登录")

    def _apply_data(self, profile: MySpaceProfile, stats: MySpaceStats) -> None:
        self.hint.setText("")
        if profile is None:
            self.hint.setText("个人资料加载失败，请稍后重试")
            return
        self.name.setText(profile.name or "未命名")
        self.vip.setText(profile.vip_type or "")
        self.sign.setText(profile.sign or "这个人很懒，什么都没写")
        bound = []
        if profile.email_bound:
            bound.append("邮箱已绑定")
        if profile.phone_bound:
            bound.append("手机已绑定")
        self.binding.setText(" · ".join(bound))

        self.level_text.setText(f"等级 Lv{profile.level}")
        if profile.level_next_exp > 0:
            self.exp_bar.setRange(0, profile.level_next_exp)
            self.exp_bar.setValue(min(profile.level_current_exp, profile.level_next_exp))
        else:
            self.exp_bar.setRange(0, 1)
            self.exp_bar.setValue(1)
            self.exp_bar.setFormat("已满级")

        if profile.face:
            self._avatar_loader.load(profile.face, _AVATAR_SIZE, self.avatar.setPixmap)

        if stats is not None:
            self.balance.setText(
                f"硬币 {stats.money:.1f}    B 币钱包 {stats.bcoin_balance:.1f}"
                if stats.show_balances else "登录后查看硬币与钱包"
            )
            self.status_labels["following"].setText(str(stats.following))
            self.status_labels["follower"].setText(str(stats.follower))
            self.status_labels["black"].setText(str(stats.black))
        self.status_labels["moral"].setText(str(profile.moral))
        self.status_labels["silence"].setText("禁言中" if profile.silence == 1 else "正常")

    def _on_error(self, message: str) -> None:
        self.hint.setText(f"加载失败：{message}")

    # ---- 入口 ----

    def _goto_download_source(self, source: str) -> None:
        """入口卡片统一跳到下载页并切换来源页签。"""
        app_signals.goto_page.emit("download")
        app_signals.prefill_requested.emit("", source)

    def _open_favorites(self):
        self._goto_download_source("fav")

    def _open_bangumi(self):
        app_signals.log_message.emit(LogCategory.NORMAL, "追番列表暂未接入 GUI，可用 SDK 查看")

    def _open_to_view(self):
        app_signals.log_message.emit(LogCategory.NORMAL, "稍后再看暂未接入 GUI")

    def _open_history(self):
        app_signals.log_message.emit(LogCategory.NORMAL, "历史记录暂未接入 GUI，可用 examples/history.py")

    def _open_dynamics(self):
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(_DYNAMICS_URL)

    def _on_logout(self):
        ans = QMessageBox.question(self, "退出登录", "确定要退出当前账号吗？")
        if ans != QMessageBox.StandardButton.Yes:
            return
        AccountManager().remove_current()
        app_signals.log_message.emit(LogCategory.NORMAL, "已退出登录")
        app_signals.login_changed.emit(None)
        recheck_login()
        app_signals.goto_page.emit("home")
