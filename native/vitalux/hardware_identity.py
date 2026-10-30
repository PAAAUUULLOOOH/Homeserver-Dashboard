"""Read-only product identities; never turn a shared GPU ID into a retail model."""
import functools
import gzip
from pathlib import Path
import re


# PCI subsystem vendors identify the board partner, rather than the GPU designer.
BOARD_VENDORS = {
    '1002': 'AMD', '10de': 'NVIDIA', '8086': 'Intel', '1da2': 'SAPPHIRE',
    '1043': 'ASUS', '1462': 'MSI', '1458': 'GIGABYTE', '1849': 'ASRock',
    '148c': 'PowerColor', '1682': 'XFX', '1eae': 'XFX', '3842': 'EVGA',
    '19da': 'ZOTAC', '196e': 'PNY', '10b0': 'Gainward', '1569': 'Palit',
    '1028': 'Dell', '103c': 'HP', '17aa': 'Lenovo', '1025': 'Acer',
}

# Unambiguous RX 9000 subsystem identities, cross-checked against the upstream
# LACT hardware database:
# https://github.com/ilya-zlobintsev/LACT/blob/master/res/device_ids.json
# Deliberately omit shared variants such as Hellhound/Reaper/Red Devil.
_RX9000 = {
    ('1da2', '3490'): 'SAPPHIRE PURE Radeon RX 9070 XT',
    ('1da2', 'e489'): 'SAPPHIRE NITRO+ Radeon RX 9070 XT',
    ('1da2', 'e490'): 'SAPPHIRE PULSE Radeon RX 9070 XT',
    ('1da2', '2490'): 'SAPPHIRE PULSE Radeon RX 9070',
    ('1da2', '4499'): 'SAPPHIRE PURE Radeon RX 9070',
    ('1043', '0613'): 'ASUS TUF Gaming Radeon RX 9070 XT',
    ('1043', '7550'): 'ASUS PRIME Radeon RX 9070 XT',
    ('1043', '0614'): 'ASUS TUF Gaming Radeon RX 9070',
    ('1043', '0618'): 'ASUS PRIME Radeon RX 9070',
    ('1849', '5401'): 'ASRock Radeon RX 9070 XT Taichi',
    ('1849', '5411'): 'ASRock Radeon RX 9070 XT Taichi',
    ('1849', '5403'): 'ASRock Radeon RX 9070 XT Steel Legend',
    ('1849', '5405'): 'ASRock Radeon RX 9070 Steel Legend',
    ('1849', '5406'): 'ASRock Radeon RX 9070 Challenger',
    ('1458', '2424'): 'GIGABYTE Radeon RX 9070 XT Gaming OC',
    ('1458', '2425'): 'GIGABYTE Radeon RX 9070 Gaming OC',
    ('1458', '2426'): 'GIGABYTE Radeon RX 9070 XT Elite',
    ('1458', '2437'): 'GIGABYTE Radeon RX 9070 XT Gaming OC ICE',
    ('1eae', '8810'): 'XFX Swift Radeon RX 9070 XT',
    ('1eae', '8710'): 'XFX Swift Radeon RX 9070',
}
_PLACEHOLDERS = {'', 'unknown', 'none', 'not specified', 'not applicable',
                 'default string', 'to be filled by o.e.m.', 'to be filled by oem',
                 'system product name', 'system manufacturer', 'base board product name',
                 'base board manufacturer', 'oem', '–', '-'}


def clean(value):
    value = re.sub(r'\s+', ' ', str(value or '')).strip()[:180]
    return '' if value.casefold() in _PLACEHOLDERS else value


def manufacturer(value):
    value = clean(value)
    lower = value.lower()
    for needle, name in (('sapphire', 'SAPPHIRE'), ('asustek', 'ASUS'), ('asus', 'ASUS'),
                         ('micro-star', 'MSI'), ('gigabyte', 'GIGABYTE'),
                         ('asrock', 'ASRock'), ('powercolor', 'PowerColor'),
                         ('zotac', 'ZOTAC'), ('biostar', 'BIOSTAR'),
                         ('dell', 'Dell'), ('hewlett', 'HP'), ('hp inc', 'HP'),
                         ('lenovo', 'Lenovo'), ('genuineintel', 'Intel'), ('intel', 'Intel'),
                         ('authenticamd', 'AMD'), ('advanced micro devices', 'AMD'),
                         ('nvidia', 'NVIDIA'), ('evga', 'EVGA'), ('acer', 'Acer'),
                         ('corsair', 'Corsair'), ('kingston', 'Kingston'), ('g.skill', 'G.Skill'),
                         ('gskill', 'G.Skill'), ('crucial', 'Crucial'), ('micron', 'Micron'),
                         ('samsung', 'Samsung'), ('hynix', 'SK hynix'), ('teamgroup', 'TeamGroup'),
                         ('adata', 'ADATA'), ('patriot', 'Patriot'), ('inno3d', 'INNO3D'),
                         ('galax', 'GALAX'), ('palit', 'Palit'), ('pny', 'PNY')):
        if needle in lower:
            return name
    return value


def _read(path):
    try:
        return Path(path).read_text(errors='replace').strip()
    except OSError:
        return ''


