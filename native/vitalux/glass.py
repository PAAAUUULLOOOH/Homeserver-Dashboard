"""Native glass materials for the Vitalux Qt6 interface.

Glass samples a cached, softly blurred in-app backdrop,
matching each card's actual position. The painted interior stays opaque.
Glass materials do not depend on KWin blur-behind effects.
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QFrame, QWidget

from . import theme, settings, backdrops, user_background, renderer, premium

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def rgba(r, g, b, a):
    return QColor(r, g, b, a)


from .paint_geometry import rounded


class _AmbientSceneCore:
    """Shared cached-background implementation for raster and OpenGL hosts."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('root')
        self.setAutoFillBackground(False)
        # Standalone scenes repaint all pixels. The rounded window frame
        # disables this hint for its transparent outer corners.
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._sharp_cache = QPixmap()
        self._soft_cache = QPixmap()
        self._render_key = None
        self._composed_key = None
        self._composed_sharp = QPixmap()
        self._composed_soft = QPixmap()
        self._phase = 0.0
        self._wallpaper_timer = QTimer(self)
        self._wallpaper_timer.setInterval(250)
        self._wallpaper_timer.timeout.connect(self._advance_backdrop)
        self.sync_background()

    def sync_background(self):
        self._render_key = None
        self._composed_key = None
        style = backdrops.resolve(settings.observed('background_style', 'theme_default'),
                                  theme.mode())
        # Only designs with moving backgrounds participate in this timer.
        # Quantum Core uses a cached static image; its logos stay independent.
        active = style in backdrops.ANIMATED_PRESETS and self.isVisible()
        if active and not self._wallpaper_timer.isActive():
            self._wallpaper_timer.start()
        elif not active:
            self._wallpaper_timer.stop()
            if style not in backdrops.ANIMATED_PRESETS:self._phase = 0.0
        self.update()

    def showEvent(self,event):
        super().showEvent(event)
        style=backdrops.resolve(settings.observed('background_style','theme_default'),theme.mode())
        if style in backdrops.ANIMATED_PRESETS:self._wallpaper_timer.start()

    def hideEvent(self,event):
        self._wallpaper_timer.stop()
        super().hideEvent(event)

    def _advance_backdrop(self):
        if not self.isVisible():
            return
        cycle = 6.28318530718
        self._phase = (self._phase + .13) % cycle
        self._composed_key = None
        self._render_key = None
        self.update()
        # Keep live glass sampling aligned to the painted moving backdrop.
        for kind in (GlassSurface, GlassSidebar):
            for card in self.findChildren(kind):
                if card.isVisible():
                    card.update()

    def set_low_power(self, enabled):
        """Free the atmospheric pixmaps in Minimalistisch; reload only if needed."""
        if enabled and backdrops.resolve(settings.observed('background_style', 'theme_default'),
                                         theme.mode()) == 'minimal':
            # Minimal releases the caches; normal scenes rebuild on return.
            self._sharp_cache = QPixmap()
            self._soft_cache = QPixmap()
            self._render_key = None
            self._composed_key = None
        self.sync_background()

    def _ensure_cache(self):
        # The softened atmosphere is an internal backdrop sampled under glass.
        style = backdrops.resolve(settings.observed('background_style', 'theme_default'),
                                  theme.mode())
        if style == 'minimal' and theme.mode() == 'minimal':
            return
        if style == 'custom_image':
            chosen = settings.observed('custom_background_selected', '')
            fit = settings.observed('custom_background_fit', 'cover')
            path = user_background.image_path(chosen)
            stamp = path.stat().st_mtime_ns if path else None
            ratio=self.devicePixelRatioF() if theme.mode()=='crystal_atrium' else 1.0
            size=self.size()*ratio
            key = (style, chosen, fit, stamp, theme.BG, size, ratio)
            if key != self._render_key:
                self._sharp_cache = user_background.draw(size, chosen, fit)
                self._soft_cache = backdrops.smooth_glass(self._sharp_cache,18*ratio) if theme.mode()=='crystal_atrium' else self._sharp_cache
                self._sharp_cache.setDevicePixelRatio(ratio);self._soft_cache.setDevicePixelRatio(ratio)
                self._render_key = key
            return
        ratio=self.devicePixelRatioF() if theme.mode()=='crystal_atrium' else 1.0
        size=self.size()*ratio
        key=(style,size,ratio,theme.mode()=='crystal_atrium',round(self._phase,3) if style in backdrops.ANIMATED_PRESETS else 0,
             theme.accent() if style in ('adaptive','animated_sparkle') else '')
        if key!=self._render_key:
            self._sharp_cache,self._soft_cache=backdrops.render(size,style,theme.accent(),light=theme.is_light(),phase=self._phase,
                                                             soften=theme.mode()!='crystal_atrium')
            if theme.mode()=='crystal_atrium':self._soft_cache=backdrops.smooth_glass(self._sharp_cache,18*ratio)
            self._sharp_cache.setDevicePixelRatio(ratio);self._soft_cache.setDevicePixelRatio(ratio)
            self._render_key=key

    def _ensure_composed(self):
        style=backdrops.resolve(settings.observed('background_style','theme_default'),theme.mode())
        if style=='minimal' and theme.mode()=='minimal':
            self._composed_sharp=QPixmap();self._composed_soft=QPixmap();self._composed_key=None;return
        self._ensure_cache()
        if self._sharp_cache.isNull():return
        key=(self._render_key,self.size())
        if key!=self._composed_key:
            self._composed_sharp=self._sharp_cache
            self._composed_soft=self._soft_cache
            self._composed_key=key

    def soft_backdrop(self):
        self._ensure_composed()
        return self._composed_soft

    def sharp_backdrop(self):
        self._ensure_composed()
        return self._composed_sharp

    def _paint_background(self):
        p = QPainter(self)
        framed = self.property('vitaluxRoundedWindow')
        if framed:
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.fillRect(self.rect(), Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        else:
            p.fillRect(self.rect(), QColor(theme.BG))
        style = backdrops.resolve(settings.observed('background_style', 'theme_default'),
                                  theme.mode())
        if style == 'minimal' and theme.mode() == 'minimal':
            background = QBrush(backdrops.minimal_color())
        else:
            self._ensure_composed()
            background = QBrush(self._composed_sharp) if not self._composed_sharp.isNull() else QBrush(QColor(theme.BG))
        if framed:
            from .window_frame import outline
            p.setRenderHint(QPainter.Antialiasing)
            p.fillPath(outline(self.rect(), self.property('vitaluxWindowRadius') or 0), background)
            if not self.property('vitaluxOutlineOverlay'):
                p.setPen(QPen(QColor(theme.BORDER), 1))
                p.drawPath(outline(self.rect(), self.property('vitaluxWindowRadius') or 0))
        elif style=='minimal' and theme.mode()=='minimal':
            p.fillRect(self.rect(), background)
        else:
            if not self._composed_sharp.isNull():
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.drawPixmap(0, 0, self._composed_sharp)
        p.end()


class AmbientScene(_AmbientSceneCore, QWidget):
    """Established Qt raster renderer. Always available and the default."""
    def paintEvent(self, event):
        self._paint_background()




def create_ambient_scene():
    """Select one backend at startup; never hot-swap a GL surface."""
    if renderer.desired() in renderer.QUICK_MODES:
        if renderer.quick_available():
            try:
                from .quick_scene import QuickAmbientScene
                scene = QuickAmbientScene()
                scene.render_backend = renderer.desired()  # Retain the explicitly selected X11 backend.
                return scene
            except (ImportError, RuntimeError, OSError) as exc:
                print('Vitalux: Qt Quick konnte nicht initialisiert werden:', exc)
        renderer.fallback()
    scene = AmbientScene()
    scene.render_backend = renderer.SOFTWARE
    return scene


def scene_for(widget):
    current = widget.parentWidget()
    while current is not None:
        if isinstance(current, _AmbientSceneCore):
            return current
        current = current.parentWidget()
    return None


def draw_frosted_backdrop(p, widget, target, opacity=1.0, *, softened=True):
    """Sample a cached blur from the *correct viewport position* on each repaint.

    Scroll offsets are handled by Qt's mapTo() on the widget, not by a local
    counter; this avoids cards showing identical/floating backgrounds.
    """
    scene = scene_for(widget)
    if scene is None:
        return
    image = scene.soft_backdrop() if softened else scene.sharp_backdrop()
    if image.isNull():
        return
    pos = widget.mapTo(scene, QPoint(0, 0))
    ratio=image.devicePixelRatioF()
    src = QRectF((pos.x() + target.x())*ratio, (pos.y() + target.y())*ratio,
                 target.width()*ratio, target.height()*ratio)
    p.save()
    p.setOpacity(opacity)
    # The source crop and destination are equal-sized in scene coordinates.
    # Avoid the expensive smooth resampling path during every scroll repaint.
    if abs(src.width()-target.width()) > .01 or abs(src.height()-target.height()) > .01:
        p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawPixmap(target, image, src)
    p.restore()


def paint_rim(p, rect, radius, *, active=False, compact=False):
    """Accent-aware thin light seams, strongest on selected elements."""
    outer = rounded(rect, radius)
    a = theme.accent_qcolor()
    other = QColor(theme.secondary_accent())
    if theme.mode() not in ('glass',):
        edge = QColor(theme.BORDER)
        if active:
            edge = a
        p.setPen(QPen(edge, 1.4 if active else 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(outer)
        return
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, rgba(224, 245, 255, 119))
    a.setAlpha(184 if active else 45)
    other.setAlpha(144 if active else 42)
    grad.setColorAt(.3, a)
    grad.setColorAt(.7, rgba(155, 185, 225, 65))
    grad.setColorAt(1, other)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QBrush(grad), 1.35 if active else 1.1))
    p.drawPath(outer)
    inset = rect.adjusted(2.4, 2.4, -2.4, -2.4)
    if inset.width() > 10 and inset.height() > 10:
        shine = QLinearGradient(inset.topLeft(), inset.bottomRight())
        shine.setColorAt(0, rgba(255, 255, 255, 46))
        shine.setColorAt(1, rgba(255, 255, 255, 0))
        p.setPen(QPen(QBrush(shine), 1.0))
        p.drawPath(rounded(inset, max(2, radius - 2.4)))
    top = QLinearGradient(rect.left(), 0, rect.right(), 0)
    top.setColorAt(0, rgba(255, 255, 255, 0))
    top.setColorAt(.17, rgba(246, 253, 255, 118))
    top.setColorAt(.65, rgba(232, 246, 255, 40))
    top.setColorAt(1, rgba(255, 255, 255, 0))
    p.setPen(QPen(QBrush(top), 1.2, Qt.SolidLine, Qt.RoundCap))
    padx = min(radius + 8, rect.width()*.2)
    p.drawLine(QPointF(rect.left()+padx, rect.top()+1.2), QPointF(rect.right()-padx, rect.top()+1.2))
    if rect.height() > 40 and not compact:
        lower = QLinearGradient(rect.left(), 0, rect.right(), 0)
        a.setAlpha(0); other.setAlpha(74)
        lower.setColorAt(0, a)
        a.setAlpha(28)
        lower.setColorAt(.42, a)
        lower.setColorAt(1, other)
        p.setPen(QPen(QBrush(lower), 1.5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(rect.left()+padx, rect.bottom()-1.1), QPointF(rect.right()-padx, rect.bottom()-1.1))


def paint_glass_body(p, widget, rect, radius, *, strong=False, compact=False, active=False):
    """Frosted materials sample a shared blurred backdrop; Dark/Light stay opaque."""
    if theme.mode() in premium.KEYS:
        premium.paint_panel(p, widget, rect, strong=strong, compact=compact, active=active)
        return
    if theme.mode() == "minimal":
        # No frosted backdrop, rounded paths, gradients or specular passes.
        p.fillRect(rect, QColor(theme.CARD))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(rect)
        return
    glass = rounded(rect, radius)
    p.save()
    p.setClipPath(glass)
    if theme.mode() not in ('glass',):
        # Solid cards are intentional. Dark and Light must not resemble frosted glass.
        bg_style = backdrops.resolve(settings.observed('background_style', 'theme_default'),
                                     theme.mode())
        bg = backdrops.material_tint(bg_style, theme.CARD, theme.accent(), .085)
        tint = QColor(theme.accent())
        bg2 = QColor(theme.CARD)
        bg2.setRed(round(bg2.red()*.94+tint.red()*.06))
        bg2.setGreen(round(bg2.green()*.94+tint.green()*.06))
        bg2.setBlue(round(bg2.blue()*.94+tint.blue()*.06))
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        g.setColorAt(0, bg2 if strong or active else bg)
        g.setColorAt(1, bg)
        p.fillPath(glass, QBrush(g))
    else:
        draw_frosted_backdrop(p, widget, rect, 1.0)
        overlay = QLinearGradient(rect.topLeft(), rect.bottomRight())
        overlay.setColorAt(0, rgba(28, 62, 88, 108 if strong else 80))
        overlay.setColorAt(.54, rgba(13, 27, 49, 130 if strong else 103))
        overlay.setColorAt(1, rgba(27, 31, 61, 123 if strong else 103))
        style = backdrops.resolve(settings.observed('background_style', 'theme_default'),
                                  theme.mode())
        if style not in backdrops.DEFAULT_THEMES:
            # New wallpapers reflect subtly in the cards, but the accent hue
            # does not overwrite the text contrast of Glass/Black Glass.
            material = backdrops.material_tint(style, theme.CARD, theme.accent(), .24)
            top = QColor(material)
            top.setAlpha(174 if strong else
                         149 if style in backdrops.LIGHT_PRESETS else 128)
            bottom = QColor(material).darker(125)
            bottom.setAlpha(166 if strong else 136)
            overlay.setColorAt(0, top)
            overlay.setColorAt(1, bottom)
        p.fillPath(glass, QBrush(overlay))
        accent = theme.accent_qcolor()
        accent.setAlpha(43 if strong or active else 17)
        shine = QRadialGradient(rect.left() + rect.width()*.19, rect.top() - rect.height()*.13, max(32, rect.width()*.85))
        shine.setColorAt(0, accent)
        end = QColor(accent); end.setAlpha(0)
        shine.setColorAt(1, end)
        p.fillPath(glass, QBrush(shine))
        reflection = QPainterPath()
        reflection.moveTo(rect.left(), rect.top())
        reflection.lineTo(rect.left()+rect.width()*.53, rect.top())
        reflection.lineTo(rect.left()+rect.width()*.14, rect.top()+rect.height()*.72)
        reflection.lineTo(rect.left(), rect.top()+rect.height()*.78)
        reflection.closeSubpath()
        spec = QLinearGradient(rect.left(), rect.top(), rect.left()+rect.width()*.51, rect.bottom())
        spec.setColorAt(0, rgba(251, 255, 255, 27))
        spec.setColorAt(.50, rgba(210, 234, 255, 10))
        spec.setColorAt(1, rgba(180, 218, 255, 0))
        p.fillPath(reflection, QBrush(spec))
    p.restore()
    paint_rim(p, rect, radius, active=active, compact=compact)


class GlassSidebar(QFrame):
    """A full-height, truly frosted sidebar behind the logo and ALL categories."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('sidebar')
        self.setAutoFillBackground(False)
        self._toggle_button = None

    def set_toggle_button(self, button):
        self._toggle_button = button
        button.setParent(self)
        self._position_toggle()
        button.show()
        button.raise_()

    def _position_toggle(self):
        if self._toggle_button is not None:
            self._toggle_button.move(
                self.width() - self._toggle_button.width() - 5, getattr(self,'_toggle_y',13))
            self._toggle_button.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toggle()

    def paintEvent(self,event):
        # Keep direct compositing: recording the layered material changes Qt's
        # clip/alpha rounding at fractional display scales.
        if self.property('vitaluxEdgeJoined'):return
        painter=QPainter(self)
        self._paint_material(painter)
        painter.end()

    def _paint_material(self, p, area=None):
        """Restore the original Vitalux frosted sidebar and luminous seam.

        Matching Glass/Black Glass/Light/Dark schemes keep their original
        treatment. For new wallpapers, the frost adapts gently to the chosen
        palette so it remains related to the cards and the scene.
        """
        area=QRectF(self.rect()) if area is None else area
        if theme.mode() in premium.KEYS:
            p.setRenderHint(QPainter.Antialiasing)
            premium.paint_sidebar(p, self, area)
            return
        style = backdrops.resolve(settings.observed('background_style', 'theme_default'),
                                  theme.mode())
        matching = style == theme.mode()
        if theme.mode() == 'minimal' and style == 'minimal':
            # Original opaque sidebar with a stable monochrome material.
            base = backdrops.minimal_color()
            p.fillRect(area, QColor(theme.blend(theme.SIDEBAR, base.name(), .68)))
        else:
            p.setRenderHint(QPainter.Antialiasing)
            rect = area
            if theme.mode() in ('glass',):
                draw_frosted_backdrop(p, self, rect, 1.0)
                shade = QLinearGradient(0, 0, self.width(), 0)
                left, right = (159, 130) if matching else (
                    (51, 43) if style in backdrops.LIGHT_PRESETS
                    else (112, 96))
                shade.setColorAt(0, rgba(7, 15, 30, left))
                shade.setColorAt(1, rgba(15, 28, 47, right))
                p.fillRect(rect, QBrush(shade))
            else:
                material = QColor(theme.blend(theme.SIDEBAR, theme.CARD, .63))
                if style in backdrops.LIGHT_PRESETS and theme.mode() != 'light':
                    material.setAlpha(80)
                elif not matching:
                    material.setAlpha(210 if theme.mode() == 'light' else 188)
                p.fillRect(rect, material)
        side = QLinearGradient(0, 0, 0, max(1, area.height()))
        accent = theme.accent_qcolor(130 if theme.mode() in ('glass',) else 82)
        side.setColorAt(0, QColor(theme.BORDER))
        side.setColorAt(.5, accent)
        side.setColorAt(1, QColor(theme.BORDER))
        p.setPen(QPen(QBrush(side), 1.1))
        x = self.width()-1
        p.drawLine(QPointF(x,0),QPointF(x,area.height()))



class GlassSurface(QFrame):
    """Glass card: soft refraction, reduced dark overlay and lit interior bevel."""
    def __init__(self, parent=None, *, hero=False, compact=False):
        super().__init__(parent)
        self._hero = hero
        self._compact = compact
        self._hover = False
        self.setObjectName('heroCard' if hero else 'chip' if compact else 'card')
        self.setAutoFillBackground(False)

    def enterEvent(self, event):
        self._hover = True
        if theme.mode() != "minimal" and self.property('interactiveSurface'):
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if theme.mode() != "minimal" and self.property('interactiveSurface'):
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        if theme.mode() != "minimal":
            p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        if r.width() >= 8 and r.height() >= 8:
            radius = 12 if self._compact else 21 if self._hero else 17
            paint_glass_body(p, self, r, radius,
                             strong=self._hero, compact=self._compact,
                             active=self._hover and bool(self.property('interactiveSurface')))
            from .presentation import paint_content_wash
            paint_content_wash(p, r, compact=self._compact)
        p.end()

