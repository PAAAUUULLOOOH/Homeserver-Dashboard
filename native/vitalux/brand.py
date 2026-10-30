"""Vitalux Pulse Core identity.

The logo and original, custom-drawn wordmark are packaged SVG vectors.  The
sidebar's animated instance uses the same vector as the desktop app icon.
No external font or image download is required.
"""
from __future__ import annotations

import math
import json
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from tempfile import NamedTemporaryFile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QIcon, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import eco


_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_PALETTES = json.loads((_ASSETS / 'brand/palettes.json').read_text())
_GEOMETRY = _PALETTES['geometry']
_VIEWBOX = _GEOMETRY['viewbox']
_CENTER = _GEOMETRY['center']
_MOTION = _PALETTES['motion_seconds']


def _frame_interval(widget, reduced=False):
    if reduced:
        return 80
    from .smooth_scroll import frame_interval_ms
    screen = widget.screen()
    return frame_interval_ms(screen.refreshRate() if screen else 60)


@lru_cache(maxsize=48)
def _renderer(filename):
    renderer = QSvgRenderer(str(_ASSETS / filename))
    if not renderer.isValid():
        raise RuntimeError(f"Vitalux design asset not readable: {filename}")
    return renderer


@lru_cache(maxsize=16)
def _logo_layers(filename):
    """Split the authored outer bands from the stationary pulse and lens.

    Explicit group IDs preserve the authored geometry and material gradients.
    Desktop/tray icons continue to use the complete static SVG.
    """
    data = filename if isinstance(filename, bytes) else (_ASSETS / filename).read_bytes()
    layers = []
    for outer in (False, True):
        root = ET.fromstring(data)
        for child in list(root):
            tag = child.tag.rsplit('}', 1)[-1]
            if tag in ('defs', 'title', 'desc'):
                continue
            keep = {'outer-bands'} if outer else {'stationary-lens', 'pulse-core'}
            if child.get('id') not in keep:
                root.remove(child)
        svg = QSvgRenderer(ET.tostring(root))
        if not svg.isValid():
            raise RuntimeError('Unable to load animated Vitalux logo layer')
        layers.append(svg)
    return tuple(layers)


def _render_pixmap(renderer, width, height, ratio=1.0):
    width, height = max(1, int(width)), max(1, int(height))
    ratio = max(1.0, float(ratio))
    pixmap = QPixmap(round(width * ratio), round(height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, width, height))
    p.end()
    return pixmap


def _pixmap(filename, width, height, ratio=1.0):
    return _render_pixmap(_renderer(filename), width, height, ratio)


@lru_cache(maxsize=48)
def _svg_renderer(data):
    return QSvgRenderer(data)


@lru_cache(maxsize=48)
def _tinted_svg(filename, accent):
    """Preserve every authored contour, cut and highlight for arbitrary hues."""
    base = QColor(accent)
    hue, saturation, _value, _alpha = base.getHsv()
    policy = _PALETTES['custom_tint']
    circle = Path(filename).name.startswith('vitalux-pulse')
    def tint(match):
        source = QColor(match.group())
        _h, s, v, _a = source.getHsv()
        if s < 22:
            return source.name()
        mixed = s*policy['source_mix']+saturation*policy['accent_mix']
        if circle and hue >= 0:
            mixed *= 1+policy['circle_saturation_boost']*saturation/255
            mixed = min(policy['circle_saturation_cap'], mixed)
        tinted_saturation = 0 if hue < 0 else min(255, round(mixed))
        return QColor.fromHsv(max(0, hue), tinted_saturation, v).name()
    return re.sub(r'#[0-9a-fA-F]{6}', tint, (_ASSETS/filename).read_text()).encode()


@lru_cache(maxsize=48)
def _asset_bytes(filename):
    return (_ASSETS/filename).read_bytes()


def _themed_svg(icon):
    from . import theme
    filename = _brand_asset(icon)
    if _selected_variant() is None:
        return _tinted_svg(filename, theme.accent())
    return _asset_bytes(filename)




# Presets use their authored SVG palettes; arbitrary and distribution colors
# tint the same original vector contours with the effective theme hue.
ACCENT_VARIANTS = {pal['accent']: key for key, pal in _PALETTES['variants'].items()
                   if key not in ('gold', *_PALETTES['theme_assets'].values())}


