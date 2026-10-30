"""Native-resolution appearance blends, with no live subtree repaint per frame."""
from PySide6.QtCore import QEasingCurve, QEvent, Signal, QVariantAnimation, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget
from . import motion


class AppearanceTransition(QWidget):
    finished = Signal()

    def __init__(self, parent, before, after, *, slide=0):
        super().__init__(parent)
        self.setObjectName('appearanceTransition')
        self.before, self.after = before, after
        self.progress = 0.0
        self.slide=slide
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.setDuration(motion.duration(300))
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self.finish)

    def start(self):
        self.show()
        self.raise_()
        self.animation.start()

    def _frame(self, value):
        self.progress = float(value)
        self.update()

    def finish(self):
        self.animation.stop()
        self.hide()
        self.before = self.after = None
        self.parentWidget().removeEventFilter(self)
        self.finished.emit()
        self.deleteLater()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Hide):
            self.finish()
        return False

    def paintEvent(self, event):
        if self.before is None:
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.before)
        painter.setOpacity(self.progress)
        if self.slide:painter.translate(round(self.slide*(1-self.progress)),0)
        painter.drawPixmap(0, 0, self.after)
        painter.end()
