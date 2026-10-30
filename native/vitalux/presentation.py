"""Shared spacing, readable content areas and design-aware dialog materials."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from . import theme
from .paint_geometry import rounded


def card_margins(width):
    side = 16 if width < 520 else 20
    return side, 16, side, 18


def paint_content_wash(painter, rect, *, compact=False):
    """Calm reflections in the data area, keeping the authored rim visible."""
    if theme.mode() == 'minimal':return
    from . import signature_designs
    inset = rect.adjusted(7, 5, -7, -5)
    if inset.width() <= 0 or inset.height() <= 0:return
    path = (signature_designs.shape(inset, theme.mode(), compact)
            if signature_designs.active() else rounded(inset, 9 if compact else 14))
    alpha = 48 if theme.mode() in ('glass', 'crystal_atrium') else 24 if theme.is_light() else 32
    solid = QColor(theme.CARD);solid.setAlpha(alpha)
    clear = QColor(solid);clear.setAlpha(0)
    wash = QLinearGradient(inset.topLeft(), inset.bottomLeft())
    for position, color in ((0, clear), (.18, solid), (.82, solid), (1, clear)):
        wash.setColorAt(position, color)
    painter.fillPath(path, wash)


def paint_dialog(widget):
    from .glass import paint_glass_body
    painter = QPainter(widget)
    painter.fillRect(widget.rect(), QColor(theme.BG))
    if theme.mode() != 'minimal':painter.setRenderHint(QPainter.Antialiasing)
    paint_glass_body(painter, widget, QRectF(widget.rect()).adjusted(5,5,-5,-5), 21, strong=True)
    paint_content_wash(painter, QRectF(widget.rect()).adjusted(5,5,-5,-5))
    painter.end()


def prepare_dialog(widget):
    """Use one safe content gutter while retaining native dialog semantics."""
    layout = widget.layout()
    if layout:
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
    screen = widget.screen()
    if screen:
        available = screen.availableGeometry()
        widget.resize(min(widget.width(), max(widget.minimumWidth(), available.width()-40)),
                      min(widget.height(), max(widget.minimumHeight(), available.height()-60)))


def stylesheet():
    """Apply hierarchy and target sizes after each design's own palette rules."""
    corners='border-top-left-radius:20px;border-bottom-right-radius:20px;border-top-right-radius:5px;border-bottom-left-radius:5px;' if theme.mode()=='aurora_bloom' else 'border-radius:10px;'
    return f'''
    QLabel#strong {{font-weight:650; color:{theme.TEXT};}}
    QLabel#telemetryValue {{font-weight:700;}}
    QLabel#cardTitle {{font-size:11px; font-weight:700; letter-spacing:1.1px;}}
    QLabel#chipTitle {{font-size:11px; font-weight:600;}}
    QLabel#chipValue {{font-size:15px; font-weight:700;}}
    QPushButton#ghostBtn,QPushButton#primaryBtn {{
        min-height:18px; padding:8px 14px; {corners}}}
    QDialog QPushButton {{min-height:18px; min-width:64px; padding:8px 14px;
        border:1px solid {theme.BORDER}; {corners}
        background:{theme.combo_surface()}; color:{theme.TEXT};}}
    QDialog QPushButton:hover,QDialog QPushButton:focus {{border-color:{theme.accent()};}}
    QDialog QPushButton:default {{border-color:{theme.accent()}; font-weight:700;}}
    QDialog QPlainTextEdit {{background:{theme.CARD};color:{theme.TEXT};
        border:1px solid {theme.BORDER};border-radius:10px;padding:10px;}}
    ''' if theme.mode() != 'minimal' else ''

