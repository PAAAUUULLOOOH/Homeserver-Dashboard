import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget, QGraphicsDropShadowEffect
from .ui_locale import QPushButton

from . import theme, motion, premium
from .glass import GlassSurface, paint_glass_body, rgba
from .i18n import tr
from .nav_icons import GLYPHS, paint_icon


from .ui_labels import label


def _glass_shadow(widget, blur=30, y=8, alpha=44):
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, y)
    c = QColor(0, 0, 0)
    c.setAlpha(alpha)
    fx.setColor(c)
    widget.setGraphicsEffect(fx)


class Card(GlassSurface):
    def __init__(self, title=None, hero=False):
        super().__init__(hero=hero)
        _glass_shadow(self, 26 if hero else 18, 6 if hero else 3, 42 if hero else 27)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(12)
        if title:
            lay.addWidget(label(title.upper(), "cardTitle"))
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        lay.addLayout(self.body)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Preserve useful text width on small windows without shrinking meters.
        from .presentation import card_margins
        self.layout().setContentsMargins(*card_margins(self.width()))


class StatChip(GlassSurface):
    def __init__(self, title, value="–"):
        super().__init__(compact=True)
        _glass_shadow(self, 12, 2, 18)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        lay.addWidget(label(title, "chipTitle", wrap=True))
        self.value = label(value, "chipValue", wrap=True)
        lay.addWidget(self.value)

    def set(self, value):
        self.value.setText(tr(value))
        self.value.setToolTip(tr(value))