def pci_slot(value):
    """NVML can return an eight-digit PCI domain; Linux sysfs uses four."""
    match = re.fullmatch(r'(?:[0-9a-f]{4})?([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7])',
                         str(value or '').lower())
    return match.group(1) if match else ''


def pci_sources():
    from . import profiles
    return (profiles.directory('cache')/'hardware-products/pci.ids',
            Path(__file__).resolve().parents[1]/'assets/hardware/pci.ids',
            Path('/usr/share/hwdata/pci.ids'), Path('/usr/share/misc/pci.ids'),
            Path('/usr/share/pci.ids'), Path('/usr/share/hwdata/pci.ids.gz'))


@functools.lru_cache(maxsize=8)
def _pci_table(filename, stamp):
    opener = gzip.open if str(filename).endswith('.gz') else open
    with opener(filename, 'rt', encoding='utf-8', errors='replace') as stream:
        text = stream.read(5*1024*1024)
    vendors, devices, subs = {}, {}, {}
    vendor = device = ''
    for line in text.splitlines():
        if not line or line.startswith('#'):continue
        if re.match(r'^[0-9a-f]{4}\s', line):
            vendor, name = line.split(None, 1);vendors[vendor] = name;device = ''
        elif vendor and re.match(r'^\t[0-9a-f]{4}\s', line):
            device, name = line.strip().split(None, 1);devices[vendor, device] = name
        elif vendor and device and line.startswith('\t\t'):
            parts = line.strip().split(None, 2)
            if len(parts) == 3:subs[vendor, device, parts[0], parts[1]] = parts[2]
    return vendors, devices, subs


def pci_lookup(vendor, device, subvendor='', subdevice=''):
    partner = model = chip = ''
    for filename in pci_sources():
        try:
            vendors, devices, subs = _pci_table(str(filename), filename.stat().st_mtime_ns)
        except (OSError,ValueError):
            continue
        partner = partner or manufacturer(vendors.get(subvendor, ''))
        model = model or clean(subs.get((vendor, device, subvendor, subdevice), ''))
        chip = chip or clean(devices.get((vendor, device), ''))
    return partner, model, chip


def _pci_names(vendor, device, subvendor, subdevice):
    return pci_lookup(vendor, device, subvendor, subdevice)[:2]


def model_name(value):
    value = clean(value)
    brackets = re.findall(r'\[([^]]+)\]', value)
    return brackets[-1] if brackets else value


def retail_model(value, partner):
    value = model_name(value)
    if re.search(r'[/|]|\bor\b', value, re.I):return ''
    generic = {'amd','nvidia','intel','radeon','geforce','graphics','card','gpu','series',
               'rx','rtx','gtx','gt','xt','xtx','ti','super','gre','arc','navi','polaris',
               'vega','gddr','gb','mb','oc','g','pro','quadro','rt','a','b','vram'}
    generic.update(re.findall(r'[a-z]+', (partner or '').lower()))
    return value if set(re.findall(r'[a-z]+', value.lower())) - generic else ''


def gpu_identity(gpu):
    path = gpu.get('device_path')
    if not path:
        slot = pci_slot(gpu.get('pci_slot'))
        path = '/sys/bus/pci/devices/' + slot if slot else ''
    raw_ids = [_read(Path(path) / field).lower().removeprefix('0x') if path else ''
               for field in ('vendor', 'device', 'subsystem_vendor', 'subsystem_device')]
    ids = tuple(value if re.fullmatch(r'[0-9a-f]{4}', value) else '' for value in raw_ids)
    vendor, device, subvendor, subdevice = ids
    db_vendor, db_model = _pci_names(*ids) if all(ids) else ('', '')
    partner = BOARD_VENDORS.get(subvendor) or db_vendor
    model = _RX9000.get((subvendor, subdevice), '') if (vendor, device) == ('1002', '7550') else ''
    # Database names containing alternatives are useful descriptions, not an
    # exact retail identity. Keep the driver name in that case.
    if not model and db_model:model = retail_model(db_model, partner)
    if not model:
        for field in ('product_name', 'board_name', 'name'):
            value = clean(gpu.get(field))
            if partner and partner.lower() in value.lower():
                model = retail_model(value, partner)
                if model:break
    chip_model = model_name(db_model) if db_model and not re.search(r'[/|]', db_model) else ''
    reported=clean(gpu.get('name'))
    if not chip_model and vendor and device and (not reported or '/' in reported or
            reported.lower() in ('gpu','amd grafik','intel grafik','nvidia grafik')):
        chip_model=model_name(pci_lookup(vendor,device)[2])
    return {'board_vendor': partner or '', 'board_model': model,
            'pci_ids': ':'.join(ids) if all(ids) else '',
            'identified_name': model or chip_model,
            'product': {'kind': 'gpu', 'vendor': partner or '', 'model': model,
                        'revision': '', 'exact': bool(partner and model),
                        'pci_ids': ':'.join(ids) if all(ids) else '', 'reported_model': gpu.get('name', '')}}


def board_identity(vendor, model, revision=''):
    vendor, model, revision = manufacturer(vendor), clean(model), clean(revision)
    return {'kind': 'mainboard', 'vendor': vendor, 'model': model,
            'revision': revision, 'exact': bool(vendor and model)}
