"""Read-only Linux sensor discovery and current power readings (no Qt/root).

Values retain their kernel device/channel identity. Overlapping RAPL domains,
GPU rails and board channels are never summed into a purported PC total.
"""
import math
from pathlib import Path
import re
import struct
import time
import xml.etree.ElementTree as ET


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def read(path):
    try:
        return Path(path).read_text(encoding='utf-8').strip()
    except (OSError, ValueError):
        return ''


def scaled(path, divisor=1, minimum=0, maximum=1e9):
    value = number(read(path))
    if value is None:
        return None
    value /= divisor
    return value if minimum <= value <= maximum else None


class RaplReader:
    def __init__(self, sysroot='/sys'):
        self.root = Path(sysroot)
        self.previous = {}

    def sample(self, now):
        records, seen = [], set()
        base = self.root/'class/powercap'
        zone_pattern = re.compile(r'(?:intel|amd)-rapl(?:-mmio)?(?::\d+)*$')
        pending = sorted(base.glob('*'), key=lambda p: ('-mmio' in p.name, p.name), reverse=True)
        visited = set()
        while pending:
            entry = pending.pop()
            if not zone_pattern.fullmatch(entry.name) or not entry.is_dir():
                continue
            try:
                zone=entry.resolve()
                children=list(entry.iterdir())
            except (OSError,RuntimeError):
                continue
            if zone in visited:
                continue
            visited.add(zone)
            # Never recursively follow sysfs device/subsystem symlinks.
            pending.extend(sorted((p for p in children if zone_pattern.fullmatch(p.name)),
                                  key=lambda p: p.name, reverse=True))
            path = zone/'energy_uj'
            if path in seen:
                continue
            seen.add(path)
            name = read(zone/'name')
            def counter(filename):
                text=read(filename)
                return int(text) if text.isascii() and text.isdigit() and len(text)<=20 and int(text)<=2**64-1 else None
            current=counter(path)
            maximum=counter(zone/'max_energy_range_uj')
            old = self.previous.pop(path, None)
            if not name:
                continue
            readable=current is not None and maximum is not None and maximum>0 and current<=maximum
            if readable:
                self.previous[path] = (current, now, maximum)
            limits = []
            for item in sorted(zone.glob('constraint_*_power_limit_uw')):
                watts = scaled(item, 1e6)
                prefix = item.name.removesuffix('_power_limit_uw')
                caption = read(zone/(prefix+'_name'))
                if watts is not None and caption:
                    # The constraint name, never its numeric index, defines PL1/PL2.
                    caption = {'long_term': 'PL1', 'short_term': 'PL2'}.get(caption, caption)
                    limits.append((caption, watts))
            if not readable and not limits:
                continue
            watts, interval = None, None
            if readable and old and old[2] == maximum and 0 < now-old[1] <= 30:
                delta = current-old[0]
                if delta < 0:
                    # A reset elsewhere in the range is not a counter wrap.
                    delta = delta+maximum if old[0] >= maximum*.8 and current <= maximum*.2 else -1
                if delta >= 0:
                    interval = now-old[1]
                    candidate = delta/1e6/interval
                    ceiling = max((v for _, v in limits if v>0), default=2000)*10
                    if 0 <= candidate <= ceiling:
                        watts = candidate
            package = bool(re.fullmatch(r'package-\d+', name))
            parent_name=read(zone.parent/'name')
            caption=(parent_name+' · ' if parent_name and parent_name!=name else '')+name
            records.append(dict(id=str(path), name=('RAPL MMIO · ' if '-mmio' in entry.name else 'RAPL · ')+caption, value=watts,
                kind='powers', unit='W', component='ram' if name.lower() == 'dram' else 'cpu',
                device=str(zone), source=str(path), limits=limits, interval=interval,
                primary=package, domain=name, scope=('CPU-Package · '+name) if package else caption))
        packages={}
        for record in records:
            if record['primary']:
                previous=packages.get(record['domain'])
                if previous is None:
                    packages[record['domain']]=record
                elif previous['value'] is None and record['value'] is not None:
                    previous['primary']=False
                    packages[record['domain']]=record
                else:
                    record['primary']=False
        for key in set(self.previous)-seen:
            self.previous.pop(key, None)
        return records