def _selected_variant():
    from . import theme,settings
    if theme.mode() in _PALETTES['theme_assets']:
        return _PALETTES['theme_assets'][theme.mode()] if settings.get('accent','design_default')=='design_default' else None
    return ACCENT_VARIANTS.get(str(theme.source_accent()).lower())


def _brand_asset(icon):
    from . import theme
    variant=_PALETTES['theme_assets'].get(theme.mode()) or _selected_variant()
    if icon:return f"brand/vitalux-pulse-{variant}.svg" if variant else 'vitalux-pulse.svg'
    if variant:
        suffix='-light' if theme.is_light() else ''
        return f"brand/vitalux-wordmark-{variant}{suffix}.svg"
    return 'vitalux-wordmark-light.svg' if theme.is_light() else 'vitalux-wordmark.svg'


def themed_icon_pixmap(size=152):
    return _render_pixmap(_svg_renderer(_themed_svg(True)), size, size)


def wordmark_pixmap(width=205, height=None, ratio=2.0):
    if height is None:
        viewbox = _GEOMETRY['wordmark_viewbox']
        height = round(width*viewbox[3]/viewbox[2])
    return _render_pixmap(_svg_renderer(_themed_svg(False)), width, height, ratio=ratio)


class Wordmark(QWidget):
    """Original vector lettering with light clipped precisely to its strokes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 50)
        self.setAccessibleName('Vitalux')
        self._base = QPixmap()
        self._phase = 0.0
        self._last_tick = time.monotonic()
        self._signature = None
        self._enabled = False
        self._reduced = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self.sync_theme()

    def sync_theme(self):
        from . import motion, theme
        signature = (theme.mode(), theme.accent(), self.size(), self.devicePixelRatioF())
        if signature != self._signature:
            self._signature = signature
            self._base = wordmark_pixmap(self.width(), self.height(),
                                        ratio=max(2.0, self.devicePixelRatioF()))
        self._enabled = motion.enabled()
        self._reduced = motion.level() == 'reduced'
        self._timer.stop()
        self._last_tick = time.monotonic()
        if self.isVisible() and self._enabled:
            self._timer.start(_frame_interval(self, self._reduced))
        self.update()

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.DevicePixelRatioChange and hasattr(self, '_timer'):
            self.sync_theme()
        return result

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_theme()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self):
        if not self._enabled:
            self._timer.stop()
            return
        now = time.monotonic()
        period = _MOTION['wordmark_glint']
        self._phase = (self._phase + max(0, now-self._last_tick)/period) % 1.0
        self._last_tick = now
        # There is no repaint loop in the quiet interval between reflections.
        active_interval = _frame_interval(self, self._reduced)
        interval = active_interval if self._phase < .46 else max(80, round((1-self._phase)*period*1000))
        self._timer.setInterval(interval)
        self.update()

    def paintEvent(self, event):
        from . import theme
        p = QPainter(self)
        p.drawPixmap(0, 0, self._base)
        if self._enabled and self._phase < .46:
            sweep = self._phase/.46
            # A broad satin reflection carries a narrower white glint across
            # the original strokes. Ease at both edges instead of flashing.
            sweep = .5-.5*math.cos(math.pi*sweep)
            x = -.25*self.width()+sweep*self.width()*1.5
            gleam = self._base.copy()
            light = QPainter(gleam)
            light.setCompositionMode(QPainter.CompositionMode_SourceIn)
            band = QLinearGradient(x-self.width()*.135, 0,
                                   x+self.width()*.135, self.height()*.6)
            warm = QColor(theme.blend('#ffffff', theme.accent(), .88))
            envelope = max(0, min(1, self._phase/.02, (.46-self._phase)/.03))
            for position, alpha in ((0,0),(.20,6),(.42,41),(.51,102),
                                    (.62,46),(.85,6),(1,0)):
                tone = QColor(warm); tone.setAlpha(round(alpha*envelope))
                band.setColorAt(position, tone)
            light.fillRect(QRectF(0,0,self.width(),self.height()),QBrush(band))
            light.end()
            p.drawPixmap(0,0,gleam)
        p.end()


@lru_cache(maxsize=12)
def _cached_app_icon(data):
    icon = QIcon()
    svg = _svg_renderer(data)
    for size in (32,48,64,128,256,512):
        icon.addPixmap(_render_pixmap(svg,size,size))
    return icon


def app_icon():
    return QIcon(_cached_app_icon(_themed_svg(True)))


def sync_installed_icon():
    """Keep the user-installed KDE launcher icon in sync with the accent.

    A distinct icon *path* per preset avoids KDE's stale hicolor/desktop-entry
    icon cache. No shared/system desktop file is touched.
    """
    import re
    base = Path(os.environ.get('XDG_DATA_HOME') or
                (Path.home() / '.local' / 'share'))
    desktop = base / 'applications' / 'vitalux.desktop'
    directory = base / 'icons' / 'hicolor' / 'scalable' / 'apps'
    original = directory / 'vitalux.svg'
    if (not desktop.is_file() or desktop.is_symlink()
            or not original.is_file() or original.is_symlink()
            or directory.is_symlink()):
        return False
    try:
        data = desktop.read_text(encoding='utf-8')
        if 'Name=Vitalux' not in data:
            return False
        found = re.search(r'^Icon=(.*)$', data, flags=re.MULTILINE)
        if not found:
            return False
        old_icon = found.group(1).strip()
        if old_icon != 'vitalux' and not (
                old_icon.startswith(str(directory / 'vitalux-'))
                and old_icon.endswith('.svg')):
            return False
        variant = _selected_variant()
        source = _ASSETS / _brand_asset(icon=True)
        if not source.is_file():
            return False
        # The selected color changes the icon *filename*, not just its bytes:
        # Plasma consequently refreshes pinned launchers more reliably.
        from . import theme
        new_bytes = _themed_svg(True)
        identity = hashlib.sha256(new_bytes).hexdigest()[:12]
        target = directory / ('vitalux-' + (variant or 'accent-'+theme.accent()[1:])
                              + '-' + identity + '.svg')
        if not target.is_file() or target.read_bytes() != new_bytes:
            with NamedTemporaryFile(dir=directory, prefix='.vitalux-color-',
                                    suffix='.svg', delete=False) as fd:
                tmp = Path(fd.name)
                fd.write(new_bytes)
                fd.flush()
                os.fsync(fd.fileno())
            try:
                os.replace(tmp, target)
            finally:
                if tmp.exists():
                    tmp.unlink()
        updated = re.sub(r'^Icon=.*$', 'Icon=' + str(target), data,
                         count=1, flags=re.MULTILINE)
        if updated != data:
            with NamedTemporaryFile(dir=desktop.parent,
                                    prefix='.vitalux-entry-',
                                    suffix='.desktop', delete=False) as fd:
                tmp = Path(fd.name)
                fd.write(updated.encode('utf-8'))
                fd.flush()
                os.fsync(fd.fileno())
            try:
                os.chmod(tmp, desktop.stat().st_mode & 0o777)
                os.replace(tmp, desktop)
            finally:
                if tmp.exists():
                    tmp.unlink()
        return True
    except OSError:
        # Window and tray color changes still work without desktop integration.
        return False


class TrayPulse(QObject):
    """Low-frequency, accent-matched animated glow around the real tray logo.

    A standard QIcon is restored immediately after an update is installed.
    There are no extra notifications or background threads.
    """

    def __init__(self, tray, parent=None):
        super().__init__(parent)
        self.tray = tray
        self.active = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(190)
        self._timer.timeout.connect(self._advance)

    def _render(self, phase):
        from . import theme
        size = 64
        px = QPixmap(size, size)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        beat = .5 + .5 * math.sin(phase)
        color = QColor(theme.accent())
        glow = QRadialGradient(QPointF(32, 32), 31)
        center = QColor(color); center.setAlpha(int(88 + 145 * beat))
        mid = QColor(color); mid.setAlpha(int(40 + 100 * beat))
        edge = QColor(color); edge.setAlpha(0)
        glow.setColorAt(0, center)
        glow.setColorAt(.62, mid)
        glow.setColorAt(1, edge)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QRectF(0, 0, 64, 64))
        ring = QColor(color).lighter(130)
        ring.setAlpha(int(115 + 140 * beat))
        p.setPen(QPen(ring, 2 + beat * 2.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(3, 3, 58, 58))
        p.drawPixmap(8, 8, 48, 48, themed_icon_pixmap(48))
        # A visible light pip survives Plasma's 22px tray scaling.
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(75 + 180*beat)))
        p.drawEllipse(QPointF(54, 10), 2 + beat * 1.8, 2 + beat * 1.8)
        p.end()
        return px

    def _advance(self):
        if not self.active:
            return
        self._phase = (self._phase + .38) % (2 * math.pi)
        pix = self._render(self._phase)
        icon = QIcon()
        icon.addPixmap(pix)
        # Explicit small render sizes avoid smooth-downscaling away the glow.
        for target in (22, 32, 48):
            icon.addPixmap(pix.scaled(target, target, Qt.KeepAspectRatio,
                                      Qt.SmoothTransformation))
        self.tray.setIcon(icon)

    def set_active(self, active):
        active = bool(active)
        if self.active == active:
            return
        self.active = active
        if active:
            self._phase = 0.0
            self._advance()
            self._timer.start()
        else:
            self._timer.stop()
            self.tray.setIcon(app_icon())

    def refresh(self):
        if self.active:
            self._advance()

    def stop(self):
        self.set_active(False)


class PulseCore(QWidget):
    """Authored vector layers with independent rotation and a clear pulse.

    Only the stationary glass/core is cached, at native or higher pixel density.
    The moving bands remain vectors, including during rotation.
    """
    def __init__(self, size=152, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._cpu = 0.0
        self._display_cpu = 0.0
        self._phase = 0.0
        self._heartbeat_phase = 0.0
        points = _GEOMETRY['waveform']
        self._waveform = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            self._waveform.lineTo(*point)
        self._last_tick = time.monotonic()
        self._update_available = False
        self._update_clock = 0.0
        self._core_signature = None
        self._core_pixmap = QPixmap()
        self._bands = None
        self._enabled = not self._low_power()
        self._reduced = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._sync_tooltip()

    def _sync_tooltip(self):
        from .i18n import tr
        self.setToolTip(tr('CPU {value}% · Live-Telemetrie').format(value=f'{self._cpu:.0f}'))

    def set_update_available(self, available):
        status = bool(available)
        if status != self._update_available:
            self._update_available = status
            self.sync_theme()

    def set_cpu_load(self, value):
        try:
            self._cpu = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            self._cpu = 0.0
        self._sync_tooltip()
        # The visible animation already has a display-paced update timer.

    @staticmethod
    def _low_power():
        from . import theme, motion
        return eco.enabled() or theme.mode() == 'minimal' or not motion.enabled()

    def sync_theme(self):
        from . import motion
        self._enabled = not self._low_power()
        self._reduced = motion.level() == 'reduced'
        self._sync_tooltip()
        if not self._enabled:
            self._timer.stop()
        elif self.isVisible():
            self._last_tick = time.monotonic()
            self._timer.start(_frame_interval(self, self._reduced))
        self.update()

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.DevicePixelRatioChange and hasattr(self, '_timer'):
            self._core_signature = None
            self.update()
        return result

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_theme()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self):
        if not self._enabled:
            self._timer.stop()
            return
        now = time.monotonic()
        elapsed = min(.25, max(0, now-self._last_tick))
        self._last_tick = now
        self._update_clock = (self._update_clock+elapsed*2*math.pi/3.2) % (2*math.pi)
        self._display_cpu += (self._cpu-self._display_cpu)*(1-math.exp(-elapsed/.42))
        self._phase = (self._phase+elapsed*360/_MOTION['outer_rotation']) % 360
        self._heartbeat_phase = (self._heartbeat_phase+elapsed/_MOTION['heartbeat']) % 1
        interval = _frame_interval(self, self._reduced)
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
        self.update()

    def _paint_layers(self, painter, rect):
        data = _themed_svg(True)
        ratio = max(2.0, self.devicePixelRatioF())
        signature = (data, self.size(), ratio)
        if signature != self._core_signature:
            core, self._bands = _logo_layers(data)
            self._core_pixmap = _render_pixmap(core, rect.width(), rect.height(), ratio)
            self._core_signature = signature
        painter.drawPixmap(rect.topLeft(), self._core_pixmap)
        origin = QPointF(rect.left()+rect.width()*_CENTER[0]/_VIEWBOX[2],
                         rect.top()+rect.height()*_CENTER[1]/_VIEWBOX[3])
        painter.save()
        painter.translate(origin)
        painter.rotate(self._phase)
        self._bands.render(painter, QRectF(rect.left()-origin.x(), rect.top()-origin.y(),
                                           rect.width(), rect.height()))
        painter.restore()

    def _paint_pulse(self, painter, rect):
        phase = self._heartbeat_phase
        if phase >= .78:
            return
        head = phase/.78*1.24
        tail, finish = max(0, head-.24), min(1, head)
        if tail >= finish:
            return
        envelope = max(0, min(1, phase/.035, (.78-phase)/.08))
        from . import theme
        palette = _PALETTES['variants'].get(_selected_variant())
        mid = palette['mid'] if palette else theme.accent()
        top = palette['top'] if palette else theme.blend('#ffffff', mid, .46)
        spec = palette['spec'] if palette else theme.blend('#ffffff', mid, .83)
        path = self._waveform
        segment = path.trimmed(tail, finish)
        start = path.pointAtPercent(path.percentAtLength(path.length()*tail))
        end = path.pointAtPercent(path.percentAtLength(path.length()*finish))
        gradient = QLinearGradient(start, end)
        for stop, tone, alpha in ((0, mid, 0), (.20, mid, 70),
                                  (.58, top, 195), (.86, spec, 235), (1, spec, 245)):
            color = QColor(tone)
            color.setAlpha(round(alpha*envelope))
            gradient.setColorAt(stop, color)
        painter.save()
        painter.translate(rect.topLeft())
        painter.scale(rect.width()/_VIEWBOX[2], rect.height()/_VIEWBOX[3])
        painter.setBrush(Qt.NoBrush)
        widths = _GEOMETRY['wave_widths']
        halo = QColor(top)
        halo.setAlpha(round(28*envelope))
        painter.setPen(QPen(halo, widths['halo'], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(segment)
        painter.setPen(QPen(QBrush(gradient), widths['signal'], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(segment)
        leading = max(0, head-.055)
        if leading < finish:
            color = QColor(spec)
            color.setAlpha(round(235*envelope))
            painter.setPen(QPen(color, widths['leading'], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path.trimmed(leading, finish))
        painter.restore()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if not self._enabled:
            _svg_renderer(_themed_svg(True)).render(painter, QRectF(self.rect()))
            painter.end()
            return
        size = min(self.width(), self.height())
        rect = QRectF((self.width()-size)/2, (self.height()-size)/2, size, size)
        from . import theme
        strength = min(1.0, self._display_cpu/100)
        tint = QColor(theme.accent())
        aura = QRadialGradient(rect.center(), size*.51)
        for stop, alpha in ((0, 12+40*strength), (.65, 4+18*strength), (1, 0)):
            color = QColor(tint)
            color.setAlpha(round(alpha))
            aura.setColorAt(stop, color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(aura)
        painter.drawEllipse(rect)
        if self._update_available:
            beat = .5+.5*math.sin(self._update_clock)
            glow = QRadialGradient(rect.center(), size*.55)
            for stop, alpha in ((0, 70+95*beat), (.53, 27+63*beat), (1, 0)):
                color = QColor(tint)
                color.setAlpha(round(alpha))
                glow.setColorAt(stop, color)
            painter.setBrush(glow)
            painter.drawEllipse(rect)
        self._paint_layers(painter, rect)
        if self._update_available:
            beat = .5+.5*math.sin(self._update_clock)
            color = QColor(tint)
            color.setAlpha(round(65+105*beat))
            painter.setPen(QPen(color, 1.3+beat*1.2))
            painter.setBrush(Qt.NoBrush)
            span = size*(.887+beat*.019)
            painter.drawEllipse(QRectF(rect.center().x()-span/2, rect.center().y()-span/2, span, span))
        self._paint_pulse(painter, rect)
        painter.end()
