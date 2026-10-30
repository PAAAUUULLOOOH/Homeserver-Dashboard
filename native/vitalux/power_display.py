"""Choose one truthful component reading without adding overlapping sources."""
from pathlib import Path
from .hardware_sensors import number


def choose(records, preferred=None):
    records=list(records)
    if not records:
        return None
    selected=next((r for r in records if r['id']==preferred),None)
    selected=selected or next((r for r in records if number(r.get('value')) is not None),None)
    selected=selected or next((r for r in records if r.get('limits')),records[0])
    result=dict(selected)
    if not result.get('limits'):
        limits=[r for r in records if r.get('limits')]
        if len(limits)==1:
            result['limits']=limits[0]['limits']
            result['limit_source']=limits[0].get('source','')
    return result


def power_records(records, preferred=None):
    """Deduplicate GPU and RAPL domains; retain genuinely different device rails."""
    powers=[r for r in records if r.get('kind')=='powers']
    packages=[r for r in powers if r.get('component')=='cpu' and r.get('primary')]
    if packages:
        powers=[r for r in powers if r.get('component')!='cpu' or r.get('primary')]
    groups={}
    for record in powers:
        component=record.get('component','')
        if component.startswith('gpu:'):
            key=(component,)
        elif record.get('domain'):
            key=(component,record.get('scope',record['domain']))
        else:
            key=(component,record['id'])
        groups.setdefault(key,[]).append(record)
    return [choose(group,preferred) for group in groups.values()]


def component_power(records, component):
    sources=power_records(r for r in records if r.get('component')==component)
    if not sources:
        return None
    if len(sources)==1:
        record=sources[0]
        # A CPU core/uncore domain alone is not a CPU-package measurement.
        if component=='cpu' and record.get('domain') and not record.get('primary'):
            return None
        return record
    independent=(component=='cpu' and all(r.get('primary') for r in sources)) or (
        component=='ram' and all(r.get('domain')=='dram' and 'package-' in r.get('scope','') for r in sources))
    if not independent or not all(number(r.get('value')) is not None for r in sources):
        return None
    return dict(id=component+':packages',component=component,kind='powers',
                value=sum(r['value'] for r in sources),limits=[],
                name=' · '.join(r['name'] for r in sources),
                source='\n'.join(r.get('source','') for r in sources))


def gpu_power(gpu):
    records=[r for r in gpu.get('hardware',[]) if r.get('kind')=='powers']
    record=choose(records,gpu.get('power_source_id'))
    if record is not None:
        return record
    value=number(gpu.get('power'))
    limit=number(gpu.get('power_limit'))
    if value is None and limit is None:
        return None
    return dict(id='gpu:driver',name=gpu.get('power_name') or gpu.get('name','GPU'),
                component='gpu:'+str(gpu.get('id','')),kind='powers',value=value,
                limits=[('Leistungsgrenze',limit)] if limit is not None else [],
                source=gpu.get('sensor_source',''))


def power_limit(record):
    limits=[(name,value) for name,value in (record or {}).get('limits',[]) if number(value) is not None]
    return limits[0][1] if len(limits)==1 else None


def disk_power(records, disk):
    paths=[Path(p) for p in (disk or {}).get('physical_paths',[])]
    if not paths:
        return None
    candidates=[]
    for record in power_records(records):
        if record.get('component')!='disks' or not record.get('device'):
            continue
        device=Path(record['device'])
        if all(device==path or device in path.parents for path in paths):
            candidates.append(record)
    # Multiple drives/rails must never masquerade as one system-drive value.
    return candidates[0] if len(candidates)==1 else None


def source_text(record):
    if not record:
        return ''
    return '\n'.join(str(v) for v in (record.get('name'),record.get('source'),record.get('limit_source')) if v)


def short_name(record):
    device=Path(record.get('device','')).name
    caption=record.get('label') or record.get('scope')
    if caption:
        return (device+' · ' if device and record.get('component')=='disks' else '')+caption
    return record.get('name','')