def hwmon_readings(sysroot='/sys', gpus=()):
    root = Path(sysroot)
    gpu_devices = {str(Path(g['device_path']).resolve()): g for g in gpus if g.get('device_path')}
    disks = [p.resolve() for p in (root/'block').glob('*/device')]
    network = [p.resolve() for p in (root/'class/net').glob('*/device')]
    records, seen = [], set()
    for hw in sorted((root/'class/hwmon').glob('hwmon*')):
        chip = read(hw/'name') or hw.name
        device = (hw/'device').resolve() if (hw/'device').exists() else hw.resolve().parent.parent
        gpu = gpu_devices.get(str(device))
        if gpu:
            component = 'gpu:'+gpu['id']
        elif chip.lower() in ('coretemp', 'k10temp', 'zenpower', 'cpu_thermal', 'amd_energy'):
            component = 'cpu'
        elif chip.lower() in ('jc42', 'spd5118'):
            component = 'ram'
        elif chip.lower().startswith(('nvme', 'drivetemp')) or any(device == p or device in p.parents for p in disks):
            component = 'disks'
        elif any(device == p for p in network):
            component = 'network'
        else:
            component = 'system'
        for kind, pattern, divisor, unit, low, high in (
                ('temps', 'temp*_input', 1000, '°C', -100, 300),
                ('fans', 'fan*_input', 1, 'U/min', 0, 100000),
                ('voltages', 'in*_input', 1000, 'V', 0, 1000),
                ('frequencies', 'freq*_input', 1e6, 'MHz', 0, 1e6),
                ('powers', 'power*_input', 1e6, 'W', 0, 1e6)):
            files = list(hw.glob(pattern))
            if kind == 'powers':
                # Prefer instantaneous input; average is a fallback on the same rail.
                files += list(hw.glob('power*_average'))
                files += list(hw.glob('power*_cap'))
            for path in sorted(files, key=lambda p: (2 if p.stem.endswith('_cap') else 1 if p.stem.endswith('_average') else 0, p.name)):
                prefix = path.name.rsplit('_', 1)[0]
                identity = str(hw.resolve()/prefix)
                if identity in seen or read(hw/(prefix+'_fault')) == '1' or read(hw/(prefix+'_enable')) == '0':
                    continue
                value = None if path.stem.endswith('_cap') else scaled(path, divisor, low, high)
                limit = scaled(hw/(prefix+'_cap'), 1e6) if kind == 'powers' else None
                if value is None and limit is None:
                    continue
                if value is None and not path.stem.endswith('_cap'):
                    continue  # Try a readable average before retaining just the limit.
                seen.add(identity)
                caption = read(hw/(prefix+'_label')) or prefix
                # Chip and physical device stay distinguishable on multi-GPU/socket hosts.
                title = f'{chip} · {device.name} · {caption}'
                limits = []
                if kind == 'powers':
                    if limit is not None:
                        limits.append(('Leistungsgrenze', limit))
                records.append(dict(id=identity, name=title, label=caption, channel=prefix,
                    value=value, kind=kind, unit=unit, component=component, device=str(device),
                    source=str(path), limits=limits, primary=False,
                    high=scaled(hw/(prefix+'_max'), divisor, low, high),
                    critical=scaled(hw/(prefix+'_crit'), divisor, low, high)))
    if not any(r['kind']=='temps' for r in records):
        for zone in sorted((root/'class/thermal').glob('thermal_zone*')):
            value=scaled(zone/'temp',1000,-100,300)
            caption=read(zone/'type')
            if value is not None and caption:
                records.append(dict(id=str(zone.resolve()/'temp'),name=caption,value=value,
                    kind='temps',unit='°C',component='cpu' if 'cpu' in caption or 'pkg' in caption else 'system',
                    device=str(zone.resolve()),source=str(zone/'temp')))
    return records