class ChipsGrid(QWidget):
    def __init__(self, titles, columns=4):
        super().__init__()
        self.columns = columns
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        self.chips = {}
        for i, t in enumerate(titles):
            chip = StatChip(t)
            self.chips[t] = chip
            self.grid.addWidget(chip, i // columns, i % columns)

    def set(self, title, value):
        if title in self.chips:
            self.chips[title].set(value)


class Bar(QWidget):
    def __init__(self):
        super().__init__()
        self.value = 0.0
        self.flat = False
        self.custom_color = None
        self.setFixedHeight(8)

    def set_value(self, v):
        self.value = 0.0 if v is None else max(0.0, min(100.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if theme.mode() == 'minimal':
            p.fillRect(self.rect(), QColor(theme.TRACK))
            p.fillRect(0, 0, round(self.width()*self.value/100.0), self.height(),
                       QColor(self.custom_color or theme.level_color(self.value)))
            p.end()
            return
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(QPen(QColor(theme.BORDER), 1))
        base = QColor(theme.TRACK)
        if theme.mode() == "light":
            base.setAlpha(95)
        else:
            base.setAlpha(80)
        p.setBrush(base)
        p.drawRoundedRect(r, 4, 4)
        w = r.width() * self.value / 100
        if w > 0:
            p.setBrush(QColor(self.custom_color or (theme.accent() if self.flat else theme.level_color(self.value))))
            p.drawRoundedRect(QRectF(0, 0, max(w, 8), r.height()), 4, 4)


class Meter(QWidget):
    def __init__(self, text):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        row = QHBoxLayout()
        self.name = label(text, "muted")
        self.value = label("–", "strong", Qt.AlignRight)
        row.addWidget(self.name)
        row.addStretch(1)
        row.addWidget(self.value)
        lay.addLayout(row)
        self.bar = Bar()
        lay.addWidget(self.bar)

    def set(self, pct, text=None):
        self.bar.set_value(pct)
        self.value.setText(tr(text) if text is not None else ("–" if pct is None else f"{pct:.0f}%"))


class KeyValue(QWidget):
    def __init__(self, key):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.addWidget(label(key, "muted"))
        lay.addStretch(1)
        self.v = label("–", "strong", Qt.AlignRight, wrap=True)
        self.v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.v, 1)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_details)
        self.v.setContextMenuPolicy(Qt.CustomContextMenu)
        self.v.customContextMenuRequested.connect(self._show_details)

    def _show_details(self, _):
        from PySide6.QtWidgets import QApplication, QMenu
        from PySide6.QtGui import QCursor
        text = self.toolTip() or self.v.toolTip()
        menu = QMenu(self)
        menu.addAction(tr('Kopieren'), lambda: QApplication.clipboard().setText(self.v.selectedText() or self.v.text()))
        if text:
            from .detail_dialog import show_details
            def open_details():
                self._detail_dialog = show_details(self, 'Datenquelle', text)
            menu.addAction(tr('Datenquelle'), open_details)
        try:menu.exec(QCursor.pos())
        finally:menu.deleteLater()

    def set(self, text):
        self.v.setText(tr(text))


class Gauge(QWidget):
    def __init__(self):
        super().__init__()
        self.value = None
        self._render_value = None
        self._target = None
        self.text = None
        self.semantic = 'load'
        font = self.font()
        font.setFamilies(['DejaVu Sans Mono', 'Noto Sans Mono', 'monospace'])
        self.setFont(font)
        self._animate = QTimer(self)
        self._animate.setInterval(25)
        self._animate.timeout.connect(self._tick)
        self.setMinimumSize(130, 130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_semantic(self, semantic):
        self.semantic = semantic or 'load'
        self.update()

    def _ring_color(self, value):
        if self.semantic == 'score':
            if value is None or value >= 86:
                return theme.accent()
            if value >= 66:
                return theme.WARN
            return theme.CRIT
        return theme.level_color(value)

    def set(self, value, text=None):
        self.text = text
        self.value = value
        self._target = value
        if theme.mode() == "minimal" or not self.isVisible():
            self._animate.stop()
            self._render_value = value
            self.update()
            return
        if value is None:
            self._render_value = None
            self._animate.stop()
            self.update()
            return
        if self._render_value is None:
            self._render_value = 0.0
        self._animate.start()

    def _tick(self):
        if self._render_value is None or self._target is None:
            self._animate.stop()
            return
        self._render_value += (self._target - self._render_value) * 0.32
        if abs(self._render_value - self._target) < 0.15:
            self._render_value = self._target
            self._animate.stop()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if theme.mode() == 'minimal':
            shown = self.text if self.text is not None else (
                '–' if self.value is None else f'{self.value:.0f}%')
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(max(16, min(self.width(), self.height()) // 6))
            p.setFont(font)
            p.setPen(QColor(theme.TEXT))
            p.drawText(self.rect(), Qt.AlignCenter, shown)
            p.end()
            return
        p.setRenderHint(QPainter.Antialiasing)
        if theme.mode() in premium.KEYS:
            value = self._render_value
            premium.paint_gauge(p, self, value, self.text,
                                self._ring_color(value or 0))
            p.end()
            return
        side = min(self.width(), self.height())
        pen_w = max(9.0, side * 0.08)
        rect = QRectF((self.width() - side) / 2 + pen_w / 2, (self.height() - side) / 2 + pen_w / 2,
                      side - pen_w, side - pen_w)
        p.setPen(QPen(QColor(theme.TRACK), pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 225 * 16, -270 * 16)
        if self._render_value is not None:
            v = max(0.0, min(100.0, self._render_value))
            ring_color = self._ring_color(v)
            glow = QColor(ring_color)
            glow.setAlpha(35)
            p.setPen(QPen(glow, pen_w * 1.75, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 225 * 16, int(-270 * 16 * v / 100))
            grad = QConicalGradient(rect.center(), 90)
            grad.setColorAt(0, QColor(ring_color))
            grad.setColorAt(0.7, QColor(theme.secondary_accent()))
            grad.setColorAt(1, QColor(ring_color))
            p.setPen(QPen(QBrush(grad), pen_w, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 225 * 16, int(-270 * 16 * v / 100))
        font = QFont(self.font())
        font.setPixelSize(int(side * 0.22))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(theme.TEXT))
        shown = self.text if self.text is not None else ("–" if self.value is None else f"{self.value:.0f}%")
        p.drawText(rect, Qt.AlignCenter, shown)


from .overview_text import ElidedLabel

class GaugeCaption(ElidedLabel):
    """Bounded model name; the complete name remains available on hover."""
    pass


class GaugeBox(QWidget):
    def __init__(self, title=None, compact_caption=False, gauge_semantic='load'):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.gauge = Gauge()
        self.gauge.set_semantic(gauge_semantic)
        lay.addWidget(self.gauge, 1)
        if title:
            lay.addWidget(label(title, "gaugeTitle", Qt.AlignHCenter))
        self.sub = GaugeCaption() if compact_caption else label("", "muted", Qt.AlignHCenter, wrap=True)
        lay.addWidget(self.sub)

    def set(self, value, sub="", text=None):
        self.gauge.set(value, text)
        if isinstance(self.sub, GaugeCaption):
            self.sub.set_caption(sub)
        else:
            self.sub.setText(tr(sub))


class GaugeCard(Card):
    def __init__(self, title, compact_caption=False, gauge_semantic='load'):
        super().__init__(title)
        self.box = GaugeBox(compact_caption=compact_caption, gauge_semantic=gauge_semantic)
        self.body.addWidget(self.box)

    def set(self, value, sub="", text=None):
        self.box.set(value, sub, text)


class _SoftHover:
    """A tiny scalar animation – no layouts or surfaces are repainted indirectly."""

    def _init_soft_hover(self):
        self._hover_amount = 0.0
        self._hover_motion = QVariantAnimation(self)
        self._hover_motion.setEasingCurve(QEasingCurve.InOutCubic)
        self._hover_motion.valueChanged.connect(self._hover_frame)

    def _hover_frame(self, value):
        self._hover_amount = max(0.0, min(1.0, float(value)))
        self.update()

    def _set_hover(self, value):
        self._hover_motion.stop()
        ms = motion.timing('hover')
        if not ms:
            self._hover_frame(value)
            return
        self._hover_motion.setDuration(ms)
        self._hover_motion.setStartValue(self._hover_amount)
        self._hover_motion.setEndValue(float(value))
        self._hover_motion.start()

    def enterEvent(self, event):
        self._set_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hover(0.0)
        super().leaveEvent(event)


class NavButton(_SoftHover, QPushButton):
    """Fully drawn frosted-glass navigation, same lighting as the content cards.

    No QPushButton/QSS background gets painted over the translucent material.
    Buttons still use the original accessible keyboard/focus/checked behavior.
    """
    def __init__(self, text):
        super().__init__(text)
        self.glow = False
        self._update_version = ''
        self.icon_key = GLYPHS.get(str(text).split('    ',1)[0].strip(), 'overview')
        self._compact = False
        self._phase = 0.0
        self._init_soft_hover()
        self.setMinimumHeight(39)
        self.setMouseTracking(True)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)

    def sizeHint(self):
        if self._compact:
            return QSize(44, 39)
        return super().sizeHint()

    def minimumSizeHint(self):
        if self._compact:
            return QSize(44, 39)
        return super().minimumSizeHint()

    def set_compact(self, compact):
        self._compact = bool(compact)
        # A compact button must not reserve space for its hidden text.
        self.setMinimumWidth(0)
        if compact:
            self.setFixedWidth(44)
        else:
            self.setMaximumWidth(16777215)
        caption = self.text().split('    ', 1)[-1]
        self.setAccessibleName(caption)
        self.setToolTip('')
        self.updateGeometry()
        self.update()


    def set_update_version(self, version):
        self._update_version = str(version or '')
        # The icon-only dock paints a badge, so it does not need an extra
        # caption row like the sidebar's update button.
        from . import theme
        self.setMinimumHeight(46 if theme.mode() == 'nebula_prism' else 47 if self._update_version else 39)
        self.setAccessibleDescription(tr('Update verfügbar:') + ' ' + self._update_version if self._update_version else '')
        self._sync_notice_animation()
        self.updateGeometry()
        self.update()

    def set_glow(self, on):
        self.glow = bool(on)
        self._sync_notice_animation()
        self.update()

    def _sync_notice_animation(self):
        if self.glow and self.isVisible() and motion.level() == 'smooth' and motion.enabled():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_notice_animation()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self):
        self._phase = (self._phase + .19) % math.tau
        self.update()

    def _notice_intensity(self):
        return .5 + .5 * math.sin(self._phase) if self.glow and motion.level() == 'smooth' and motion.enabled() else .65

    def paint_update_background(self, painter, rect, path=None):
        if not (self._update_version or self.glow):return
        painter.save()
        amount = self._notice_intensity()
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.accent_qcolor(round(28 + 40 * amount)))
        if path is not None:painter.drawPath(path)
        else:painter.drawRoundedRect(rect, 10, 10)
        painter.restore()

    def paint_notice_and_focus(self, painter, rect, path=None):
        painter.save()
        if self._update_version or self.glow:
            amount = self._notice_intensity()
            tone = QColor(theme.accent())
            # A solid badge stays visible even at the pulse's dimmest point.
            # Its contrasting rim works over bright glass and dark materials.
            point = QPointF(rect.right() - (7 if self._compact else 10), rect.top() + 8)
            painter.setPen(QPen(QColor(theme.BG), 1.7))
            painter.setBrush(tone)
            painter.drawEllipse(point, 3.4 + .8 * amount, 3.4 + .8 * amount)
            if self.glow and motion.level() == 'smooth' and motion.enabled():
                painter.setPen(QPen(theme.accent_qcolor(round(75 + 145 * amount)), 1.1))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(point, 5.2 + 1.4 * amount, 5.2 + 1.4 * amount)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(theme.accent_qcolor(230), 1.3))
            if path is not None:painter.drawPath(path)
            else:painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 9, 9)
        painter.restore()

    def _paint_minimal_nav(self):
        """Plain navigation with two text draws and no effects."""
        p = QPainter(self)
        if self.isChecked():
            p.fillRect(self.rect(), QColor(theme.CARD))
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        self.paint_update_background(p, rect)
        text = self.text()
        glyph, caption = text.split('    ', 1) if '    ' in text else ('◈', text)
        color = QColor(theme.accent() if self.isChecked() else theme.TEXT)
        p.setPen(color)
        font = self.font()
        font.setPixelSize(15)
        p.setFont(font)
        paint_icon(p, self.icon_key, QRectF((44-20)/2 if self._compact else 19, (self.height()-20)/2, 20, 20), color)
        if not self._compact:
            font.setPixelSize(13)
            p.setFont(font)
            ypos = 7 if self._update_version else 0
            height = self.height()-19 if ypos else self.height()
            p.drawText(QRectF(52, ypos, max(1, self.width()-54), height), Qt.AlignVCenter | Qt.AlignLeft, caption)
            if self._update_version:
                font.setPixelSize(10)
                font.setBold(True)
                p.setFont(font)
                p.setPen(theme.accent_qcolor())
                p.drawText(QRectF(52, self.height()-20, max(1, self.width()-54), 16),
                           Qt.AlignVCenter | Qt.AlignLeft, self._update_version)
        self.paint_notice_and_focus(p, rect)
        p.end()

    def paintEvent(self, event):
        if theme.mode() == "minimal":
            self._paint_minimal_nav()
            return
        from . import signature_designs
        if signature_designs.active():
            return signature_designs.paint_navigation(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.isDown(): p.translate(0, .8)
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        checked = self.isChecked()
        hover_amount = 1.0 if self.hasFocus() else self._hover_amount
        hovered = hover_amount > .01
        # Keep the selected card stable; idle hover lighting fades in with a
        # low-alpha brush, rather than forcing a glass redraw every tick.
        if theme.mode() in premium.KEYS:
            premium.paint_nav(p, self, r, checked, hover_amount)
        elif checked:
            paint_glass_body(p, self, r, 11, compact=True, active=True)
        else:
            idle = QColor(218, 243, 255, 7) if theme.mode() != 'light' else QColor(40, 65, 90, 6)
            p.setBrush(idle)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 11, 11)
            if hovered:
                c = theme.accent_qcolor(max(0, round((19 if theme.mode() in ('glass',) else 14) * hover_amount)))
                p.setBrush(c)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(r, 11, 11)

        self.paint_update_background(p, r)

        if checked:
            # A precision-cut cyan seam indicates the current section.
            rail = QLinearGradient(0, r.top(), 0, r.bottom())
            a = theme.accent_qcolor()
            faint = QColor(a); faint.setAlpha(0)
            rail.setColorAt(0.0, faint)
            a.setAlpha(240)
            rail.setColorAt(.22, a)
            a.setAlpha(220)
            rail.setColorAt(.75, a)
            rail.setColorAt(1.0, faint)
            p.setPen(QPen(QBrush(rail), 2.3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(r.left()+1.8, r.top()+9),
                       QPointF(r.left()+1.8, r.bottom()-9))

        text = self.text()
        if '    ' in text:
            glyph, caption = text.split('    ', 1)
            glyph = glyph.strip()
        else:
            glyph, caption = '◈', text
        # Minimal glass node, anchored in the same place on every row.
        cx, cy = (r.center().x() if self._compact else r.left() + 21), r.center().y()
        color = QColor(theme.accent() if checked else theme.blend(theme.accent(), theme.TEXT, .60+.32*hover_amount))
        aura = QColor(color); aura.setAlpha(43 if checked else 10)
        p.setPen(Qt.NoPen)
        p.setBrush(aura)
        p.drawRoundedRect(QRectF(cx-12, cy-12, 24, 24), 7, 7)
        # Distinct category symbols stay recognizable in both wide and compact nav.
        paint_icon(p, self.icon_key, QRectF(cx-10, cy-10, 20, 20), color)

        font = self.font()
        font.setBold(checked)
        font.setPixelSize(13)
        p.setFont(font)
        ink = QColor(color)
        p.setPen(ink)
        if not self._compact:
            if self._update_version:
                p.drawText(QRectF(r.left()+45, r.top()+4, r.width()-54, r.height()-23),
                           Qt.AlignVCenter | Qt.AlignLeft, caption)
                p.setPen(theme.accent_qcolor())
                small = QFont(self.font())
                small.setPixelSize(10)
                small.setBold(True)
                p.setFont(small)
                p.drawText(QRectF(r.left()+45, r.bottom()-20, r.width()-54, 15),
                           Qt.AlignVCenter | Qt.AlignLeft, self._update_version)
            else:
                p.drawText(QRectF(r.left()+45, r.top(), r.width()-54, r.height()),
                           Qt.AlignVCenter | Qt.AlignLeft, caption)

        self.paint_notice_and_focus(p, r)
        p.end()


class SidebarToggle(_SoftHover, QPushButton):
    """Small, keyboard-accessible arrow that docks to the sidebar seam."""
    def __init__(self, parent=None, orientation="horizontal"):
        super().__init__('', parent)
        self._collapsed = False
        self._orientation = orientation
        self._init_soft_hover()
        self.setObjectName('sidebarToggle')
        self.setFixedSize(26, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(tr('Seitenleiste ein-/ausklappen'))
        self.setToolTip(tr('Seitenleiste einklappen'))

    def reset_highlight(self):
        """Clear clicked/focused highlight, especially after closing edit mode."""
        self.clearFocus()
        self._hover_motion.stop()
        self._hover_frame(0.0)
        self.update()

    def set_collapsed(self, collapsed):
        self._collapsed = bool(collapsed)
        self.setToolTip(tr('Seitenleiste ausklappen') if collapsed else tr('Seitenleiste einklappen'))
        self.update()

    def paintEvent(self, event):
        """Theme-native, understated edge control (no generic opaque glass tile).

        The small arrow is kept exactly in place. Only its material, rim and ink
        change with the active theme; hover and keyboard focus remain apparent.
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        mode = theme.mode()
        hover_amount = self._hover_amount
        hovered = hover_amount > .01
        focused = self.hasFocus()
        if focused:
            hover_amount = 1.0

        if mode == 'glass':
            # This control belongs to the frosted sidebar, not to the active
            # navigation items. A mostly clear surface and a faint rim prevent
            # it looking like a bright, glued-on button.
            fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
            fill.setColorAt(0, rgba(34, 59, 81, round(76 + 26 * hover_amount)))
            fill.setColorAt(1, rgba(14, 29, 49, round(47 + 32 * hover_amount)))
            border = rgba(179, 213, 234, round(48 + 52 * hover_amount))
            ink = QColor(theme.blend(theme.accent(), theme.MUTED, hover_amount))
            ink.setAlpha(round(186 + 36 * hover_amount))
        elif mode == 'light':
            # Light deliberately uses a solid, pale button with a visible
            # graphite chevron, rather than transparent frosted navy.
            fill = QColor(theme.blend(theme.CARD, theme.SIDEBAR, .67))
            if hovered:
                fill = QColor(theme.blend(theme.accent(), fill, .07 * hover_amount))
            border = QColor(theme.BORDER)
            border.setAlpha(238)
            ink = QColor(theme.blend(theme.accent(), theme.MUTED, hover_amount))
        else:  # Dark: matte and quiet, matching the surrounding solid rail.
            fill = QColor(theme.blend(theme.CARD, theme.SIDEBAR, .47))
            if hovered:
                fill = QColor(theme.blend(theme.accent(), fill, .09 * hover_amount))
            border = QColor(theme.BORDER)
            border.setAlpha(160)
            ink = QColor(theme.blend(theme.accent(), theme.MUTED, hover_amount))

        if hovered or focused:
            # The distribution/user accent is subtle on hover, but the focus
            # state remains clear for keyboard users in all three themes.
            border = theme.accent_qcolor(
                round((165 if focused else 105 * hover_amount) if mode in ('glass',) else
                      (225 if focused else 168 * hover_amount))
            )
            if focused:
                ink = QColor(theme.accent())
                ink.setAlpha(240)

        p.setBrush(QBrush(fill))
        p.setPen(QPen(border, 1.15 if focused else .85 if mode in ('glass',) else 1.0))
        p.drawRoundedRect(rect, 9, 9)

        if mode in ('glass',):
            # A short, low-opacity specular reflection replaces a harsh
            # bright outline; it is almost invisible until light catches it.
            sheen = rgba(233,248,255,round(35+25*hover_amount))
            p.setPen(QPen(sheen, .8, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(rect.left()+7, rect.top()+1.4),
                       QPointF(rect.right()-7, rect.top()+1.4))

        p.setPen(QPen(ink, 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx, cy = rect.center().x(), rect.center().y()
        if self._orientation == 'vertical':
            shift = -1 if self._collapsed else 1
            p.drawLine(QPointF(cx-4.5,cy-2*shift),QPointF(cx,cy+2.5*shift))
            p.drawLine(QPointF(cx,cy+2.5*shift),QPointF(cx+4.5,cy-2*shift))
        elif self._collapsed:
            p.drawLine(QPointF(cx-2, cy-4.5), QPointF(cx+2.5, cy))
            p.drawLine(QPointF(cx+2.5, cy), QPointF(cx-2, cy+4.5))
        else:
            p.drawLine(QPointF(cx+2, cy-4.5), QPointF(cx-2.5, cy))
            p.drawLine(QPointF(cx-2.5, cy), QPointF(cx+2, cy+4.5))
        p.end()

