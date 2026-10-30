"""Format actual sensor readings for the native system-tray tooltip."""
import math
from .i18n import tr


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def percent(value):
    value = number(value)
    return '–' if value is None else f'{value:.0f}%'


def temperature(value):
    value = number(value)
    return '–' if value is None else f'{value:.0f} °C'


def measurements(sample):
    sample = sample or {}
    cpu = sample.get('cpu') or {}
    ram = sample.get('ram') or {}
    gpu = next((g for g in (sample.get('gpus') or []) if isinstance(g, dict)), {})
    return (number(cpu.get('usage')), number(gpu.get('usage')),
            number(ram.get('percent')), number(cpu.get('temp')),
            number(gpu.get('temp')))


def tray_tooltip(sample):
    cpu, gpu, ram, cpu_temp, gpu_temp = measurements(sample)
    return ('Vitalux · ' + tr('Live-Übersicht') + '\n'
            + f'CPU {percent(cpu)}  ·  GPU {percent(gpu)}\n'
            + f'RAM {percent(ram)}\n'
            + f'{tr("CPU-Temperatur")}: {temperature(cpu_temp)}\n'
            + f'{tr("GPU-Temperatur")}: {temperature(gpu_temp)}')