def amd_metrics(data):
    """Decode only documented v1 prefixes; unknown revisions/APU layouts are skipped.

    Layout: Linux drivers/gpu/drm/amd/include/kgd_pp_interface.h.
    In particular v1.4 moves fields: it must never use v1.1 offsets.
    """
    if len(data) < 4:
        return {}
    size, major, minor = struct.unpack_from('<HBB', data)
    minimum = {1: 96, 2: 104, 3: 120, 4: 24, 5: 24}
    if major != 1 or minor not in minimum or size < minimum[minor] or len(data) < size:
        return {}
    def u16(offset, maximum=65534):
        value = struct.unpack_from('<H', data, offset)[0]
        return value if value != 65535 and value <= maximum else None
    if minor <= 3:
        result = dict(temp=u16(4, 300), hotspot=u16(6, 300), vram_temp=u16(8, 300),
            usage=u16(16, 100), memory_busy=u16(18, 100), video_busy=u16(20, 100),
            socket_power=u16(22), clock=u16(54), clock_mem=u16(58), fan_rpm=u16(72))
        if minor == 3:
            result['voltage'] = u16(106, 3000)
            bits = struct.unpack_from('<Q', data, 112)[0]
            if bits != 0xffffffffffffffff:
                result['throttle_flags'] = hex(bits)
        return result
    video = [u16(offset, 100) for offset in (16, 18, 20, 22)]
    # Separate VCN instances are not separate encoder/decoder readings.
    return dict(hotspot=u16(4, 300), vram_temp=u16(6, 300), socket_power=u16(10),
                usage=u16(12, 100), memory_busy=u16(14, 100),
                **{f'video_busy_{i}': value for i, value in enumerate(video) if value is not None})


def nvidia_details(xml):
    """Optional nvidia-smi XML fields, keyed by the GPU's UUID."""
    try:
        document = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    result = {}
    for gpu in document.findall('gpu'):
        uuid = gpu.findtext('uuid')
        if not uuid:
            continue
        def value(*paths):
            for path in paths:
                text = gpu.findtext(path, '').split()
                candidate = number(text[0]) if text else None
                if candidate is not None and candidate >= 0:
                    return candidate
            return None
        readings = dict(power_limit=value('gpu_power_readings/enforced_power_limit', 'power_readings/enforced_power_limit', 'power_readings/power_limit'),
            vram_temp=value('temperature/memory_temp'), memory_busy=value('utilization/memory_util'),
            encoder_busy=value('utilization/encoder_util'), decoder_busy=value('utilization/decoder_util'))
        pci_bus = gpu.findtext('pci/pci_bus_id') or gpu.get('id')
        if pci_bus:
            readings['pci_slot'] = pci_bus
        reasons = []
        for parent in ('clocks_event_reasons', 'clocks_throttle_reasons'):
            node = gpu.find(parent)
            if node is not None:
                for item in node:
                    if item.text and item.text.strip().lower() == 'active':
                        reasons.append(re.sub(r'^clocks_(?:event|throttle)_reasons?_', '', item.tag).replace('_', ' '))
        if reasons:
            readings['throttle_reasons'] = ', '.join(reasons)
        result[uuid] = readings
    return result


