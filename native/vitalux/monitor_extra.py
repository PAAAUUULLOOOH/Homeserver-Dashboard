"""Optional Linux metadata and low-overhead local process telemetry.

Every optional datum is reported as missing when unavailable. No root access,
privileged commands, network calls or extra dependencies are required.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess

import psutil

_PROCESS = psutil.Process(os.getpid())


def app_resources():
    """This process's CPU percent (total single-core units) and resident memory."""
    try:
        cpu = _PROCESS.cpu_percent(interval=None)
        mem = _PROCESS.memory_info().rss
        return {'cpu_percent': round(cpu, 2), 'rss_bytes': mem}
    except (psutil.Error, OSError):
        return {'cpu_percent': None, 'rss_bytes': None}


def _kscreen_mode_size(item):
    """Extract an active physical mode from kscreen-doctor JSON (if available).

    KScreen mode sizes are actual monitor pixels, unlike QScreen.geometry(),
    which uses device-independent coordinates on a fractionally scaled desktop.
    """
    modes = item.get('modes') or []
    current_id = item.get('currentModeId', item.get('currentMode'))
    active = next((m for m in modes if str(m.get('id')) == str(current_id)), None)
    if active is None and isinstance(current_id, dict):
        active = current_id
    if not isinstance(active, dict):
        return None
    size = active.get('size')
    if isinstance(size, dict):
        width, height = size.get('width'), size.get('height')
    elif isinstance(size, (list, tuple)) and len(size) == 2:
        width, height = size
    elif isinstance(size, str):
        try:
            width, height = size.lower().split('x', 1)
        except ValueError:
            return None
    else:
        return None
    try:
        width, height = int(width), int(height)
        if 0 < width <= 32768 and 0 < height <= 32768:
            return width, height
    except (ValueError, TypeError):
        pass
    return None


def _kscreen_active_displays():
    """Read one KScreen snapshot: physical video modes AND desktop scale.

    KDE's output.scale is the compositor setting (e.g. 1.45). Qt's
    QScreen.devicePixelRatio() may instead report a rounded value (2.0).
    Keep the scale associated with each output so multiple monitors work.
    """
    doctor = shutil.which('kscreen-doctor')
    if not doctor:
        return {}
    try:
        result = subprocess.run([doctor, '-j'], capture_output=True, text=True,
                                timeout=2, check=False)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        outputs = data.get('outputs') if isinstance(data, dict) else data
        if not isinstance(outputs, list):
            return {}
        displays = {}
        for item in outputs:
            if not isinstance(item, dict):
                continue
            name = str(item.get('name') or '')
            mode = _kscreen_mode_size(item)
            if not name or not mode:
                continue
            scale = item.get('scale')
            try:
                scale = float(scale)
                if not (0.5 <= scale <= 5.0) or not math.isfinite(scale):
                    scale = None
            except (TypeError, ValueError):
                scale = None
            displays[name] = {'mode': mode, 'scale': scale}
        return displays
    except (OSError, ValueError, subprocess.TimeoutExpired, TypeError):
        return {}




def _native_screen_size(screen, known_modes=None):
    """Physical screen size and true desktop scale, preferring KDE settings.

    If the native video mode is known but no explicit scale exists, compare
    BOTH physical and logical dimensions. This also bypasses Qt's rounded DPR,
    without inventing a percentage when geometry does not match the mode.
    """
    geo = screen.geometry()
    logical_width, logical_height = geo.width(), geo.height()
    try:
        dpr = float(screen.devicePixelRatio())
        if not (0.25 <= dpr <= 8.0):
            dpr = 1.0
    except (AttributeError, ValueError, TypeError, RuntimeError):
        dpr = 1.0
    entry = (known_modes or {}).get(screen.name())
    if isinstance(entry, dict):
        exact = entry.get('mode') or entry.get('size')
        kde_scale = entry.get('scale')
    else:
        exact, kde_scale = entry, None
    if exact:
        width, height = exact
        source = 'native'
    else:
        width = round(logical_width * dpr)
        height = round(logical_height * dpr)
        source = 'qt-scale'
    actual_scale = dpr
    if exact:
        try:
            candidate = float(kde_scale)
            if not (0.5 <= candidate <= 5 and math.isfinite(candidate)):
                candidate = None
        except (TypeError, ValueError):
            candidate = None
        if candidate is not None:
            actual_scale = candidate
        elif logical_width > 0 and logical_height > 0:
            ratios = (width / logical_width, height / logical_height)
            if (0.5 <= ratios[0] <= 5 and 0.5 <= ratios[1] <= 5
                    and abs(ratios[0] - ratios[1]) < 0.04):
                actual_scale = (ratios[0] + ratios[1]) / 2
    return {'width': width, 'height': height, 'logical_width': logical_width,
            'logical_height': logical_height, 'scale_percent': round(actual_scale * 100),
            'resolution_source': source}


def graphics_runtime(qt_platform=None, screens=None, environ=None, native_modes=None):
    """Qt session, native physical display resolution and current refresh rate.

    The optional native_modes argument lets tests and non-KDE callers supply
    compositor-reported physical resolutions without subprocess calls.
    """
    env = os.environ if environ is None else environ
    session = str(env.get('XDG_SESSION_TYPE') or '').lower()
    platform = str(qt_platform or '').lower()
    if platform.startswith('wayland'):
        runtime = 'Wayland (nativ)'
    elif platform in ('xcb', 'x11'):
        runtime = 'X11 / XWayland' if session == 'wayland' else 'X11'
    else:
        runtime = f'{platform or "Unbekannt"} (Qt)'
    result = {'qt_platform': platform or '–', 'session': session or '–',
              'runtime': runtime, 'screens': []}
    known_modes = _kscreen_active_displays() if native_modes is None else native_modes
    for display in screens or []:
        try:
            name = display.name() or 'Bildschirm'
            hertz = display.refreshRate()
            dimensions = _native_screen_size(display, known_modes)
            result['screens'].append({'name': name, **dimensions,
                                      'hz': round(hertz, 2) if hertz > 0 else None})
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
    return result


def system_gpu_device(gpus):
    """The first detected GPU is NOT necessarily the active render device."""
    if not gpus:
        return 'Nicht verfügbar'
    if len(gpus) == 1:
        return gpus[0].get('name') or 'Nicht verfügbar'
    return 'Nicht eindeutig ermittelbar (mehrere GPUs)'
