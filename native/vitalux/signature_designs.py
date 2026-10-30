"""Authored glass materials and live instruments for the signature designs.

All geometry is native, resolution independent and shared by every renderer.
Atmospheres are cached; the live instruments only repaint on a sensor sample.
"""
import math
from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation, QEasingCurve
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidget
from . import nebula_prism, quantum_core, crystal_atrium, aurora_bloom

COLLECTIONS = {
    'eclipse_crystal': dict(title='Eclipse Crystal', subtitle='BLACK CRYSTAL / CHAMPAGNE',
        bg='#08090b', sidebar='#101113', card='#151617', border='#89785e',
        track='#302d27', grid='#35312c', text='#fff3df', muted='#c3b8a7',
        accent='#efc68d', secondary='#f4a86e', light='#9e7548', bloom='#4d3728',
        shadow='#101012', series=('#efc68d', '#f4a86e', '#e1d9cb', '#a8a6a2')),
}
COLLECTIONS['nebula_prism'] = nebula_prism.PALETTE
COLLECTIONS['quantum_core'] = quantum_core.PALETTE
COLLECTIONS['crystal_atrium'] = crystal_atrium.PALETTE
COLLECTIONS['aurora_bloom'] = aurora_bloom.PALETTE
KEYS = tuple(COLLECTIONS)


def active():
    from . import theme
    return theme.mode() in KEYS



def color(value, alpha=255):
    c = QColor(value)
    c.setAlpha(max(0, min(255, round(alpha))))
    return c



def shape(rect, mode, compact=False):
    if mode == aurora_bloom.KEY:return aurora_bloom.shape(rect,compact)
    if mode == crystal_atrium.KEY:return crystal_atrium.shape(rect,compact)
    if mode == 'nebula_prism':
        return nebula_prism.shape(rect, compact)
    if mode == 'quantum_core':
        return quantum_core.shape(rect, compact)
    path = QPainterPath()
    if mode != 'eclipse_crystal':
        radius = 11 if compact else 22
        path.addRoundedRect(rect, radius, radius)
        return path
    cut = min(15 if not compact else 7, rect.width()/6, rect.height()/4)
    x, y, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()
    path.moveTo(x+cut, y)
    for px, py in ((r-cut,y),(r,y+cut),(r,b-cut),(r-cut,b),(x+cut,b),(x,b-cut),(x,y+cut)):
        path.lineTo(px, py)
    path.closeSubpath()
    return path



def scene_pixmap(size, mode, phase=0.0):
    if mode == aurora_bloom.KEY:return aurora_bloom.scene_pixmap(size)
    if mode == crystal_atrium.KEY:return crystal_atrium.scene_pixmap(size,phase)
    if mode == 'nebula_prism':
        return nebula_prism.scene_pixmap(size)
    if mode == 'quantum_core':
        return quantum_core.scene_pixmap(size)
    pal = COLLECTIONS[mode]
    w, h = max(1, size.width()), max(1, size.height())
    pixmap = QPixmap(w, h)
    pixmap.fill(color(pal['bg']))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0, 0, w, h)
    base = QLinearGradient(0, 0, w, h)
    for t, c in ((0,pal['shadow']),(.45,pal['bg']),(1,pal['sidebar'])):
        base.setColorAt(t, color(c))
    p.fillRect(rect, base)
    center = QPointF(w*.60, h*.13)
    radius = w*.33
    glow = QRadialGradient(center, radius*1.12)
    for t, tone, a in ((0,pal['light'],0),(.86,pal['light'],0),(.91,pal['accent'],48),
                       (.94,pal['secondary'],110),(.97,pal['light'],25),(1,pal['light'],0)):
        glow.setColorAt(t, color(tone,a))
    p.fillRect(rect, glow)
    lens = QRadialGradient(center-QPointF(radius*.5,radius*.5), radius*1.7)
    lens.setColorAt(0,color('#28231d'))
    lens.setColorAt(.5,color('#111113'))
    lens.setColorAt(1,color('#070809'))
    p.setBrush(lens)
    p.setPen(QPen(color(pal['accent'],100),.9))
    p.drawEllipse(center,radius*.91,radius*.91)
    # Authored facets are stable, without random noise or an animation loop.
    for i in range(14):
        x = w*((i*37 % 101)/100)
        y = h*((i*29 % 89)/100)
        facet = QPainterPath(QPointF(x,y))
        facet.lineTo(x+w*.18,y+h*.13)
        facet.lineTo(x+w*.05,y+h*.24)
        facet.closeSubpath()
        g = QLinearGradient(x,y,x+w*.17,y+h*.2)
        g.setColorAt(0,color(pal['accent'],12 if i%3 == 0 else 4))
        g.setColorAt(1,color(pal['accent'],0))
        p.fillPath(facet,g)
        p.setPen(QPen(color(pal['accent'],8),.5))
        p.drawPath(facet)
    shade = QLinearGradient(0,0,0,h)
    shade.setColorAt(0,QColor(0,0,0,0))
    shade.setColorAt(1,QColor(0,0,0,90))
    p.fillRect(rect,shade)
    p.end()
    return pixmap


