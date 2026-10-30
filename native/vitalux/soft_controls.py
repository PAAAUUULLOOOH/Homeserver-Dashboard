"""Small native controls with interruptible, local-only transitions."""
from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QBoxLayout, QGraphicsOpacityEffect, QLayout, QSizePolicy, QWidget
from . import motion, theme


class ResponsiveActions(QWidget):
    """Keep complete action captions on small or fractionally scaled windows."""
    def __init__(self, buttons, parent=None):
        super().__init__(parent)
        self.buttons = buttons
        self.row = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(10)
        self.row.setSizeConstraint(QLayout.SetNoConstraint)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        for button in buttons:
            self.row.addWidget(button, 0, Qt.AlignLeft)

    def _natural_width(self):
        return sum(button.sizeHint().width() for button in self.buttons)+10*(len(self.buttons)-1)

    def minimumSizeHint(self):
        return QSize(max(button.minimumSizeHint().width() for button in self.buttons),
                     max(button.sizeHint().height() for button in self.buttons))

    def sizeHint(self):
        return QSize(self._natural_width(), self.heightForWidth(self.width()))

    def heightForWidth(self, width):
        sizes = [button.sizeHint().height() for button in self.buttons]
        return sum(sizes)+10*(len(sizes)-1) if width < self._natural_width() else max(sizes)

    def resizeEvent(self, event):
        direction = QBoxLayout.TopToBottom if self.width() < self._natural_width() else QBoxLayout.LeftToRight
        if direction != self.row.direction():
            self.row.setDirection(direction)
            self.updateGeometry()
        super().resizeEvent(event)


class SoftReveal(QWidget):
    """Clip and fade one control while releasing its layout space smoothly."""
    def __init__(self, control, parent=None):
        super().__init__(parent)
        self.control = control
        control.setParent(self)
        self.revealed = False
        self.progress = 0.0
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.effect = QGraphicsOpacityEffect(control)
        control.setGraphicsEffect(self.effect)
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self._finished)
        self._frame(0.0)
        self.control.hide()
        self.hide()

    def sizeHint(self):
        size = self.control.sizeHint()
        return QSize(size.width(), round(size.height()*self.progress))

    def setRevealed(self, shown, animate=True):
        shown = bool(shown)
        if shown == self.revealed:
            return
        self.revealed = shown
        self.animation.stop()
        self.control.setEnabled(shown)
        if shown:
            self.show()
            self.control.show()
        duration = motion.duration(240) if animate and self.window().isVisible() else 0
        if not duration:
            self._frame(float(shown))
            self._finished()
            return
        start = self.progress
        self.animation.blockSignals(True)
        self.animation.setDuration(max(1, round(duration*abs(float(shown)-start))))
        self.animation.setStartValue(start)
        self.animation.setEndValue(float(shown))
        self.animation.setCurrentTime(0)
        self.animation.blockSignals(False)
        self.animation.start()

    def _frame(self, fraction):
        self.progress = float(fraction)
        height = max(1, self.control.sizeHint().height())
        self.setFixedHeight(round(height*self.progress))
        self.effect.setOpacity(self.progress)
        self.control.setGeometry(0, 0, self.width(), height)
        self.updateGeometry()

    def _finished(self):
        if not self.revealed:
            self.control.hide()
            self.hide()
        self.updateGeometry()

    def resizeEvent(self, event):
        self.control.setGeometry(0, 0, self.width(), max(1, self.control.sizeHint().height()))
        super().resizeEvent(event)

    def hideEvent(self, event):
        if hasattr(self, 'animation') and self.animation.state() == QAbstractAnimation.Running:
            self.animation.stop()
            self._frame(float(self.revealed))
        super().hideEvent(event)


class AccentSwatch(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('accentPreview')
        self.setFixedSize(38, 26)
        self._color = QColor(theme.accent())
        self._target = QColor(self._color)
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self._frame)
        self.setColor(self._color, animate=False)

    def setColor(self, color, animate=True):
        color = QColor(color)
        if color == self._target:
            self.setToolTip(color.name())
            return
        self._target = color
        self.setToolTip(color.name())
        self.animation.stop()
        duration = motion.duration(260) if animate and self.isVisible() else 0
        if duration:
            self.animation.setDuration(duration)
            self.animation.setStartValue(self._color)
            self.animation.setEndValue(color)
            self.animation.start()
        else:
            self._frame(color)

    def _frame(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        material = QLinearGradient(rect.topLeft(), rect.bottomRight())
        material.setColorAt(0, self._color.lighter(118))
        material.setColorAt(.5, self._color)
        material.setColorAt(1, self._color.darker(115))
        p.setBrush(material)
        p.setPen(QPen(QColor(theme.TEXT), .65))
        p.drawRoundedRect(rect, 7, 7)
        shine = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shine.setColorAt(0, QColor(255, 255, 255, 105))
        shine.setColorAt(.55, QColor(255, 255, 255, 0))
        p.setBrush(shine)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
        p.end()
