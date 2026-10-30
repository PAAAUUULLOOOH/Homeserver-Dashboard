"""Asynchronous datasheets and a native, scrollable manufacturer-spec dialog."""
from threading import Event
import time
from PySide6.QtCore import QObject,QRunnable,QThreadPool,Signal,Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QHBoxLayout,QScrollArea,QWidget,QSizePolicy
from .ui_locale import QLabel,QPushButton
from . import product_specs,theme,i18n,spec_language
from .i18n import tr

class _Signals(QObject):done=Signal(str,object)
class _Task(QRunnable):
    def __init__(self,product,signals,cancelled,language,source=None):
        super().__init__();self.product=dict(product);self.signals=signals;self.cancelled=cancelled
        self.language=language;self.source=source
    def run(self):
        source=self.source;localized=None
        try:
            source=source or product_specs.resolve(self.product,cancelled=self.cancelled)
            localized=spec_language.localize(source,self.language,cancelled=self.cancelled)
        except Exception:pass
        if not self.cancelled.is_set():
            self.signals.done.emit(product_specs.product_key(self.product),
                                   dict(source=source,localized=localized,language=self.language))

class SpecLoader(QObject):
    loaded=Signal(str,object)
    def __init__(self,app):
        super().__init__(app);self.pool=QThreadPool(self);self.pool.setMaxThreadCount(3)
        self.signals=_Signals(self);self.signals.done.connect(self._ready)
        self.results={};self.views={};self.pending=set();self._languages=set();self.failed_at={}
        self.cancelled=Event();app.aboutToQuit.connect(self.shutdown)
    def request(self,product):
        if self.cancelled.is_set():return
        key=product_specs.product_key(product);language=i18n.lang();pair=(key,language)
        if not key or product.get('kind') not in ('cpu','gpu','mainboard'):return
        if pair in self.failed_at and time.monotonic()-self.failed_at[pair]>=60:
            self.views.pop(pair,None);self.failed_at.pop(pair,None)
        if pair in self.views:self.loaded.emit(key,self.views[pair]);return
        if pair in self._languages:return
        source=self.results.get(key) or product_specs.SpecCache().load(product)
        if source:self.results[key]=source
        import os
        if os.environ.get('VITALUX_SPEC_OFFLINE')=='1':
            try:localized=spec_language.localize(source,language,offline=True)
            except (OSError,ValueError,TypeError,KeyError):localized=None
            self._ready(key,dict(source=source,localized=localized,language=language));return
        self.pending.add(key);self._languages.add(pair)
        self.pool.start(_Task(product,self.signals,self.cancelled,language,source))
    def _ready(self,key,result):
        # Raw source data may also be provided by startup/network diagnostics.
        if result is not None and 'localized' not in result:
            self.results[key]=result
            result=dict(source=result,localized=result,language=i18n.lang())
        result=result or dict(source=None,localized=None,language=i18n.lang())
        pair=(key,result['language']);self._languages.discard(pair)
        if not any(k==key for k,_ in self._languages):self.pending.discard(key)
        if result['source']:self.results[key]=result['source']
        self.views[pair]=result['localized']
        if result['localized'] is None:self.failed_at[pair]=time.monotonic()
        else:self.failed_at.pop(pair,None)
        if result['language']==i18n.lang():self.loaded.emit(key,result['localized'])
    def view(self,key):return self.views.get((key,i18n.lang()))
    def shutdown(self):
        self.cancelled.set();self.pool.clear()
        return self.pool.activeThreadCount()==0
    def resume(self):
        if not self.cancelled.is_set():return
        self.cancelled=Event();self.pending.clear();self._languages.clear()

def loader():
    app=QApplication.instance()
    if not hasattr(app,'_spec_loader'):app._spec_loader=SpecLoader(app)
    return app._spec_loader

KEYS={'video memory':'Videospeicher','memory size/bus':'Speichergröße / Busbreite','bus standard':'Schnittstelle','graphic engine':'Grafikchip','total cores':'Kerne','total threads':'Threads','# of cpu cores':'Kerne','# of threads':'Threads','max. boost clock':'Maximaler Boost-Takt','memory support':'Speicherunterstützung','cpu':'Prozessor','socket':'Sockel','chipset':'Chipsatz','form factor':'Formfaktor','memory type':'Speichertyp',
      'memory size':'Speichergröße','engine clock':'GPU-Takt','boost clock':'Boost-Takt','outputs':'Anschlüsse',
      'dimensions':'Abmessungen','cores':'Kerne','threads':'Threads','cache':'Cache','tdp':'TDP',
      'memory':'Speicher','graphics memory':'Videospeicher','gpu':'GPU','power consumption':'Leistungsaufnahme'}
def caption(key):return tr(KEYS.get(key.strip().casefold(),key))

