"""Integration tests for local administrator authentication."""
import hashlib
import http.cookiejar
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

SRC=Path(__file__).resolve().parent


def port_free():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


class VitaluxLocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=Path(tempfile.mkdtemp(prefix='vitalux-test-'))
        for f in ('server.py','dashboard.html','login.html','media_library.py','engine.py','telemetry.py','app.js','app.css','designs.json'):
            shutil.copy2(SRC/f,cls.d/f)
        (cls.d/'data').mkdir()
        salt=b'a-test-salt-not-used-live'
        digest=hashlib.pbkdf2_hmac('sha256',b'correct-horse-battery-staple',salt,600000)
        (cls.d/'data/admin.json').write_text(json.dumps({'user':'admin','salt':salt.hex(),'hash':digest.hex(),'iterations':600000}))
        cls.port=port_free();cls.url=f'http://127.0.0.1:{cls.port}'
        cls.proc=subprocess.Popen([sys.executable,'server.py','--port',str(cls.port)],cwd=cls.d,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                with socket.create_connection(('127.0.0.1',cls.port),.1):break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Local server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate();cls.proc.wait(timeout=4)
        shutil.rmtree(cls.d)

    def req(self,path='/',opener=None,method='GET',data=None,csrf=None):
        o=opener or build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        headers={}
        if data is not None:
            data=urlencode(data).encode();headers['Content-Type']='application/x-www-form-urlencoded'
        if csrf:headers['X-CSRF-Token']=csrf
        request=Request(self.url+path,method=method,data=data,headers=headers)
        return o.open(request)

    def test_login_is_required(self):
        for path in ('/','/dashboard','/api/session'):
            response=self.req(path)
            self.assertEqual('/login',response.url.split(str(self.url))[-1])
            self.assertNotIn(b'Survival-Insel',response.read())

    def test_login_and_logout_and_csrf(self):
        jar=http.cookiejar.CookieJar();o=build_opener(HTTPCookieProcessor(jar))
        r=self.req('/login',o,method='POST',data={'username':'admin','password':'correct-horse-battery-staple'})
        self.assertEqual('/dashboard',r.url.replace(self.url,''))
        html=r.read().decode()
        self.assertIn('Vitalux',html)
        self.assertNotIn('Registrieren',html)
        self.assertNotIn('data-a="usr:',html)
        token=html.split('name="csrf-token" content="',1)[1].split('"',1)[0]
        with self.assertRaises(HTTPError) as err:self.req('/logout',o,method='POST',csrf='not-valid')
        self.assertEqual(403,err.exception.code)
        r=self.req('/logout',o,method='POST',csrf=token)
        self.assertEqual(200,r.status)
        self.assertEqual('/login',self.req('/dashboard',o).url.replace(self.url,''))

    def test_wrong_password_cannot_enter(self):
        o=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        r=self.req('/login',o,method='POST',data={'username':'admin','password':'wrong'})
        self.assertIn('/login',r.url)

    def test_media_config_scan_and_stream_auth(self):
        import json
        video= self.d/'film-collection'/'Filme'
        video.mkdir(parents=True,exist_ok=True)
        movie=video/'Unser Testfilm (2025).mp4';movie.write_bytes(b'123456789abcdef')
        (video/'Unser Testfilm (2025).nfo').write_text('<movie><title>Unser Testfilm</title><year>2025</year><genre>Action</genre></movie>','utf-8')
        jar=http.cookiejar.CookieJar();opener=build_opener(HTTPCookieProcessor(jar))
        response=self.req('/login',opener,method='POST',data={'username':'admin','password':'correct-horse-battery-staple'})
        page=response.read().decode()
        csrf=page.split('name="csrf-token" content="',1)[1].split('"',1)[0]
        def post(path,data):
            req=Request(self.url+path,data=json.dumps(data).encode('utf-8'),method='POST',headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
            return json.load(opener.open(req))
        with self.assertRaises(HTTPError) as err:
            post('/api/paulflix/settings',{'sources':[{'path':'/path/not-available','type':'Film'}]})
        self.assertEqual(err.exception.code,400)
        result=post('/api/paulflix/settings',{'sources':[{'path':str(video),'type':'Film'}],'auto_scan':True,'interval_minutes':15})
        self.assertEqual(len(result['sources']),1)
        with self.assertRaises(HTTPError) as err:
            opener.open(Request(self.url+'/api/paulflix/scan',data=b'',method='POST'))
        self.assertEqual(err.exception.code,403)
        result=post('/api/paulflix/scan',{})
        self.assertEqual(result['videos'],1)
        catalog=json.load(opener.open(self.url+'/api/paulflix/catalog'))
        m=next(x for x in catalog if x['title']=='Unser Testfilm')
        self.assertEqual(m['genre'],'Action')
        rid=m['videoId']
        request=Request(self.url+'/api/paulflix/stream/'+rid,headers={'Range':'bytes=2-6'})
        r=opener.open(request)
        self.assertEqual(r.status,206)
        self.assertEqual(r.read(),b'34567')
        self.assertEqual(r.headers['Content-Range'],'bytes 2-6/15')
        post('/api/paulflix/metadata/'+m['id'],{'title':'Anderer Titel','genre':'Sci-Fi','year':2026,'description':'Test'})
        catalog=json.load(opener.open(self.url+'/api/paulflix/catalog'))
        self.assertEqual(catalog[0]['genre'],'Sci-Fi')
        self.assertEqual(catalog[0]['title'],'Anderer Titel')
        r=build_opener().open(self.url+'/api/paulflix/stream/'+rid)
        self.assertTrue(r.url.endswith('/login'))
        self.assertNotIn(b'123456789abcdef',r.read())

    def test_no_signup_or_external_assets(self):
        o=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with self.assertRaises(HTTPError) as err:self.req('/register',o,method='POST',data={'email':'anything'})
        self.assertEqual(404,err.exception.code)
        dashboard=(SRC/'dashboard.html').read_text()
        for text in ('https://','fonts.googleapis.com','Konto beantragen','demo-demo',"'lol'",'function users()'):
            self.assertNotIn(text,dashboard)

if __name__=='__main__':unittest.main()
