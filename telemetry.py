"""Real host metrics; psutil is bundled in the portable package."""
import platform
import shutil
import time

try:
    import psutil
except ImportError:
    psutil=None


def collect(path):
    disk=shutil.disk_usage(path)
    result=dict(hostname=platform.node(),system=platform.platform(),disk_used=disk.used,disk_total=disk.total,disk_percent=round(100*disk.used/disk.total,1),cpu=None,ram_percent=None,ram_used=None,ram_total=None,uptime=None)
    if psutil:
        mem=psutil.virtual_memory()
        result.update(cpu=psutil.cpu_percent(),ram_percent=mem.percent,ram_used=mem.used,ram_total=mem.total,uptime=int(time.time()-psutil.boot_time()))
    return result
