"""User-selectable, low-overhead motion profiles.

All durations are resolved at animation start, so changes take effect without
rebuilding pages or restarting live measurements.
"""
from . import DEFAULT_THEME
from . import settings, eco

MODES = ("smooth", "reduced", "off")


def level():
    if eco.enabled():
        return 'off'
    value = settings.get("motion", "smooth")
    return value if value in MODES else "smooth"


def duration(milliseconds):
    base = max(0, int(milliseconds))
    profile = level()
    if profile == "off" or eco.enabled() or settings.get("theme", DEFAULT_THEME) == "minimal":
        return 0
    if profile == "reduced":
        return max(50, min(110, round(base * .43)))
    return base


def enabled():
    return not eco.enabled() and level() != "off" and settings.get("theme", DEFAULT_THEME) != "minimal"
