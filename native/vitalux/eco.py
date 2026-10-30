"""Ultra Eco: reversible, deliberately plain, low-frequency application profile.

Saved theme, wallpaper, accent, motion, sampler interval and renderer are
never overwritten. Disabling the toggle restores every previous preference.
"""
from . import DEFAULT_THEME
from . import settings

KEY = 'ultra_eco'
SAMPLE_INTERVAL = 10


def enabled():
    return settings.get(KEY, False) is True


def theme_name():
    return 'minimal' if enabled() else settings.get('theme', DEFAULT_THEME)


def interval():
    if enabled():
        return SAMPLE_INTERVAL
    try:
        return max(1, min(5, int(settings.get('interval', 1))))
    except (ValueError, TypeError):
        return 1
