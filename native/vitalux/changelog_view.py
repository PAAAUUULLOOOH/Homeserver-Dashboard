"""A bounded release-note view; short notes need no scrollbar."""
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QFrame

from .smooth_scroll import AdaptiveScrollArea


class ChangelogView(AdaptiveScrollArea):
    def __init__(self, text_label, parent=None):
        self._height_window = None
        self._layout_timer = None
        super().__init__(parent)
        self.setObjectName('glassScroll')
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWidgetResizable(False)
        self.setWidget(text_label)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._identity = None
        self._reset_pending = False
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._fit_content)

    def set_notes(self, text, identity):
        if identity != self._identity:
            self._identity = identity
            self._reset_pending = True
            self._cancel_scroll()
        if text != self.widget().text():
            self.widget().setText(text)
        self._layout_timer.start(0)

    def _fit_content(self):
        label = self.widget()
        width = max(1, self.contentsRect().width())
        limit = max(140, min(350, round(self.window().height() * .38)))
        height = max(1, label.heightForWidth(width))
        if height > limit:
            width = max(1, width - self.verticalScrollBar().sizeHint().width())
            height = max(1, label.heightForWidth(width))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if height>limit else Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(min(limit, height))
        label.resize(width, height)
        if self._reset_pending:
            self.verticalScrollBar().setValue(0)
            self._reset_pending = False

    def showEvent(self, event):
        super().showEvent(event)
        window = self.window()
        if window is not self._height_window:
            if self._height_window is not None:
                self._height_window.removeEventFilter(self)
            self._height_window = window
            window.installEventFilter(self)
        self._layout_timer.start(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._layout_timer is not None:
            self._layout_timer.start(0)

    def eventFilter(self, watched, event):
        if watched is self._height_window and event.type() == QEvent.Resize:
            self._layout_timer.start(0)
        return super().eventFilter(watched, event)
