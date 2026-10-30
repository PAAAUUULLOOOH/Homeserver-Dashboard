"""Allowlisted Docker management for a single, authenticated homeserver admin."""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock


CATALOG = [
    dict(id='minecraft', name='Minecraft Java', category='Aufbau', image='itzg/minecraft-server:java21', port=25565, protocols=['tcp'], target='/data', color='#74d88a', code='MC', ram=4, variants=['PAPER', 'VANILLA', 'FABRIC', 'FORGE'], license='Minecraft EULA'),
    dict(id='valheim', name='Valheim', category='Survival', image='ghcr.io/lloesche/valheim-server:latest', port=2456, protocols=['udp','udp'], target='/config', color='#edb977', code='VH', ram=4, license='Valheim / Steam'),
    dict(id='palworld', name='Palworld', category='Survival', image='thijsvanloef/palworld-server-docker:latest', port=8211, protocols=['udp'], target='/palworld', color='#82cfff', code='PW', ram=8, license='Palworld / Steam'),
    dict(id='cs2', name='Counter-Strike 2', category='Shooter', image='joedwards32/cs2:latest', port=27015, protocols=['tcp','udp'], same_port=True, target='/home/steam/cs2-dedicated', color='#ffc378', code='CS', ram=4, license='Counter-Strike 2 / Steam', requires_token=True),
    dict(id='terraria', name='Terraria', category='Aufbau', image='ryshe/terraria:latest', port=7777, protocols=['tcp'], target='/root/.local/share/Terraria/Worlds', color='#a9e37d', code='TR', ram=2, license='Terraria'),
    dict(id='satisfactory', name='Satisfactory', category='Aufbau', image='wolveix/satisfactory-server:latest', port=7777, protocols=['tcp','udp'], same_port=True, target='/config', color='#ffba73', code='SF', ram=8, license='Satisfactory / Steam'),
    dict(id='factorio', name='Factorio', category='Aufbau', image='factoriotools/factorio:stable', port=34197, protocols=['udp'], target='/factorio', color='#f4cf79', code='FA', ram=2, license='Factorio'),
    dict(id='zomboid', name='Project Zomboid', category='Survival', image='renegademaster/zomboid-dedicated-server:latest', port=16261, protocols=['udp','udp'], target='/home/steam/Zomboid', color='#d79f9a', code='PZ', ram=4, license='Project Zomboid / Steam'),
    dict(id='teamspeak', name='TeamSpeak 3', category='Sprache', image='teamspeak:3.13.7', port=9987, protocols=['udp'], target='/var/ts3server', color='#8db8ff', code='TS', ram=1, license='TeamSpeak Server License'),
]
TEMPLATES = {item['id']: item for item in CATALOG}
ID_RE = re.compile(r'^[a-f0-9]{12}$')


class EngineError(ValueError):
    pass


