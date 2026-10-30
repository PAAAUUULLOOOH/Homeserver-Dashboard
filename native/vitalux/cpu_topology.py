"""Complete, numerically ordered Linux CPU identities, including offline CPUs."""
import functools
from pathlib import Path
import re


def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ''


def cpu_ids(value):
    result = set()
    for part in value.split(','):
        if re.fullmatch(r'\d+(?:-\d+)?', part):
            bounds = [int(x) for x in part.split('-')]
            if max(bounds) <= 65535:
                result.update(range(bounds[0], bounds[-1] + 1))
    return sorted(result)


@functools.lru_cache(maxsize=16)
def _topology(ids, sysroot):
    result = []
    for ident in ids:
        base = Path(sysroot) / f'cpu{ident}' / 'topology'
        core, package = _read(base/'core_id'), _read(base/'physical_package_id')
        result.append({'id': ident, 'core': int(core) if core.isdigit() else None,
                       'package': int(package) if package.isdigit() else None})
    return result


def logical_cpus(readings, sysroot='/sys/devices/system/cpu', procstat='/proc/stat'):
    # psutil's per-CPU readings follow /proc/stat, whose CPU numbers may have
    # gaps after hotplug. Never relabel CPU 8 as CPU 4 just by enumerating.
    measured = sorted(int(x) for x in re.findall(r'^cpu(\d+)\s', _read(procstat), re.M))
    online = cpu_ids(_read(Path(sysroot)/'online'))
    if len(measured) != len(readings):
        measured = online if len(online) == len(readings) else list(range(len(readings)))
    present = cpu_ids(_read(Path(sysroot)/'present')) or measured
    ids = tuple(sorted(set(present) | set(measured)))
    values = dict(zip(measured, readings))
    online = set(online or measured)
    return [dict(row, usage=values.get(row['id']), online=row['id'] in online)
            for row in _topology(ids, str(sysroot))]
