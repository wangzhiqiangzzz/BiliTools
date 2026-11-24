"""主窗口：标题栏 + 导航栏 + 内容区（QStackedWidget）。无边框。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from frontend.pyside6.pages.download_page import DownloadPage
from frontend.pyside6.pages.friends_page import FriendsPage
from frontend.pyside6.pages.home_page import HomePage
from frontend.pyside6.pages.login_page import LoginPage
from frontend.pyside6.pages.media_list_page import MediaListPage
from frontend.pyside6.pages.myspace_page import MySpacePage
from frontend.pyside6.pages.settings_page import SettingsPage
from frontend.pyside6.pages.user_space_page import UserSpacePage
from frontend.pyside6.signals import app_signals
from frontend.pyside6.title_bar import TitleBar
from frontend.pyside6.workers.download_manager import DownloadManager


class MainWindow(QWidget):
    PAGE_INDEX = {
        "home": 0, "download": 1, "login": 2, "settings": 3, "myspace": 4,
        "friends": 5, "user_space": 6, "favorites": 7, "bangumi": 8,
        "watch_later": 9, "history": 10,
    }

    def __init__(self, settings, theme_mgr, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.theme_mgr = theme_mgr
        self.manager = DownloadManager(self)
        self._build()

    def _build(self):
        self.setWindowTitle("b站工具助手")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1100, 700)
        self.setMinimumSize(980, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.title_bar = TitleBar(self)

        self.stack = QStackedWidget()
        self.home_page = HomePage()
        self.download_page = DownloadPage(self.settings, self.manager)
        self.login_page = LoginPage()
        self.settings_page = SettingsPage(self.settings, self.theme_mgr)
        self.myspace_page = MySpacePage()
        self.friends_page = FriendsPage()
        self.user_space_page = UserSpacePage()
        self.favorites_page = MediaListPage("favorites")
        self.bangumi_page = MediaListPage("bangumi")
        self.watch_later_page = MediaListPage("watch_later")
        self.history_page = MediaListPage("history")
        self.stack.addWidget(self.home_page)          # 0
        self.stack.addWidget(self.download_page)      # 1
        self.stack.addWidget(self.login_page)         # 2
        self.stack.addWidget(self.settings_page)      # 3
        self.stack.addWidget(self.myspace_page)       # 4
        self.stack.addWidget(self.friends_page)       # 5
        self.stack.addWidget(self.user_space_page)    # 6
        self.stack.addWidget(self.favorites_page)     # 7
        self.stack.addWidget(self.bangumi_page)       # 8
        self.stack.addWidget(self.watch_later_page)   # 9
        self.stack.addWidget(self.history_page)       # 10

        outer.addWidget(self.title_bar)
        outer.addWidget(self.stack, 1)

        # 首页搜索框只负责识别来源，实际预填交给下载页，不在这里发网络请求。
        self.home_page.prefill_requested.connect(self.download_page.panel.prefill)
        app_signals.prefill_requested.connect(self.download_page.panel.prefill)
        # 记住当前登录用户：点头像跳个人页时把手数据带过去
        self._current_user = None
        app_signals.login_changed.connect(self._on_login_changed)
        # 点击博主 / 视频的跨页跳转
        app_signals.user_space_requested.connect(self._open_user_space)
        app_signals.video_detail_requested.connect(self._open_video_detail)

        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximize)
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.theme_toggled.connect(self._toggle_theme)
        self.title_bar.home_requested.connect(lambda: self._goto_page("home"))
        self.manager.count_changed.connect(self.title_bar.set_task_count)

        app_signals.goto_page.connect(self._goto_page)

    # ---- 窗口动作 ----

    def _toggle_theme(self):
        nxt = "dark" if self.theme_mgr.current() == "light" else "light"
        self.theme_mgr.set_theme(nxt)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_login_changed(self, user):
        self._current_user = user

    @property
    def _current_mid(self) -> int:
        user = self._current_user
        return int(getattr(user, "mid", 0) or 0) if user and getattr(user, "is_login", False) else 0

    def _open_user_space(self, mid: int):
        self.user_space_page.load(mid)
        self.stack.setCurrentIndex(self.PAGE_INDEX["user_space"])

    def _open_video_detail(self, bvid: str):
        """视频详情：复用下载页预填（完整详情页尚未接入 GUI）。"""
        app_signals.log_message.emit(0, f"打开视频：{bvid}（已填入下载页）")
        self.download_page.panel.prefill(bvid, "bv")
        self.stack.setCurrentIndex(self.PAGE_INDEX["download"])

    def _goto_page(self, name):
        idx = self.PAGE_INDEX.get(name)
        if idx is None:
            return
        mid = self._current_mid
        # 进入各页前带上当前用户 mid，触发对应加载
        if name == "myspace":
            self.myspace_page.load(self._current_user)
        elif name == "friends":
            tab = getattr(self.myspace_page, "_friends_tab", "following")
            self.friends_page.load(mid, tab)
        elif name == "favorites":
            self.favorites_page.load(mid)
        elif name == "bangumi":
            self.bangumi_page.load(mid)
        elif name == "watch_later":
            self.watch_later_page.load(mid)
        elif name == "history":
            self.history_page.load(mid)
        self.stack.setCurrentIndex(idx)

    def closeEvent(self, event):
        if self.manager.has_running():
            ans = QMessageBox.question(
                self, "退出 b站工具助手", "有下载任务正在运行，确定要退出吗？"
            )
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        # 停止后台线程，避免进程退出时 QThread 仍运行导致崩溃。
        # 协作取消可能受网络/ffmpeg 阻塞影响；若线程尚未退出，必须阻止窗口销毁，
        # 否则 QThread 对象会在线程仍运行时被回收并触发 Qt 致命退出。
        if not self.manager.shutdown():
            QMessageBox.warning(
                self, "下载任务仍在退出", "后台下载尚未安全退出，请稍后再次关闭窗口。"
            )
            event.ignore()
            return
        from frontend.pyside6.workers.login_worker import shutdown_all
        shutdown_all()
        from frontend.pyside6.workers import search_worker
        search_worker.shutdown_all()
        super().closeEvent(event)