def paint_panel(p, widget, rect, *, strong=False, compact=False, active=False):
    from . import theme
    if theme.mode() == aurora_bloom.KEY:return aurora_bloom.paint_panel(p,widget,rect,strong=strong,compact=compact,active=active)
    if theme.mode() == crystal_atrium.KEY:return crystal_atrium.paint_panel(p,widget,rect,strong=strong,compact=compact,active=active)
    from . import theme
    from .glass import draw_frosted_backdrop
    mode = theme.mode()
    if mode == 'nebula_prism':
        return nebula_prism.paint_panel(p,widget,rect,strong=strong,compact=compact,active=active)
    if mode == 'quantum_core':
        return quantum_core.paint_panel(p,widget,rect,strong=strong,compact=compact,active=active)
    pal = palette(mode)
    path = shape(rect,mode,compact)
    p.save()
    p.setClipPath(path)
    p.fillPath(path,color(pal['card']))
    draw_frosted_backdrop(p,widget,rect,.62)
    wash = QLinearGradient(rect.topLeft(),rect.bottomRight())
    wash.setColorAt(0,color(pal['card'],217))
    wash.setColorAt(.4,color(pal['bg'],208))
    wash.setColorAt(1,color(pal['card'],225))
    p.fillPath(path,wash)
    light = QLinearGradient(rect.topLeft(),rect.bottomLeft())
    light.setColorAt(0,color(pal['text'],12))
    light.setColorAt(.13,color(pal['text'],3))
    light.setColorAt(1,color(pal['text'],0))
    p.fillPath(path,light)
    if not compact and rect.height()>110:
        if mode=='eclipse_crystal':
            # Light catches separate planes at the edges, never over data.
            for side in (0,1):
                x = rect.left() if not side else rect.right()-15
                facet = QPainterPath(QPointF(x,rect.top()+14))
                facet.lineTo(x+15,rect.top()+2)
                facet.lineTo(x+10,rect.top()+rect.height()*.35)
                facet.lineTo(x+15,rect.bottom()-13)
                facet.lineTo(x,rect.bottom()-5)
                facet.closeSubpath()
                reflection=QLinearGradient(x,rect.top(),x+15,rect.bottom())
                for t,a in ((0,115),(.25,12),(.42,77),(.60,4),(.86,60),(1,120)):
                    reflection.setColorAt(t,color(pal['accent'],a))
                p.fillPath(facet,reflection)
                for i in range(5):
                    top=rect.top()+14+i*(rect.height()-28)/5
                    height=(rect.height()-28)/5
                    triangle=QPainterPath(QPointF(x,top))
                    triangle.lineTo(x+15,top+height*.30)
                    triangle.lineTo(x+(3 if i%2 else 11),top+height)
                    triangle.closeSubpath()
                    g=QLinearGradient(x,top,x+15,top+height)
                    g.setColorAt(0,color(pal['text'],140 if i in (0,4) else 54))
                    g.setColorAt(.35,color(pal['accent'],15))
                    g.setColorAt(.68,color(pal['text'],75))
                    g.setColorAt(1,color(pal['bg'],0))
                    p.fillPath(triangle,g)
                    p.setPen(QPen(color(pal['text'],45),.6))
                    p.drawPath(triangle)
        else:
            curve=QPainterPath(QPointF(rect.left()+rect.width()*.20,rect.top()-8))
            curve.cubicTo(rect.left()-25,rect.top()+20,rect.left()-30,rect.bottom()-30,rect.left()+30,rect.bottom()+20)
            g=QLinearGradient(rect.topLeft(),rect.bottomLeft())
            g.setColorAt(0,color(pal['secondary'],135 if strong else 60))
            g.setColorAt(.40,color(pal['accent'],20))
            g.setColorAt(1,color(pal['accent'],90 if strong else 28))
            p.setPen(QPen(g,1.2))
            p.drawPath(curve)
    p.restore()
    edge=QLinearGradient(rect.topLeft(),rect.bottomRight())
    for t,tone,a in ((0,pal['text'],180),(.17,pal['accent'],160),(.4,pal['border'],60),
                      (.67,pal['border'],100),(.84,pal['secondary'],120),(1,pal['text'],180)):
        edge.setColorAt(t,color(tone,min(255,a+45) if active else a))
    p.setBrush(Qt.NoBrush)
    if active:
        p.setPen(QPen(color(pal['accent'],24),5))
        p.drawPath(path)
    p.setPen(QPen(edge,1.1 if active else .85))
    p.drawPath(path)
    p.setPen(QPen(color(pal['text'],16),.7))
    p.drawPath(shape(rect.adjusted(2,2,-2,-2),mode,compact))



