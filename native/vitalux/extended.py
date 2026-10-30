"""Additional optional Linux monitoring. Missing sensors are reported as unavailable."""
import glob
import os
import re
import socket
import struct
import subprocess
import time



def read(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read().strip()
    except (OSError, ValueError):
        return ''


def num(value, divisor=1.0):
    try:
        return float(value) / divisor
    except (ValueError, TypeError, OverflowError):
        return None


def _hwmon(card_device):
    for path in sorted(glob.glob(os.path.join(card_device, 'hwmon', 'hwmon*'))):
        if os.path.isdir(path):
            return path
    return None


def _temp_label_data(hw):
    out = {}
    if not hw:
        return out
    for file in glob.glob(os.path.join(hw, 'temp*_input')):
        prefix = file[:-6]  # cut '_input'
        label = read(prefix + '_label').lower()
        val = num(read(file), 1000)
        if val is not None:
            out[label or os.path.basename(prefix)] = val
    return out


def _freq_active(path):
    data = read(path)
    for line in data.splitlines():
        if '*' in line:
            match = re.search(r'\b(\d+)Mhz\b', line, re.I)
            if match:
                return float(match.group(1))
    return None


def drm_extra(card_device):
    hw = _hwmon(card_device)
    temps = _temp_label_data(hw)
    hotspot = next((v for k, v in temps.items() if 'junction' in k or 'hotspot' in k or 'hot spot' in k), None)
    edge = next((v for k, v in temps.items() if 'edge' in k), None)
    if edge is None:
        edge = temps.get('temp1')  # Do not relabel memory/junction as edge temperature.
    raw_pwm = num(read(os.path.join(hw, 'pwm1'))) if hw else None
    raw_max = num(read(os.path.join(hw, 'pwm1_max'))) if hw else None
    fan_percent = raw_pwm / raw_max * 100 if raw_pwm is not None and raw_max else None
    rpm = num(read(os.path.join(hw, 'fan1_input'))) if hw else None
    clk = _freq_active(os.path.join(card_device, 'pp_dpm_sclk'))
    memclk = _freq_active(os.path.join(card_device, 'pp_dpm_mclk'))
    uevent = read(os.path.join(card_device, 'uevent'))
    match = re.search(r'^DRIVER=(.+)$', uevent, re.M)
    return dict(hotspot=hotspot, edge=edge, fan_percent=fan_percent, fan_rpm=rpm,
                clock=clk, clock_mem=memclk, driver=match.group(1) if match else None)


def _default_route():
    for line in read('/proc/net/route').splitlines()[1:]:
        f = line.split()
        if len(f) < 4 or f[1] != '00000000':
            continue
        try:
            gateway = socket.inet_ntoa(struct.pack('<L', int(f[2], 16)))
            return f[0], gateway
        except (ValueError, OSError, struct.error):
            continue
    return None, None


def _dns():
    servers = []
    for line in read('/etc/resolv.conf').splitlines():
        m = re.match(r'^\s*nameserver\s+(\S+)', line)
        if m:
            servers.append(m.group(1))
    if servers == ['127.0.0.53'] or servers == ['127.0.0.54']:
        try:
            p = subprocess.run(['resolvectl','dns'], capture_output=True, text=True, timeout=1)
            extra = re.findall(r'(?<!\w)(?:\d{1,3}\.){3}\d{1,3}(?!\w)', p.stdout)
            extra = [x for x in extra if not x.startswith('127.')]
            if extra:
                servers = extra
        except (OSError, subprocess.TimeoutExpired):
            pass
    return list(dict.fromkeys(servers))


_route_cache = (0, {})

def net_static_details():
    global _route_cache
    now = time.monotonic()
    if now - _route_cache[0] >= 20:
        primary, gateway = _default_route()
        _route_cache = (now, {'route_interface': primary, 'gateway': gateway, 'dns': _dns()})
    return dict(_route_cache[1])