class HardwareMonitor:
    def __init__(self, sysroot='/sys'):
        self.sysroot = Path(sysroot)
        self.rapl = RaplReader(sysroot)

    def reset_baselines(self):
        """Start a fresh energy-counter baseline after missed samples."""
        self.rapl.previous.clear()

    def sample(self, gpus, now=None):
        now = time.monotonic() if now is None else now
        records = hwmon_readings(self.sysroot, gpus) + self.rapl.sample(now)
        for gpu in gpus:
            ident = 'gpu:'+gpu['id']
            own = [r for r in records if r['component'] == ident]
            if gpu.get('device_path'):
                try:
                    data = (Path(gpu['device_path'])/'gpu_metrics').read_bytes()
                except OSError:
                    data = b''
                for key, value in amd_metrics(data).items():
                    if gpu.get(key) is None and value is not None:
                        gpu[key] = value
            memory = next((r['value'] for r in own if r['kind'] == 'temps' and any(k in r.get('label', '').lower() for k in ('mem', 'vram'))), None)
            if memory is not None:
                gpu['vram_temp'] = memory
            represented = []
            for r in own:
                label = r.get('label', '').lower()
                kind, channel = r['kind'], r.get('channel')
                field = ('hotspot' if any(k in label for k in ('junction', 'hotspot', 'hot spot')) else
                         'vram_temp' if any(k in label for k in ('mem', 'vram')) else
                         'temp' if label == 'edge' or channel == 'temp1' else None) if kind == 'temps' else (
                         'fan_rpm' if kind == 'fans' and channel == 'fan1' else
                         'voltage' if kind == 'voltages' and channel == 'in0' else None)
                if field:
                    if number(gpu.get(field)) is None:
                        gpu[field]=r['value']*(1000 if field=='voltage' else 1)
                    if number(gpu.get(field)) is not None:
                        represented.append(r['id'])
            gpu['represented_sensors'] = represented
            for key,value in list(gpu.items()):
                if re.fullmatch(r'video_busy_\d+',key) and number(value) is not None:
                    records.append(dict(id=ident+':'+key,name='VCN '+key.rsplit('_',1)[1],value=value,
                        kind='activity',unit='%',component=ident,source='AMDGPU gpu_metrics'))
            busy = scaled(Path(gpu['device_path'])/'mem_busy_percent', maximum=100) if gpu.get('device_path') else None
            if busy is not None:
                gpu['memory_busy'] = busy
            powers = [r for r in own if r['kind'] == 'powers']
            if not any(number(r['value']) is not None for r in powers) and number(gpu.get('power')) is not None:
                limits = [('Leistungsgrenze', gpu['power_limit'])] if number(gpu.get('power_limit')) is not None else []
                record = dict(id=ident+':power', name=gpu['name'], value=gpu['power'], kind='powers',
                    component=ident, unit='W', limits=limits, source=gpu.get('sensor_source', ''), scope='GPU-Leistung (Treiber)')
                records.append(record)
                powers.append(record)
            if number(gpu.get('socket_power')) is not None:
                # Keep a documented socket measurement separate from hwmon's ASIC/PPT rail.
                record = dict(id=ident+':socket', name=gpu['name']+' · GPU-Socket', value=gpu['socket_power'],
                    kind='powers', component=ident, unit='W', limits=[], source='AMDGPU gpu_metrics', scope='GPU-Socket')
                records.append(record)
                if not any(number(r['value']) is not None for r in powers):
                    powers.append(record)
            if powers:
                chosen=next((r for r in powers if number(r['value']) is not None),powers[0])
                if not chosen.get('limits') and number(gpu.get('power_limit')) is not None:
                    chosen['limits'] = [('Leistungsgrenze', gpu['power_limit'])]
                gpu['power'] = chosen['value']
                gpu['power_name'] = chosen.get('scope') or chosen['name']
                gpu['power_source_id'] = chosen['id']
        for gpu in gpus:
            gpu['hardware'] = [r for r in records if r['component'] == 'gpu:'+gpu['id']]
        return records


def sensor_groups(records):
    return {kind: [r for r in records if r['kind'] == kind and number(r['value']) is not None]
            for kind in ('temps', 'fans', 'voltages', 'powers', 'frequencies')}


def primary_power(records, component):
    candidates = [r for r in records if r['component'] == component and r['kind'] == 'powers']
    packages = [r for r in candidates if r.get('primary')]
    # Only independent CPU package counters can safely be added.
    if packages:
        return sum(r['value'] for r in packages) if all(number(r['value']) is not None for r in packages) else None
    valid = [r for r in candidates if number(r['value']) is not None]
    return valid[0]['value'] if len(valid) == 1 else None


def block_devices(device, sysroot='/sys'):
    """Resolve physical block paths in the sampling worker, including dm/LVM."""
    root=Path(sysroot)/'class/block'
    try:
        pending=[Path(device).resolve().name]
    except (OSError,RuntimeError):
        return []
    seen=set();leaves=[]
    while pending and len(seen)<64:
        name=pending.pop()
        if name in seen:
            continue
        seen.add(name)
        block=root/name
        if not block.exists():
            return []
        try:
            slaves=list((block/'slaves').iterdir()) if (block/'slaves').is_dir() else []
            if slaves:
                pending.extend(p.name for p in slaves)
            else:
                leaves.append(str(block.resolve()))
        except (OSError,RuntimeError):
            return []
    return sorted(set(leaves)) if not pending else []
