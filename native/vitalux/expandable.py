"""An interruptible glass card that reveals its content by growing downwards."""
from PySide6.QtCore import QEvent, QEasingCurve, QPointF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
from . import motion, theme
from .ui_locale import QPushButton
from .widgets import Card


class _Header(QPushButton):
    def __init__(self, parent):
        super().__init__('Erweiterte Einstellungen', parent)
        self.setCheckable(True)
        self.setMinimumHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.progress = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(theme.accent() if self.underMouse() or self.hasFocus() else theme.TEXT)
        painter.setPen(color)
        font = self.font()
        font.setWeight(font.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(0, 0, -32, 0), Qt.AlignLeft | Qt.AlignVCenter, self.text())
        painter.translate(self.width()-14, self.height()/2)
        painter.rotate(90*self.progress)
        painter.setPen(QPen(QColor(theme.accent()), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(QPointF(-3, -5), QPointF(2, 0))
        painter.drawLine(QPointF(2, 0), QPointF(-3, 5))
        painter.end()


class ExpandableCard(Card):
    expandedChanged = Signal(bool)
    settled = Signal()

    def __init__(self, parent=None):
        super().__init__()
        if parent is not None:
            self.setParent(parent)
        self.setObjectName('advancedSettings')
        self.expanded = False
        self._extent = 0
        self._measuring = False
        self.header = _Header(self)
        self.body.addWidget(self.header)
        self.clip = QWidget(self)
        self.clip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.clip.setFixedHeight(0)
        self.body.addWidget(self.clip)
        self.panel = QWidget(self.clip)
        self.panel.setObjectName('advancedSettingsContent')
        self.content = QVBoxLayout(self.panel)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(14)
        self.panel.installEventFilter(self)
        self.clip.installEventFilter(self)
        self.clip.hide()
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self._finished)
        self.header.clicked.connect(self.setExpanded)
        self._measure_timer = QTimer(self)
        self._measure_timer.setSingleShot(True)
        self._measure_timer.timeout.connect(self._measure)

    def addWidget(self, widget):
        self.content.addWidget(widget)

    def _measure(self):
        if self._measuring:
            return
        self._measuring = True
        try:
            margins = self.layout().contentsMargins()
            width = max(1, self.width()-margins.left()-margins.right())
            self.panel.resize(width, max(1, self._extent))
            self.content.activate()
            height = self.content.totalHeightForWidth(width)
            if height < 0:
                height = self.content.sizeHint().height()
            height = max(0, height)
            changed = height != self._extent
            self._extent = height
            self.panel.setGeometry(0, 0, width, height)
            self.content.activate()
            if changed and self.expanded:
                self._animate(height)
        finally:
            self._measuring = False

    def setExpanded(self, expanded, animate=True):
        expanded = bool(expanded)
        if expanded == self.expanded:
            return
        self.expanded = expanded
        self.header.setChecked(expanded)
        self._measure()
        if expanded:
            self.clip.show()
        self._animate(self._extent if expanded else 0, animate)
        self.expandedChanged.emit(expanded)

    def _animate(self, height, animate=True):
        self.animation.stop()
        duration = motion.duration(340) if animate and self.isVisible() else 0
        if not duration or self.clip.height() == height:
            self._frame(height)
            self._finished()
            return
        self.animation.setDuration(duration)
        self.animation.setStartValue(self.clip.height())
        self.animation.setEndValue(height)
        self.animation.start()

    def _frame(self, height):
        self.clip.setFixedHeight(round(height))
        self.header.progress = min(1.0, self.clip.height()/max(1, self._extent))
        self.header.update()

    def _finished(self):
        if not self.expanded:
            self.clip.hide()
        self.settled.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width() and hasattr(self, '_measure_timer'):
            self._measure_timer.start(0)

    def eventFilter(self, obj, event):
        if obj is self.clip and event.type() == QEvent.Resize:
            if event.size().width() != event.oldSize().width():
                self._measure_timer.start(0)
        if event.type() == QEvent.LayoutRequest and not self._measuring:
            self._measure_timer.start(0)
        return False

    def hideEvent(self, event):
        if hasattr(self, 'animation'):
            self.animation.stop()
            self._frame(self._extent if self.expanded else 0)
            self._finished()
        super().hideEvent(event)
