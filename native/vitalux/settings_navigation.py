"""Smooth, cancellable navigation from setting predictions and search results."""
from PySide6.QtCore import QEvent, QEasingCurve, QObject, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QScrollArea
from shiboken6 import isValid
from . import motion, theme


class SettingsNavigator(QObject):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.scroll = None
        self.target = None
        self._focus = False
        self._highlight = None
        self._highlight_rule = ''
        self.animation = None
        self.prediction = QTimer(self)
        self.prediction.setSingleShot(True)
        self.prediction.setInterval(200)
        self.prediction.timeout.connect(self._start)
        self.highlight_timer = QTimer(self)
        self.highlight_timer.setSingleShot(True)
        self.highlight_timer.timeout.connect(self._clear_highlight)
        page.installEventFilter(self)

    def install_on(self, scroll):
        if self.scroll is scroll:
            return
        self.scroll = scroll
        self.animation = QPropertyAnimation(scroll.verticalScrollBar(), b'value', self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.finished.connect(self._arrived)
        scroll.verticalScrollBar().sliderPressed.connect(self.cancel)
        scroll.viewport().installEventFilter(self)

    def predict(self, target):
        if target is self.target:
            return
        self.cancel()
        self.target, self._focus = target, False
        if target is not None:
            self.prediction.start()

    def choose(self, target):
        self.prediction.stop()
        self.target, self._focus = target, True
        self._start()

    def cancel(self):
        self.prediction.stop()
        if self.animation is not None:
            self.animation.stop()
        self.target = None

    def _start(self):
        target = self.target
        if target is None or not isValid(target):
            return
        if self.scroll is None:
            parent = self.page.parentWidget()
            while parent is not None and not isinstance(parent, QScrollArea):
                parent = parent.parentWidget()
            if parent is None:
                return
            self.install_on(parent)
        cancel_wheel = getattr(self.scroll, '_cancel_scroll', None)
        if callable(cancel_wheel):
            cancel_wheel()
        self.page.layout().activate()
        destination = max(0, target.mapTo(self.page, QPoint(0, 0)).y()-110)
        bar = self.scroll.verticalScrollBar()
        self.animation.stop()
        duration = motion.duration(420)
        if duration:
            self.animation.setDuration(duration)
            self.animation.setStartValue(bar.value())
            self.animation.setEndValue(destination)
            self.animation.start()
        else:
            bar.setValue(destination)
            self._arrived()

    def _arrived(self):
        target = self.target
        if target is None or not isValid(target):
            return
        if self._focus and target.isEnabled():
            target.setFocus(Qt.OtherFocusReason)
        self._clear_highlight()
        self._highlight = target
        self._highlight_rule = '/* settings-match */ border: 2px solid '+theme.accent()+';'
        target.setStyleSheet(target.styleSheet()+self._highlight_rule)
        self.highlight_timer.start(1500)

    def _clear_highlight(self):
        target = self._highlight
        if target is not None and isValid(target):
            style = target.styleSheet()
            if style.endswith(self._highlight_rule):
                target.setStyleSheet(style[:-len(self._highlight_rule)])
        self._highlight = None

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel or (obj is self.page and event.type() == QEvent.Hide):
            self.cancel()
        return False
