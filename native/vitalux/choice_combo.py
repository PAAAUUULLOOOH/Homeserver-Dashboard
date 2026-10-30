"""A fixed theme value is a grey, disabled readout rather than a popup."""
from PySide6.QtWidgets import QStyle, QStyleOptionComboBox, QStylePainter
from .ui_locale import QComboBox
from .i18n import tr


class ChoiceComboBox(QComboBox):
    def __init__(self, parent=None):
        self._lock_reason = self._lock_title = ''
        super().__init__(parent)

    def isLocked(self):
        return bool(self._lock_reason)

    def setLocked(self, reason='', title=''):
        self._lock_reason, self._lock_title = reason, title
        self.hidePopup()
        self.setEnabled(not bool(reason))
        style = ('QComboBox { color: #8b8e95; border-color: #54565c; '
                 'background: rgba(92,96,104,35); } '
                 'QComboBox::drop-down { width: 0px; border: none; } '
                 'QComboBox::down-arrow { image: none; }') if reason else ''
        if self.styleSheet() != style:
            self.setStyleSheet(style)
        self.setToolTip(tr(reason) if reason else self.currentText())
        self.update()

    def paintEvent(self, event):
        if not self.isLocked():
            return super().paintEvent(event)
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = tr(self._lock_title)
        option.subControls = QStyle.SC_ComboBoxFrame | QStyle.SC_ComboBoxEditField
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)

    def showPopup(self):
        if not self.isLocked() and self.isEnabled():
            super().showPopup()
