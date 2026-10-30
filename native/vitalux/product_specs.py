"""Model-verified manufacturer specifications with persistent offline reuse."""
from dataclasses import dataclass,field
from html.parser import HTMLParser
import json,re,time,math
from pathlib import Path
from urllib.parse import urljoin,urlsplit
from . import profiles
from .product_images import (product_key,search_model,matches_product,ProductPage,ProductCache,
                            domains,allowed_url,manufacturer_pages,search_pages,fetch,MAX_PAGE,_atomic_bytes)

@dataclass
class Node:
    tag:str
    attrs:dict=field(default_factory=dict)
    children:list=field(default_factory=list)
    cached:str|None=None
    def text(self):
        if self.cached is None:
            self.cached=re.sub(r'\s+',' ',' '.join(c.text() if isinstance(c,Node) else c for c in self.children)).strip()
        return self.cached
    def walk(self):
        role=self.attrs.get('class','')+' '+self.attrs.get('id','')
        if re.search(r'mega.?menu|main.?menu|navigation|related.?products|recommend|breadcrumb|cookie|site.?header|site.?footer',role,re.I):return
        yield self
        for child in self.children:
            if isinstance(child,Node):yield from child.walk()

class Document(HTMLParser):
    def __init__(self):
        super().__init__();self.root=Node('root');self.stack=[self.root];self.scripts=[];self.json=[];self.skip=0;self.count=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='script':
            self.scripts.append(attrs.get('type','')=='application/ld+json');self.json.append([]);return
        if self.scripts:return
        if tag in ('style','nav','footer','noscript','svg'):self.skip+=1
        if self.skip:return
        self.count+=1
        if self.count>100000:raise ValueError('Specification document too complex')
        node=Node(tag,attrs);self.stack[-1].children.append(node)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):
            self.stack.append(node)
    def handle_endtag(self,tag):
        if tag=='script':
            if self.scripts:
                wanted=self.scripts.pop();data=self.json.pop()
                if wanted:
                    try:self.root.children.append(Node('json',{'data':json.loads(''.join(data))}))
                    except (ValueError,RecursionError):pass
            return
        if self.scripts:return
        if tag in ('style','nav','footer','noscript','svg') and self.skip:self.skip-=1;return
        if self.skip:return
        for index in range(len(self.stack)-1,0,-1):
            if self.stack[index].tag==tag:self.stack=self.stack[:index];break
    def handle_data(self,data):
        if self.scripts:self.json[-1].append(data)
        elif not self.skip:self.stack[-1].children.append(data)

TECHNICAL=re.compile(r'gpu|chipset|socket|processor|core|thread|cache|clock|boost|memory|ram|ddr|display|output|hdmi|port|usb|pci|slot|storage|sata|m\.2|ethernet|lan|wifi|wi-fi|audio|power|watt|tdp|tbp|size|dimension|form.factor|bios|graphics|shader|compute|architecture|resolution|cooling|fan|directx|opengl|vulkan|support|connector|feature|frequency|speed|thermal|family|series|product.id|launch|lithography|technology|package',re.I)

def official(product,url):
    host=(urlsplit(url).hostname or '').casefold()
    return allowed_url(url) and any(host==d or host.endswith('.'+d) for d in domains(product))

def category(key):
    if re.search(r'memory|ram|ddr|cache',key,re.I):return 'Arbeitsspeicher'
    if re.search(r'power|watt|tdp|tbp|thermal|cool|fan',key,re.I):return 'Leistung und Kühlung'
    if re.search(r'usb|port|output|display|hdmi|connector|ethernet|lan|wifi|audio|pci|storage|sata|slot|m\.2',key,re.I):return 'Anschlüsse und Erweiterungen'
    if re.search(r'size|dimension|form.factor|weight',key,re.I):return 'Abmessungen'
    return 'Technische Spezifikationen'

