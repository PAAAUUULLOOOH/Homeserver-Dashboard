"""Experimental Qt Quick/scene-graph wallpaper under ordinary Qt widgets.

Qt Quick owns the background texture through Qt RHI (OpenGL or Vulkan).
Ordinary QWidget charts/cards remain CPU-painted.
"""
from pathlib import Path

from PySide6.QtCore import QMutex, QMutexLocker, QTimer, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickWidgets import QQuickWidget

from . import theme
from .glass import ASSETS, _AmbientSceneCore


class WallpaperProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self._lock = QMutex()
        self._image = QImage(1, 1, QImage.Format_ARGB32)
        self._image.fill(QColor(theme.BG))

    def replace(self, image):
        if not image.isNull():
            with QMutexLocker(self._lock):
                self._image = image.copy()

    def requestImage(self, identifier, size, requestedSize):
        with QMutexLocker(self._lock):
            image = self._image.copy()
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image


class QuickAmbientScene(_AmbientSceneCore, QQuickWidget):
    """Real GPU scene graph for backgrounds with QWidget children on top."""

    def __init__(self, parent=None):
        self._quick_ready = False
        self._generation = 0
        super().__init__(parent)
        # QQuickWidget composites its own backing texture; do not mark it as
        # a manually painted, opaque raster widget (can corrupt its surface).
        from PySide6.QtCore import Qt
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self._upload_timer = QTimer(self)
        self._upload_timer.setSingleShot(True)
        self._upload_timer.timeout.connect(self._upload_frame)
        self.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.setClearColor(QColor(theme.BG))
        self._provider = WallpaperProvider()
        self.engine().addImageProvider('vitaluxwallpaper', self._provider)
        source = Path(ASSETS) / 'quick-background.qml'
        self.setSource(QUrl.fromLocalFile(str(source)))
        if self.status() != QQuickWidget.Ready or self.rootObject() is None:
            details = '; '.join(item.toString() for item in self.errors())
            raise RuntimeError('Qt Quick background could not start: ' + details)
        self._quick_ready = True
        self._schedule_upload()

    def _schedule_upload(self):
        if self._quick_ready and not self._upload_timer.isActive():
            self._upload_timer.start(16)

    def _upload_frame(self):
        if not self._quick_ready:
            return
        self._ensure_composed()
        source = self._composed_sharp
        if source.isNull():
            image = QImage(max(1, self.width()), max(1, self.height()),
                           QImage.Format_ARGB32)
            image.fill(QColor(theme.BG))
        else:
            image = source.toImage()
        self._provider.replace(image)
        self.setClearColor(QColor(theme.BG))
        self._generation += 1
        root = self.rootObject()
        if root is not None:
            root.setProperty('generation', self._generation)

    def sync_background(self):
        super().sync_background()
        if self._quick_ready:
            self._schedule_upload()

    def finish_background_frame(self):
        """Make a palette-change snapshot include the new RHI texture now."""
        if self._quick_ready:
            self._upload_timer.stop()
            self._upload_frame()
            self.grabFramebuffer()

    def _advance_backdrop(self):
        super()._advance_backdrop()
        if self._quick_ready and self.isVisible():
            self._schedule_upload()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._quick_ready:
            self._schedule_upload()

    def closeEvent(self, event):
        # Never let a pending image-provider update race Qt Quick destruction.
        self._quick_ready = False
        self._upload_timer.stop()
        super().closeEvent(event)
