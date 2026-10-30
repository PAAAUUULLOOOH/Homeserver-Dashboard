"""Shared localized labels for charts and ordinary widgets."""
from .ui_locale import QLabel
from .i18n import tr


def label(text="", name=None, align=None, wrap=False):
    l = QLabel(tr(text))
    if name:
        l.setObjectName(name)
    if name in ('chipValue', 'telemetryValue'):
        font = l.font()
        font.setFamilies(['DejaVu Sans Mono', 'Noto Sans Mono', 'monospace'])
        l.setFont(font)
    if align:
        l.setAlignment(align)
    l.setWordWrap(wrap)
    return l

