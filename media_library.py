"""Local folder scanner for PAULFLIX. No cloud and no external connections.

Extracts title/type/season/episode from folder & filename. Extracts genres, plot,
year from locally owned NFO files, or simple user-made .json sidecars.
A genre which has no verifiable source remains 'Nicht zugeordnet'.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET

VIDEO_EXT={'.mkv','.mp4','.m4v','.webm','.avi','.mov','.wmv','.mpg','.mpeg','.ts'}
ART_EXT={'.jpg','.jpeg','.png','.webp'}
SERIES_RE=re.compile(r'(?i)(?:^|[ ._\-])s(\d{1,2})[ ._\-]?e(\d{1,3})(?:\b|[ ._\-])|(?:^|\b)(\d{1,2})x(\d{1,3})(?:\b|[ ._\-])')
YEAR_RE=re.compile(r'(?:\(|\[|\b)((?:19|20)\d\d)(?:\)|\]|\b)')
JUNK_RE=re.compile(r'(?i)\b(1080p|2160p|720p|480p|4k|bluray|brrip|webrip|web.?dl|x264|x265|h\.?264|h\.?265|hevc|aac|dts|hdr|dv|remux|german|multi|proper|repack|extended|directors.cut)\b')
SERIES_PARTS={'serien','series','tv','tv shows','tvshows','shows','staffeln','staffel'}
GENRE_ALIASES={'action':'Action','abenteuer':'Abenteuer','adventure':'Abenteuer','animation':'Animation','anime':'Anime','biografie':'Biografie','comedy':'Comedy','komödie':'Comedy','dokumentation':'Dokumentation','documentary':'Dokumentation','drama':'Drama','familie':'Familie','family':'Familie','fantasy':'Fantasy','geschichte':'Historie','history':'Historie','horror':'Horror','krimi':'Krimi','crime':'Krimi','mystery':'Mystery','musik':'Musik','musical':'Musical','romanze':'Romantik','romance':'Romantik','sci-fi':'Sci-Fi','science fiction':'Sci-Fi','science-fiction':'Sci-Fi','sport':'Sport','thriller':'Thriller','western':'Western'}

def clean_title(name):
    s=Path(name).stem
    s=SERIES_RE.sub(' ',s)
    s=YEAR_RE.sub(' ',s)
    s=JUNK_RE.sub(' ',s)
    s=re.sub(r'(?i)\b(?:season|staffel)[ ._\-]*\d{1,2}\b',' ',s)
    s=re.sub(r'[._]+',' ',s)
    s=re.sub(r'\s*[-–]\s*$','',s)
    return re.sub(r'\s+',' ',s).strip(' -_[]()') or 'Unbenannt'

def extract_year(path):
    m=YEAR_RE.search(str(path))
    return int(m.group(1)) if m else None

def local_metadata(path):
    if not path or not path.is_file() or path.stat().st_size>1_000_000:return {}
    try:
        if path.suffix.lower()=='.json':
            m=json.loads(path.read_text('utf-8'))
            if not isinstance(m,dict):return {}
            return {k:m[k] for k in ('title','year','genre','genres','plot','description','season','episode','type') if k in m}
        raw=path.read_text('utf-8-sig',errors='replace')
        root=ET.fromstring(raw)
        one=lambda tag:(root.findtext(tag) or '').strip()
        genres=[(node.text or '').strip() for node in root.findall('genre') if (node.text or '').strip()]
        return {'title':one('title'),'year':one('year') or one('premiered')[:4],'genres':genres,
                'description':one('plot') or one('outline'),'season':one('season'),'episode':one('episode')}
    except (OSError,ValueError,ET.ParseError,TypeError):return {}

def find_metadata(video,seriesdir=None):
    # Prioritize sibling NFO; then movie.nfo / tvshow.nfo. Nothing sent online.
    candidates=[video.with_suffix('.nfo'),video.with_suffix('.json'),video.parent/'movie.nfo',video.parent/'movie.json']
    if seriesdir:candidates=[seriesdir/'tvshow.nfo',seriesdir/'tvshow.json']+candidates
    for path in candidates:
        if path.is_file():
            v=local_metadata(path)
            if v:return v
    return {}

def genres_for(meta,relparts):
    raw=meta.get('genres') or meta.get('genre') or []
    if isinstance(raw,str):raw=re.split(r'[,;|/]',raw)
    clean=[str(g).strip() for g in raw if str(g).strip()]
    if clean:return clean[:8], 'NFO/JSON'
    for part in relparts:
        norm=part.strip().lower()
        if norm in GENRE_ALIASES:return [GENRE_ALIASES[norm]],'Ordnername'
    return ['Nicht zugeordnet'],'Unbekannt'

def poster_for(video,seriesdir=None):
    dirs=[video.parent]
    if seriesdir and seriesdir != video.parent:dirs.append(seriesdir)
    for d in dirs:
        for candidate in [video.with_suffix('.jpg'),video.with_suffix('.png'),*[d/n for n in ('poster.jpg','poster.png','folder.jpg','folder.png','cover.jpg','cover.png')]]:
            if candidate.is_file() and candidate.suffix.lower() in ART_EXT:
                return candidate
    return None

def file_id(path):return hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:24]

class MediaLibrary:
    def __init__(self,data_dir):
        self.data_dir=Path(data_dir)
        self.config_file=self.data_dir/'paulflix-settings.json'
        self.override_file=self.data_dir/'paulflix-metadata.json'
        self.overrides={}
        self.lock=threading.RLock()
        self.settings={'sources':[], 'interval_minutes':15, 'auto_scan':True}
        self.items=[]
        self.file_map={}
        self.posters={}
        self.last_scan=None
        self.last_error=None
        self.scan_count=0
        self.load()

    def load(self):
        if self.override_file.exists():
            try:
                obj=json.loads(self.override_file.read_text('utf-8'))
                if isinstance(obj,dict):self.overrides=obj
            except (ValueError,OSError):pass
        if self.config_file.exists():
            try:
                data=json.loads(self.config_file.read_text('utf-8'))
                self.settings=self.validate(data,exist_check=False)
            except (ValueError,OSError):pass

    @staticmethod
    def validate(data,exist_check=True):
        if not isinstance(data,dict):raise ValueError('Ungültige Einstellungen.')
        sources=data.get('sources',[])
        if not isinstance(sources,list) or len(sources)>12:raise ValueError('Maximal zwölf Medienordner erlaubt.')
        result=[]
        seen=set()
        for source in sources:
            if not isinstance(source,dict):raise ValueError('Ungültiger Medienordner.')
            raw=str(source.get('path','')).strip()
            if not raw:continue
            p=Path(raw).expanduser().resolve()
            if exist_check and (not p.exists() or not p.is_dir()):
                raise ValueError(f'Medienordner existiert nicht oder ist nicht lesbar: {p}')
            t=source.get('type','Auto')
            if t not in ('Auto','Film','Serie'):raise ValueError('Ungültiger Medientyp.')
            if str(p) not in seen:result.append({'path':str(p),'type':t});seen.add(str(p))
        mins=int(data.get('interval_minutes',15))
        if mins not in (5,15,30,60):raise ValueError('Ungültiges Scanintervall.')
        return {'sources':result,'interval_minutes':mins,'auto_scan':bool(data.get('auto_scan',True))}

    def save(self,data):
        s=self.validate(data)
        self.data_dir.mkdir(parents=True,exist_ok=True)
        tmp=self.config_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(s,ensure_ascii=False,indent=2),'utf-8')
        os.replace(tmp,self.config_file)
        with self.lock:self.settings=s
        return s

    def overview(self):
        with self.lock:return {**self.settings,'last_scan':self.last_scan,'last_error':self.last_error,'count':len(self.items),'scan_count':self.scan_count}

    def scan(self):
        with self.lock:
            settings=self.settings.copy()
            result=[];files={};posters={};shows={};scanned=0
            for src in settings['sources']:
                root=Path(src['path'])
                if not root.is_dir():continue
                for dirname,dirs,names in os.walk(root,followlinks=False):
                    dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(dirname)/d).is_symlink()]
                    for fn in sorted(names):
                        if not fn.lower().endswith(tuple(VIDEO_EXT)):continue
                        p=Path(dirname)/fn
                        if p.is_symlink() or not p.is_file():continue
                        if not p.resolve().is_relative_to(root):continue
                        scanned+=1
                        if scanned>10000:break
                        rel=p.relative_to(root)
                        parts=list(rel.parts)
                        episode=SERIES_RE.search(p.stem)
                        is_show=(src['type']=='Serie' or (src['type']=='Auto' and (episode is not None or any(q.lower() in SERIES_PARTS for q in parts[:-1]))))
                        showdir=None
                        if is_show:
                            meaningful=[z for z in parts[:-1] if z.lower() not in SERIES_PARTS and not re.match(r'(?i)^(season|staffel|s)\s*\d+$',z)]
                            showname=meaningful[-1] if meaningful else clean_title(p.name)
                            showdir=root.joinpath(*parts[:parts.index(showname)+1]) if showname in parts else p.parent
                        meta=find_metadata(p,showdir)
                        genres,gsource=genres_for(meta,parts[:-1])
                        pid=file_id(p.resolve())
                        files[pid]=p.resolve()
                        poster=poster_for(p,showdir)
                        if is_show:
                            sn=clean_title(showname)
                            groupid='show-'+hashlib.sha256((str(root)+sn).encode('utf-8')).hexdigest()[:22]
                            if groupid not in shows:
                                shows[groupid]={'id':groupid,'title':str(meta.get('title') or sn)[:160],
                                  'type':'Serie','year':extract_year(showname) or extract_year(p.name) or int(str(meta.get('year') or '0')[:4] or 0),
                                  'genre':genres[0],'genres':genres,'genre_source':gsource,'description':str(meta.get('description') or '')[:1600],
                                  'duration':'Serie','custom':True,'serverMedia':True,'art':'aurora','episodes':[]}
                                if poster:posters[groupid]=poster
                            if shows[groupid]['genre']=='Nicht zugeordnet' and genres[0]!='Nicht zugeordnet':
                                shows[groupid].update(genre=genres[0],genres=genres,genre_source=gsource)
                            sm=episode
                            season=int(sm.group(1) or sm.group(3)) if sm else int(meta.get('season') or 1)
                            epno=int(sm.group(2) or sm.group(4)) if sm else int(meta.get('episode') or len(shows[groupid]['episodes'])+1)
                            shows[groupid]['episodes'].append({'id':pid,'season':season,'episode':epno,'title':clean_title(p.stem)})
                        else:
                            title=str(meta.get('title') or clean_title(p.stem))[:160]
                            year=int(str(meta.get('year') or '0')[:4] or 0) or extract_year(p.name) or 0
                            item={'id':pid,'videoId':pid,'title':title,'type':'Film','year':year,'genre':genres[0],
                                'genres':genres,'genre_source':gsource,'description':str(meta.get('description') or '')[:1600],
                                'duration':'Lokale Datei','custom':True,'serverMedia':True,'art':'orion'}
                            result.append(item)
                            if poster:posters[pid]=poster
                    if scanned>10000:break
                if scanned>10000:break
            for show in shows.values():
                show['episodes'].sort(key=lambda e:(e['season'],e['episode'],e['title']))
                show['duration']=f"{len(show['episodes'])} Folge(n)"
                result.append(show)
            result.sort(key=lambda x:(x['type'],x['title'].casefold()))
            self.items=result;self.file_map=files;self.posters=posters;self.last_scan=time.strftime('%Y-%m-%d %H:%M:%S');self.last_error=None;self.scan_count+=1
            return {'count':len(result),'videos':len(files),'last_scan':self.last_scan}

    def update_metadata(self,id,data):
        with self.lock:
            if id not in {x['id'] for x in self.items}:raise ValueError('Titel nicht gefunden.')
            if not isinstance(data,dict):raise ValueError('Ungültige Metadaten.')
            title=str(data.get('title','')).strip()[:160]
            genre=str(data.get('genre','')).strip()[:90]
            desc=str(data.get('description','')).strip()[:1600]
            try:year=int(data.get('year') or 0)
            except (TypeError,ValueError):raise ValueError('Ungültiges Erscheinungsjahr.')
            if not title:raise ValueError('Titel darf nicht leer sein.')
            if year and not (1888<=year<=2100):raise ValueError('Ungültiges Erscheinungsjahr.')
            self.overrides[id]={'title':title,'genre':genre or 'Nicht zugeordnet','description':desc,'year':year}
            self.data_dir.mkdir(parents=True,exist_ok=True)
            tmp=self.override_file.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.overrides,ensure_ascii=False,indent=2),'utf-8')
            os.replace(tmp,self.override_file)
            return dict(self.overrides[id])

    def catalog(self):
        with self.lock:
            items=[]
            for item in self.items:
                data=dict(item,posterUrl=('/api/paulflix/poster/'+item['id'] if item['id'] in self.posters else None))
                if item['id'] in self.overrides:data.update(self.overrides[item['id']],genre_source='Manuell')
                items.append(data)
            return items

    def video(self,id):
        with self.lock:return self.file_map.get(id)

    def poster(self,id):
        with self.lock:return self.posters.get(id)
