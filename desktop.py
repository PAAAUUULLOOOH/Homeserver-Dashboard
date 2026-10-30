#!/usr/bin/env python3
"""Native test dashboard using Vitalux's original Qt design components."""
import base64
import json
import os
from pathlib import Path
import sys
import threading
import webbrowser

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'native'))
from PySide6.QtCore import Qt, QTimer, QRunnable, QThreadPool, QObject, Signal
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QScrollArea,QStackedWidget,QLabel,QPushButton,QComboBox,QDialog,QFormLayout,QLineEdit,QSpinBox,QCheckBox,QDialogButtonBox,QMessageBox,QTextEdit,QFileDialog,QInputDialog)
from vitalux import theme,settings,design_catalog
from vitalux.glass import create_ambient_scene,GlassSidebar
from vitalux.widgets import Card,NavButton,StatChip,label
from vitalux.brand import app_icon
import server
from telemetry import collect


class Signals(QObject):
    done=Signal(object)
    failed=Signal(str)


class Task(QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=Signals()
    def run(self):
        try:self.signals.done.emit(self.fn())
        except Exception as exc:self.signals.failed.emit(str(exc))


def authenticate():
    if server.AUTH.exists():
        for _ in range(3):
            password,ok=QInputDialog.getText(None,'Vitalux Homeserver · Anmeldung','Administrator-Passwort:',QLineEdit.Password)
            if not ok:return False
            if server.valid_password(password):return True
            QMessageBox.warning(None,'Anmeldung','Das Passwort stimmt nicht.')
        return False
    while True:
        password,ok=QInputDialog.getText(None,'Testkonto einrichten','Neues lokales Passwort (mindestens 12 Zeichen):',QLineEdit.Password)
        if not ok:return False
        if not 12<=len(password)<=256:
            QMessageBox.warning(None,'Passwort','Bitte 12 bis 256 Zeichen verwenden.');continue
        confirm,ok=QInputDialog.getText(None,'Testkonto einrichten','Passwort wiederholen:',QLineEdit.Password)
        if not ok:return False
        if confirm!=password:
            QMessageBox.warning(None,'Passwort','Die Passwörter stimmen nicht überein.');continue
        server.write_auth(password);return True


class Window(QMainWindow):
    def __init__(self,web_port=0):
        super().__init__();self.setWindowTitle('Vitalux Homeserver · 0.10.0 Test');self.setWindowIcon(app_icon());self.resize(1340,870);self.setMinimumSize(880,600)
        self.pool=QThreadPool(self);self.tasks=set();self.refresh_pending=False;self.route='overview';self.snapshot={};self.selected=None;self.web_port=web_port
        self.scene=create_ambient_scene();self.setCentralWidget(self.scene)
        outer=QHBoxLayout(self.scene);outer.setContentsMargins(15,15,15,15);outer.setSpacing(20)
        self.sidebar=GlassSidebar();self.sidebar.setFixedWidth(218);side=QVBoxLayout(self.sidebar);side.setContentsMargins(15,24,15,18);side.setSpacing(8)
        side.addWidget(label('Vitalux','pageTitle'));side.addWidget(label('HOMESERVER · TESTVERSION','sidebarVersion'));side.addSpacing(20)
        self.nav={}
        for key,text in [('overview','Übersicht'),('catalog','Spielekatalog'),('teamspeak','TeamSpeak 3'),('paulflix','PAULFLIX'),('events','Protokoll'),('system','Homeserver'),('design','Design & Darstellung')]:
            btn=NavButton(text);btn.icon_key={'overview':'overview','catalog':'gpu','teamspeak':'network','paulflix':'drives','events':'info','system':'system','design':'settings'}[key];btn.setCheckable(True);btn.clicked.connect(lambda checked=False,k=key:self.navigate(k));self.nav[key]=btn;side.addWidget(btn)
        side.addStretch();side.addWidget(label('Lokales Testpaket','muted'));side.addWidget(label('Eigene Daten · keine Cloud','sidebarVersion'));outer.addWidget(self.sidebar)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QScrollArea.NoFrame);outer.addWidget(self.scroll,1)
        self.page=QWidget();self.scroll.setWidget(self.page);self.layout=QVBoxLayout(self.page);self.layout.setContentsMargins(18,22,24,24);self.layout.setSpacing(20)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(6000)
        self.apply_design(settings.get('theme','aurora_bloom'));self.refresh()

    def task(self,fn,done=None,quiet=False):
        worker=Task(fn);self.tasks.add(worker)
        def finish(result):
            self.tasks.discard(worker)
            if done:done(result)
        def fail(message):
            self.tasks.discard(worker)
            if not quiet:QMessageBox.warning(self,'Vitalux Homeserver',message)
        worker.signals.done.connect(finish);worker.signals.failed.connect(fail);self.pool.start(worker)

    def refresh(self):
        if self.refresh_pending:return
        self.refresh_pending=True
        def fetch():
            try:return dict(servers=server.ENGINE.list(),docker=server.ENGINE.health(),metrics=collect(server.DATA),events=list(server.ENGINE.events),jobs=[dict(j) for j in server.ENGINE.jobs.values()])
            finally:pass
        def done(snapshot):
            self.refresh_pending=False
            changed=self.snapshot!=snapshot;self.snapshot=snapshot
            if self.route=='detail':
                if changed:self.refresh_detail()
            elif self.route!='catalog' and self.route!='design':self.draw()
        def safe_fetch():
            try:return fetch()
            except Exception as exc:return dict(servers=[],docker={'ready':False,'error':str(exc)},metrics={},events=[],jobs=[])
        self.task(safe_fetch,done,quiet=True)

    def apply_design(self,key):
        if key not in design_catalog.VISIBLE:key='aurora_bloom'
        settings.set_many(dict(theme=key,accent='design_default',background_style='theme_default',render_backend='software',lang='de',ultra_eco=False))
        theme.set_mode(key);QApplication.instance().setStyleSheet(theme.stylesheet());self.scene.sync_background();self.draw()

    def navigate(self,key):
        self.route=key
        if key=='paulflix':
            self.open_web('paulflix')
        self.draw()

    def open_web(self,route='uebersicht'):
        if self.web_port:webbrowser.open(f'http://127.0.0.1:{self.web_port}/dashboard#{route}')

    def clear(self):
        while self.layout.count():
            item=self.layout.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
            elif item.layout():self.clear_layout(item.layout())

    def clear_layout(self,lay):
        while lay.count():
            item=lay.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
            elif item.layout():self.clear_layout(item.layout())

    def heading(self,title,sub):
        self.layout.addWidget(label(title,'pageTitle'));self.layout.addWidget(label(sub,'pageSub',wrap=True))

    def btn(self,text,fn,primary=False):
        b=QPushButton(text);b.setObjectName('primaryBtn' if primary else 'ghostBtn');b.clicked.connect(fn);return b

    def grid(self,cards,columns=2):
        host=QWidget();grid=QGridLayout(host);grid.setContentsMargins(0,0,0,0);grid.setSpacing(18)
        for i,card in enumerate(cards):grid.addWidget(card,i//columns,i%columns)
        self.layout.addWidget(host)

    def draw(self):
        self.clear()
        for key,b in self.nav.items():b.setChecked(key==self.route)
        snap=self.snapshot;servers=snap.get('servers',[])
        if self.route=='catalog':
            self.heading('Dein nächstes Abenteuer.','Spiel auswählen und mit einem Klick den Installer öffnen.')
            cards=[]
            from engine import CATALOG
            for t in CATALOG:
                c=Card(t['category']);c.body.addWidget(label(t['name'],'heroTitle'));c.body.addWidget(label(f"Ab {t['ram']} GB RAM · Port {t['port']}",'muted'));row=QHBoxLayout();row.addWidget(self.btn('Installieren',lambda checked=False,t=t:self.install(t),True));row.addWidget(self.btn('Vorladen',lambda checked=False,t=t:self.enqueue(lambda:server.ENGINE.preload(t['id']))));c.body.addLayout(row);cards.append(c)
            self.grid(cards)
        elif self.route=='design':
            self.heading('Dein Vitalux. Dein Stil.','Originale Qt-Designkomponenten aus Vitalux unstable.')
            from vitalux.premium import DesignTile
            cards=[]
            for key,title in design_catalog.CHOICES:
                tile=DesignTile(key);tile.setChecked(key==theme.mode());tile.clicked.connect(lambda checked=False,k=key:self.apply_design(k));cards.append(tile)
            self.grid(cards,2)
        elif self.route=='events':
            self.heading('Dein Serverprotokoll','Installationen, Serveraktionen und Backups.')
            c=Card('Ereignisse')
            for event in snap.get('events',[])[:30]:c.body.addWidget(label(event['time']+' · '+event['text'],wrap=True))
            for job in snap.get('jobs',[]):c.body.addWidget(label(job['label']+' · '+job['status']+(' · '+job['error'] if job['error'] else ''),wrap=True))
            self.layout.addWidget(c)
        elif self.route=='system':
            self.heading('Alles im Blick.','Echte Messwerte des lokalen Hosts.')
            c=Card('Homeserver');m=snap.get('metrics',{})
            for key in ('hostname','system','cpu','ram_percent','disk_percent','uptime'):c.body.addWidget(label(f"{key}: {m.get(key,'—')}",wrap=True))
            d=snap.get('docker',{});c.body.addWidget(label('Docker: '+(d.get('version','') if d.get('ready') else d.get('error','Wird geprüft')),wrap=True));self.layout.addWidget(c)
        elif self.route=='paulflix':
            self.heading('Dein privates Heimkino.','PAULFLIX läuft lokal im Browser mit demselben Datenverzeichnis und Passwort.')
            c=Card('PAULFLIX');c.body.addWidget(label('Filme, Serien, Cover und Metadaten von deinen lokalen Medienordnern.',wrap=True));c.body.addWidget(self.btn('PAULFLIX im Browser öffnen',lambda:self.open_web('paulflix'),True));self.layout.addWidget(c)
        elif self.route=='detail':
            self.draw_detail();return
        else:
            only_ts=self.route=='teamspeak'
            self.heading('Zusammen im Gespräch.' if only_ts else 'Dein Server. Dein Zuhause.','TeamSpeak 3 · dein eigener Sprachserver' if only_ts else 'Gameserver, Sprache und Heimkino – lokal verwaltet.')
            m=snap.get('metrics',{});row=QHBoxLayout()
            for title,value in [('CPU',str(m.get('cpu','—'))+' %'),('RAM',str(m.get('ram_percent','—'))+' %'),('Speicher',str(m.get('disk_percent','—'))+' %'),('Aktive Server',str(sum(s['status']=='running' for s in servers)))]:row.addWidget(StatChip(title,value))
            self.layout.addLayout(row)
            selected=[s for s in servers if not only_ts or s['template']=='teamspeak']
            cards=[]
            from engine import TEMPLATES
            for s in selected:
                t=TEMPLATES[s['template']];c=Card(t['name']);c.body.addWidget(label(s['name'],'heroTitle'));c.body.addWidget(label(s['status']+' · '+str(s['ram'])+' GB RAM','muted'));c.body.addWidget(label('Ports: '+', '.join(str(p['host'])+'/'+p['protocol'] for p in s['ports']),'muted'));r=QHBoxLayout();r.addWidget(self.btn('Stoppen' if s['status']=='running' else 'Starten',lambda checked=False,s=s:self.action(s['id'],'stop' if s['status']=='running' else 'start')));r.addWidget(self.btn('Verwalten',lambda checked=False,s=s:self.show_detail(s['id'])));c.body.addLayout(r);cards.append(c)
            if not cards:
                c=Card('Dein Homeserver ist bereit');c.body.addWidget(label('Noch kein Server installiert. Wähle ein Spiel im Katalog aus.',wrap=True));c.body.addWidget(self.btn('TeamSpeak installieren' if only_ts else 'Spielekatalog öffnen',lambda:self.install(TEMPLATES['teamspeak']) if only_ts else self.navigate('catalog'),True));cards=[c]
            self.grid(cards)
            if not only_ts:
                c=Card('Dein privates Heimkino');c.body.addWidget(label('PAULFLIX','heroTitle'));c.body.addWidget(label('Deine Filme und Serien direkt vom Homeserver.','muted'));c.body.addWidget(self.btn('PAULFLIX öffnen',lambda:self.navigate('paulflix'),True));self.layout.addWidget(c)
        self.layout.addStretch()

    def enqueue(self,fn):
        def done(result):self.statusBar().showMessage('Auftrag gestartet. Details im Protokoll.',8000);self.refresh()
        self.task(fn,done)

    def action(self,sid,action,options=None):self.enqueue(lambda:server.ENGINE.action(sid,action,options))

    def install(self,t):
        dialog=QDialog(self);dialog.setWindowTitle(t['name']+' installieren');dialog.setMinimumWidth(460);lay=QVBoxLayout(dialog);form=QFormLayout();lay.addLayout(form)
        name=QLineEdit('Mein '+t['name']+' Server');form.addRow('Servername',name)
        ram=QSpinBox();ram.setRange(1,64);ram.setValue(t['ram']);form.addRow('RAM-Limit (GB)',ram)
        port=QSpinBox();port.setRange(1024,65533);port.setValue(t['port']);form.addRow('Spielport',port)
        variant=QComboBox();variant.addItems(t.get('variants',[]))
        if t.get('variants'):form.addRow('Servertyp',variant)
        version=QLineEdit('LATEST')
        if t['id']=='minecraft':form.addRow('Spielversion',version)
        password=QLineEdit();password.setEchoMode(QLineEdit.Password)
        if t['id'] in ('valheim','palworld','cs2','zomboid'):form.addRow('Serverpasswort',password)
        token=QLineEdit();token.setEchoMode(QLineEdit.Password)
        if t.get('requires_token'):form.addRow('Steam Gameserver Token',token)
        terms=QCheckBox('Ich akzeptiere die '+t['license']+'-Bedingungen.');terms.setToolTip('Lizenzbedingungen des jeweiligen Herstellers vor der Installation lesen.');lay.addWidget(terms)
        info=QLabel('Der erste Start kann weitere Spieldateien herunterladen.');info.setWordWrap(True);lay.addWidget(info)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Installieren & starten');buttons.button(QDialogButtonBox.Ok).setEnabled(False);terms.toggled.connect(buttons.button(QDialogButtonBox.Ok).setEnabled);buttons.rejected.connect(dialog.reject);lay.addWidget(buttons)
        def accept():
            options=dict(template=t['id'],name=name.text(),ram=ram.value(),port=port.value(),variant=variant.currentText(),version=version.text(),password=password.text(),token=token.text(),accept_license=terms.isChecked())
            try:server.ENGINE.install(options)
            except Exception as exc:QMessageBox.warning(dialog,'Installation',str(exc));return
            dialog.accept();self.navigate('overview');self.refresh()
        buttons.accepted.connect(accept);dialog.exec()

    def show_detail(self,sid):self.selected=sid;self.route='detail';self.draw();self.refresh_detail()

    def draw_detail(self):
        s=next((s for s in self.snapshot.get('servers',[]) if s['id']==self.selected),None)
        if not s:self.heading('Server nicht verfügbar.','Zur Übersicht zurückkehren.');return
        self.heading(s['name'],s['status']+' · '+s['template']);row=QHBoxLayout()
        for text,act in [('Starten','start'),('Stoppen','stop'),('Neustart','restart'),('Backup erstellen','backup')]:row.addWidget(self.btn(text,lambda checked=False,a=act:self.action(self.selected,a)))
        row.addWidget(self.btn('Backups',self.backups));row.addWidget(self.btn('Mods',self.mods));self.layout.addLayout(row)
        self.log_view=QTextEdit();self.log_view.setReadOnly(True);self.log_view.setMinimumHeight(350);self.layout.addWidget(self.log_view)
        if s['template']=='minecraft':
            row=QHBoxLayout();self.command=QLineEdit();self.command.setPlaceholderText('Minecraft-Konsolenbefehl, z. B. list');row.addWidget(self.command);row.addWidget(self.btn('Senden',self.send_command));self.layout.addLayout(row)
        self.layout.addWidget(self.btn('Alle Serverdetails im Browser',lambda:self.open_web('server-'+self.selected)))
        self.refresh_detail()

    def refresh_detail(self):
        sid=self.selected
        if not sid:return
        def done(result):
            if self.route=='detail' and self.selected==sid:self.log_view.setPlainText(result.get('text',''))
        self.task(lambda:server.ENGINE.logs(sid),done,quiet=True)

    def send_command(self):
        command=self.command.text()
        if command:self.task(lambda:server.ENGINE.action(self.selected,'command',{'command':command}),lambda result:QMessageBox.information(self,'Konsolenantwort',result.get('output','Gesendet')));self.command.clear()

    def backups(self):
        sid=self.selected
        items=server.ENGINE.backups(sid)
        if not items:QMessageBox.information(self,'Backups','Noch keine Backups. Server stoppen und „Backup erstellen“ wählen.');return
        name,ok=QInputDialog.getItem(self,'Backup wiederherstellen','Backup auswählen:',[i['name'] for i in items],0,False)
        if ok and QMessageBox.question(self,'Wiederherstellen','Aktuelle Serverdateien ersetzen? Ein Sicherheitsbackup wird vorher erstellt.')==QMessageBox.Yes:self.action(sid,'restore',dict(backup=name))

    def mods(self):
        sid=self.selected
        self.task(lambda:server.ENGINE.mods(sid),lambda result:self.mods_dialog(sid,result))

    def mods_dialog(self,sid,result):
        if not result.get('supported'):QMessageBox.information(self,'Mods','Integrierte Mods benötigen Minecraft Paper, Fabric oder Forge.');return
        dialog=QDialog(self);dialog.setWindowTitle('Mods & Plugins · '+result['folder']);dialog.setMinimumWidth(500);lay=QVBoxLayout(dialog);lay.addWidget(label('Server vor Änderungen stoppen. Vor jeder Änderung entsteht ein Backup.',wrap=True))
        for item in result['items']:
            name=item['name'];lay.addWidget(self.btn(('Deaktivieren: ' if item['enabled'] else 'Aktivieren: ')+name,lambda checked=False,n=name:self.task(lambda:server.ENGINE.change_mod(sid,dict(action='toggle',name=n)),lambda r:dialog.accept())))
        def upload():
            name,_=QFileDialog.getOpenFileName(self,'JAR auswählen','','Minecraft JAR (*.jar)')
            if not name:return
            p=Path(name)
            if p.stat().st_size>20*1024*1024:QMessageBox.warning(self,'Mods','Maximal 20 MB.');return
            self.task(lambda:server.ENGINE.change_mod(sid,dict(action='upload',name=p.name,data=base64.b64encode(p.read_bytes()).decode())),lambda r:dialog.accept())
        lay.addWidget(self.btn('JAR hochladen',upload,True));dialog.exec()

    def closeEvent(self,event):
        self.timer.stop()
        # Wait only for short read jobs. Docker installation jobs persist until safely finished.
        event.accept()


def main():
    app=QApplication(sys.argv);app.setApplicationName('Vitalux Homeserver Test')
    if not authenticate():return 0
    # Both frontends use the same in-process backend, registry and lock.
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    threading.Thread(target=server.periodic_scan,daemon=True).start()
    window=Window(http.server_port);window.show();result=app.exec()
    server.STOP.set();http.shutdown();http.server_close()
    return result


if __name__=='__main__':sys.exit(main())
