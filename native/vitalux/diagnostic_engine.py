"""Read-only, explicit-on-demand Linux diagnostic checks for Vitalux.

No system modifications, privilege escalation, external telemetry or automatic
network access. Unsupported observations stay explicitly unknown.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import psutil

from . import __version__
from . import settings, profiles

STATE_DIR = profiles.directory('state')
BASELINE = STATE_DIR / 'change-radar.json'
BLACKBOX = STATE_DIR / 'diagnostic-blackbox.jsonl'


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def numeric(value):
    try:
        n = float(value)
        return n if n == n and abs(n) < 1e12 else None
    except (TypeError, ValueError, OverflowError):
        return None


def shown(v, unit='', digits=1):
    f = numeric(v)
    return f'{f:.{digits}f}{unit}' if f is not None else 'nicht verfügbar'


def read_text(p):
    try:
        return Path(p).read_text(encoding='utf-8', errors='replace').strip()
    except (OSError, UnicodeError):
        return None


def cmd(command, timeout=3):
    if not shutil.which(command[0]):
        return None, f'{command[0]} nicht installiert'
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=timeout, check=False)
        out = completed.stdout.strip()[:16000]
        if completed.returncode:
            return None, (completed.stderr.strip() or f'Exit {completed.returncode}')[:320]
        return out, None
    except (subprocess.SubprocessError, OSError) as exc:
        return None, str(exc)[:320]


def gpu(sample):
    gpus = (sample or {}).get('gpus') or []
    return next((g for g in gpus if isinstance(g, dict)), {})


def systemcheck(sample):
    cpu = (sample or {}).get('cpu') or {}
    ram = (sample or {}).get('ram') or {}
    g = gpu(sample)
    fs = (sample or {}).get('disks') or []
    root = next((disk for disk in fs if disk.get('mount') == '/'), {})
    lines = [f'SYSTEMCHECK · {now()}', 'Messwerte beschreiben den aktuellen Zustand, keine vollständige Hardwareprüfung.', '',
             f'Betriebssystem: {platform.platform()}', f'Kernel: {platform.release()}',
             f'CPU-Auslastung: {shown(cpu.get("usage"), "%")}',
             f'GPU-Auslastung: {shown(g.get("usage"), "%")}',
             f'RAM-Auslastung: {shown(ram.get("percent"), "%")}',
             f'CPU-Temperatur: {shown(cpu.get("temp"), " °C")}',
             f'GPU-Temperatur: {shown(g.get("temp"), " °C")}',
             f'GPU-Hotspot: {shown(g.get("hotspot"), " °C")}',
             f'Systemlaufwerk-Belegung: {shown(root.get("percent"), "%")}', '']
    thresholds = [('CPU-Temperatur', cpu.get('temp'), settings.get('cpu_temp', 90), '°C'),
                  ('GPU-Temperatur', g.get('temp'), settings.get('gpu_temp', 90), '°C'),
                  ('RAM', ram.get('percent'), settings.get('ram_usage', 90), '%'),
                  ('Systemlaufwerk', root.get('percent'), settings.get('disk_usage', 95), '%')]
    warnings = [f'{name}: {shown(v, unit)} ≥ Warnwert {limit}{unit}' for name, v, limit, unit in thresholds
                if numeric(v) is not None and numeric(limit) is not None and numeric(v) >= numeric(limit)]
    if warnings:
        lines += ['ÜBERSCHRITTENE KONFIGURIERTE WARNWERTE'] + warnings
    else:
        lines += ['Keine Überschreitung in den verfügbaren Messwerten festgestellt.',
                  'Das ist ausdrücklich keine Freigabe oder Garantie für die Hardware.']
    return '\n'.join(lines)


def crashes(_sample=None):
    out, err = cmd(['journalctl', '--no-pager', '--boot', '--priority=0..3',
                    '--lines=40', '--output=short-iso'], timeout=6)
    if out is None:
        return 'CRASH INVESTIGATOR\nSystemjournal nicht auswertbar: ' + (err or 'nicht verfügbar') + '\nJe nach Distribution fehlen Leserechte.'
    if not out or out.lower().startswith('-- no entries --'):
        return ('CRASH INVESTIGATOR\nKeine kritischen Journalmeldungen im verfügbaren Bootprotokoll.\n'
                'Nicht alle Abstürze erscheinen zwangsläufig im Journal.')
    interesting = ('amdgpu', 'gpu reset', 'pcie', 'nvme', 'i/o error', 'segfault', 'oom', 'kernel panic')
    entries = out.splitlines()
    highlights = [line for line in entries if any(term in line.lower() for term in interesting)]
    return '\n'.join(['CRASH INVESTIGATOR · aktueller Boot',
                      'Journalmeldungen (Priorität Fehler und kritischer). Keine automatische Ursachenfeststellung.', '',
                      'MÖGLICHE HARDWARE-/TREIBERHINWEISE:'] +
                     (highlights[-20:] or ['Keine der gesuchten Signaturen gefunden.']) +
                     ['', 'WEITERE FEHLERMELDUNGEN:'] + entries[-35:])


def displays(_sample=None):
    ses = os.environ.get('XDG_SESSION_TYPE', 'unbekannt')
    lines = ['DISPLAYDOCTOR', f'Sitzung: {ses}', f'Desktop: {os.environ.get("XDG_CURRENT_DESKTOP", "nicht verfügbar")}',
             f'Wayland-Socket: {"vorhanden" if os.environ.get("WAYLAND_DISPLAY") else "nicht festgestellt"}', '']
    connectors = []
    drm_path = Path('/sys/class/drm')
    if drm_path.is_dir():
        for p in sorted(drm_path.iterdir()):
            if not (p / 'status').is_file():
                continue
            state = read_text(p / 'status')
            if state != 'connected':
                continue
            modes = (read_text(p / 'modes') or '').splitlines()
            enabled = read_text(p / 'enabled')
            lines.extend([f'{p.name}: verbunden', f'  DRM enabled: {enabled or "unbekannt"}',
                          f'  Unterstützte DRM-Modi (Auswahl): {", ".join(modes[:8]) or "nicht verfügbar"}'])
            connectors.append(p.name)
    if not connectors:
        lines.append('Kein angeschlossener DRM-Connector auslesbar. (Container/VM oder eingeschränkte Rechte möglich.)')
    if shutil.which('kscreen-doctor'):
        out, err = cmd(['kscreen-doctor', '-o'], timeout=4)
        if out:
            lines += ['', 'KSCREEN-DOCTOR (Anzeigezustand):', out[:5200]]
        else:
            lines.append(f'KScreen-Auskunft: {err or "nicht verfügbar"}')
    lines += ['', 'HDR, VRR, Bildfarbtiefe und die tatsächliche XWayland-Bildausgabe sind',
              'nicht mit einem allgemeinen DRM-Status allein verlässlich nachweisbar.',
              'Der aktive Spiel-Renderingpfad muss separat im Spiel/Compositor geprüft werden.']
    return '\n'.join(lines)


def _pcie_devices():
    devices = []
    root = Path('/sys/bus/pci/devices')
    if not root.is_dir():
        return devices
    for p in sorted(root.iterdir()):
        cls = read_text(p / 'class') or ''
        if not cls.startswith(('0x0300', '0x0302', '0x0380')):
            continue
        vendor = read_text(p / 'vendor') or '?'
        device = read_text(p / 'device') or '?'
        d = {'address': p.name, 'vendor': vendor, 'device': device, 'current_speed': read_text(p / 'current_link_speed'),
             'current_width': read_text(p / 'current_link_width'), 'max_speed': read_text(p / 'max_link_speed'),
             'max_width': read_text(p / 'max_link_width')}
        devices.append(d)
    return devices


def pcie(sample):
    devices = _pcie_devices()
    lines = ['PCIE GUARDIAN', 'Link-Zustände können im Leerlauf durch Energiesparen abweichen.\n',
             f'GPU-Auslastung zum Messzeitpunkt: {shown(gpu(sample).get("usage"), "%")}']
    if not devices:
        return '\n'.join(lines + ['Keine GPU-PCIe-Verbindungsdaten verfügbar.'])
    for d in devices:
        lines += ['', f'GPU: {d["address"]} · {d["vendor"]}:{d["device"]}',
                  f'  Aktuell: {d["current_speed"] or "nicht verfügbar"} ×{d["current_width"] or "?"}',
                  f'  Maximal laut Gerät: {d["max_speed"] or "nicht verfügbar"} ×{d["max_width"] or "?"}']
        u = numeric(gpu(sample).get('usage'))
        c = numeric(d['current_width'])
        m = numeric(d['max_width'])
        if c is not None and m is not None and c < m:
            if u is not None and u >= 70:
                lines.append('  HINWEIS: Geringere Linkbreite bei hoher GPU-Last – erneut prüfen.')
            else:
                lines.append('  HINWEIS: Geringere Linkbreite kann bei Leerlauf normal sein.')
    lines.append('\nPCIe-Generation wird aus der vom Kernel gemeldeten Linkgeschwindigkeit abgeleitet, nicht aus dem Mainboardnamen.')
    return '\n'.join(lines)


def thermal(sample):
    cpu = (sample or {}).get('cpu') or {}
    g = gpu(sample)
    entries = [('CPU', cpu.get('temp'), settings.get('cpu_temp', 90)),
               ('GPU', g.get('temp'), settings.get('gpu_temp', 90)),
               ('GPU Hotspot', g.get('hotspot'), None)]
    lines = ['THERMAL COMPASS', 'Abstand zu selbst festgelegten Warnwerten ist keine Hersteller-Throttling-Grenze.', '']
    for name, value, limit in entries:
        if numeric(value) is None:
            lines.append(f'{name}: nicht verfügbar')
        elif numeric(limit) is None:
            lines.append(f'{name}: {shown(value, " °C")} · Herstellergrenzwert nicht bekannt')
        else:
            lines.append(f'{name}: {shown(value, " °C")} · Abstand zum Warnwert: {shown(numeric(limit)-numeric(value), " °C")}')
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
        extras = [(chip, x.label or 'Sensor', x.current) for chip, readings in temps.items() for x in readings]
        for chip, name, value in extras[:28]:
            lines.append(f'  {chip} / {name}: {shown(value, " °C")}')
    except (OSError, AttributeError, RuntimeError):
        lines.append('Weitere hwmon-Temperatursensoren: nicht verfügbar')
    return '\n'.join(lines)


def network(_sample=None):
    lines = ['NETWORKPULSE · lokaler Check', 'Kein Ping und keine externen Verbindungen bei diesem Test.', '']
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        io = psutil.net_io_counters(pernic=True)
    except (OSError, RuntimeError) as exc:
        return '\n'.join(lines + [f'Netzwerkinformationen nicht verfügbar: {exc}'])
    for name, status in sorted(stats.items()):
        if name == 'lo':
            continue
        speed = f'{status.speed} Mbit/s' if status.speed and status.speed > 0 else 'nicht verfügbar'
        ips = [a.address for a in addrs.get(name, []) if getattr(a, 'family', None) == 2]
        usage = io.get(name)
        lines += [f'{name}: {"aktiv" if status.isup else "inaktiv"} · Link: {speed}',
                  f'  IPv4: {", ".join(ips) if ips else "nicht verfügbar"}',
                  f'  Bytes gesendet / empfangen: {usage.bytes_sent if usage else "?"} / {usage.bytes_recv if usage else "?"}']
    lines += ['', 'Paketverlust und Latenz lassen sich nur durch einen ausdrücklich gestarteten Netzwerktest messen.']
    return '\n'.join(lines)


def network_ping(_sample=None):
    lines = ['NETWORKPULSE · manueller Verbindungstest', 'Ziel: 1.1.1.1; drei ICMP-Echoanfragen (nur nach Klick).', '']
    out, err = cmd(['ping', '-n', '-c', '3', '-W', '2', '1.1.1.1'], timeout=9)
    if out is None:
        lines.append(f'Ping nicht ausführbar: {err or "nicht verfügbar"}')
    else:
        lines.append(out[:4000])
    lines.append('\nHinweis: ICMP kann durch Netzwerke blockiert werden, ohne dass die Internetverbindung ausfällt.')
    return '\n'.join(lines)


def processes(_sample=None):
    lines = ['PROCESS SPOTLIGHT', 'Kurze CPU-Stichprobe (~0,4 Sekunden); Werte sind Momentaufnahmen.', '']
    try:
        procs = {}
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                p.cpu_percent(interval=None)
                procs[p.pid] = p
            except (psutil.Error, OSError):
                continue
        time.sleep(.4)
        data = []
        for pid, p in procs.items():
            try:
                pct = p.cpu_percent(interval=None)
                mem = p.memory_info().rss / (1024**2)
                data.append((pct, mem, pid, p.name()[:56]))
            except (psutil.Error, OSError):
                continue
        data.sort(reverse=True)
        for pct, mem, pid, name in data[:14]:
            lines.append(f'{pct:>6.1f}% CPU · {mem:>8.1f} MiB RAM · PID {pid:<7} {name}')
        lines.append('\nCPU-Prozent kann bei Mehrkernprozessen über 100 % liegen.')
    except (OSError, RuntimeError) as exc:
        lines.append(f'Prozessinformationen nicht verfügbar: {exc}')
    return '\n'.join(lines)


def fingerprint():
    fields = {'kernel': platform.release(),
              'distribution': read_text('/etc/os-release') or 'nicht verfügbar',
              'desktop': os.environ.get('XDG_CURRENT_DESKTOP', 'nicht verfügbar'),
              'session_type': os.environ.get('XDG_SESSION_TYPE', 'nicht verfügbar')}
    if len(fields['distribution']) > 4000:
        fields['distribution'] = fields['distribution'][:4000]
    out, _ = cmd(['glxinfo', '-B'], timeout=4)
    if out:
        mesa_lines = [line.strip() for line in out.splitlines()
                      if any(t in line for t in ('OpenGL version string:', 'OpenGL renderer string:', 'Mesa'))]
        fields['mesa'] = '\n'.join(mesa_lines[:5]) or 'nicht verfügbar'
    else:
        fields['mesa'] = 'nicht verfügbar'
    fields['pcie_gpu'] = [{k: d.get(k) for k in ('address', 'vendor', 'device', 'max_speed', 'max_width')} for d in _pcie_devices()]
    fields['displays'] = sorted([p.name for p in Path('/sys/class/drm').glob('*')
                                if (p / 'status').is_file() and read_text(p / 'status') == 'connected'])
    return fields


def baseline_save():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    obj = {'created_at': now(), 'vitalux_version': __version__, 'fingerprint': fingerprint()}
    target = BASELINE.with_suffix('.tmp')
    target.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    target.replace(BASELINE)
    return f'Vergleichsbasis lokal gespeichert: {BASELINE}\nStand: {obj["created_at"]}'


def compare():
    if not BASELINE.is_file():
        return 'CHANGERADAR\nNoch keine Vergleichsbasis vorhanden. Mit „Aktuellen Stand merken“ anlegen.'
    try:
        data = json.loads(BASELINE.read_text(encoding='utf-8'))
        old = data['fingerprint']
        new = fingerprint()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f'CHANGERADAR\nGespeicherte Vergleichsbasis nicht auswertbar: {exc}'
    lines = ['CHANGERADAR', f'Vergleich mit: {data.get("created_at", "unbekannt")}',
             'Änderungen belegen noch keinen ursächlichen Zusammenhang mit einem Fehler.', '']
    for key in ('kernel', 'distribution', 'desktop', 'session_type', 'mesa', 'pcie_gpu', 'displays'):
        if old.get(key) != new.get(key):
            before = json.dumps(old.get(key), ensure_ascii=False)
            after = json.dumps(new.get(key), ensure_ascii=False)
            lines.extend([f'GEÄNDERT: {key}', f'  Alt: {before[:900]}', f'  Neu: {after[:900]}', ''])
    if len(lines) == 4:
        lines.append('Keine Unterschiede in den unterstützten Vergleichsfeldern festgestellt.')
    return '\n'.join(lines)


def blackbox_events(limit=40):
    try:
        lines = BLACKBOX.read_text(encoding='utf-8').splitlines()[-max(1, limit):]
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
        except ValueError:
            pass
    return events


class BlackboxRecorder:
    """Event-only, opt-in, bounded local history. No periodic writes."""
    def __init__(self):
        self.previous = {}

    def ingest(self, sample):
        if not settings.get('diag_blackbox_enabled', False):
            self.previous.clear()
            return
        cpu = (sample or {}).get('cpu') or {}
        ram = (sample or {}).get('ram') or {}
        g = gpu(sample)
        fields = {'cpu_temp': cpu.get('temp'), 'gpu_temp': g.get('temp'),
                  'ram_usage': ram.get('percent'), 'vram_usage': None}
        a, b = numeric(g.get('vram_used')), numeric(g.get('vram_total'))
        if a is not None and b and b > 0:
            fields['vram_usage'] = a/b*100
        limits = {'cpu_temp': settings.get('cpu_temp', 90), 'gpu_temp': settings.get('gpu_temp', 90),
                  'ram_usage': settings.get('ram_usage', 90), 'vram_usage': 90}
        new_events = []
        for k, v in fields.items():
            value, limit = numeric(v), numeric(limits[k])
            was_high = self.previous.get(k)
            high = value is not None and limit is not None and value >= limit
            if (was_high is None and high) or (was_high is not None and was_high != high):
                new_events.append({'time': now(), 'metric': k, 'value': round(value, 2) if value is not None else None,
                                   'threshold': limit, 'event': 'Warnwert überschritten' if high else 'Entwarnung'})
            self.previous[k] = high
        if new_events:
            try:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                previous = blackbox_events(limit=290)
                with BLACKBOX.open('w', encoding='utf-8') as out:
                    for event in (previous + new_events)[-300:]:
                        out.write(json.dumps(event, ensure_ascii=False) + '\n')
            except OSError:
                pass


def blackbox_report():
    events = blackbox_events(limit=60)
    lines = ['BLACKBOX · lokales Ereignisprotokoll',
             f'Langzeitaufzeichnung: {"aktiviert" if settings.get("diag_blackbox_enabled", False) else "deaktiviert"}',
             f'Datei: {BLACKBOX}',
             'Nur Warnwert-Übergänge, keine kontinuierliche Speicherung von Rohmessungen.', '']
    if not events:
        lines.append('Noch keine gespeicherten Ereignisse vorhanden.')
    for x in events[-60:][::-1]:
        lines.append(f'{x.get("time", "?")} | {x.get("metric", "?")} | {x.get("event", "?")} | '
                     f'{x.get("value", "?")} (Schwelle {x.get("threshold", "?")})')
    return '\n'.join(lines)


def blackbox_clear():
    try:
        BLACKBOX.unlink(missing_ok=True)
        return 'Blackbox-Daten gelöscht.'
    except OSError as exc:
        return f'Blackbox konnte nicht gelöscht werden: {exc}'


RUNNERS = {
    'system': systemcheck,
    'crashes': crashes,
    'displays': displays,
    'pcie': pcie,
    'thermal': thermal,
    'network': network,
    'ping': network_ping,
    'processes': processes,
    'compare': lambda _sample: compare(),
    'blackbox': lambda _sample: blackbox_report(),
}


def run(section, sample):
    if section == 'all':
        parts = []
        # No active external probe as part of the standard full scan.
        for key in ('system', 'crashes', 'displays', 'pcie', 'thermal', 'network', 'processes', 'compare', 'blackbox'):
            try:
                parts.append(RUNNERS[key](sample))
            except Exception as exc:
                parts.append(f'{key.upper()}: nicht verfügbar ({type(exc).__name__}: {exc})')
        return '\n\n' + ('\n' + '═'*50 + '\n\n').join(parts)
    return RUNNERS[section](sample)