class Engine:
    def __init__(self, data: Path, runner=None):
        self.data = Path(data).resolve()
        self.root = self.data / 'servers'
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.data / 'servers.json'
        self.events_path = self.data / 'events.json'
        self.lock = RLock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='vitalux-docker')
        self.runner = runner or subprocess.run
        self.jobs = {}
        self.busy = set()
        self.preloads = set()
        self.servers = json.loads(self.path.read_text()) if self.path.exists() else []
        self.events = json.loads(self.events_path.read_text()) if self.events_path.exists() else []
        for server in self.servers:
            if server.get('status') in ('installing', 'busy'):
                server['status'] = 'unknown'

    def _atomic(self, path, value):
        tmp = path.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        if os.name != 'nt':
            tmp.chmod(0o600)
        tmp.replace(path)

    def _save(self):
        with self.lock:
            self._atomic(self.path, self.servers)

    def event(self, text):
        with self.lock:
            self.events.insert(0, dict(time=time.strftime('%Y-%m-%d %H:%M:%S'), text=text))
            self.events = self.events[:150]
            self._atomic(self.events_path, self.events)

    def docker(self, *args, timeout=30):
        # A local socket is intentional: never follow inherited remote Docker contexts.
        env = dict(os.environ)
        for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
            env.pop(key, None)
        try:
            result = self.runner(['docker', '--host=unix:///var/run/docker.sock', *args], capture_output=True, text=True, timeout=timeout, env=env)
        except FileNotFoundError:
            raise EngineError('Docker fehlt. Bitte Docker Engine installieren.') from None
        except subprocess.TimeoutExpired:
            raise EngineError('Docker-Zeitlimit erreicht. Status und Protokoll prüfen.') from None
        if result.returncode:
            # Do not return command arguments: they may contain installation secrets.
            detail = (result.stderr or result.stdout or 'Unbekannter Docker-Fehler').strip()[-1500:]
            raise EngineError(detail)
        return result.stdout.strip()

    def health(self):
        try:
            version = self.docker('version', '--format', '{{.Server.Version}}', timeout=5)
            return dict(ready=True, version=version, error='')
        except EngineError as exc:
            return dict(ready=False, version='', error=str(exc))

    def _server(self, server_id):
        if not isinstance(server_id, str) or not ID_RE.fullmatch(server_id):
            raise EngineError('Ungültige Server-ID.')
        server = next((s for s in self.servers if s['id'] == server_id), None)
        if not server:
            raise EngineError('Server nicht gefunden.')
        return server

    def _directory(self, server):
        return self.root / server['id']

    def _owned(self, server):
        raw = self.docker('inspect', '--format', '{{json .Config.Labels}}', server['container'])
        if json.loads(raw or '{}').get('io.vitalux.dashboard.id') != server['id']:
            raise EngineError('Container gehört nicht zu diesem Dashboard.')

    def public(self, server):
        return {k:v for k,v in server.items() if k not in ('env',)}

    def list(self):
        with self.lock:
            items = [dict(s) for s in self.servers]
        try:
            raw = self.docker('ps', '-a', '--filter', 'label=io.vitalux.dashboard=homeserver', '--format', '{{json .}}', timeout=8)
            states = {x['Names']: x for x in (json.loads(line) for line in raw.splitlines() if line)}
            for s in items:
                if s['id'] in self.busy:
                    continue
                state = states.get(s['container'])
                s['status'] = state.get('State','unknown') if state else 'missing'
                s['state_detail'] = state.get('Status','') if state else 'Kein Container vorhanden'
        except EngineError:
            for s in items:
                if s['id'] not in self.busy:
                    s['status'] = 'unknown'
        return [self.public(s) for s in items]

    def submit(self, label, fn, server_id=None, preload=None):
        with self.lock:
            if server_id and server_id in self.busy:
                raise EngineError('Für diesen Server läuft bereits ein Auftrag.')
            if preload and preload in self.preloads:
                raise EngineError('Dieses Abbild wird bereits vorgeladen.')
            if sum(j['status']=='running' for j in self.jobs.values()) >= 8:
                raise EngineError('Es laufen bereits mehrere Aufträge. Bitte kurz warten.')
            if len(self.jobs)>100:
                self.jobs={k:v for k,v in self.jobs.items() if v['status']=='running'}
            job_id=secrets.token_hex(8)
            job=dict(id=job_id, label=label, status='running', error='', started=time.time())
            self.jobs[job_id]=job
            if server_id:self.busy.add(server_id)
            if preload:self.preloads.add(preload)
        def run():
            try:
                result=fn()
                with self.lock:job.update(status='done', result=result)
                self.event(label+' abgeschlossen')
            except Exception as exc:
                with self.lock:job.update(status='error', error=str(exc)[:1500])
                if server_id:
                    with self.lock:
                        self._server(server_id)['status']='error'
                        self._save()
                self.event(label+' fehlgeschlagen: '+str(exc)[:250])
            finally:
                with self.lock:
                    self.busy.discard(server_id)
                    self.preloads.discard(preload)
        self.pool.submit(run)
        return dict(job_id=job_id)

    @staticmethod
    def _text(value, name, minimum=1, maximum=80):
        if not isinstance(value,str) or not minimum<=len(value)<=maximum or any(ord(c)<32 for c in value):
            raise EngineError(f'{name}: {minimum} bis {maximum} Zeichen ohne Steuerzeichen benötigt.')
        return value

    def install(self, options):
        template=TEMPLATES.get(options.get('template'))
        if not template:raise EngineError('Unbekannte Servervorlage.')
        if options.get('accept_license') is not True:raise EngineError('Bitte die Lizenzbedingungen des Spiels bestätigen.')
        name=self._text(options.get('name'), 'Servername')
        try:
            ram=int(options.get('ram',template['ram']))
            port=int(options.get('port',template['port']))
        except (TypeError,ValueError):raise EngineError('Port und RAM müssen Zahlen sein.') from None
        if not 1<=ram<=64 or not 1024<=port<=65533:raise EngineError('RAM: 1–64 GB; Port: 1024–65533.')
        password=str(options.get('password',''))
        if password:self._text(password,'Passwort',5,128)
        key=template['id']
        variant=options.get('variant','PAPER') if key=='minecraft' else ''
        if key=='minecraft' and variant not in template['variants']:raise EngineError('Unbekannter Minecraft-Modus.')
        version=str(options.get('version','LATEST')).strip()
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',version):raise EngineError('Ungültige Version.')
        token=str(options.get('token',''))
        if key=='cs2' and not re.fullmatch(r'[A-Za-z0-9]{20,128}',token):raise EngineError('CS2 benötigt einen Steam Gameserver Login Token.')
        if key=='valheim' and len(password)<5:raise EngineError('Valheim benötigt mindestens 5 Zeichen Passwort.')
        sid=secrets.token_hex(6)
        ports=[]
        for i,protocol in enumerate(template['protocols']):
            source=port if template.get('same_port') else port+i
            target=template['port'] if template.get('same_port') else template['port']+i
            ports.append(dict(host=source, target=target, protocol=protocol))
        if key=='satisfactory':ports.append(dict(host=8888,target=8888,protocol='tcp'))
        if key=='teamspeak':ports.append(dict(host=30033,target=30033,protocol='tcp'))
        with self.lock:
            for old in self.servers:
                for p in old['ports']:
                    if any(p['host']==q['host'] and p['protocol']==q['protocol'] for q in ports):
                        raise EngineError(f"Port {p['host']}/{p['protocol']} wird bereits von {old['name']} verwendet.")
            env={}
            if key=='minecraft':env=dict(EULA='TRUE',TYPE=variant,VERSION=version,MEMORY=f'{max(1,ram-1)}G',MOTD=name,ENABLE_RCON='true',RCON_PASSWORD=secrets.token_urlsafe(24))
            elif key=='valheim':env=dict(SERVER_NAME=name,WORLD_NAME='Vitalux',SERVER_PASS=password,SERVER_PUBLIC='false')
            elif key=='palworld':env=dict(SERVER_NAME=name,SERVER_PASSWORD=password,COMMUNITY='false',PORT='8211',PUID=str(os.getuid()),PGID=str(os.getgid()))
            elif key=='cs2':env=dict(SRCDS_TOKEN=token,CS2_SERVERNAME=name,CS2_PW=password)
            elif key=='satisfactory':env=dict(MAXPLAYERS='8',PGID=str(os.getgid()),PUID=str(os.getuid()))
            elif key=='zomboid':env=dict(SERVER_NAME='Vitalux',SERVER_PASSWORD=password,ADMIN_PASSWORD=secrets.token_urlsafe(20))
            elif key=='teamspeak':env=dict(TS3SERVER_LICENSE='accept')
            server=dict(id=sid,template=key,name=name,container='vitalux-'+sid,status='installing',ports=ports,ram=ram,variant=variant,version=version,env=env,created=time.strftime('%Y-%m-%d %H:%M:%S'))
            self.servers.append(server)
            self._save()
        def install_container():
            folder=self._directory(server)
            folder.mkdir(exist_ok=True)
            self.docker('pull',template['image'],timeout=1800)
            args=['create','--name',server['container'],'--label','io.vitalux.dashboard=homeserver','--label',f'io.vitalux.dashboard.id={sid}', '--restart','unless-stopped','--memory',f'{ram}g','--log-opt','max-size=10m','--log-opt','max-file=3']
            for p in ports:args+=['-p',f"{p['host']}:{p['target']}/{p['protocol']}"]
            # No privileged mode, host filesystem mount, docker socket or host networking.
            args+=['--mount',f"type=bind,src={folder},dst={template['target']}"]
            if key in ('palworld','satisfactory'):
                folder.chmod(0o755)
            for k,v in env.items():args+=['-e',f'{k}={v}']
            args.append(template['image'])
            self.docker(*args,timeout=60)
            self.docker('start',server['container'],timeout=60)
            with self.lock:server['status']='running';self._save()
            return self.public(server)
        return self.submit('Installation: '+name,install_container,sid)

    def preload(self, template_id):
        template=TEMPLATES.get(template_id)
        if not template:raise EngineError('Unbekannte Servervorlage.')
        return self.submit('Vorabladen: '+template['name'],lambda:self.docker('pull',template['image'],timeout=1800),preload=template_id)

    def action(self, sid, action, options=None):
        options=options or {}
        server=self._server(sid)
        if action not in ('start','stop','restart','delete','backup','restore','command','update'):
            raise EngineError('Unbekannte Serveraktion.')
        if action=='command':
            if server['template']!='minecraft':raise EngineError('Konsolenbefehle werden derzeit nur für Minecraft unterstützt.')
            command=self._text(options.get('command'),'Befehl',1,500)
            self._owned(server)
            return dict(output=self.docker('exec',server['container'],'rcon-cli',command,timeout=15))
        if action=='restore':
            backup=options.get('backup','')
            if not re.fullmatch(r'backup-\d{8}-\d{6}-[a-f0-9]{4}\.tar\.gz',str(backup)):raise EngineError('Ungültiger Backupname.')
        def perform():
            if action=='delete':
                # A failed installation may have no container yet.
                exists=self.docker('ps','-a','--filter','name=^/'+server['container']+'$','--format','{{.Names}}')
                if exists:
                    self._owned(server)
                    if self.docker('inspect','--format','{{.State.Running}}',server['container'])=='true':raise EngineError('Server vor dem Entfernen stoppen.')
                    self.docker('rm',server['container'])
                with self.lock:self.servers.remove(server);self._save()
                # Retain saves, mods and backups deliberately; deleting a tile never erases them.
                return dict(retained_data=str(self._directory(server)))
            self._owned(server)
            if action in ('backup','restore','update'):
                if self.docker('inspect','--format','{{.State.Running}}',server['container'])=='true':raise EngineError('Server für konsistente Dateien zuerst stoppen.')
            if action=='backup':return self.backup(server)
            if action=='restore':return self.restore(server,options['backup'])
            if action=='update':
                # Pull only; automatic recreation could replace important image-specific settings.
                return dict(output=self.docker('pull',TEMPLATES[server['template']]['image'],timeout=1800),note='Abbild vorgeladen; bestehender Container bleibt auf seiner Version.')
            self.docker(action,'--time','60',server['container'],timeout=90) if action in ('stop','restart') else self.docker('start',server['container'],timeout=60)
            return dict(ok=True)
        return self.submit(action+': '+server['name'],perform,sid)

    def logs(self,sid):
        server=self._server(sid)
        self._owned(server)
        # Docker writes some log entries to stderr even when the command succeeds.
        result=self.runner(['docker','--host=unix:///var/run/docker.sock','logs','--tail','160',server['container']],capture_output=True,text=True,timeout=10)
        if result.returncode:raise EngineError('Container-Protokoll konnte nicht gelesen werden.')
        return dict(text=(result.stdout+'\n'+result.stderr)[-60000:])

    def backups(self,sid):
        self._server(sid)
        folder=self.data/'backups'/sid
        return [dict(name=p.name,bytes=p.stat().st_size) for p in sorted(folder.glob('backup-*.tar.gz'),reverse=True)]

    def backup(self,server):
        folder=self.data/'backups'/server['id'];folder.mkdir(parents=True,exist_ok=True)
        name=time.strftime('backup-%Y%m%d-%H%M%S-')+secrets.token_hex(2)+'.tar.gz'
        partial=folder/(name+'.partial')
        def filter_member(info):
            if not (info.isfile() or info.isdir()):return None
            return info
        try:
            with tarfile.open(partial,'w:gz',dereference=False) as tar:
                tar.add(self._directory(server),arcname='server',filter=filter_member)
            partial.replace(folder/name)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return dict(backup=name)

    def restore(self,server,name):
        path=self.data/'backups'/server['id']/name
        if not path.is_file():raise EngineError('Backup nicht gefunden.')
        staging=self.root/(server['id']+'.restore-'+secrets.token_hex(4))
        staging.mkdir()
        try:
            with tarfile.open(path,'r:gz') as tar:
                members=tar.getmembers()
                for member in members:
                    dest=(staging/member.name).resolve()
                    if not dest.is_relative_to(staging/'server') or not (member.isfile() or member.isdir()):raise EngineError('Backup enthält unzulässige Pfade oder Dateitypen.')
                tar.extractall(staging,members=members,filter='data')
            if not (staging/'server').is_dir():raise EngineError('Leeres Backup.')
            previous=self.backup(server)
            directory=self._directory(server)
            # Preserve the bind-mounted directory inode so a later Docker start sees restored data.
            for child in directory.iterdir():
                if child.is_dir() and not child.is_symlink():shutil.rmtree(child)
                else:child.unlink()
            for child in (staging/'server').iterdir():shutil.move(str(child),directory/child.name)
            return dict(ok=True,safety_backup=previous['backup'])
        finally:shutil.rmtree(staging,ignore_errors=True)

    def mods(self,sid):
        server=self._server(sid)
        if server['template']!='minecraft':return dict(supported=False,items=[])
        name='plugins' if server['variant']=='PAPER' else 'mods'
        if server['variant']=='VANILLA':return dict(supported=False,items=[])
        folder=self._directory(server)/name
        if folder.is_symlink():raise EngineError('Mod-Verzeichnis darf kein Symlink sein.')
        return dict(supported=True,folder=name,items=[dict(name=p.name,enabled=p.name.endswith('.jar'),bytes=p.stat().st_size) for p in sorted(folder.glob('*')) if p.is_file() and not p.is_symlink() and (p.name.endswith('.jar') or p.name.endswith('.jar.disabled'))])

    def change_mod(self,sid,options):
        server=self._server(sid)
        with self.lock:
            if sid in self.busy:raise EngineError('Es läuft bereits ein Serverauftrag.')
            self.busy.add(sid)
        try:
            self._owned(server)
            if self.docker('inspect','--format','{{.State.Running}}',server['container'])=='true':raise EngineError('Server vor Mod-Änderungen stoppen.')
            settings=self.mods(sid)
            if not settings['supported']:raise EngineError('Mods benötigen Paper, Fabric oder Forge.')
            name=options.get('name','')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,110}\.jar(?:\.disabled)?',name):raise EngineError('Ungültiger JAR-Dateiname.')
            folder=self._directory(server)/settings['folder'];folder.mkdir(exist_ok=True)
            path=folder/name
            if path.is_symlink():raise EngineError('Symlinks sind nicht zulässig.')
            if options.get('action')=='toggle':
                if not path.is_file():raise EngineError('Mod nicht gefunden.')
                target=folder/(name[:-9] if name.endswith('.disabled') else name+'.disabled')
                if target.exists():raise EngineError('Zieldatei existiert bereits.')
                self.backup(server)
                path.rename(target)
            elif options.get('action')=='upload':
                try:payload=base64.b64decode(options.get('data',''),validate=True)
                except (ValueError,TypeError):raise EngineError('Ungültige Datei.') from None
                if not 4<=len(payload)<=20*1024*1024 or not payload.startswith(b'PK'):raise EngineError('JAR/ZIP-Datei bis 20 MB benötigt.')
                if not name.endswith('.jar'):raise EngineError('Datei muss auf .jar enden.')
                self.backup(server)
                with path.open('wb') as output:output.write(payload)
            else:raise EngineError('Unbekannte Mod-Aktion.')
            self.event('Mods geändert: '+server['name'])
            return self.mods(sid)
        finally:
            with self.lock:self.busy.discard(sid)
