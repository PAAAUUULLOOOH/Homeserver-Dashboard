"""Find real manufacturer product images and keep a verified, persistent cache."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import ipaddress
from threading import Lock
import time
from urllib.parse import urlencode, urljoin, urlsplit, parse_qs, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
import xml.etree.ElementTree as ET

from . import profiles
from .hardware_identity import manufacturer, clean
from .updater import _tls_context


DOMAINS = {
    'sapphire': ('sapphiretech.com', 'sapphiretech.com.cn', 'sapphiretech.global'),
    'asus': ('asus.com',), 'msi': ('msi.com',), 'gigabyte': ('gigabyte.com',),
    'asrock': ('asrock.com',), 'powercolor': ('powercolor.com',),
    'xfx': ('xfxforce.com',), 'zotac': ('zotac.com',), 'evga': ('evga.com',),
    'pny': ('pny.com',), 'palit': ('palit.com',), 'gainward': ('gainward.com',),
    'biostar': ('biostar.com.tw',), 'intel': ('intel.com',),
    'amd': ('amd.com',), 'nvidia': ('nvidia.com',),
    'dell': ('dell.com',), 'hp': ('hp.com',), 'lenovo': ('lenovo.com',),
    'corsair': ('corsair.com',), 'kingston': ('kingston.com',), 'crucial': ('crucial.com',),
    'g.skill': ('gskill.com',), 'samsung': ('samsung.com',), 'sk hynix': ('skhynix.com',),
    'teamgroup': ('teamgroupinc.com',), 'adata': ('adata.com',), 'patriot': ('patriotmemory.com',),
}
SAPPHIRE_PURE_PAGE = 'https://www.sapphiretech.com/en/consumer/pure-radeon-rx-9070-xt-16g-gddr6'
SAPPHIRE_PURE_IMAGE = ('https://media.cdn.sapphiretech.com.cn/-/media/sites/sapphire/pim/'
                       'product-images/11348_02_rx9070xt_pure_16ggddr6/'
                       'rx9070xt_pure_photo_c01_800x500.ashx?v=4f6b3314b44c4a42882a5f98b0404402')
MAX_IMAGE = 10 * 1024 * 1024
MAX_PAGE = 4 * 1024 * 1024


def product_key(product):
    if not product or not product.get('exact'):
        return ''
    fields = [str(product.get(k) or '').strip().casefold()
              for k in ('kind', 'vendor', 'model', 'revision')]
    if fields[0] not in ('gpu', 'mainboard', 'cpu', 'ram') or not all(fields[1:3]):
        return ''
    return hashlib.sha256(json.dumps(fields, ensure_ascii=True).encode()).hexdigest()


def domains(product):
    return DOMAINS.get(manufacturer(product.get('vendor')).lower(), ())


def allowed_url(url, hosts=()):
    try:
        value = urlsplit(url)
        host = (value.hostname or '').rstrip('.').lower()
        if (not host or '.' not in host or host.endswith(('.local','.internal','.localhost','.invalid','.test','.example')) or
                host in ('localhost','metadata.google.internal')):return False
        try:
            if not ipaddress.ip_address(host).is_global:return False
        except ValueError:pass
        return (value.scheme == 'https' and value.port in (None, 443) and
                not value.username and not value.password and
                (not hosts or any(host == item or host.endswith('.' + item) for item in hosts)))
    except ValueError:
        return False


def fetch(url, limit, hosts):
    if not allowed_url(url, hosts):
        raise ValueError('Unsupported product source')
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Vitalux-ProductImages/1.0',
                                   'Accept-Language': 'en-US,en;q=0.9,de;q=0.7',
                                   'Accept': 'text/html,application/xml,image/*;q=0.9,*/*;q=0.5'})
    class ManufacturerRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            if not allowed_url(newurl, hosts):
                raise ValueError('Unsupported product redirect')
            return super().redirect_request(request, fp, code, msg, headers, newurl)
    opener = build_opener(ManufacturerRedirect(), HTTPSHandler(context=_tls_context()))
    with opener.open(request, timeout=5) as response:
        if not allowed_url(response.url, hosts):
            raise ValueError('Unsupported product redirect')
        chunks, size, deadline = [], 0, time.monotonic() + 6
        while size <= limit:
            if time.monotonic() >= deadline:
                raise TimeoutError('Product response timed out')
            chunk = response.read1(min(65536, limit + 1 - size))
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)
            size += len(chunk)
        raise ValueError('Product response too large')


def valid_image(raw):
    # Decode in the image worker, never on the GUI thread. Reject HTML error
    # pages and huge dimensions before asking an image plugin to allocate.
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QImageReader
    if not raw or len(raw) > MAX_IMAGE:
        return False
    buffer = QBuffer()
    buffer.setData(QByteArray(raw))
    buffer.open(QIODevice.ReadOnly)
    reader = QImageReader(buffer)
    size = reader.size()
    if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > 16000000:
        return False
    image=reader.read()
    if image.isNull():return False
    # A fully transparent placeholder is decodable but is not a product photo.
    if image.hasAlphaChannel():
        from PySide6.QtCore import Qt
        sample=image.scaled(40,40,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        visible=sum(sample.pixelColor(x,y).alpha()>220
                    for y in range(sample.height()) for x in range(sample.width()))
        if visible/max(1,sample.width()*sample.height())<.025:return False
    return True


def _atomic_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.product-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class ProductCache:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else profiles.directory('cache') / 'hardware-products'

    def load(self, product):
        key = product_key(product)
        if not key:
            return None
        try:
            meta = json.loads((self.root / (key + '.json')).read_text())
            path = self.root / (key + '.image')
            if (meta.get('key') != key or path.stat().st_size > MAX_IMAGE or
                    meta.get('vendor', '').casefold() != product['vendor'].casefold() or
                    meta.get('model', '').casefold() != product['model'].casefold()):
                return None
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != meta.get('sha256') or not valid_image(raw):
                return None
            if not allowed_url(meta.get('source', '')):
                return None
            if not cpu_image_matches(product,meta.get('image_url',''),meta.get('image_identity','')):return None
            return dict(meta, path=str(path), cached=True, cutout=cutout_image(raw))
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def save(self, product, raw, source, image_url, image_identity=""):
        key = product_key(product)
        if not key or not valid_image(raw):
            raise ValueError('Invalid product image')
        if not all(allowed_url(url) for url in (source, image_url)):
            raise ValueError('Unsupported manufacturer source')
        if not cpu_image_matches(product,image_url,image_identity):raise ValueError('CPU image does not identify the exact processor')
        meta = {'image_identity':image_identity,'key': key, 'source': source, 'image_url': image_url,
                'sha256': hashlib.sha256(raw).hexdigest(), 'saved': int(time.time()),
                'vendor': product['vendor'], 'model': product['model'], 'cutout': cutout_image(raw)}
        path = self.root / (key + '.image')
        _atomic_bytes(path, raw)
        _atomic_bytes(self.root / (key + '.json'), json.dumps(meta).encode())
        return dict(meta, path=str(path), cached=False)


def cutout_image(raw):
    """Require a real transparent surround, never just a PNG filename/alpha flag."""
    from PySide6.QtGui import QImage
    from PySide6.QtCore import Qt
    if not valid_image(raw):return False
    image = QImage.fromData(raw)
    if not image.hasAlphaChannel():return False
    image = image.scaled(96,96,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    width,height = image.width(),image.height()
    clear=solid=border_clear=border_count=0
    for y in range(height):
        for x in range(width):
            alpha=image.pixelColor(x,y).alpha()
            clear += alpha < 12
            solid += alpha > 220
            if x in (0,width-1) or y in (0,height-1):
                border_count+=1;border_clear+=alpha<20
    pixels=max(1,width*height)
    return clear/pixels>=.035 and solid/pixels>=.025 and border_clear/max(1,border_count)>=.60


def search_model(product):
    value=clean(product.get('model'))
    if product.get('kind')=='mainboard':
        value=re.sub(r'\s*\(MS-[A-Z0-9]+\)', '', value, flags=re.I)
        value=re.sub(r'\s+(?:rev(?:ision)?\.?\s*[:.]?\s*\d+(?:\.\d+)*)$', '', value, flags=re.I)
    if product.get('kind')=='cpu':
        value=re.sub(r'\b\d+(?:st|nd|rd|th)\s+Gen(?:eration)?\s*', '', value, flags=re.I)
        value=re.sub(r'\s+@\s*\d+(?:\.\d+)?\s*[GM]Hz\b.*$', '', value, flags=re.I)
        value=re.sub(r'\b\d+[- ]Core(?:\s+Processor)?\b', '', value, flags=re.I)
        value=re.sub(r'\s+with\s+Radeon\b.*$', '', value, flags=re.I)
    return re.sub(r'\s+', ' ', re.sub(r'\((?:R|TM)\)|[®™]', '', value, flags=re.I)).strip()


def search_query(product):
    model=search_model(product)
    vendor=manufacturer(product.get('vendor'))
    return model if model.casefold().startswith(vendor.casefold()+' ') else f'{vendor} {model}'.strip()


def matches_product(product, title):
    def words(value):
        value=re.sub(r'\bwi[\W_]*fi\b','wifi',str(value).casefold())
        return set(re.findall(r'[a-z]+|\d+',value))
    ignored=words(manufacturer(product.get('vendor'))) | {'amd','radeon','nvidia','geforce','graphics','card','gpu','processor','cpu'}
    required=words(search_model(product))-ignored
    actual=words(title)
    if not required or not required<=actual:return False
    if re.search(r'\b(?:vs\.?|versus|comparison|unveils|announces|roundup)\b',str(title),re.I):return False
    if product['kind'] in ('mainboard','ram','cpu'):
        # Retail pages separate model codes differently from firmware: i7-13700K
        # / i7 13700K, B650-A / B650 A. Preserve full suffix boundaries so B650
        # never matches B650M and a different RAM part is not selected.
        codes=re.findall(r'\b[a-z]+[a-z0-9-]*\d[a-z0-9-]*\b',search_model(product),re.I)
        for code in codes:
            pieces=re.findall(r'[a-z]+|\d+',code.casefold())
            pattern=r'(?<![a-z0-9])'+r'[\W_]*'.join(map(re.escape,pieces))+r'(?![a-z0-9])'
            if not re.search(pattern,str(title).casefold()):return False
    if product['kind']=='gpu':
        for variant in ('xt','xtx','super','ti','gre'):
            if (variant in required)!=(variant in actual):return False
    return True


def cpu_image_matches(product, image_url, identity=''):
    """Require image-level CPU identity, not just the enclosing article title."""
    if product.get('kind')!='cpu':return True
    model=search_model(product)
    evidence=unquote(str(image_url))+' '+str(identity)
    # An i9 hero shot on an i5 product/review page is never the requested CPU.
    tier=re.search(r'\bi[3579]\b',model,re.I)
    tiers=re.findall(r'(?<![a-z0-9])i[3579](?![a-z0-9])',evidence,re.I)
    if tier and any(value.casefold()!=tier[0].casefold() for value in tiers):return False
    code=re.search(r'(?<![a-z0-9])(\d{4,5}[a-z][a-z0-9]*)(?![a-z0-9])',model,re.I)
    if code:
        expected=code[1].casefold()
        codes=re.findall(r'(?<![a-z0-9])(\d{4,5}[a-z][a-z0-9]*)(?![a-z0-9])',evidence,re.I)
        if any(value.casefold()!=expected for value in codes):return False
        if any(value.casefold()==expected for value in codes):return True
    return matches_product(product,evidence)


class ProductPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.titles,self.images,self.gallery,self.named_images=[],[],[],[]
        self.product_images=[]
        self.in_title=False;self.in_heading=False;self.heading=[];self.json_script=False;self.json_data=[]

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='title':self.in_title=True
        if tag=='h1':self.in_heading=True;self.heading=[]
        if tag=='script' and (attrs.get('type') or '').lower()=='application/ld+json':
            self.json_script=True;self.json_data=[]
        if tag=='meta':
            field=(attrs.get('property') or attrs.get('name') or '').lower()
            if field in ('og:image','og:image:secure_url','twitter:image','twitter:image:src'):
                self.images.append(attrs.get('content',''))
            elif field in ('og:title','twitter:title'):self.titles.append(attrs.get('content',''))
        if tag=='img':
            alt=attrs.get('alt','')
            for key in ('data-src','data-original','data-lazy-src','src'):
                if attrs.get(key):
                    self.gallery.append((attrs[key],alt))
                    role=(attrs.get('class') or '')+' '+(attrs.get('id') or '')
                    if re.search(r'product|gallery|goods|pdp',role,re.I):self.product_images.append(attrs[key])
            for key in ('data-srcset','srcset'):
                for entry in reversed((attrs.get(key) or '').split(',')):
                    if entry.strip():self.gallery.append((entry.strip().split()[0],alt))

    def handle_endtag(self, tag):
        if tag=='title':self.in_title=False
        if tag=='h1' and self.in_heading:
            self.in_heading=False;self.titles.append(''.join(self.heading))
        if tag=='script' and self.json_script:
            self.json_script=False
            try:self._product(json.loads(''.join(self.json_data)))
            except (ValueError,RecursionError):pass

    def _product(self, data, depth=0):
        if depth>12:return
        if isinstance(data,list):
            for item in data[:100]:self._product(item,depth+1)
        elif isinstance(data,dict):
            types=data.get('@type',[])
            if isinstance(types,str):types=[types]
            if not isinstance(types,list):types=[]
            if any(str(value).rstrip('/').rsplit('/',1)[-1]=='Product' for value in types):
                name=' '.join(str(data.get(key,'')) for key in ('name','sku','mpn'))
                images=data.get('image',[])
                if not isinstance(images,list):images=[images]
                for image in images:
                    if isinstance(image,dict):image=image.get('contentUrl') or image.get('url') or ''
                    if isinstance(image,str):self.named_images.append((name,image))
            if '@graph' in data:self._product(data['@graph'],depth+1)
            if 'mainEntity' in data:self._product(data['mainEntity'],depth+1)

    def handle_data(self, data):
        if self.in_title:self.titles.append(data)
        if self.in_heading:self.heading.append(data)
        if self.json_script:self.json_data.append(data)


class SearchPage(HTMLParser):
    def __init__(self):
        super().__init__();self.results=[];self.link='';self.title=[];self.in_link=False
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='a' and 'result__a' in attrs.get('class',''):
            link=attrs.get('href','')
            if 'duckduckgo.com/l/' in link:link=parse_qs(urlsplit('https:'+link if link.startswith('//') else link).query).get('uddg',[''])[0]
            self.link=link;self.title=[];self.in_link=True
    def handle_data(self, data):
        if self.in_link:self.title.append(data)
    def handle_endtag(self, tag):
        if tag=='a' and self.in_link:
            self.results.append((self.link,''.join(self.title)));self.in_link=False


def search_pages(product, download=fetch, provider='auto'):
    query=search_query(product)
    candidates=[]
    try:
        if provider!='duckduckgo':
            url='https://www.bing.com/search?'+urlencode({'format':'rss','q':query})
            document=ET.fromstring(download(url,MAX_PAGE,('bing.com',)))
            candidates=[(item.findtext('link') or '',item.findtext('title') or '') for item in document.findall('.//item')]
    except (OSError,ValueError,ET.ParseError):pass
    result=[link for link,title in candidates if allowed_url(link) and
            (matches_product(product,title) or matches_product(product,unquote(urlsplit(link).path+' '+urlsplit(link).query)))]
    if not result:
        try:
            url='https://html.duckduckgo.com/html/?'+urlencode({'q':query})
            page=SearchPage();page.feed(download(url,MAX_PAGE,('duckduckgo.com',)).decode('utf-8','replace'))
            result=[link for link,title in page.results if allowed_url(link) and
                    (matches_product(product,title) or matches_product(product,unquote(urlsplit(link).path+' '+urlsplit(link).query)))]
        except (OSError,ValueError):pass
    return sorted(dict.fromkeys(result),key=lambda url:0 if allowed_url(url,domains(product)) and domains(product) else 1)[:4]


class ImageSearch(HTMLParser):
    def __init__(self):super().__init__();self.results=[]
    def handle_starttag(self, tag, attrs):
        value=dict(attrs).get('m')
        if value and len(value)<20000:
            try:
                item=json.loads(value)
                if isinstance(item,dict):self.results.append(item)
            except ValueError:pass


def search_images(product, download=fetch, transparent=True):
    query=search_query(product)+' product'+(' transparent png' if transparent else '')
    params={'q':query,'count':12}
    if transparent:params['qft']='+filterui:photo-transparent'
    url='https://www.bing.com/images/search?'+urlencode(params)
    page=ImageSearch();page.feed(download(url,MAX_PAGE,('bing.com',)).decode('utf-8','replace'))
    result=[]
    for item in page.results[:60]:
        source,image=item.get('purl',''),item.get('murl','')
        if (allowed_url(source) and allowed_url(image) and
                (matches_product(product,item.get('t','')) or matches_product(product,unquote(urlsplit(source).path)))):
            result.append((source,image))
    return sorted(dict.fromkeys(result),key=lambda row:0 if domains(product) and allowed_url(row[0],domains(product)) else 1)[:6]


_refresh_lock=Lock()
_refreshed=False

def refresh_pci(cache, download):
    global _refreshed
    with _refresh_lock:
        if _refreshed:return
        _refreshed=True
        try:
            raw=download('https://raw.githubusercontent.com/pciutils/pciids/master/pci.ids',5*1024*1024,('raw.githubusercontent.com',))
            if raw.startswith(b'#') and b'List of PCI ID' in raw[:200] and b'1002 ' in raw:
                _atomic_bytes(cache.root/'pci.ids',raw)
        except (OSError,ValueError):pass


def lookup_key(product):
    key=product_key(product)
    ids=product.get('pci_ids','') if product else ''
    if key:return key
    if re.fullmatch(r'(?:[a-f0-9]{4}:){3}[a-f0-9]{4}',ids):
        return hashlib.sha256(('pci:'+ids).encode()).hexdigest()
    return ''


def manufacturer_pages(product):
    """Public model-based manufacturer routes; every response is still matched."""
    vendor=manufacturer(product.get('vendor')).lower()
    model=search_model(product)
    if product['kind']=='mainboard' and vendor=='msi':
        slug=re.sub(r'[^a-z0-9]+','-',model.lower()).strip('-')
        return ['https://www.msi.com/Motherboard/'+slug]
    if product['kind']=='ram' and vendor=='kingston':
        return ['https://www.kingston.com/en/memory/search?'+urlencode({'partid':model}),
                'https://www.kingston.com/en/memory/search/discontinuedmodels?'+urlencode({'partid':model})]
    if product['kind']=='cpu' and vendor=='amd':
        match=re.search(r'\bRyzen\s+(\d)\s+(\d{4}[a-z0-9]*)\b',model,re.I)
        if match:
            tier,code=match.groups();series=code[0]+'000'
            return [f'https://www.amd.com/en/products/processors/desktops/ryzen/{series}-series/amd-ryzen-{tier}-{code.lower()}.html']
    return []


def resolve(product, cache=None, download=fetch, cancelled=None, on_preview=None):
    """Prefer a cutout, retain a verified background alternative and offline cache."""
    cache=cache or ProductCache()
    saved=cache.load(product)
    if saved:return saved
    if not product:return None
    if not product_key(product):
        if lookup_key(product):refresh_pci(cache,download)
        return None
    deadline=time.monotonic()+40
    original_download=download
    fallback=None
    visited=set()
    report=dict(kind=product['kind'],model=search_model(product),events=[])
    def note(stage, **details):
        if len(report['events'])<50:report['events'].append(dict(stage=stage,**details))
    def finish(result):
        report['result']='cutout' if result and result.get('cutout') else 'background' if result else 'missing'
        try:_atomic_bytes(cache.root/(product_key(product)+'.lookup.json'),json.dumps(report,ensure_ascii=False).encode())
        except OSError:pass
        return result
    def download(url,limit,hosts=()):
        if time.monotonic()>=deadline or (cancelled is not None and cancelled.is_set()):
            raise TimeoutError('Product lookup finished')
        try:return original_download(url,limit,hosts)
        except (OSError,ValueError) as exc:
            note('download_failed',host=urlsplit(url).hostname,error=type(exc).__name__)
            raise
    def image_result(source,image,identity=""):
        nonlocal fallback
        if not allowed_url(image) or image in visited:return None
        if not cpu_image_matches(product,image,identity):
            note('cpu_identity_rejected',host=urlsplit(image).hostname)
            return None
        visited.add(image)
        if re.search(r'(?:^|[/_.-])(?:logo|icon|banner)(?:[/_.-]|$)',urlsplit(image).path,re.I):return None
        try:
            raw=download(image,MAX_IMAGE,())
            if not valid_image(raw):note('invalid_image',host=urlsplit(image).hostname);return None
            if cutout_image(raw):
                note('cutout',host=urlsplit(image).hostname)
                return cache.save(product,raw,source,image,identity)
            if fallback is None:
                fallback=cache.save(product,raw,source,image,identity)
                note('background_alternative',host=urlsplit(image).hostname)
                if on_preview:on_preview(fallback)
        except (OSError,ValueError):pass
        return None
    if product['kind']=='gpu' and re.sub(r'[^a-z0-9]','',product['model'].lower())=='sapphirepureradeonrx9070xt':
        saved=image_result(SAPPHIRE_PURE_PAGE,SAPPHIRE_PURE_IMAGE)
        if saved:return finish(saved)
    def page_results(pages):
        for source in pages:
            try:
                page=ProductPage();page.feed(download(source,MAX_PAGE,()).decode('utf-8','replace'))
                matches=any(matches_product(product,title) for title in page.titles)
                images=[(url,name) for name,url in page.named_images if matches_product(product,name)]
                if matches:images += [(url,'') for url in page.images+page.product_images]
                images += [(url,alt) for url,alt in page.gallery if matches_product(product,alt) or
                           (matches and matches_product(product,unquote(url)))]
                note('product_page',host=urlsplit(source).hostname,matched=matches,candidates=len(images))
                for image,identity in list(dict.fromkeys(images))[:12]:
                    result=image_result(source,urljoin(source,image),identity)
                    if result:return result
            except (OSError,ValueError):continue
        return None
    saved=page_results(manufacturer_pages(product))
    if saved:return finish(saved)
    try:pages=search_pages(product,download)
    except (OSError,ValueError):pages=[]
    saved=page_results(pages)
    if saved:return finish(saved)
    try:
        for source,image in search_images(product,download):
            saved=image_result(source,image)
            if saved:return finish(saved)
    except (OSError,ValueError):pass
    if pages:
        try:
            saved=page_results([url for url in search_pages(product,download,'duckduckgo') if url not in pages])
            if saved:return finish(saved)
        except (OSError,ValueError):pass
    # Transparent search filters often hide the only valid photograph.
    try:
        for source,image in search_images(product,download,transparent=False):
            saved=image_result(source,image)
            if saved:return finish(saved)
    except (OSError,ValueError):pass
    return finish(fallback)
