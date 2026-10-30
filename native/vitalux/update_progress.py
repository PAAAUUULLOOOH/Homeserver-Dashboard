"""Centered update percentage, readable on both sides of the progress fill."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from .widgets import Bar
from . import theme
from .i18n import tr


class UpdateProgress(Bar):
    def __init__(self):
        super().__init__()
        self.flat=True;self.setFixedHeight(28)
        self.setAccessibleName(tr('Update-Fortschritt'))
        self.set_value(0)

    def set_value(self,value):
        super().set_value(value)
        self.setAccessibleDescription(f'{round(self.value)}%')

    def paintEvent(self,event):
        self.custom_color=theme.accent()
        super().paintEvent(event)
        p=QPainter(self)
        font=p.font();font.setBold(True);p.setFont(font)
        text=f'{round(self.value)}%'
        p.setPen(QColor(theme.TEXT));p.drawText(self.rect(),Qt.AlignCenter,text)
        p.setClipRect(QRectF(0,0,self.width()*self.value/100,self.height()))
        p.setPen(QColor('#ffffff' if theme.is_light() else '#07111b'))
        p.drawText(self.rect(),Qt.AlignCenter,text);p.end()
