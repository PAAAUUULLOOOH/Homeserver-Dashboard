"""Small local app-event history; disk writes run outside the GUI thread."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
from pathlib import Path
from threading import RLock
import time

from . import profiles, logfiles
from .i18n import tr

_lock = RLock()
_writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vitalux-events')
_path = None
_records = deque(maxlen=100)
_revision = 0
KINDS = {'warning', 'update_failed', 'renderer_fallback'}
METRICS = {'cpu_temp': 'CPU-Temperatur', 'gpu_temp': 'GPU-Temperatur',
           'ram_usage': 'RAM-Auslastung', 'disk_usage': 'Systemlaufwerk-Belegung'}


def _load():
    global _path, _revision
    path = profiles.directory('state')/'events.jsonl'
    if path == _path:return path
    _path = path
    _records.clear()
    for file in (Path(str(path)+'.1'), path):
        for line in logfiles.tail(file).splitlines():
            try:
                row = json.loads(line)
                if (isinstance(row, dict) and row.get('kind') in KINDS
                        and isinstance(row.get('time'), (int, float)) and math.isfinite(row['time'])):
                    _records.append(row)
            except (ValueError, TypeError, OverflowError):pass
    _revision += 1
    return path


def _save(path, row):
    try:logfiles.append(path, json.dumps(row, ensure_ascii=False)+'\n')
    except OSError:pass


def record(kind, **details):
    global _revision
    if kind not in KINDS:return
    row = dict(time=time.time(), kind=kind)
    if kind == 'warning':
        if details.get('metric') not in METRICS:return
        for key in ('value', 'limit'):
            value = details.get(key)
            if type(value) not in (int, float):return
            row[key] = round(value, 2)
        row['metric'] = details['metric']
    elif kind == 'update_failed':
        row['stage'] = details.get('stage') if details.get('stage') in ('check', 'install', 'restart') else 'install'
    with _lock:
        path = _load()
        if _records and row['time']-_records[-1]['time'] < 60:
            if {k:v for k,v in row.items() if k!='time'} == {k:v for k,v in _records[-1].items() if k!='time'}:
                return
        _records.append(row)
        _revision += 1
        _writer.submit(_save, path, row)


def snapshot(limit=5):
    with _lock:
        _load()
        return _revision, [dict(row) for row in list(_records)[-limit:][::-1]]


def describe(row):
    kind = row.get('kind')
    if kind == 'renderer_fallback':return tr('CPU-Rendering aktiviert')
    if kind == 'update_failed':
        stage = row.get('stage')
        if not isinstance(stage, str):stage = 'install'
        return tr({'check': 'Updateprüfung fehlgeschlagen', 'install': 'Updateinstallation fehlgeschlagen',
                   'restart': 'Update-Neustart fehlgeschlagen'}.get(stage, 'Updateinstallation fehlgeschlagen'))
    if kind == 'warning':
        metric = row.get('metric')
        if not isinstance(metric, str) or metric not in METRICS:return tr('Warnwert überschritten')
        try:
            unit = '°C' if metric.endswith('_temp') else '%'
            return f"{tr(METRICS[metric])}: {row['value']:.0f}{unit} ≥ {row['limit']:.0f}{unit}"
        except (KeyError, TypeError, ValueError):return tr('Warnwert überschritten')
    return ''


def timestamp(row):
    try:return datetime.fromtimestamp(row['time']).astimezone().strftime('%d.%m. %H:%M')
    except (KeyError, ValueError, OverflowError, OSError):return '–'


def flush():
    """Drain queued writes for export/controlled validation, never per sample."""
    _writer.submit(lambda: None).result(timeout=5)
