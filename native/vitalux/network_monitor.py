"""Process traffic aggregation, session budgets and optional helper transport."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import threading

from PySide6.QtCore import QObject,QProcess,QThread,Signal
from .network_kernel import socket_snapshot

HELPER=Path('/usr/local/libexec/vitalux-network-helper')
SOURCE=Path(__file__).with_name('network_kernel.py')


class TrafficLedger:
    def __init__(self):
        self.backend=None
        self.reset()

    def reset(self):
        self.previous={}
        self.apps={}
        self.stamp=None
        self.warned=set()
        self.errors=[]
        self.connections=[]
        self.rules=set()
        self.connection_rules=set()
        self.limits={}

    def ingest(self,sample,limits=None):
        backend=sample.get('backend','tcp')
        changed=self.backend is not None and backend!=self.backend
        if changed:self.reset()
        self.backend=backend
        now=float(sample['monotonic'])
        elapsed=now-self.stamp if self.stamp is not None else None
        if elapsed is not None and elapsed<=0:return []
        rows=sample.get('connections',[])
        self.connections=rows
        self.rules=set(sample.get('rules',[]))
        self.connection_rules=set(sample.get('connection_rules',[]))
        self.errors=sample.get('errors',[])
        for app in self.apps.values():
            app.update(down_delta=0,up_delta=0,pids={},connections=0,measured=False,partial=False)
        def get(row):
            key=row.get('key') or '@unassigned'
            app=self.apps.setdefault(key,dict(key=key,name=row.get('name',''),exe=row.get('exe',''),
                total_down=0,total_up=0,down_delta=0,up_delta=0,pids={},connections=0,
                measured=False,partial=False))
            if row.get('pid') is not None:app['pids'][row['pid']]=row.get('start')
            return app
        for row in sample.get('applications',{}).values():
            if row.get('exe'):get(row)
        for row in rows:
            app=get(row)
            app['connections']+=1
            if row.get('rx') is None and backend!='bpf':app['partial']=True
        counters=sample.get('counters',[]) if backend=='bpf' else rows
        for row in counters:
            app=get(row)
            rx,tx=row.get('rx'),row.get('tx')
            if rx is None or tx is None:continue
            if type(rx) is not int or type(tx) is not int or rx<0 or tx<0:continue
            app['measured']=True
            cookie=int(row['cookie'])
            old=self.previous.get(cookie)
            if old and old[2]==app['key']:
                down,up=max(0,rx-old[0]),max(0,tx-old[1])
            elif self.stamp is not None and old is None:
                down,up=rx,tx
            else:down=up=0
            app['total_down']+=down
            app['total_up']+=up
            app['down_delta']+=down
            app['up_delta']+=up
            self.previous[cookie]=(rx,tx,app['key'],now)
        if len(self.previous)>32768:
            keep=sorted(self.previous,key=lambda key:self.previous[key][3],reverse=True)[:16384]
            self.previous={key:self.previous[key] for key in keep}
        # Bound retained process history. Never let a long session grow without limit.
        if len(self.apps)>4096:
            keep=sorted(self.apps,key=lambda key:(bool(self.apps[key]['connections']),
                self.apps[key]['total_down']+self.apps[key]['total_up']),reverse=True)[:2048]
            self.apps={key:self.apps[key] for key in keep}
        notifications=[]
        current_limits=limits or {}
        for key,limit in current_limits.items():
            if self.limits.get(key)!=limit:self.warned.discard(key)
        self.limits=dict(current_limits)
        for key,app in self.apps.items():
            measured=app['measured'] and elapsed is not None
            app['down']=app['down_delta']/elapsed if measured else None
            app['up']=app['up_delta']/elapsed if measured else None
            app['blocked']=key in self.rules
            limit=current_limits.get(key)
            total=app['total_down']+app['total_up']
            if type(limit) is int and limit>0 and total>=limit and key not in self.warned:
                self.warned.add(key)
                notifications.append((key,total,limit))
        self.stamp=now
        return notifications


class NetworkSampler(QThread):
    sampled=Signal(object)
    failed=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self._stop=threading.Event()
        self.paused=False

    def stop(self):
        self.requestInterruption()
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            if not self.paused:
                try:self.sampled.emit(socket_snapshot())
                except Exception as exc:self.failed.emit(str(exc)[:500])
            self._stop.wait(1)


def installed_helper():
    try:
        if HELPER.is_symlink() or HELPER.resolve()!=HELPER:return False
        info=HELPER.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:return False
        for folder in (HELPER.parent,HELPER.parent.parent):
            mode=folder.stat()
            if mode.st_uid!=0 or mode.st_mode&0o022 or folder.is_symlink():return False
        return hashlib.sha256(HELPER.read_bytes()).digest()==hashlib.sha256(SOURCE.read_bytes()).digest()
    except OSError:return False


class HelperClient(QObject):
    sample=Signal(object)
    state=Signal(str)
    error=Signal(str)
    rules=Signal(object)
    connection_rules=Signal(object)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.process=QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.buffer=b''
        self.active=False
        self.installing=False
        self.stopping=False
        self.last_error=''

    def start(self):
        if self.process.state()!=QProcess.NotRunning:return
        self.stopping=False
        self.last_error=''
        pkexec=shutil.which('pkexec')
        if not pkexec:
            self.error.emit('Polkit / pkexec ist nicht verfügbar.')
            return
        if not Path('/usr/bin/python3').is_file():
            self.error.emit('Der Netzwerk-Helfer benötigt /usr/bin/python3. Die normale App benötigt kein System-Python.')
            return
        self.buffer=b''
        if not installed_helper():
            for folder in (HELPER.parent.parent,HELPER.parent):
                if folder.exists():
                    info=folder.stat()
                    if folder.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:
                        self.error.emit('Das Installationsverzeichnis des Netzwerk-Helfers ist nicht geschützt.')
                        return
            if HELPER.is_symlink():
                self.error.emit('Der Netzwerk-Helfer darf kein symbolischer Link sein.')
                return
            executable=next((path for path in ('/usr/bin/install','/bin/install') if Path(path).is_file()),None)
            if not executable:
                self.error.emit('Das Linux-Werkzeug install ist nicht verfügbar.')
                return
            self.installing=True
            self.state.emit('installing')
            self.process.start(pkexec,[executable,'-D','-o','root','-g','root','-m','0755',str(SOURCE.resolve()),str(HELPER)])
        else:
            self.installing=False
            self.state.emit('authenticating')
            self.process.start(pkexec,[str(HELPER),'--session'])

    def _process_error(self,error):
        if error==QProcess.FailedToStart:
            self.active=False
            self.error.emit(self.process.errorString())
            self.state.emit('stopped')

    def _read(self):
        self.buffer+=bytes(self.process.readAllStandardOutput())
        if len(self.buffer)>16*1024*1024:
            self.error.emit('Die Antwort des Netzwerk-Helfers überschreitet das Größenlimit.')
            self.stop()
            self.buffer=b''
            return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:
                message=json.loads(line)
                kind=message['type']
                if kind=='ready' and message.get('uid')==os.getuid():
                    self.active=True
                    self.state.emit('ready')
                elif kind=='sample' and self.active:self.sample.emit(message['data'])
                elif kind=='rules' and self.active:
                    self.rules.emit(message['rules'])
                    self.connection_rules.emit(message.get('connection_rules',[]))
                elif kind in ('error','command_error'):
                    self.last_error=message.get('error','')
                    self.error.emit(self.last_error)
            except (ValueError,KeyError,TypeError):
                self.error.emit('Ungültige Antwort des Netzwerk-Helfers.')
                self.stop()

    def _finished(self,code,status):
        if self.installing:
            self.installing=False
            if code==0 and installed_helper() and not self.stopping:
                self.start()
                return
            if not self.stopping:self.error.emit('Die Einrichtung des Netzwerk-Helfers wurde nicht abgeschlossen.')
        elif code and not self.stopping and not self.last_error:
            self.error.emit('Die Netzwerk-Freigabe wurde abgebrochen oder ist fehlgeschlagen.')
        self.active=False
        self.buffer=b''
        self.state.emit('stopped')

    def command(self,op,**values):
        if self.active:self.process.write((json.dumps(dict(op=op,**values))+'\n').encode())

    def stop(self):
        self.stopping=True
        if self.active:self.command('quit')
        # EOF also cleans up if authentication or startup is still in progress.
        if self.process.state()!=QProcess.NotRunning:
            self.process.closeWriteChannel()
            if not self.active:self.process.terminate()

    def is_stopped(self):return self.process.state()==QProcess.NotRunning
