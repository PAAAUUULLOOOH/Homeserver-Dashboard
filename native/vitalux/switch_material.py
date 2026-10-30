"""Quiet native toggle materials following each classic design's palette."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor,QLinearGradient,QPen
from . import theme


def paint_switch(p,rect,progress,focused):
    flat=theme.mode()=='minimal'
    active=theme.blend(theme.accent(),theme.TRACK,.12+.62*progress)
    p.setBrush(QColor(active));p.setPen(QPen(QColor(theme.accent() if focused else theme.BORDER),1.5 if focused else .9))
    radius=3 if flat else rect.height()/2
    p.drawRoundedRect(rect,radius,radius)
    thumb=QRectF(rect.left()+3+progress*(rect.width()-rect.height()),rect.top()+3,rect.height()-6,rect.height()-6)
    if flat:p.setBrush(QColor(theme.TEXT))
    else:
        gradient=QLinearGradient(thumb.topLeft(),thumb.bottomRight())
        gradient.setColorAt(0,QColor(theme.TEXT));gradient.setColorAt(1,QColor(theme.accent() if progress>.5 else theme.MUTED))
        p.setBrush(gradient)
    p.setPen(QPen(QColor(theme.blend(theme.TEXT,theme.BORDER,.35)),.7))
    p.drawRoundedRect(thumb,2 if flat else 8,2 if flat else 8)
