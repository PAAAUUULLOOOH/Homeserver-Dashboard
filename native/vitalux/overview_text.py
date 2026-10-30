"""Bounded overview captions with a full-name hover exception."""
from PySide6.QtCore import Qt, QEvent, QSize
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QSizePolicy, QToolTip
from .i18n import tr

class ElidedLabel(QLabel):
    def __init__(self,text='',parent=None):
        super().__init__('',parent)
        self.original_text=''
        self.setObjectName('muted')
        self.setAlignment(Qt.AlignCenter)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.set_caption(text)

    def setText(self,text):
        self.set_caption(text)

    def set_caption(self,text):
        self.original_text=tr(str(text))
        self.setAccessibleName(self.original_text)
        self._elide()

    def _elide(self):
        if not hasattr(self,'original_text'):return
        metrics=QFontMetrics(self.font())
        full=' · '.join(self.original_text.splitlines())
        shown=metrics.elidedText(full,Qt.ElideRight,max(1,self.contentsRect().width()))
        QLabel.setText(self,shown)
        truncated=shown!=full
        self.setProperty('vitaluxFullNameHint',truncated)
        self.setToolTip(self.original_text if truncated else '')
        self.setFixedHeight(max(18,metrics.height()+2))

    def resizeEvent(self,event):
        super().resizeEvent(event);self._elide()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange,QEvent.StyleChange):self._elide()

    def event(self,event):
        if event.type()==QEvent.ToolTip and self.property('vitaluxFullNameHint'):
            QToolTip.showText(event.globalPos(),self.original_text,self)
            event.accept();return True
        return super().event(event)

    def sizeHint(self):return QSize(0,max(18,self.fontMetrics().height()+2))

class OverviewInfo(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.row=QVBoxLayout(self);self.row.setContentsMargins(0,0,0,0);self.row.setSpacing(4);self.row.setAlignment(Qt.AlignTop)
        self.name=ElidedLabel();self.detail=ElidedLabel();self.power=ElidedLabel()
        for item in (self.name,self.detail,self.power):self.row.addWidget(item);item.hide()
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)

    def set(self,name='',detail='',power=''):
        for widget,text in ((self.name,name),(self.detail,detail),(self.power,power)):
            widget.set_caption(text);widget.setVisible(bool(text))


class OverviewValue(QWidget):
    def __init__(self,title):
        super().__init__()
        row=QVBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(2)
        self.name=ElidedLabel(title);self.v=ElidedLabel('–');self.v.setObjectName('strong')
        row.addWidget(self.name);row.addWidget(self.v)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
    def set(self,text):self.v.set_caption(text)

class OverviewMeter(QWidget):
    def __init__(self,title):
        super().__init__()
        from .widgets import Bar
        row=QVBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(4)
        self.name=ElidedLabel(title);self.value=ElidedLabel();self.bar=Bar()
        for item in (self.name,self.value,self.bar):row.addWidget(item)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
    def set(self,pct,text=None):
        self.bar.set_value(pct);self.value.set_caption(text or ('–' if pct is None else f'{pct:.0f}%'))
