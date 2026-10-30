#!/usr/bin/env python3
"""Vitalux Homeserver test build: authenticated local Docker/media dashboard."""
import argparse
import getpass
import hashlib
import hmac
import html
import json
import os
import secrets
import socket
import sys
import time
from http import HTTPStatus
import mimetypes
import re
from threading import Thread, Event
from media_library import MediaLibrary
from engine import Engine, EngineError, CATALOG
from telemetry import collect
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('VITALUX_DATA',str(ROOT/'data'))).resolve()
AUTH=DATA/'admin.json'
ITERATIONS=600_000
SESSION_TTL=8*3600
SESSIONS={}
FAILURES={}
LOCK=Lock()
LOGIN=(ROOT/'login.html').read_bytes()
DASHBOARD=(ROOT/'dashboard.html').read_text(encoding='utf-8')
MEDIA=MediaLibrary(DATA)
ENGINE=Engine(DATA)
STOP=Event()


def create_auth():
    if AUTH.exists():
        print('Admin-Passwort ist bereits eingerichtet. Es wurde nichts überschrieben.')
        return
    if not sys.stdin.isatty():
        raise SystemExit('Ersteinrichtung im Terminal ausführen: python server.py --setup')
    print('Vitalux Dashboard – lokales Administratorkonto einrichten')
    while True:
        password=getpass.getpass('Neues Passwort (mindestens 12 Zeichen): ')
        if len(password)<12 or len(password)>256:
            print('Bitte ein Passwort mit 12 bis 256 Zeichen eingeben.');continue
        confirm=getpass.getpass('Passwort wiederholen: ')
        if password!=confirm: print('Passwörter stimmen nicht überein.');continue
        break
    write_auth(password)
    print('Lokaler Admin-Zugang eingerichtet. Es existieren keine Registrierung oder weiteren Benutzer.')


def write_auth(password):
    if not isinstance(password,str) or not 12<=len(password)<=256:
        raise ValueError('Passwort muss 12 bis 256 Zeichen lang sein.')
    salt=secrets.token_bytes(24)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,ITERATIONS)
    DATA.mkdir(parents=True,exist_ok=True)
    if os.name!='nt': DATA.chmod(0o700)
    payload={'user':'admin','salt':salt.hex(),'hash':digest.hex(),'iterations':ITERATIONS}
    # Exclusive creation; never overwrite an existing password.
    fd=os.open(AUTH,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(payload,f)


def valid_password(password):
    record=json.loads(AUTH.read_text('utf-8'))
    try:
        guess=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(record['salt']),int(record['iterations']))
        return hmac.compare_digest(guess,bytes.fromhex(record['hash']))
    except (ValueError,KeyError,TypeError): return False


def clean_sessions():
    now=time.time()
    with LOCK:
        for token,value in list(SESSIONS.items()):
            if value['expires']<=now: SESSIONS.pop(token,None)


