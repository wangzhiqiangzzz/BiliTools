"""社交/个人内容的后台加载线程：关注、粉丝、分组、收藏夹、稍后再看、追番、历史。

统一返回 (items, total, extra)，避免网络请求卡住 UI。
"""
from functools import partial
import logging
from typing import Callable

from PySide6.QtCore import QThread, Signal

from src.services.social import SocialService

logger = logging.getLogger(__name__)

_keepalive = []


class SocialLoadWorker(QThread):
    """通用社交列表加载线程。

    :param loader: 无参 callable，返回 (items, total, extra) 或 items
    """

    result = Signal(list, int, dict)
    failed = Signal(str)

    def __init__(self, loader: Callable, parent=None):
        super().__init__(parent)
        self.loader = loader
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self):
        if self._stop:
            return
        try:
            out = self.loader()
            if isinstance(out, tuple):
                items = out[0] if out else []
                total = out[1] if len(out) > 1 and isinstance(out[1], int) else 0
                extra = out[2] if len(out) > 2 and isinstance(out[2], dict) else (
                    out[1] if len(out) > 1 and isinstance(out[1], dict) else {}
                )
            else:
                items, total, extra = out or [], 0, {}
            if not self._stop:
                self.result.emit(list(items), int(total), extra)
        except Exception as e:
            logger.warning("[SocialLoadWorker] 加载失败：%s", e)
            if not self._stop:
                self.failed.emit(str(e) or e.__class__.__name__)


def load_social(loader: Callable, on_result, on_error=None) -> SocialLoadWorker:
    """启动一次后台加载，结果通过回调送达主线程。返回 worker 供取消。"""
    w = SocialLoadWorker(loader)
    w.result.connect(on_result)
    if on_error:
        w.failed.connect(on_error)
    w.finished.connect(lambda: _drop(w))
    _keepalive.append(w)
    w.start()
    return w


def _drop(w):
    if w in _keepalive:
        _keepalive.remove(w)


def shutdown_all() -> None:
    """退出前停止所有社交加载线程。"""
    for w in list(_keepalive):
        try:
            if w.isRunning():
                w.stop()
                w.wait(2000)
        except Exception:
            pass
        _drop(w)


# 常用 loader 构造器（给各页面直接用 partial 组合）
def following_loader(service: SocialService, mid: int, pn: int, ps: int = 20):
    return partial(service.get_following, mid, pn, ps)


def followers_loader(service: SocialService, mid: int, pn: int, ps: int = 20):
    return partial(service.get_followers, mid, pn, ps)


def group_members_loader(service: SocialService, tag_id: int, pn: int, ps: int = 20):
    return partial(service.get_group_members, tag_id, pn, ps)


def fav_folders_loader(service: SocialService, mid: int, pn: int, ps: int = 20):
    return partial(service.get_fav_folders, mid, pn, ps)


def fav_medias_loader(service: SocialService, media_id: int, pn: int, ps: int = 20):
    return partial(service.get_fav_medias, media_id, pn, ps)


def watch_later_loader(service: SocialService, pn: int, ps: int = 20):
    return partial(service.get_watch_later, pn, ps)


def bangumi_loader(service: SocialService, mid: int, pn: int, ps: int = 15, typ: int = 1):
    return partial(service.get_bangumi_follow, mid, pn, ps, typ)


def history_loader(service: SocialService, max_id: int, view_at: int, ps: int = 30):
    return partial(service.get_history, max_id, view_at, "", ps)