def brief(data,local,kind=''):
    if not data:return list(local)
    import re
    patterns={
        'gpu':(r'video.?memory|memory.?size|memory.?type|graphics.?memory',r'engine.?clock|boost|core.?clock',r'^outputs?$|^interface$|bus.standard',r'^gpu$|graphic.engine'),
        'cpu':(r'total.cores|#.of.cpu.cores|^cores$',r'total.threads|#.of.threads|^threads$',r'max.*(?:boost|turbo)|boost.clock',r'socket|package'),
        'mainboard':(r'chipset',r'^cpu$|socket',r'^memory$|memory.support',r'form.factor',r'^lan$|^storage$')
    }.get(kind,(r'socket|chipset|memory|clock|boost|core|thread|output|interface',))
    preferred=[]
    for section in data.get('sections',[]):
        for key,value in section['rows']:
            if len(value)>180:continue
            rank=next((index for index,pattern in enumerate(patterns) if re.search(pattern,data.get('original_keys',{}).get(key,key),re.I)),None)
            if rank is not None:preferred.append((rank,caption(key),value))
    preferred.sort(key=lambda row:row[0])
    seen=set();result=[]
    for key,value in [(key,value) for _,key,value in preferred]+list(local):
        if key.casefold() in seen:continue
        seen.add(key.casefold());result.append((key,value))
        if len(result)==4:break
    return result

class SpecificationDialog(QDialog):
    def __init__(self,header):
        super().__init__(header.window());self.header=header;self.key=header.key;self.local_specs=list(header._local_specs)
        self.product=dict(header.product)
        self.setWindowTitle(tr('Alle Spezifikationen'));self.setObjectName('specificationDialog')
        self.setStyleSheet(f'QDialog#specificationDialog {{ background:{theme.BG}; color:{theme.TEXT}; }}')
        self.resize(760,650);self.setMinimumSize(400,320)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,20,24,20);layout.setSpacing(14)
        title=QLabel(header.name.text());title.setObjectName('bigName');title.setWordWrap(True);title.setAlignment(Qt.AlignCenter);layout.addWidget(title)
        self.status=QLabel();self.status.setObjectName('muted');self.status.setWordWrap(True);self.status.setAlignment(Qt.AlignCenter);layout.addWidget(self.status)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);layout.addWidget(self.scroll,1)
        actions=QHBoxLayout();self.source_button=QPushButton('Herstellerseite öffnen');self.source_button.clicked.connect(self.open_source)
        actions.addWidget(self.source_button);actions.addStretch();close=QPushButton('Schließen');close.clicked.connect(self.accept);actions.addWidget(close);layout.addLayout(actions)
        loader().loaded.connect(self._ready);self.finished.connect(lambda *_:self._disconnect())
        self.populate(header._manufacturer_specs)
    def _disconnect(self):
        try:loader().loaded.disconnect(self._ready)
        except (RuntimeError,TypeError):pass
    def _ready(self,key,result):
        if key==self.key:self.populate(result)
    def open_source(self):
        if self.source:QDesktopServices.openUrl(QUrl(self.source))
    def populate(self,data):
        original=loader().results.get(self.key) or {}
        self.source=(data or original).get('source','')
        self.source_button.setVisible(bool(self.source))
        host=QWidget();body=QVBoxLayout(host);body.setContentsMargins(8,8,8,8);body.setSpacing(14)
        groups=[]
        if self.local_specs:groups.append(dict(title='Erkannte Systemdaten',rows=self.local_specs))
        if data:groups+=data['sections']
        for group in groups:
            heading=QLabel(tr(group['title']));heading.setObjectName('strong');heading.setWordWrap(True);body.addWidget(heading)
            for key,value in group['rows']:
                name=QLabel(caption(key));name.setObjectName('muted');name.setWordWrap(True);body.addWidget(name)
                text=QLabel(str(value));text.setTextFormat(Qt.PlainText);text.setWordWrap(True);text.setTextInteractionFlags(Qt.TextSelectableByMouse)
                text.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);text.setMinimumWidth(0);body.addWidget(text)
        body.addStretch(1)
        old=self.scroll.takeWidget()
        if old:old.deleteLater()
        self.scroll.setWidget(host)
        if data:
            from datetime import datetime
            stamp=datetime.fromtimestamp(data['checked_at']).strftime('%d.%m.%Y')
            self.status.setText(tr('Herstellerangaben · {language} · Stand: {date}').format(language='Deutsch' if i18n.lang()=='de' else 'English',date=stamp))
        elif self.key in loader().pending:self.status.setText(tr('Herstellerspezifikationen werden geladen …'))
        elif original:self.status.setText(tr('Übersetzung derzeit nicht verfügbar. Erkannte Systemdaten werden angezeigt.'))
        else:self.status.setText(tr('Herstellerangaben derzeit nicht verfügbar. Erkannte Systemdaten werden angezeigt.'))
    def retranslate(self):
        self.setWindowTitle(tr('Alle Spezifikationen'))
        self.populate(loader().view(self.key))
        loader().request(self.product)
