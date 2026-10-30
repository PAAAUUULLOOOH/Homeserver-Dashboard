"""A minimal secondary native Qt window; reuses the MainWindow sensor stream."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QGridLayout, QProgressBar, QFrame)
from . import eco, settings, theme
from .monitoring import telemetry, valid_number

METRIC_OPTIONS = (
    ('cpu_usage', 'CPU', '%'), ('gpu_usage', 'GPU', '%'),
    ('ram_usage', 'RAM', '%'), ('vram_usage', 'VRAM', '%'),
    ('cpu_temp', 'CPU-Temp', '°C'), ('gpu_temp', 'GPU-Temp', '°C'),
    ('gpu_clock', 'GPU-Takt', 'MHz'), ('gpu_power', 'GPU-Watt', 'W'),
)
DEFAULT_KEYS = ['cpu_usage', 'gpu_usage', 'ram_usage', 'cpu_temp', 'gpu_temp']


class MiniHUD(QWidget):
    hidden_by_user = Signal()

    def __init__(self):
        # Wayland/KWin does not guarantee permanent stacking above other
        # windows, especially fullscreen apps. Do not expose a broken toggle.
        flags = Qt.Tool | Qt.FramelessWindowHint
        super().__init__(None, flags)
        self.setWindowTitle('Vitalux · MiniHUD')
        self.setObjectName('vitaluxMiniHUD')
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.latest = None
        self._rows = {}
        self.setMinimumSize(200, 62)
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(0, 0, 0, 0)
        self.layout_root.setSpacing(0)
        self.surface = QFrame(self)
        self.surface.setObjectName('hudSurface')
        self.surface.installEventFilter(self)
        self.layout_root.addWidget(self.surface)
        self.inner = QVBoxLayout(self.surface)
        self.inner.setContentsMargins(12, 9, 12, 11)
        self.inner.setSpacing(6)
        self.header = QHBoxLayout()
        self.header.setSpacing(4)
        self.brand = QLabel('◈  VITALUX   ·   MINI HUD')
        self.brand.setObjectName('hudBrand')
        self.brand.installEventFilter(self)
        self.header.addWidget(self.brand, 1)
        self.close_btn = QPushButton('×')
        self.close_btn.setToolTip('MiniHUD ausblenden')
        self.close_btn.setFixedSize(24, 22)
        self.close_btn.clicked.connect(self.hide_by_user)
        self.header.addWidget(self.close_btn)
        self.inner.addLayout(self.header)
        self.value_area = QWidget()
        self.values_layout = QGridLayout(self.value_area)
        self.values_layout.setContentsMargins(0, 0, 0, 0)
        self.values_layout.setHorizontalSpacing(13)
        self.values_layout.setVerticalSpacing(5)
        self.inner.addWidget(self.value_area)
        self.apply_settings()

    def hide_by_user(self):
        self.hide()
        settings.set('mini_hud_enabled', False)
        self.hidden_by_user.emit()

    def closeEvent(self, event):
        self.hide_by_user()
        event.ignore()

    def eventFilter(self, obj, event):
        if obj in (getattr(self, 'surface', None), getattr(self, 'brand', None)) and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return True
        return super().eventFilter(obj, event)

    def apply_settings(self):
        mode = settings.get('mini_hud_layout', 'compact')
        if mode not in ('minimal', 'compact', 'extended'):
            mode = 'compact'
        chosen = settings.get('mini_hud_metrics', DEFAULT_KEYS)
        if not isinstance(chosen, list):
            chosen = list(DEFAULT_KEYS)
        chosen = [k for k in chosen if k in {x[0] for x in METRIC_OPTIONS}]
        if not chosen:
            chosen = ['cpu_usage']
        while self.values_layout.count():
            item = self.values_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._rows = {}
        self._layout_mode = mode
        columns = 3 if mode == 'minimal' else 2
        for i, (key, title, unit) in enumerate(x for x in METRIC_OPTIONS if x[0] in chosen):
            host = QFrame()
            host.setObjectName('hudCell')
            cell = QVBoxLayout(host)
            cell.setSpacing(2)
            cell.setContentsMargins(6, 4, 6, 4)
            head = QLabel(title)
            head.setObjectName('hudCaption')
            val = QLabel('–')
            val.setObjectName('hudValue')
            cell.addWidget(head)
            cell.addWidget(val)
            bar = None
            if mode == 'extended' and unit == '%':
                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setTextVisible(False)
                bar.setFixedHeight(4)
                cell.addWidget(bar)
            self.values_layout.addWidget(host, i // columns, i % columns)
            self._rows[key] = (val, bar, unit)
        self.close_btn.setVisible(True)
        self.brand.setText('◈  VITALUX  ·  ECO HUD' if eco.enabled() else '◈  VITALUX  ·  MINI HUD')
        # QLayout size hints are unreliable until a frameless Qt.Tool window is mapped.
        # Reserve the real content height explicitly (also under fractional Wayland scaling).
        import math
        rows = math.ceil(len(self._rows) / columns)
        self.setMinimumSize(180, 60)
        self.setMaximumSize(440, 550)
        self.setFixedSize(290 if mode == 'minimal' else 325, 44 + rows * (65 if mode == 'extended' else 52))
        # Wayland may ignore setWindowOpacity() entirely. Paint the HUD surfaces
        # with real alpha instead; text stays solid/readable at 50%.
        opacity = 1.0 if eco.enabled() else max(0.5, min(1.0, float(settings.get('mini_hud_opacity', 90)) / 100))
        self.setWindowOpacity(1.0)
        def layer(hex_color):
            c = QColor(hex_color)
            return f'rgba({c.red()}, {c.green()}, {c.blue()}, {round(255 * opacity)})'
        accent = '#4f8cff' if eco.enabled() else theme.accent()
        # 0.9.4.7 live palette, not the old, extra-dark 0.9.4.0 test skin.
        bg = theme.SIDEBAR if not eco.enabled() else '#1d1d1d'
        cellbg = theme.CARD if not eco.enabled() else '#262626'
        caption = theme.MUTED if not eco.enabled() else '#b9b9b9'
        valuecolor = theme.TEXT if not eco.enabled() else '#f3f5f9'
        closecolor = theme.MUTED if not eco.enabled() else '#b7c4d0'
        self.setStyleSheet('''
            QWidget#vitaluxMiniHUD { background: transparent; }
            QFrame#hudSurface { background-color: %s; border: 1px solid %s; border-radius: %spx; }
            QFrame#hudCell { background-color: %s; border: none; border-radius: 5px; }
            QLabel#hudBrand { color: %s; font-size: 11px; font-weight: bold; border: none; }
            QLabel#hudCaption { color: %s; font-size: 10px; border: none; }
            QLabel#hudValue { color: %s; font-size: 17px; font-weight: bold; border: none; }
            QPushButton { color: %s; background: transparent; border: none; font-size: 19px; }
            QProgressBar { background: #364455; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: %s; border: none; border-radius: 2px; }
        ''' % (layer(bg),accent if not eco.enabled() else '#555555',
               '0' if eco.enabled() else '9',layer(cellbg),
               accent,caption,valuecolor,closecolor,accent))
        self.update_sample(self.latest)

    def update_sample(self, sample):
        self.latest = sample
        if not self.isVisible() and sample is not None:
            # Avoid widget updates when the MiniHUD is disabled.
            return
        values = telemetry(sample or {})
        for key, (field, bar, unit) in self._rows.items():
            value = values.get(key)
            if valid_number(value):
                digits = 0 if unit in ('%', 'MHz', 'W') else 1
                new_text = f'{value:.{digits}f} {unit}'
            else:
                new_text = '–'
            if field.text() != new_text:
                field.setText(new_text)
            if bar is not None:
                bar.setValue(max(0, min(100, round(value))) if valid_number(value) else 0)
