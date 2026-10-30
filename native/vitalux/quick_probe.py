"""Isolated Qt Quick/RHI startup smoke test: catches native Qt/driver aborts."""
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from PySide6.QtQuick import QSGRendererInterface


def main():
    # QSG_RHI_BACKEND must be configured before creating the Quick surface.
    selected = os.environ.get('VITALUX_QUICK_API', 'opengl').lower()
    if selected not in ('opengl', 'vulkan'):
        return 8
    os.environ['QSG_RHI_BACKEND'] = selected
    app = QApplication([])
    from PySide6.QtQuickWidgets import QQuickWidget
    from .quick_scene import QuickAmbientScene
    # Set native window policy before constructing Qt Quick. Applying it to
    # an already constructed top-level QQuickWidget is too late on some QPAs.
    host = QWidget(None, Qt.Tool | Qt.FramelessWindowHint)
    host.setAttribute(Qt.WA_DontShowOnScreen, True)
    host.setAttribute(Qt.WA_ShowWithoutActivating, True)
    host.move(-32000, -32000)
    host.resize(640, 440)
    scene = QuickAmbientScene(host)
    # Keep the hardware preflight invisible: its former 800x560 top-level
    # window was briefly shown to users on every backend switch.
    # QQuickWidget can render to its offscreen RHI texture without mapping
    # a visible native window.
    scene.setAttribute(Qt.WA_DontShowOnScreen, True)
    scene.setAttribute(Qt.WA_ShowWithoutActivating, True)
    scene.resize(640, 440)
    # Simulate the actual mixed Qt Widget layout, not only an empty Quick view.
    layout = QVBoxLayout(scene)
    layout.addWidget(QLabel('Qt Widget overlay smoke test', scene))
    frame = QVBoxLayout(host)
    frame.setContentsMargins(0, 0, 0, 0)
    frame.addWidget(scene)
    # Logical show initializes the real RHI, but the preconfigured host is
    # never mapped to the display and can never take focus or a taskbar slot.
    host.show()
    expected = (QSGRendererInterface.Vulkan if selected == 'vulkan'
                else QSGRendererInterface.OpenGL)
    def check():
        if scene.status() != QQuickWidget.Ready or scene.rootObject() is None:
            app.exit(3)
            return
        image = scene.grabFramebuffer()
        actual = scene.quickWindow().rendererInterface().graphicsApi()
        if actual != expected:
            print(f'Unexpected RHI: {actual}; expected {expected}', file=sys.stderr)
            app.exit(4)
            return
        if image.isNull():
            app.exit(5)
            return
        scene.resize(880, 610)
        scene.sync_background()
        QTimer.singleShot(450, finish)
    def finish():
        if (scene.status() != QQuickWidget.Ready or
                scene.quickWindow().rendererInterface().graphicsApi() != expected or
                scene.grabFramebuffer().isNull()):
            app.exit(6)
        elif any(window.isVisible() for window in app.allWindows()):
            print('Graphics preflight unexpectedly mapped a window', file=sys.stderr)
            app.exit(9)
        else:
            host.close()
            app.exit(0)
    QTimer.singleShot(750, check)
    QTimer.singleShot(5500, lambda: app.exit(7))
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