def parse(product,raw,source):
    if not official(product,source):return None
    text=raw.decode('utf-8','replace') if isinstance(raw,bytes) else raw
    identity=ProductPage();identity.feed(text)
    if not any(matches_product(product,title) for title in identity.titles):return None
    doc=Document();doc.feed(text);rows=[];seen=set()
    def add(key,value):
        key=re.sub(r'\s+',' ',str(key)).strip(' :\t\n');value=re.sub(r'\s+',' ',str(value)).strip()
        if not key or not value or key==value or len(key)>160 or len(value)>14000:return
        if matches_product(product,key) or re.search(r'\b(?:rx|rtx|gtx)\s*\d',key,re.I):return
        if key.casefold().endswith('specifications') or re.search(r'choose.a.language|ordering.*compliance|learn.more|view.all|downloads.*support',key,re.I):return
        if re.search(r'cookie|privacy|newsletter|shopping|sign.in|shipping|warranty.registration',key,re.I):return
        ident=key.casefold(),value.casefold()
        if ident not in seen and len(rows)<300:seen.add(ident);rows.append([key,value])
    def structured(value,depth=0):
        if depth>16:return
        if isinstance(value,list):
            for item in value[:300]:structured(item,depth+1)
        elif isinstance(value,dict):
            kind=value.get('@type','')
            if kind=='Product' or isinstance(kind,list) and 'Product' in kind:
                name=' '.join(str(value.get(k,'')) for k in ('name','sku','mpn'))
                if matches_product(product,name):
                    for item in value.get('additionalProperty',[]) if isinstance(value.get('additionalProperty',[]),list) else []:
                        if isinstance(item,dict):add(item.get('name',''),str(item.get('value',''))+' '+str(item.get('unitText','')))
            for key in ('@graph','mainEntity'):structured(value.get(key),depth+1)
    for node in doc.root.walk():
        if node.tag=='json':structured(node.attrs['data']);continue
        children=[c for c in node.children if isinstance(c,Node)]
        if node.tag=='tr':
            cells=[c for c in children if c.tag in ('td','th')]
            if len(cells)>=2:add(cells[0].text(),' · '.join(c.text() for c in cells[1:]))
        if len(children)==2:
            key=children[0].text()
            if len(key)<60 and TECHNICAL.search(key):add(key,children[1].text())
        if node.tag=='dl':
            key=None
            for child in children:
                if child.tag=='dt':key=child.text()
                elif child.tag=='dd' and key:add(key,child.text())
        for index,child in enumerate(children[:-1]):
            role=child.attrs.get('class','')+' '+child.attrs.get('id','')
            if re.search(r'(?:techspec.*(?:name|title)|spec[-_ ]?(?:name|label|title)|attribute[-_ ]name|field__label)',role,re.I):
                add(child.text(),children[index+1].text())
            elif child.tag in ('h2','h3','h4','h5') and len(child.text())<90 and TECHNICAL.search(child.text()) and not re.search(r'\b(?:rx|rtx|gtx)\s*\d',child.text(),re.I):
                following=[]
                for sibling in children[index+1:]:
                    if sibling.tag in ('h1','h2','h3','h4','h5'):break
                    if sibling.tag in ('ul','ol','p','div','span'):
                        value=sibling.text()
                        if value and (sibling.tag!='div' or sum(1 for _ in sibling.walk())<40):following.append(value)
                    if len(following)>=4:break
                if following:add(child.text(),' · '.join(following))
    if not rows:return None
    groups={}
    for key,value in rows:groups.setdefault(category(key),[]).append([key,value])
    return dict(schema=1,key=product_key(product),model=search_model(product),source=source,checked_at=time.time(),
                sections=[dict(title=title,rows=items) for title,items in groups.items()])

class SpecCache:
    def __init__(self,root=None):self.root=Path(root) if root is not None else profiles.directory('cache')/'hardware-specifications'
    def path(self,product):return self.root/(product_key(product)+'.json')
    def load(self,product):
        if not product_key(product):return None
        try:
            path=self.path(product)
            if path.stat().st_size>2*1024*1024:return None
            data=json.loads(path.read_text())
            if data.get('schema')!=1 or data.get('key')!=product_key(product) or not official(product,data.get('source','')):return None
            stamp=data.get('checked_at')
            if not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or not 0<=stamp<=time.time()+300:return None
            sections=data.get('sections')
            if not isinstance(sections,list) or not 1<=len(sections)<=20:return None
            if sum(len(s.get('rows',[])) for s in sections if isinstance(s,dict))>300:return None
            for section in sections:
                if not isinstance(section,dict) or not isinstance(section.get('title'),str) or not isinstance(section.get('rows'),list):return None
                if any(not isinstance(row,list) or len(row)!=2 or not all(isinstance(x,str) for x in row) for row in section['rows']):return None
            return data
        except (OSError,ValueError,TypeError):return None
    def save(self,product,data):_atomic_bytes(self.path(product),json.dumps(data,ensure_ascii=False).encode())

def specification_pages(product,url):
    result=[]
    if 'asus.com' in url and '/techspec' not in url:result.append(url.rstrip('/')+'/techspec/')
    if 'msi.com' in url and '/Specification' not in url:result.append(url.rstrip('/')+'/Specification')
    result.append(url)
    return result

def resolve(product,cache=None,download=fetch,cancelled=None):
    if product.get('kind') not in ('cpu','gpu','mainboard') or not product_key(product) or not domains(product):return None
    cache=cache or SpecCache();saved=cache.load(product)
    if saved:return saved
    deadline=time.monotonic()+30
    def checked_download(url,limit,hosts):
        if time.monotonic()>deadline or cancelled is not None and cancelled.is_set():raise TimeoutError('Specification lookup finished')
        return download(url,limit,hosts)
    candidates=list(manufacturer_pages(product))
    image=ProductCache().load(product)
    if image and official(product,image.get('source','')):candidates.insert(0,image['source'])
    visited=set()
    def attempt(urls):
        for url in urls:
            if not official(product,url):continue
            for source in specification_pages(product,url):
                if source in visited:continue
                visited.add(source)
                try:
                    data=parse(product,checked_download(source,MAX_PAGE,domains(product)),source)
                    if data:cache.save(product,data);return data
                except (OSError,ValueError,RecursionError):continue
        return None
    data=attempt(candidates)
    if data:return data
    try:data=attempt(search_pages(product,checked_download))
    except (OSError,ValueError):data=None
    return data
