"""Shared rounded gallery outline and inset selection marker."""
from PySide6.QtCore import QRectF,QPointF,Qt
from PySide6.QtGui import QPainterPath,QColor,QPen

def outline(tile):
    rect=QRectF(tile.rect()).adjusted(2,2,-2,-2)
    path=QPainterPath();path.addRoundedRect(rect,28,28)
    return path

def selection_center(tile):return QPointF(tile.width()-21,18)

def finish(p,tile,pal):
    p.setClipping(False)
    path=outline(tile)
    selected=tile.isChecked() or tile.hasFocus()
    ink=QColor(pal['accent']);ink.setAlpha(245 if selected else round(75+100*tile._hover))
    p.setPen(QPen(ink,2 if selected else 1));p.setBrush(Qt.NoBrush);p.drawPath(path)
    if tile.isChecked():
        c=selection_center(tile)
        p.setPen(Qt.NoPen);p.setBrush(QColor(pal['accent']));p.drawEllipse(c,7,7)
        p.setPen(QPen(QColor(pal['bg']),1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        p.drawLine(c+QPointF(-3,0),c+QPointF(-1,2));p.drawLine(c+QPointF(-1,2),c+QPointF(3,-2))