class Handler(BaseHTTPRequestHandler):
    server_version='VitaluxHomeserver/0.10.0-test'
    def log_message(self,fmt,*args):
        # Avoid logging password values or cookie headers.
        sys.stderr.write('%s - %s\n'%(self.client_address[0],fmt%args))

    def respond(self,code,body=b'',ctype='text/html; charset=utf-8',extras=None):
        self.send_response(code)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store, private')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        for k,v in (extras or {}).items(): self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD': self.wfile.write(body)

    def redirect(self,path,cookie=None):
        extras={'Location':path}
        if cookie: extras['Set-Cookie']=cookie
        self.respond(HTTPStatus.SEE_OTHER,b'','text/plain',extras)

    def session(self):
        raw=self.headers.get('Cookie','')
        if len(raw)>4096:return None,None
        cookies=SimpleCookie()
        try: cookies.load(raw)
        except Exception: return None,None
        item=cookies.get('vlx_session')
        if not item:return None,None
        token=item.value
        with LOCK:
            session=SESSIONS.get(token)
            if session and session['expires']>time.time(): return token,session
        return None,None

    def request_path(self): return urlsplit(self.path).path

    def json_response(self,code,obj):
        return self.respond(code,json.dumps(obj,ensure_ascii=False).encode('utf-8'),'application/json; charset=utf-8')

    def csrf_ok(self,session):
        if not session:return False
        supplied=self.headers.get('X-CSRF-Token','')
        return bool(supplied) and hmac.compare_digest(session['csrf'],supplied)

    def serve_media(self,path,poster=False):
        # Paths originate exclusively from the configured server-side index, never URL parameters.
        if not path or not path.is_file():return self.respond(HTTPStatus.NOT_FOUND,b'Media unavailable','text/plain')
        total=path.stat().st_size
        if poster:
            if total>12*1024*1024:return self.respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,b'Image too large','text/plain')
            mime=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
            if mime not in ('image/jpeg','image/png','image/webp'):return self.respond(HTTPStatus.UNSUPPORTED_MEDIA_TYPE,b'Unsupported','text/plain')
            return self.respond(HTTPStatus.OK,path.read_bytes(),mime)
        mime=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        start,end=0,total-1
        part=False
        header=self.headers.get('Range','')
        if header:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
            if not match or (not match.group(1) and not match.group(2)):
                return self.respond(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,b'Invalid range','text/plain',{'Content-Range':f'bytes */{total}'})
            try:
                if match.group(1):
                    start=int(match.group(1));end=int(match.group(2)) if match.group(2) else total-1
                else:
                    suffix=int(match.group(2));start=max(0,total-suffix);end=total-1
            except ValueError: return self.respond(HTTPStatus.BAD_REQUEST,b'Invalid range','text/plain')
            if start> end or start>=total:
                return self.respond(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,b'Invalid range','text/plain',{'Content-Range':f'bytes */{total}'})
            end=min(end,total-1)
            part=True
        count=end-start+1
        self.send_response(HTTPStatus.PARTIAL_CONTENT if part else HTTPStatus.OK)
        self.send_header('Content-Type',mime)
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(count))
        if part:self.send_header('Content-Range',f'bytes {start}-{end}/{total}')
        self.send_header('Cache-Control','private, no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'none'")
        self.end_headers()
        if self.command=='HEAD':return
        try:
            with path.open('rb') as source:
                source.seek(start)
                remaining=count
                while remaining>0:
                    chunk=source.read(min(1024*1024,remaining))
                    if not chunk:break
                    self.wfile.write(chunk)
                    remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

    def do_GET(self):
        path=self.request_path()
        token,session=self.session()
        if path=='/favicon.ico':return self.respond(HTTPStatus.NO_CONTENT,b'')
        if path=='/':return self.redirect('/dashboard' if session else '/login')
        if path=='/login':
            if session:return self.redirect('/dashboard')
            return self.respond(HTTPStatus.OK,LOGIN)
        if not session:return self.redirect('/login')
        if path=='/dashboard':
            page=DASHBOARD.replace('__CSRF_TOKEN__',session['csrf']).encode('utf-8')
            return self.respond(HTTPStatus.OK,page)
        if path in ('/app.js','/app.css','/designs.json') or (path.startswith('/assets/') and re.fullmatch(r'/assets/[a-z_]+\.png',path)):
            file=ROOT/path.lstrip('/')
            if not file.is_file():return self.respond(HTTPStatus.NOT_FOUND,b'Not found','text/plain')
            return self.respond(HTTPStatus.OK,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        if path=='/api/host':return self.json_response(HTTPStatus.OK,dict(metrics=collect(DATA),docker=ENGINE.health()))
        if path=='/api/catalog':return self.json_response(HTTPStatus.OK,CATALOG)
        if path=='/api/servers':return self.json_response(HTTPStatus.OK,ENGINE.list())
        if path=='/api/events':return self.json_response(HTTPStatus.OK,ENGINE.events)
        if path=='/api/jobs':
            with ENGINE.lock:jobs=[dict(j) for j in ENGINE.jobs.values()]
            return self.json_response(HTTPStatus.OK,jobs)
        match=re.fullmatch(r'/api/servers/([a-f0-9]{12})/(logs|mods|backups)',path)
        if match:
            try:
                method=getattr(ENGINE,match.group(2))
                return self.json_response(HTTPStatus.OK,method(match.group(1)))
            except (EngineError,ValueError,OSError) as exc:return self.json_response(HTTPStatus.BAD_REQUEST,{'error':str(exc)[:1500]})
        if path=='/api/paulflix/settings':return self.json_response(HTTPStatus.OK,MEDIA.overview())
        if path=='/api/paulflix/catalog':return self.json_response(HTTPStatus.OK,MEDIA.catalog())
        if path.startswith('/api/paulflix/stream/'):
            return self.serve_media(MEDIA.video(path.rsplit('/',1)[-1]))
        if path.startswith('/api/paulflix/poster/'):
            return self.serve_media(MEDIA.poster(path.rsplit('/',1)[-1]),poster=True)
        if path=='/api/session':
            return self.respond(HTTPStatus.OK,b'{"authenticated":true,"role":"local_admin"}','application/json; charset=utf-8')
        return self.respond(HTTPStatus.NOT_FOUND,b'Not found','text/plain')

    def do_POST(self):
        path=self.request_path()
        origin=self.headers.get('Origin')
        # Prevent cross-origin POSTs. Some local browsers omit Origin on a normal form submit.
        if origin:
            expected='http://'+self.headers.get('Host','')
            if origin!=expected:return self.respond(HTTPStatus.FORBIDDEN,b'Forbidden','text/plain')
        size_header=self.headers.get('Content-Length','0')
        try:size=int(size_header)
        except ValueError:size=8193
        limit=28*1024*1024 if re.fullmatch(r'/api/servers/[a-f0-9]{12}/mods',path) else 8192
        if size<0 or size>limit:return self.respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,b'Request too large','text/plain')
        if limit>8192:
            _,upload_session=self.session()
            if not self.csrf_ok(upload_session):return self.json_response(HTTPStatus.FORBIDDEN,{'error':'Ungültige Sitzung oder CSRF-Token.'})
        body=self.rfile.read(size)
        if path=='/login':
            if self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded':
                return self.respond(HTTPStatus.BAD_REQUEST,b'Invalid form','text/plain')
            ip=self.client_address[0]
            with LOCK:
                recent=[t for t in FAILURES.get(ip,[]) if time.time()-t<120]
                FAILURES[ip]=recent
                limited=len(recent)>=6
            if limited:return self.respond(HTTPStatus.TOO_MANY_REQUESTS,b'Zu viele Versuche. Bitte spaeter erneut probieren.','text/plain; charset=utf-8',{'Retry-After':'120'})
            data=parse_qs(body.decode('utf-8','replace'),keep_blank_values=True)
            username=data.get('username',[''])[0]
            password=data.get('password',[''])[0]
            if username=='admin' and valid_password(password):
                with LOCK: FAILURES.pop(ip,None)
                token=secrets.token_urlsafe(36)
                csrf=secrets.token_urlsafe(32)
                clean_sessions()
                with LOCK:SESSIONS[token]={'expires':time.time()+SESSION_TTL,'csrf':csrf}
                cookie=f'vlx_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}'
                return self.redirect('/dashboard',cookie)
            with LOCK:FAILURES.setdefault(ip,[]).append(time.time())
            return self.redirect('/login?error=1')
        if path in ('/api/servers/install','/api/preload') or re.fullmatch(r'/api/servers/[a-f0-9]{12}/(action|mods)',path):
            token,session=self.session()
            if not self.csrf_ok(session):return self.json_response(HTTPStatus.FORBIDDEN,{'error':'Ungültige Sitzung oder CSRF-Token.'})
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON benötigt.')
                options=json.loads(body.decode('utf-8'))
                if not isinstance(options,dict):raise ValueError('JSON-Objekt benötigt.')
                if path=='/api/servers/install':result=ENGINE.install(options)
                elif path=='/api/preload':result=ENGINE.preload(options.get('template'))
                else:
                    sid=path.split('/')[3]
                    if path.endswith('/mods'):result=ENGINE.change_mod(sid,options)
                    else:result=ENGINE.action(sid,options.get('action'),options)
                return self.json_response(HTTPStatus.OK,result)
            except (ValueError,TypeError,OSError) as exc:
                return self.json_response(HTTPStatus.BAD_REQUEST,{'error':str(exc)[:1500]})
        if path in ('/api/paulflix/settings','/api/paulflix/scan') or (path.startswith('/api/paulflix/metadata/') and path.rsplit('/',1)[-1]):
            token,session=self.session()
            if not self.csrf_ok(session):return self.json_response(HTTPStatus.FORBIDDEN,{'error':'Ungültige Sitzung oder CSRF-Token.'})
            try:
                if path.startswith('/api/paulflix/metadata/'):
                    if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON benötigt.')
                    return self.json_response(HTTPStatus.OK,MEDIA.update_metadata(path.rsplit('/',1)[-1],json.loads(body.decode('utf-8'))))
                if path.endswith('/settings'):
                    if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                        raise ValueError('JSON benötigt.')
                    settings=json.loads(body.decode('utf-8'))
                    result=MEDIA.save(settings)
                    return self.json_response(HTTPStatus.OK,result)
                return self.json_response(HTTPStatus.OK,MEDIA.scan())
            except (ValueError,TypeError,OSError) as exc:
                return self.json_response(HTTPStatus.BAD_REQUEST,{'error':str(exc)[:250]})
        if path=='/logout':
            token,session=self.session()
            csrf=self.headers.get('X-CSRF-Token','')
            if not session or not hmac.compare_digest(session['csrf'],csrf):
                return self.respond(HTTPStatus.FORBIDDEN,b'Forbidden','text/plain')
            with LOCK:SESSIONS.pop(token,None)
            return self.respond(HTTPStatus.OK,b'OK','text/plain; charset=utf-8',{'Set-Cookie':'vlx_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        return self.respond(HTTPStatus.NOT_FOUND,b'Not found','text/plain')


def periodic_scan():
    while not STOP.is_set():
        settings=MEDIA.overview()
        if settings['auto_scan'] and settings['sources']:
            try:MEDIA.scan()
            except Exception as exc:
                with MEDIA.lock: MEDIA.last_error=str(exc)[:250]
        STOP.wait(settings['interval_minutes']*60)

def main():
    p=argparse.ArgumentParser(description='Vitalux Dashboard – lokaler Admin-Zugang')
    p.add_argument('--setup',action='store_true',help='Einmalig Administratorpasswort einrichten')
    p.add_argument('--host',default='127.0.0.1',help='Bind-Adresse (Standard nur dieser Rechner)')
    p.add_argument('--port',type=int,default=8765)
    args=p.parse_args()
    if args.setup:create_auth();return
    if not AUTH.exists():create_auth()
    if args.host not in ('127.0.0.1','localhost','::1'):
        print('WARNUNG: HTTP im LAN ist unverschlüsselt. Nicht ins Internet freigeben. Für LAN lieber HTTPS oder SSH-Tunnel verwenden.')
        if args.host in ('0.0.0.0','::'): print('WARNUNG: Bindung an ALLE Interfaces. Besser nur die konkrete Heimnetz-IP verwenden.')
    thread=Thread(target=periodic_scan,name='PaulflixLocalScanner',daemon=True)
    thread.start()
    with ThreadingHTTPServer((args.host,args.port),Handler) as srv:
        print(f'Vitalux Dashboard lokal erreichbar: http://{args.host}:{args.port}')
        print('Anmeldung: Benutzer admin, Passwort aus der Ersteinrichtung. Strg+C zum Beenden.')
        try:srv.serve_forever()
        except KeyboardInterrupt:print('\nBeendet.')
        finally:STOP.set()

if __name__=='__main__':main()
