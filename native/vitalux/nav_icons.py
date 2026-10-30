"""Twelve coherent, cached vector symbols; no platform-dependent font glyphs."""
import math
from functools import lru_cache
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

GLYPHS = {'◈':'overview', '◉':'cpu', '▣':'gpu', '▤':'memory', '▱':'drives',
          '◎':'network', '♨':'sensors', '⌕':'diagnostics', '⚙':'system',
          '≡':'settings', '↻':'updates', 'ⓘ':'info'}


@lru_cache(maxsize=12)
def geometry(key):
    path = QPainterPath()
    def line(*points):
        path.moveTo(*points[0])
        for point in points[1:]: path.lineTo(*point)
    def box(x,y,w,h,r=1.5): path.addRoundedRect(QRectF(x,y,w,h),r,r)
    def circle(x,y,r): path.addEllipse(QPointF(x,y),r,r)
    if key == 'overview':
        for x,y,w,h in ((3,3,7,10),(14,3,7,6),(3,17,7,4),(14,13,7,8)): box(x,y,w,h)
    elif key == 'cpu':
        box(6,6,12,12,2); box(9,9,6,6,1)
        for i in (8,12,16):
            line((i,2),(i,5));line((i,19),(i,22));line((2,i),(5,i));line((19,i),(22,i))
    elif key == 'gpu':
        box(3,6,18,12);circle(11,12,4)
        for angle in (0,2.094,4.189):
            line((11,12),(11+3*math.cos(angle),12+3*math.sin(angle)))
        line((1,5),(1,19),(4,19));line((7,18),(7,21),(16,21),(16,18))
        line((18,9),(18,15))
    elif key == 'memory':
        box(2,6,20,11)
        for x in (5,10,15): box(x,9,3,5,.5)
        for x in (4,7,10,14,17,20): line((x,18),(x,21))
    elif key == 'drives':
        box(4,2,16,20,2);circle(12,10,5);circle(12,10,1)
        line((12,10),(17,14));line((7,18),(12,18));circle(17,18,.6)
    elif key == 'network':
        circle(12,4,2);box(2,17,6,5,1);box(16,17,6,5,1)
        line((12,6),(12,11),(5,11),(5,17));line((12,11),(19,11),(19,17))
    elif key == 'sensors':
        path.moveTo(9,15);path.lineTo(9,5);path.cubicTo(9,1,15,1,15,5)
        path.lineTo(15,15);path.arcTo(QRectF(7,13,10,10),45,-270);path.closeSubpath()
        line((12,7),(12,18));circle(12,18,1.4)
        line((18,7),(21,7));line((18,11),(20,11))
    elif key == 'diagnostics':
        path.moveTo(12,2);path.lineTo(21,6);path.lineTo(20,13)
        path.cubicTo(19,18,16,21,12,23);path.cubicTo(8,21,5,18,4,13)
        path.lineTo(3,6);path.closeSubpath()
        line((6,12),(9,12),(11,8),(14,16),(16,12),(19,12))
    elif key == 'system':
        box(2,3,20,14,2);line((12,17),(12,22));line((7,22),(17,22))
        line((5,12),(8,12),(10,7),(13,14),(16,9),(19,9))
    elif key == 'settings':
        for i in range(48):
            angle=2*math.pi*i/48
            radius=9.5 if i%4 in (1,2) else 7.5
            point=QPointF(12+radius*math.cos(angle),12+radius*math.sin(angle))
            if i: path.lineTo(point)
            else: path.moveTo(point)
        path.closeSubpath();circle(12,12,3.2)
    elif key == 'updates':
        path.arcMoveTo(QRectF(3,3,18,18),35)
        path.arcTo(QRectF(3,3,18,18),35,290)
        line((20,3),(20,9),(14,9));line((12,8),(12,16));line((9,13),(12,16),(15,13))
    else:
        circle(12,12,9);circle(12,7,.6);line((10,11),(12,11),(12,17));line((10,17),(14,17))
    return path


def paint_icon(painter, key, rect, color):
    painter.save()
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width()/24, rect.height()/24)
    painter.setPen(QPen(QColor(color),1.7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(geometry(key))
    painter.restore()
