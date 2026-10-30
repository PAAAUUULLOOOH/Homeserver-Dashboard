"""Short measurement status; only source-confirmed causes get specific text."""
from .i18n import tr


def unavailable(reason=None):
    return tr({'no_sensor': 'Kein Sensor erkannt',
               'permission': 'Berechtigung fehlt',
               'unsupported': 'Nicht unterstützt',
               'driver_no_data': 'Vom Treiber nicht geliefert'}.get(reason, 'nicht verfügbar'))