def stylesheet(mode):
    if mode == aurora_bloom.KEY:return aurora_bloom.stylesheet()
    if mode == crystal_atrium.KEY:return crystal_atrium.stylesheet()
    if mode=='nebula_prism':
        return nebula_prism.stylesheet()
    if mode=='quantum_core':
        return quantum_core.stylesheet()
    pal=palette(mode)
    radius=3
    return f'''
    #heroTitle {{font-size:20px;font-weight:650;color:{pal['text']};}}
    #pageTitle {{font-size:30px;font-weight:750;}}
    #cardTitle {{font-size:10px;font-weight:700;letter-spacing:1.3px;color:{pal['text']};}}
    #chipValue {{font-size:11px;font-weight:650;color:{pal['text']};}}
    #chipTitle {{font-size:9px;color:{pal['muted']};}}
    QLineEdit,QComboBox,QSpinBox,QTextEdit,QListWidget,QTableWidget {{
        background:{pal['sidebar']};color:{pal['text']};border:1px solid {pal['border']};border-radius:{radius}px;}}
    QHeaderView::section {{background:{pal['sidebar']};color:{pal['muted']};border:none;padding:8px;}}
    QTableWidget::item {{padding:6px;border-bottom:1px solid {pal['grid']};}}
    QTableWidget::item:selected {{background:{pal['track']};color:{pal['text']};}}
    QComboBox::drop-down {{border-radius:{radius}px;background:{pal['card']};}}
    QPushButton#ghostBtn,QPushButton#langBtn,QToolButton#layoutAction {{
        border:1px solid {pal['border']};border-radius:{radius}px;background:{pal['sidebar']};color:{pal['text']};}}
    QPushButton#ghostBtn:hover,QPushButton#langBtn:hover,QToolButton#layoutAction:hover {{
        border-color:{pal['accent']};background:{pal['track']};}}
    QPushButton#primaryBtn,QPushButton#langBtn:checked {{
        background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {pal['text']},stop:.45 {pal['accent']},stop:1 {pal['border']});
        border-radius:{radius}px;border:1px solid {pal['accent']};color:{pal['bg']};}}
    QProgressBar,QProgressBar::chunk {{border-radius:{radius}px;}}
    QScrollBar::handle:vertical {{background:{pal['border']};border-radius:3px;}}
    '''



