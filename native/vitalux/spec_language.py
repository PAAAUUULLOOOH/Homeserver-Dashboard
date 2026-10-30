"""Translate public manufacturer text into DE/EN, retaining technical identifiers."""
import copy
import hashlib
import json
from pathlib import Path
import re
import textwrap
from threading import Lock
from urllib.request import Request,urlopen
from . import profiles,i18n
from .product_images import _atomic_bytes
from .updater import _tls_context

_LOCK=Lock()
_TOKEN=re.compile(r'https?://\S+|\b(?:Intel|AMD|Ryzen|Core|Xeon|Threadripper|Radeon|NVIDIA|GeForce|Windows|Linux|Microsoft|DirectX|OpenGL|Vulkan|DisplayPort|HDMI|Wi-Fi|PCIe|DDR[345]|GDDR[567])\b|\b[A-Za-z0-9][A-Za-z0-9./+-]*\d[A-Za-z0-9./+-]*\b|\b\d+(?:[.,]\d+)?\b')


def network_translate(text,language):
    """Use Microsoft's public web translator; no user credential is requested."""
    if language not in ('de','en'):raise ValueError('Unsupported translation language')
    lines=text.split('\n')
    payload=json.dumps(lines,ensure_ascii=False).encode()
    request=Request('https://edge.microsoft.com/translate/translatetext?isEnterpriseClient=false&to='+language,
                    data=payload,headers={'Content-Type':'application/json; charset=UTF-8',
                                         'User-Agent':'Mozilla/5.0'})
    with urlopen(request,timeout=6,context=_tls_context()) as response:
        raw=response.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('Translation response too large')
    data=json.loads(raw)
    if not isinstance(data,list) or len(data)!=len(lines):raise ValueError('Translation rows changed')
    translated=[]
    for item in data:
        choices=item.get('translations',[]) if isinstance(item,dict) else []
        if not choices or choices[0].get('to')!=language:raise ValueError('Wrong translation language')
        translated.append(choices[0]['text'])
    return '\n'.join(translated)


def _known(text,language):
    from .spec_ui import KEYS
    tables={**i18n.EN,**i18n.EN_MORE}
    german=KEYS.get(text.casefold())
    if german:return german if language=='de' else tables.get(german,text)
    if text in tables:return text if language=='de' else tables[text]
    if language=='de':
        inverse={value:key for key,value in tables.items()}
        if text in inverse:return inverse[text]
    # Pure quantities and identifiers need no language service.
    if not re.search(r'[A-Za-zÄÖÜäöüß]{3}',_TOKEN.sub('',text)):return text
    return None


def localize(data,language,*,download=None,cancelled=None,offline=False,root=None):
    if not data or language not in ('de','en'):return None
    if data.get('language')==language:return data
    root=Path(root) if root is not None else profiles.directory('cache')/'hardware-specifications'/'translations'
    fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    path=root/(fingerprint+'-'+language+'.json')
    try:
        cached=json.loads(path.read_text())
        if (cached.get('source_fingerprint')==fingerprint and cached.get('language')==language
                and isinstance(cached.get('sections'),list)
                and all(isinstance(group,dict) and isinstance(group.get('title'),str)
                        and isinstance(group.get('rows'),list)
                        and all(isinstance(row,list) and len(row)==2 and all(isinstance(part,str) for part in row)
                                for row in group['rows']) for group in cached['sections'])):return cached
    except (OSError,ValueError,TypeError,AttributeError):pass
    values=[]
    for group in data['sections']:
        values.append(group['title'])
        for key,value in group['rows']:values.extend((key,value))
    original_values=list(dict.fromkeys(values))
    segments={text:textwrap.wrap(text,width=1400,break_long_words=False,break_on_hyphens=False) or [''] for text in original_values}
    values=list(dict.fromkeys(part for parts in segments.values() for part in parts))
    dictionary=root/('strings-'+language+'.json')
    with _LOCK:
        try:known=json.loads(dictionary.read_text())
        except (OSError,ValueError):known={}
    if not isinstance(known,dict):known={}
    def saved(text):
        value=known.get(hashlib.sha256(text.encode()).hexdigest())
        return value if isinstance(value,str) and value.strip() else None
    translated={text:_known(text,language) or saved(text) for text in values}
    missing=[text for text in values if translated[text] is None]
    if missing and offline:return None
    download=download or network_translate
    while missing:
        if cancelled is not None and cancelled.is_set():return None
        batch=[];length=0
        while missing and (not batch or length+len(missing[0])<2200):
            text=missing.pop(0);batch.append(text);length+=len(text)
        protected={};lines=[]
        for index,text in enumerate(batch):
            def protect(match):
                marker=f'ZXQKEEP{len(protected):06}ZXQ';protected[marker]=match[0];return marker
            lines.append(f'ZXQLINE{index:06}ZXQ '+_TOKEN.sub(protect,text))
        result=download('\n'.join(lines),language)
        parts=re.split(r'ZXQLINE(\d{6})ZXQ\s*',result)
        if len(parts)!=len(batch)*2+1:raise ValueError('Translation rows changed')
        indices=[int(parts[offset]) for offset in range(1,len(parts),2)]
        if sorted(indices)!=list(range(len(batch))):raise ValueError('Translated rows repeated or missing')
        for offset in range(1,len(parts),2):
            index=int(parts[offset]);text=parts[offset+1].strip()
            if not text:raise ValueError('Empty translated row')
            original=batch[index]
            markers=re.findall(r'ZXQKEEP\d{6}ZXQ',lines[index])
            if sorted(re.findall(r'ZXQKEEP\d{6}ZXQ',text))!=sorted(markers):raise ValueError('Technical identifiers changed')
            for marker in markers:text=text.replace(marker,protected[marker])
            translated[original]=text
        with _LOCK:
            try:stored=json.loads(dictionary.read_text())
            except (OSError,ValueError):stored={}
            if not isinstance(stored,dict):stored={}
            stored.update({hashlib.sha256(text.encode()).hexdigest():translated[text] for text in batch})
            _atomic_bytes(dictionary,json.dumps(stored,ensure_ascii=False).encode())
    translated={text:' '.join(translated[part] for part in parts) for text,parts in segments.items()}
    result=copy.deepcopy(data);result['language']=language;result['source_fingerprint']=fingerprint
    result['original_keys']={}
    for group in result['sections']:
        group['title']=translated[group['title']]
        rows=[]
        for key,value in group['rows']:
            result['original_keys'][translated[key]]=key
            rows.append([translated[key],translated[value]])
        group['rows']=rows
    _atomic_bytes(path,json.dumps(result,ensure_ascii=False).encode())
    return result
