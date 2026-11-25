"""图片加载工具：网络图片 + 磁盘缓存 + 圆形/矩形裁剪 + 默认占位。

头像（圆形）供首页头像按钮、下载页登录卡片、个人中心页共用；
封面（矩形）供视频网格卡片使用。
加载在网络请求的 reply 线程完成信号里回调（Qt 自动排回主线程），不阻塞 UI。
"""
import hashlib
import logging
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap, QPixmapCache
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from src.config.path import ASSETS_DIR

logger = logging.getLogger(__name__)

CACHE_DIR = ASSETS_DIR / "cache"
_PLACEHOLDER = QColor("#cfd6de")

# 内存缓存容量（KB）：封面/头像解码后驻留，避免翻页时反复从磁盘解码导致卡顿。
QPixmapCache.setCacheLimit(64 * 1024)


def _mem_key(url: str, mode: str, spec) -> str:
    size = spec if isinstance(spec, int) else f"{spec[0]}x{spec[1]}"
    return f"avatar:{mode}:{size}:{url}"


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
        self._pending = {}  # reply -> (mode, spec, [callbacks], cache, url, key)
        self._inflight = {}  # cache_path -> reply（同一图片只发一个请求）

    def _get(self, url: str, mode: str, spec, callback, fallback):
        key = _mem_key(url, mode, spec)
        pm = QPixmapCache.find(key)
        if pm is not None and not pm.isNull():
            callback(pm)
            return
        if not url:
            callback(fallback())
            return
        cache = _cache_path(url)
        # 已在下载中的同一图片：把回调挂到同一请求上，避免重复下载
        if cache in self._inflight:
            self._pending[self._inflight[cache]][2].append(callback)
            # 新请求的尺寸可能和已有请求不同；内存 key 不同时无法复用，
            # 但磁盘缓存会在首个请求返回后写入，这里先回调占位图兜底。
            return
        if cache.exists():
            disk = QPixmap(str(cache))
            if not disk.isNull():
                pm = round_pixmap(disk, spec) if mode == "round" else cover_pixmap(disk, spec[0], spec[1])
                QPixmapCache.insert(key, pm)
                callback(pm)
                return
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        reply = self._net.get(QNetworkRequest(QUrl(url)))
        self._pending[reply] = (mode, spec, [callback], cache, url, key)
        self._inflight[cache] = reply

    def load(self, url: str, size: int, callback) -> None:
        """加载头像：内存缓存 → 磁盘缓存 → 网络。失败回调默认占位图。"""
        self._get(url, "round", size, callback, lambda: placeholder(size))

    def load_cover(self, url: str, width: int, height: int, callback) -> None:
        """加载矩形封面：内存缓存 → 磁盘缓存 → 网络。失败回调灰色占位。"""
        self._get(url, "cover", (width, height), callback,
                  lambda: cover_placeholder(width, height))

    def _on_finished(self, reply) -> None:
        item = self._pending.pop(reply, None)
        if item is None:
            return
        mode, spec, callbacks, cache, url, key = item
        self._inflight.pop(cache, None)
        try:
            data = reply.readAll()
            img = QImage.fromData(data)
            if img.isNull():
                raise ValueError("图片数据不是有效图片")
            img.save(str(cache), "PNG")
            pm = QPixmap.fromImage(img)
            done = cover_pixmap(pm, spec[0], spec[1]) if mode == "cover" else round_pixmap(pm, spec)
            QPixmapCache.insert(key, done)
            for cb in callbacks:
                cb(done)
        except Exception as e:
            logger.warning("[AvatarLoader] 图片加载失败：%s", e)
            fallback = cover_placeholder(spec[0], spec[1]) if mode == "cover" else placeholder(spec)
            for cb in callbacks:
                cb(fallback)
        finally:
            reply.deleteLater()
