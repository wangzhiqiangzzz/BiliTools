"""图片加载工具：网络图片 + 磁盘缓存 + 圆形/矩形裁剪 + 默认占位。

头像（圆形）供首页头像按钮、下载页登录卡片、个人中心页共用；
封面（矩形）供视频网格卡片使用。
加载在网络请求的 reply 线程完成信号里回调（Qt 自动排回主线程），不阻塞 UI。
"""
import hashlib
import logging
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from src.config.path import ASSETS_DIR

logger = logging.getLogger(__name__)

CACHE_DIR = ASSETS_DIR / "cache"
_PLACEHOLDER = QColor("#cfd6de")


def _cache_path(url: str) -> Path:
    """缓存文件名 = SHA256(url)，与 downkyicore 的图片缓存策略一致。"""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"avatar_{digest}.png"


def round_pixmap(pm: QPixmap, size: int) -> QPixmap:
    """把图片按圆形裁剪并缩放到 size×size。"""
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    p.setClipPath(path)
    scaled = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


def cover_pixmap(pm: QPixmap, width: int, height: int) -> QPixmap:
    """把图片按矩形裁剪缩放（保持比例填满，多余部分裁掉），用于视频封面。"""
    scaled = pm.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    x = (scaled.width() - width) // 2
    y = (scaled.height() - height) // 2
    return scaled.copy(x, y, width, height)


def cover_placeholder(width: int, height: int) -> QPixmap:
    """默认灰色矩形封面占位。"""
    pm = QPixmap(width, height)
    pm.fill(_PLACEHOLDER)
    return pm


def placeholder(size: int) -> QPixmap:
    """默认灰色圆形头像。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(_PLACEHOLDER)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(0, 0, size, size))
    p.end()
    return pm


class AvatarLoader:
    """异步头像加载器。持有一个 QNetworkAccessManager，加载结果回调 callback(QPixmap)。

    用法：
        self._avatar = AvatarLoader(self)
        self._avatar.load(url, 32, lambda pm: self.label.setPixmap(pm))
    """

    def __init__(self, parent=None):
        self._net = QNetworkAccessManager(parent)
        self._net.finished.connect(self._on_finished)
        self._pending = {}  # reply -> (size, callback)

    def load(self, url: str, size: int, callback) -> None:
        """加载头像；优先读缓存，否则发起网络请求。失败回调默认占位图。"""
        if not url:
            callback(placeholder(size))
            return
        cache = _cache_path(url)
        if cache.exists():
            pm = QPixmap(str(cache))
            if not pm.isNull():
                callback(round_pixmap(pm, size))
                return
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        reply = self._net.get(QNetworkRequest(QUrl(url)))
        self._pending[reply] = ("round", size, callback, cache)

    def load_cover(self, url: str, width: int, height: int, callback) -> None:
        """加载矩形封面（不裁剪成圆）；优先读缓存，失败回调灰色占位。"""
        if not url:
            callback(cover_placeholder(width, height))
            return
        cache = _cache_path(url)
        if cache.exists():
            pm = QPixmap(str(cache))
            if not pm.isNull():
                callback(cover_pixmap(pm, width, height))
                return
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        reply = self._net.get(QNetworkRequest(QUrl(url)))
        self._pending[reply] = ("cover", (width, height), callback, cache)

    def _on_finished(self, reply) -> None:
        item = self._pending.pop(reply, None)
        if item is None:
            return
        mode, spec, callback, cache = item
        try:
            data = reply.readAll()
            img = QImage.fromData(data)
            if img.isNull():
                raise ValueError("图片数据不是有效图片")
            img.save(str(cache), "PNG")
            pm = QPixmap.fromImage(img)
            if mode == "cover":
                callback(cover_pixmap(pm, spec[0], spec[1]))
            else:
                callback(round_pixmap(pm, spec))
        except Exception as e:
            logger.warning("[AvatarLoader] 图片加载失败：%s", e)
            if mode == "cover":
                callback(cover_placeholder(spec[0], spec[1]))
            else:
                callback(placeholder(spec))
        finally:
            reply.deleteLater()