def paint_navigation(button):
    from . import theme
    from .nav_icons import paint_icon
    if theme.mode()==aurora_bloom.KEY:
        return aurora_bloom.paint_navigation(button)
    if theme.mode()=='nebula_prism':
        return nebula_prism.paint_navigation(button)
    p=QPainter(button)
    p.setRenderHint(QPainter.Antialiasing)
    rect=QRectF(button.rect()).adjusted(3,3,-3,-3)
    selected=button.isChecked()
    pal=palette(theme.mode())
    if selected:
        paint_panel(p,button,rect,compact=True,active=True)
        if theme.mode()=='eclipse_crystal':
            face=QLinearGradient(rect.topLeft(),rect.bottomRight())
            face.setColorAt(0,color(pal['text']))
            face.setColorAt(.5,color(pal['accent']))
            face.setColorAt(1,color(pal['border']))
            p.fillPath(shape(rect,theme.mode(),True),face)
    elif button._hover_amount>.01 or button.hasFocus():
        p.fillPath(shape(rect,theme.mode(),True),color(pal['accent'],20))
    button.paint_update_background(p, rect, shape(rect, theme.mode(), True))
    ink=color(pal['bg'] if selected and theme.mode()=='eclipse_crystal' else pal['text'])
    compact=button._compact
    x=rect.center().x()-10 if compact else rect.left()+12
    paint_icon(p,button.icon_key,QRectF(x,rect.center().y()-10,20,20),ink)
    if not compact:
        font=QFont(button.font())
        font.setPixelSize(13)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        p.setFont(font)
        p.setPen(ink)
        caption=button.text().split('    ',1)[-1]
        text_rect=QRectF(rect.left()+40,rect.top(),rect.width()-57,rect.height())
        if button._update_version:
            text_rect.adjust(0,1,0,-17)
        p.drawText(text_rect,
                   Qt.AlignLeft|Qt.AlignVCenter,
                   p.fontMetrics().elidedText(caption,Qt.ElideRight,max(1,round(text_rect.width()))))
        if button._update_version:
            font.setPixelSize(10);font.setWeight(QFont.DemiBold);p.setFont(font)
            p.drawText(QRectF(text_rect.left(),rect.bottom()-18,text_rect.width(),15),
                       Qt.AlignLeft|Qt.AlignVCenter,p.fontMetrics().elidedText(button._update_version,Qt.ElideRight,round(text_rect.width())))
    button.paint_notice_and_focus(p, rect, shape(rect.adjusted(1,1,-1,-1),theme.mode(),True))
    p.end()



def paint_toggle(p,rect,checked,progress):
    from . import theme
    pal=palette(theme.mode())
    p.setPen(QPen(color(pal['accent'] if checked else pal['border']),.8))
    p.setBrush(color(pal['track']))
    p.drawPath(shape(rect,theme.mode(),True))
    thumb=QRectF(rect.left()+3+progress*(rect.width()-rect.height()),rect.top()+3,rect.height()-6,rect.height()-6)
    fill=QLinearGradient(thumb.topLeft(),thumb.bottomRight())
    fill.setColorAt(0,color(pal['text'] if checked else pal['muted']))
    fill.setColorAt(1,color(pal['accent'] if checked else pal['border']))
    p.setBrush(fill)
    p.drawPath(shape(thumb,theme.mode(),True))



class Surface(QWidget):
    def paintEvent(self,event):
        frame=getattr(self,'_window_frame',None)
        if frame is not None:
            p=QPainter(self);frame.materials.paint_header(p,self);p.end();return
        if not active():
            return
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_panel(p,self,QRectF(self.rect()).adjusted(1,1,-1,-1),compact=True)
        p.end()

    def mousePressEvent(self,event):
        frame=getattr(self,'_window_frame',None)
        if frame is not None:return frame.titlebar.mousePressEvent(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        frame=getattr(self,'_window_frame',None)
        if frame is not None:return frame.titlebar.mouseMoveEvent(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        frame=getattr(self,'_window_frame',None)
        if frame is not None:return frame.titlebar.mouseReleaseEvent(event)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self,event):
        frame=getattr(self,'_window_frame',None)
        if frame is not None:return frame.titlebar.mouseDoubleClickEvent(event)
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self,event):
        frame=getattr(self,'_window_frame',None)
        if frame is not None:return frame.titlebar.wheelEvent(event)
        super().wheelEvent(event)

    def contextMenuEvent(self,event):
        frame=getattr(self,'_window_frame',None)
        if frame is not None:
            frame.show_menu(event.globalPos());event.accept()
        else:
            super().contextMenuEvent(event)












