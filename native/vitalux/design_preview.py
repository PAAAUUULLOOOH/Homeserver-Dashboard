"""Complete miniature layouts fitted inside the gallery's safe rounded area."""
from PySide6.QtCore import QRectF,QPointF,Qt
from PySide6.QtGui import QColor,QPen,QPainterPath,QFont

def paint(p,tile,pal):
    from .gallery_shape import finish
    from .design_capabilities import paint as capabilities
    p.save()
    # The icon column and rounded corners are deliberately outside the miniature.
    frame=QRectF(13,13,max(50,tile.width()-55),59)
    p.setPen(QPen(QColor(pal['border']),.7));p.setBrush(QColor(pal['bg']))
    p.drawRoundedRect(frame,7,7)
    p.save();p.setClipRect(frame.adjusted(3,3,-3,-3))
    quantum=tile.key=='quantum_core';nebula=tile.key=='nebula_prism'
    def panel(rect):
        p.setPen(QPen(QColor(pal['accent']),.55));p.setBrush(QColor(pal['card']))
        if quantum:
            path=QPainterPath(rect.topLeft()+QPointF(3,0));path.lineTo(rect.topRight());path.lineTo(rect.bottomRight()-QPointF(3,0));path.lineTo(rect.bottomLeft());path.closeSubpath();p.drawPath(path)
        else:p.drawRoundedRect(rect,2.5,2.5)
    left=frame.left()+5;right=frame.right()-5;top=frame.top()+5;bottom=frame.bottom()-5
    if not nebula:
        rail=QRectF(left,top,9,bottom-top);panel(rail)
        for index in range(5):
            p.setPen(QPen(QColor(pal['muted']),.9));p.drawLine(QPointF(left+3,top+6+index*7),QPointF(left+6,top+6+index*7))
        left+=13
    else:bottom-=8
    header=QRectF(left,top,right-left,8);panel(header)
    y=top+12;gap=3;width=(right-left-2*gap)/3
    for index in range(3):
        box=QRectF(left+index*(width+gap),y,width,16);panel(box)
        dial=QRectF(box.center().x()-4,box.center().y()-4,8,8)
        p.setPen(QPen(QColor(pal['accent'] if index!=1 else pal['secondary']),1));p.setBrush(Qt.NoBrush);p.drawArc(dial,225*16,-220*16)
    plot=QRectF(left,y+20,right-left,max(8,bottom-y-20));panel(plot)
    p.setBrush(Qt.NoBrush)
    for index,tone in enumerate((pal['accent'],pal['secondary'])):
        path=QPainterPath()
        for n,level in enumerate((.2,.5,.35,.8,.6,.9)):
            pt=QPointF(plot.left()+3+n*(plot.width()-6)/5,plot.bottom()-2-(plot.height()-4)*max(.05,level-index*.18))
            path.moveTo(pt) if n==0 else path.lineTo(pt)
        p.setPen(QPen(QColor(tone),.8));p.drawPath(path)
    if nebula:
        dock=QRectF(frame.center().x()-18,frame.bottom()-9,36,5);panel(dock)
        for index in range(6):
            p.setPen(QPen(QColor(pal['text']),1));x=dock.left()+4+index*5;p.drawPoint(QPointF(x,dock.center().y()))
    p.restore()
    p.fillRect(QRectF(0,77,tile.width(),35),QColor(pal['bg']))
    font=QFont(tile.font());font.setPixelSize(11);font.setWeight(QFont.DemiBold)
    p.setFont(font);p.setPen(QColor(pal['text']));p.drawText(QRectF(12,79,tile.width()-24,25),Qt.AlignCenter,tile.text())
    p.restore()
    capabilities(p,tile,pal,tile._hover)
    finish(p,tile,pal)
