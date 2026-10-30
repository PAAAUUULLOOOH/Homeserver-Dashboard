"""Crystal Glass glass from the supplied reference, on the original dashboard.

The blue/violet scene is static and cached by the normal scene owner. There is
no custom overview, animation timer or replacement measurement layout here.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from . import theme
from PySide6.QtGui import QBrush,QColor,QConicalGradient,QFont,QLinearGradient,QPainter,QPainterPath,QPen,QPixmap,QRadialGradient

KEY='crystal_glass'
PALETTE=dict(title='Crystal Glass',subtitle='LIQUID GLASS / BLUE VIOLET',
    bg='#080f26',sidebar='#102347',card='#182a48',border='#b5d4ff',track='#294569',
    grid='#405779',text='#f2f8ff',muted='#c0cce4',accent='#94dfff',secondary='#baa7ff',
    light='#dff7ff',bloom='#8970db',shadow='#0b1230',series=('#94dfff','#baa7ff','#cdeaff','#83b1df'))

def color(value, alpha=255):
    c = QColor(value)
    c.setAlpha(max(0, min(255, round(alpha))))
    return c

def _rr(rect, radius):
    path = QPainterPath()
    radius = max(0.0, min(radius, rect.width() / 2, rect.height() / 2))
    path.addRoundedRect(rect, radius, radius)
    return path

def _soft_shadow(p, rect, radius, strength=1.0):
    for i in range(8):
        t = (i + 1) / 8
        grow = t * 18
        dy = t * 11
        alpha = ((1 - t) ** 1.8) * 62 * strength
        if alpha >= 1:
            p.fillPath(_rr(rect.adjusted(-grow, -grow + dy, grow, grow + dy), radius + grow * .6),
                       color('#02030c', alpha))

def glass(p, rect, radius, draw_backdrop, *, strength=1.0, tint=None,
          active=False, lens=True, shadow=True):
    """One pane of physically-motivated glass."""
    path = _rr(rect, radius)
    if shadow:
        _soft_shadow(p, rect, radius, strength)
    p.save()
    p.setClipPath(path)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    draw_backdrop(p, rect, .94 if lens else 1.0)
    if lens:
        inner = _rr(rect.adjusted(11, 11, -11, -11), max(2.0, radius - 11))
        band = path.subtracted(inner)
        p.save()
        p.setClipPath(band, Qt.IntersectClip)
        draw_backdrop(p, rect, .72)
        p.fillPath(band, color('#ffffff', 12))
        p.restore()
    # Glass is lighter towards its rim (Fresnel) and a touch darker inside.
    cx, cy = rect.center().x(), rect.center().y()
    fresnel = QRadialGradient(QPointF(cx, cy), max(rect.width(), rect.height()) * .72)
    fresnel.setColorAt(0, color('#040a22', 150 * strength))
    fresnel.setColorAt(.62, color('#0a1640', 96 * strength))
    fresnel.setColorAt(1, color('#bcd0ff', 46 * strength))
    p.fillPath(path, fresnel)
    if tint:
        p.fillPath(path, color(tint, 30))
    shade = QLinearGradient(rect.bottomRight(),
                            QPointF(rect.right() - rect.width() * .30, rect.bottom() - rect.height() * .30))
    shade.setColorAt(0, color('#01020a', 92))
    shade.setColorAt(1, color('#01020a', 0))
    p.fillPath(path, shade)
    lit = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * .26))
    lit.setColorAt(0, color('#ffffff', 58))
    lit.setColorAt(1, color('#ffffff', 0))
    p.fillPath(path, lit)
    glare = QLinearGradient(rect.topLeft(), QPointF(rect.left() + rect.width() * .55, rect.top() + rect.height() * .95))
    glare.setColorAt(0, color('#ffffff', 40))
    glare.setColorAt(.2, color('#ffffff', 12))
    glare.setColorAt(.38, color('#ffffff', 0))
    p.fillPath(path, glare)
    p.restore()
    rim = QConicalGradient(rect.center(), 135)
    for t, a in ((0, 235), (.12, 125), (.25, 46), (.38, 112), (.5, 205),
                 (.62, 112), (.75, 46), (.88, 125), (1, 235)):
        rim.setColorAt(t, color('#ffffff', min(255, a + (30 if active else 0))))
    p.setBrush(Qt.NoBrush)
    if active:
        p.setOpacity(.5)
        p.setPen(QPen(color(theme.accent(), 190), 4.5))
        p.drawPath(path)
        p.setOpacity(1)
    # A hint of chromatic dispersion: red/blue ghosts either side of the rim.
    p.setPen(QPen(color('#7fd0ff', 54), 1.0))
    p.drawPath(path.translated(.8, .3))
    p.setPen(QPen(color('#ff8fb0', 44), 1.0))
    p.drawPath(path.translated(-.8, -.3))
    p.setPen(QPen(QBrush(rim), 1.5))
    p.drawPath(path)
    p.setPen(QPen(color('#ffffff', 24), .8))
    p.drawPath(_rr(rect.adjusted(2.2, 2.2, -2.2, -2.2), max(2.0, radius - 2.2)))
    if rect.width() > 80 and rect.height() > 40:
        edge = min(radius, rect.width() / 2) * .9
        streak = QLinearGradient(rect.left() + edge, 0, rect.right() - edge, 0)
        streak.setColorAt(0, color('#ffffff', 0))
        streak.setColorAt(.35, color('#ffffff', 170 if active else 130))
        streak.setColorAt(.65, color('#ffffff', 60))
        streak.setColorAt(1, color('#ffffff', 0))
        p.setPen(QPen(QBrush(streak), 1.8))
        p.drawLine(QPointF(rect.left() + edge, rect.top() + 1.7),
                   QPointF(rect.right() - edge, rect.top() + 1.7))

def scene_pixmap(size, mode=None, phase=0.0):
    width,height=max(1,size.width()),max(1,size.height())
    pixmap=QPixmap(width,height);pixmap.fill(QColor(PALETTE['bg']))
    painter=QPainter(pixmap)
    gradient=QLinearGradient(0,0,width,height)
    for stop,tone in ((0,'#08162f'),(.26,'#173f68'),(.50,'#4677a6'),(.74,'#4b397e'),(1,'#1d153f')):
        gradient.setColorAt(stop,QColor(tone))
    painter.fillRect(pixmap.rect(),gradient)
    for x,y,radius,tone,alpha in ((.18,.12,.72,'#72cfff',65),(.85,.72,.83,'#9c6ce8',98)):
        light=QRadialGradient(QPointF(width*x,height*y),max(width,height)*radius)
        light.setColorAt(0,color(tone,alpha));light.setColorAt(1,color(tone,0))
        painter.fillRect(pixmap.rect(),light)
    painter.end();return pixmap


def paint_panel(painter,widget,rect,*,strong=False,compact=False,active=False):
    from .glass import draw_frosted_backdrop,scene_for
    area=rect.adjusted(1,1,-1,-1)
    def backdrop(p,r,zoom):
        if scene_for(widget) is not None:draw_frosted_backdrop(p,widget,r)
        else:
            gradient=QLinearGradient(r.topLeft(),r.bottomRight())
            gradient.setColorAt(0,color('#204367'));gradient.setColorAt(1,color('#493872'))
            p.fillRect(r,gradient)
    glass(painter,area,11 if compact else 25,backdrop,
          strength=1.10 if strong else 1.0,active=active,lens=False,shadow=False)


def paint_sidebar(painter,widget,rect):
    paint_panel(painter,widget,rect.adjusted(2,2,-2,-2),strong=True)


def paint_gauge(painter,widget,value,text,ring_color):
    area=QRectF(widget.rect());side=min(area.width(),area.height())-26
    circle=QRectF(area.center().x()-side/2,area.center().y()-side/2,side,side)
    from .glass import draw_frosted_backdrop
    glass(painter,circle,side/2,lambda p,r,z:draw_frosted_backdrop(p,widget,r),lens=False,shadow=False)
    ring=circle.adjusted(8,8,-8,-8)
    painter.setBrush(Qt.NoBrush);painter.setPen(QPen(color(theme.TRACK,200),6))
    painter.drawArc(ring,225*16,-270*16)
    if value is not None:
        fill=QConicalGradient(ring.center(),90)
        for stop,tone in ((0,theme.accent()),(.4,PALETTE['light']),(.7,theme.secondary_accent()),(1,theme.accent())):fill.setColorAt(stop,color(tone))
        painter.setPen(QPen(fill,6,Qt.SolidLine,Qt.RoundCap))
        painter.drawArc(ring,225*16,round(-270*16*max(0,min(100,value))/100))
    font=QFont(widget.font());font.setPixelSize(max(20,round(side*.23)));font.setWeight(QFont.DemiBold)
    painter.setFont(font);painter.setPen(color(theme.TEXT))
    painter.drawText(circle,Qt.AlignCenter,str(text if text is not None else ('–' if value is None else f'{value:.0f}%')))


def stylesheet():
    return '''
    #primaryBtn {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #dff7ff,stop:.5 #94dfff,stop:1 #baa7ff);color:#10233d;border:1px solid #def5ff;}
    QLineEdit,QComboBox,QSpinBox,QTextEdit,QListWidget,QTableWidget {background:rgba(12,25,54,150);border:1px solid rgba(185,213,255,115);border-radius:11px;}
    #ghostBtn,#langBtn {background:rgba(18,35,65,130);border:1px solid rgba(185,213,255,125);}
    QHeaderView::section {background:rgba(15,30,59,185);border:none;padding:8px;}
    '''


def shape(rect,compact=False):return _rr(rect,11 if compact else 25)