class Metric(QWidget):
    """New instruments use real values and preserve unavailable data explicitly."""
    def __init__(self,title,kind,parent=None):
        super().__init__(parent)
        self.title,self.kind=title,kind
        self.value=None
        self.detail=''
        self.extra=''
        self.history=[]
        self._display_value=None
        self._value_animation=QVariantAnimation(self)
        self._value_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._value_animation.valueChanged.connect(self._value_frame)
        self.setMinimumWidth(110)
        self.setFixedHeight(180)

    def _value_frame(self,value):
        self._display_value=float(value)
        self.update()

    def hideEvent(self,event):
        self._value_animation.stop()
        self._display_value=self.value
        super().hideEvent(event)

    def set(self,value,detail='',*,extra='',history=()):
        from . import motion
        old=self._display_value
        self.value=value
        self._value_animation.stop()
        if value is not None and old is not None and self.isVisible() and motion.duration(210) and abs(value-old)>.05:
            self._value_animation.setDuration(motion.duration(210))
            self._value_animation.setStartValue(old)
            self._value_animation.setEndValue(float(value))
            self._value_animation.start()
        else:self._display_value=value
        self.detail=detail
        self.extra=extra
        self.history=list(history)[-120:]
        self.setAccessibleName(self.title)
        self.setAccessibleDescription(f'{value if value is not None else "–"} · {detail} · {extra}')
        self.setToolTip(f'{extra}\n{detail}'.strip())
        self.update()

    def drawing_rect(self):
        return self.rect()

    def paintEvent(self,event):
        from . import theme,premium
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        pal=palette(theme.mode())
        side=min(156.0,self.width()-12.0)
        box=QRectF((self.width()-side)/2,3,side,side)
        shown='–' if self._display_value is None else (
            f'{self._display_value:.0f}' if self.kind=='health' else f'{self._display_value:.0f}%')
        if theme.mode()==aurora_bloom.KEY:
            value=self._display_value
            level=theme.level_color(value) if value is not None and self.kind!='health' else None
            aurora_bloom._ring(p,box,value,level_tone=level)
            aurora_bloom.paint_center(p,box,shown.rstrip('%'),'' if self.kind=='health' or value is None else '%',
                                      self.font(),color(pal['text']),color(pal['muted']))
        elif theme.mode() in ('nebula_prism','quantum_core'):
            renderer=nebula_prism if theme.mode()=='nebula_prism' else quantum_core
            renderer._ring(p,box,self._display_value)
            font=QFont(self.font());font.setPixelSize(round(side*.23));font.setWeight(QFont.DemiBold)
            p.setFont(font);p.setPen(color(pal['text']));p.drawText(box,Qt.AlignCenter,shown)
        else:
            # Faceted crystal uses the same centered instrument diameter.
            centre=box.center();ring=box.adjusted(9,9,-9,-9)
            p.setPen(QPen(color(pal['track']),3));p.setBrush(Qt.NoBrush)
            p.drawArc(ring,225*16,-270*16)
            if self._display_value is not None:
                p.setPen(QPen(color(pal['accent']),3.5,Qt.SolidLine,Qt.RoundCap))
                p.drawArc(ring,225*16,round(-270*16*max(0,min(100,self._display_value))/100))
            font=QFont(self.font());font.setPixelSize(round(side*.23));font.setWeight(QFont.DemiBold)
            p.setFont(font);p.setPen(color(pal['text']));p.drawText(box,Qt.AlignCenter,shown)
        if self.kind in ('cpu','gpu'):
            self._graph(p,QRectF((self.width()-side)/2,164,side,13),pal)
        p.end()

    def _graph(self,p,rect,pal):
        from . import theme
        if theme.mode()==aurora_bloom.KEY:
            return aurora_bloom.paint_sparkline(p,rect,self.history)
        if rect.width()<5 or rect.height()<5:
            return
        for i in range(3):
            y=rect.top()+rect.height()*i/2
            p.setPen(QPen(color(pal['grid'],130),.6,Qt.DotLine))
            p.drawLine(QPointF(rect.left(),y),QPointF(rect.right(),y))
        runs=[]
        run=[]
        n=len(self.history)
        for i,value in enumerate(self.history):
            if value is None or not math.isfinite(float(value)):
                if run:runs.append(run)
                run=[]
                continue
            run.append(QPointF(rect.right()-(n-1-i)*rect.width()/max(59,n-1),
                              rect.bottom()-max(0,min(100,value))*rect.height()/100))
        if run:runs.append(run)
        for points in runs:
            path=QPainterPath(points[0])
            for point in points[1:]:path.lineTo(point)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color(pal['accent'],35),4.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            p.drawPath(path)
            p.setPen(QPen(color(pal['accent']),1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            p.drawPath(path)
            if len(points)==1:
                p.setBrush(color(pal['accent']))
                p.drawEllipse(points[0],2,2)



def palette(mode):
    from . import theme
    return theme.palette_for(mode)

