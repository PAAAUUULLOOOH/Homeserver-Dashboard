"""One source of truth for customization controls and preview indicators."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QConicalGradient,QPainterPath,QPen

FIXED=frozenset(('minimal',))


def capabilities(key):
    return dict(accent=key not in FIXED,custom_accent=key not in FIXED,
                background=key not in FIXED)


def description(key):
    from .i18n import tr
    cap=capabilities(key)
    accent=('Feste Designpalette' if not cap['accent'] else
            'Akzentfarben: Voreinstellungen verfügbar; eigene Farben gesperrt' if not cap['custom_accent'] else 'Akzentfarben anpassbar')
    return tr(accent)+' · '+tr('Hintergrund anpassbar' if cap['background'] else 'Fester Hintergrund')


def paint(p,tile,pal,amount):
    if amount<=.001:return
    cap=capabilities(tile.key)
    p.save();p.setOpacity(amount);p.translate(0,4*(1-amount))
    size=22;gap=4
    for index,kind in enumerate(('accent','background')):
        enabled=cap[kind];x=tile.width()-size-10;y=(tile.height()-(2*size+gap))/2+index*(size+gap)
        p.setPen(QPen(QColor('#8e9aa8'),.75));p.setBrush(QColor(12,16,23,244))
        p.drawRoundedRect(QRectF(x,y,size,size),6,6)
        p.save();p.translate(x+2,y+2);p.scale(.78,.78)
        ink=QColor(pal['accent'] if enabled else '#a6aab2')
        p.setPen(QPen(ink,1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.setBrush(Qt.NoBrush)
        if kind=='accent':
            gradient=QConicalGradient(10,10,90)
            colors=('#ed7886','#efc357','#7bca8b','#56bddb','#818ce7','#c87ed4','#ed7886') if enabled else ('#a4a9b3','#68717e','#a4a9b3')
            for i,value in enumerate(colors):gradient.setColorAt(i/(len(colors)-1),QColor(value))
            p.setPen(QPen(QColor('#e6eaf1'),.7));p.setBrush(gradient);p.drawEllipse(QRectF(.5,.5,20,20))
        else:
            p.drawRoundedRect(QRectF(1,2,20,17),2,2)
            path=QPainterPath(QPointF(2,16));path.lineTo(7,9);path.lineTo(12,14);path.lineTo(16,10);path.lineTo(21,16)
            p.drawPath(path);p.drawEllipse(QRectF(14,5,3,3))
        p.restore()
    p.restore()
