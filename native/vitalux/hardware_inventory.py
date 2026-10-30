"""Unprivileged CPU and SMBIOS module identities; no probing or guessed brands."""
import functools
from pathlib import Path
import re
import shutil
import struct
import subprocess

from .hardware_identity import clean, manufacturer


@functools.lru_cache(maxsize=1)
def cpu_product():
    try:text = Path('/proc/cpuinfo').read_text(errors='replace').split('\n\n')[0]
    except OSError:text = ''
    fields = {k.strip():v.strip() for line in text.splitlines() if ':' in line for k,v in [line.split(':',1)]}
    vendor = manufacturer(fields.get('vendor_id', ''))
    model = clean(fields.get('model name', ''))
    exact = bool(vendor and model and not re.search(r'\b(QEMU|KVM|Virtual|Common)\b',model,re.I))
    return dict(kind='cpu',vendor=vendor,model=model,revision='',exact=exact)


_MEMORY_TYPES = {0x12:'DDR',0x13:'DDR2',0x18:'DDR3',0x1a:'DDR4',0x1b:'LPDDR',
                 0x1c:'LPDDR2',0x1d:'LPDDR3',0x1e:'LPDDR4',0x22:'DDR5',0x23:'LPDDR5'}


def parse_smbios(raw):
    modules = []
    offset = 0
    while offset + 4 <= len(raw):
        kind, length = raw[offset], raw[offset+1]
        if length < 4 or offset + length > len(raw):break
        end = raw.find(b'\0\0', offset+length)
        if end < 0:break
        body = raw[offset:offset+length]
        strings = raw[offset+length:end].decode('utf-8','replace').split('\0')
        def string(at):
            index = body[at] if at < length else 0
            return clean(strings[index-1]) if 0 < index <= len(strings) else ''
        def number(at, fmt='<H'):
            return struct.unpack_from(fmt, body, at)[0] if at+struct.calcsize(fmt)<=length else 0
        if kind == 17 and length >= 0x15:
            size = number(0x0c)
            if size not in (0,0xffff):
                capacity = ((number(0x1c,'<I') & 0x7fffffff)*1024*1024 if size==0x7fff else
                            (size&0x7fff)*(1024 if size&0x8000 else 1024*1024))
                vendor, part = manufacturer(string(0x17)), string(0x1a)
                if not capacity:
                    offset=end+2
                    continue
                speed=number(0x20) or number(0x15)
                if speed==65535:speed=0
                modules.append(dict(vendor=vendor,model=part,capacity=capacity,
                    memory_type=_MEMORY_TYPES.get(body[0x12],''),
                    speed=speed,slot=string(0x10),
                    product=dict(kind='ram',vendor=vendor,model=part,revision='',exact=bool(vendor and part))))
        offset = end+2
        if kind == 127:break
    return modules


def parse_dmidecode(text):
    modules = []
    for block in re.split(r'\n\s*\n', text):
        if 'Memory Device' not in block:continue
        fields = dict((key.strip(),value.strip()) for line in block.splitlines() if ':' in line for key,value in [line.split(':',1)])
        size = re.fullmatch(r'(\d+)\s*(kB|MB|GB|TB)',fields.get('Size',''),re.I)
        if not size:continue
        scale = {'kb':1024,'mb':1024**2,'gb':1024**3,'tb':1024**4}[size[2].lower()]
        vendor,part = manufacturer(fields.get('Manufacturer')),clean(fields.get('Part Number'))
        speed = re.search(r'\d+',fields.get('Configured Memory Speed') or fields.get('Speed') or '')
        modules.append(dict(vendor=vendor,model=part,capacity=int(size[1])*scale,
            memory_type=clean(fields.get('Type')),speed=int(speed[0]) if speed else 0,
            slot=clean(fields.get('Locator')),
            product=dict(kind='ram',vendor=vendor,model=part,revision='',exact=bool(vendor and part))))
    return modules


@functools.lru_cache(maxsize=1)
def memory_modules():
    try:
        with open('/sys/firmware/dmi/tables/DMI','rb') as stream:raw = stream.read(2*1024*1024)
        result = parse_smbios(raw)
        if result:return result
    except OSError:pass
    if shutil.which('dmidecode'):
        try:
            run = subprocess.run(['dmidecode','--type','17'],capture_output=True,text=True,timeout=3)
            if run.returncode==0:return parse_dmidecode(run.stdout)
        except (OSError,subprocess.TimeoutExpired):pass
    return []
