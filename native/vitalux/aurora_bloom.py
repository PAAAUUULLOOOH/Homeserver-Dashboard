"""Aurora Bloom: northern-light ribbons, petal-shaped glass and segmented rings.

Everything is painted natively and resolution independent. The atmosphere is
cached by the scene and sampled by the panels through the shared frosted
backdrop; the instruments only repaint on a sensor sample, so the design costs
no continuous animation loop.

The signature form is the *petal*: two large, sweeping corners (upper left and
lower right) opposed by two tight ones. Light gathers along the large corners,
which echoes the rounded frameless window and makes every tile, button and
dock element read as one family.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)

KEY = 'aurora_bloom'
PALETTE = dict(
    title='Aurora Bloom', subtitle='AURORA SILK / PETAL GLASS',
    bg='#030b0e', sidebar='#061419', card='#0a1d22', border='#3fb59f',
    track='#11313a', grid='#16414a', text='#f1fffb', muted='#9fcdc5',
    accent='#4dffc4', secondary='#ff8e6b', light='#2ee6d0', bloom='#ff5f8a',
    shadow='#02070a',
    series=('#4dffc4', '#ff8e6b', '#7aa8ff', '#ffd36a', '#c58bff'))
# Light travels mint -> sky -> lilac -> coral; used for ribbons, rings, edges.
SPECTRUM = ('#4dffc4', '#7ad9ff', '#c58bff', '#ff8e6b')


def color(value, alpha=255):
    c = QColor(value)
    c.setAlpha(max(0, min(255, round(alpha))))
    return c


def stops():
    """Spectrum whose ends follow the active accent and secondary colour."""
    series = palette()['series']
    return (series[0], SPECTRUM[1], SPECTRUM[2], series[1])


def _lerp(a, b, t):
    return a + (b - a) * t


def spectrum_at(t, tones=None):
    """Colour at position *t* (0..1) along the spectrum."""
    tones = tones or stops()
    t = max(0.0, min(1.0, t)) * (len(tones) - 1)
    index = min(len(tones) - 2, int(t))
    a, b = QColor(tones[index]), QColor(tones[index + 1])
    f = t - index
    return QColor(round(_lerp(a.red(), b.red(), f)), round(_lerp(a.green(), b.green(), f)),
                  round(_lerp(a.blue(), b.blue(), f)))


def _spectrum(gradient, alpha=255, tones=None):
    tones = tones or stops()
    for i, tone in enumerate(tones):
        gradient.setColorAt(i / (len(tones) - 1), color(tone, alpha))
    return gradient


# ------------------------------------------------------------------- shape
def radii(rect, compact=False, scale=1.0):
    big = (16 if compact else 34) * scale
    big = max(1.0, min(big, rect.width() * .45, rect.height() * .45))
    small = max(.6, min((4.5 if compact else 9) * scale, big * .5))
    return big, small


def shape(rect, compact=False, scale=1.0):
    """The petal: sweeping upper-left / lower-right corners, tight others."""
    big, small = radii(rect, compact, scale)
    x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    path = QPainterPath()
    path.moveTo(x0 + big, y0)
    path.lineTo(x1 - small, y0)
    path.arcTo(QRectF(x1 - 2 * small, y0, 2 * small, 2 * small), 90, -90)
    path.lineTo(x1, y1 - big)
    path.arcTo(QRectF(x1 - 2 * big, y1 - 2 * big, 2 * big, 2 * big), 0, -90)
    path.lineTo(x0 + small, y1)
    path.arcTo(QRectF(x0, y1 - 2 * small, 2 * small, 2 * small), 270, -90)
    path.lineTo(x0, y0 + big)
    path.arcTo(QRectF(x0, y0, 2 * big, 2 * big), 180, -90)
    path.closeSubpath()
    return path


# -------------------------------------------------------------- atmosphere
def _soften(pixmap, factor):
    """Cheap, smooth blur: down-scale and up-scale with filtering."""
    w, h = pixmap.width(), pixmap.height()
    small = pixmap.scaled(max(2, w // factor), max(2, h // factor), Qt.IgnoreAspectRatio,
                          Qt.SmoothTransformation)
    return small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def _noise(x, seed):
    """Smooth, deterministic 1-D value noise in 0..1 (clumps the rays)."""
    return .5 + .5 * (math.sin(x * .031 + seed) * math.sin(x * .0113 + seed * 1.7) * .6
                      + math.sin(x * .071 + seed * 2.3) * .4)


def _ribbon(p, w, h, base, amplitude, wavelength, phase, drop, tones, alpha):
    """One aurora curtain: soft luminous body, clumped rays and a glowing lip."""
    step = max(8, w // 120)
    xs = list(range(-step, w + 2 * step, step))

    def edge_y(x):
        swell = 1 + .35 * math.sin(2 * math.pi * x / (wavelength * 2.7) + phase * 2.1)
        return (base + amplitude * swell * math.sin(2 * math.pi * x / wavelength + phase)
                + amplitude * .5 * math.sin(2 * math.pi * x / (wavelength * .37) + phase * 1.7)
                + amplitude * .2 * math.sin(2 * math.pi * x / (wavelength * .17) + phase * .6))
    edge = [QPointF(x, edge_y(x)) for x in xs]
    curtain = QPainterPath(edge[0])
    for point in edge[1:]:
        curtain.lineTo(point)
    curtain.lineTo(edge[-1].x(), edge[-1].y() + drop)
    curtain.lineTo(edge[0].x(), edge[0].y() + drop)
    curtain.closeSubpath()
    horizontal = QLinearGradient(0, 0, w, 0)
    for i, tone in enumerate(tones):
        horizontal.setColorAt(i / (len(tones) - 1), color(tone, alpha))
    body = QPixmap(w, h)
    body.fill(Qt.transparent)
    q = QPainter(body)
    q.setRenderHint(QPainter.Antialiasing)
    q.fillPath(curtain, horizontal)
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    fade = QLinearGradient(0, base - amplitude * 1.8, 0, base + drop)
    fade.setColorAt(0, QColor(255, 255, 255, 255))
    fade.setColorAt(.15, QColor(255, 255, 255, 200))
    fade.setColorAt(.55, QColor(255, 255, 255, 70))
    fade.setColorAt(1, QColor(255, 255, 255, 0))
    q.fillRect(QRectF(0, 0, w, h), fade)
    q.end()
    # 1) soft glow around and below the curtain
    glow = _soften(body, 6)
    p.setOpacity(.95)
    p.drawPixmap(0, 0, glow)
    p.setOpacity(.30)
    p.drawPixmap(0, 0, body)
    # 2) rays: the body with a clumped comb removed from it
    rays = QPixmap(body)
    q = QPainter(rays)
    q.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    seed = abs(phase) * 3.1 + 1
    x = 0
    while x < w:
        quiet = _noise(x, seed)
        q.fillRect(QRectF(x, 0, 1.4 + 1.6 * (1 - quiet), h), QColor(0, 0, 0, round(70 + 150 * quiet)))
        x += 2.4
    q.end()
    p.setOpacity(.62)
    p.drawPixmap(0, 0, rays)
    p.setOpacity(1)
    # 3) the luminous lower lip, as bloom rather than a hard rule
    lip = QPainterPath(edge[0])
    for point in edge[1:]:
        lip.lineTo(point)
    line = QLinearGradient(0, 0, w, 0)
    p.setBrush(Qt.NoBrush)
    for width, factor in ((11.0, .10), (5.0, .22), (1.3, .62)):
        for i, tone in enumerate(tones):
            line.setColorAt(i / (len(tones) - 1), color(tone, min(255, alpha * 2.4 * factor)))
        p.setPen(QPen(QBrush(line), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(lip)


def _build_aurora(w, h):
    """The soft, luminous layers. Rendered at reduced size and scaled up."""
    pal = PALETTE
    layer = QPixmap(w, h)
    layer.fill(Qt.transparent)
    p = QPainter(layer)
    p.setRenderHint(QPainter.Antialiasing)
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for base_y, amp, wave, phase, drop, tones, alpha in (
            (.17, .050, .66, .4, .52, ('#4dffc4', '#2ee6d0', '#7ad9ff', '#c58bff'), 76),
            (.10, .040, .50, 2.2, .46, ('#7ad9ff', '#4dffc4', '#4dffc4', '#7aa8ff'), 58),
            (.26, .060, .84, 4.0, .48, ('#c58bff', '#7aa8ff', '#4dffc4', '#2ee6d0'), 42),
            (.35, .045, .58, 5.3, .36, ('#ff8e6b', '#c58bff', '#7ad9ff', '#4dffc4'), 30)):
        _ribbon(p, w, h, h * base_y, h * amp, w * wave, phase, h * drop, tones, alpha)
    p.end()
    return layer


def _build_scene(w, h):
    pal = PALETTE
    pixmap = QPixmap(w, h)
    pixmap.fill(color(pal['bg']))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0, 0, w, h)
    base = QLinearGradient(0, 0, 0, h)
    for t, tone in ((0, '#04181d'), (.45, pal['bg']), (1, pal['shadow'])):
        base.setColorAt(t, color(tone))
    p.fillRect(rect, base)

    # Deep colour fields: teal sky, violet haze, coral ember at the horizon.
    for x, y, radius, tone, alpha in ((.18, -.06, .62, '#0c8f86', 118),
                                      (.78, .02, .52, '#5b3bd0', 82),
                                      (.96, 1.02, .66, '#ff6a4d', 96),
                                      (.04, .98, .46, '#ff3f8e', 54),
                                      (.50, .50, .40, '#0a4a55', 46)):
        glow = QRadialGradient(QPointF(w * x, h * y), max(w, h) * radius)
        glow.setColorAt(0, color(tone, alpha))
        glow.setColorAt(.55, color(tone, alpha * .28))
        glow.setColorAt(1, color(tone, 0))
        p.fillRect(rect, glow)

    # Aurora curtains at half resolution: they are soft by nature.
    half = _build_aurora(max(2, w // 2), max(2, h // 2))
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawPixmap(rect, half, QRectF(half.rect()))
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    # Flow lines: fine contour curves drifting across the lower scene.
    p.setBrush(Qt.NoBrush)
    for i in range(26):
        y0 = h * (.46 + i * .021)
        points = [QPointF(w * k / 16 - 8,
                          y0 + math.sin(k * .55 + i * .21) * h * .034
                          + math.sin(k * 1.3 + i * .5) * h * .008 - i * h * .0045)
                  for k in range(17)]
        line = QLinearGradient(0, 0, w, 0)
        line.setColorAt(0, color(SPECTRUM[0], 0))
        line.setColorAt(.35, color(SPECTRUM[1], 16 if i % 4 else 34))
        line.setColorAt(.7, color(SPECTRUM[2], 14 if i % 4 else 30))
        line.setColorAt(1, color(SPECTRUM[3], 0))
        p.setPen(QPen(QBrush(line), .7))
        p.drawPath(_smooth(points))

    # Deterministic stars and a few four-point glints.
    p.setPen(Qt.NoPen)
    seed = 4217
    for i in range(130):
        seed = (seed * 1103515245 + 12345) & 0x7fffffff
        x = (seed % 10000) / 10000 * w
        seed = (seed * 1103515245 + 12345) & 0x7fffffff
        y = (seed % 10000) / 10000 * h * .62
        radius = .45 + (i % 5) * .2
        tone = SPECTRUM[i % 4] if i % 9 == 0 else pal['text']
        p.setBrush(color(tone, 40 + (i * 29) % 130))
        p.drawEllipse(QPointF(x, y), radius, radius)
        if i % 23 == 0:
            p.setPen(QPen(color(tone, 80), .6))
            p.drawLine(QPointF(x - 5, y), QPointF(x + 5, y))
            p.drawLine(QPointF(x, y - 5), QPointF(x, y + 5))
            p.setPen(Qt.NoPen)

    vignette = QRadialGradient(QPointF(w * .5, h * .42), max(w, h) * .9)
    vignette.setColorAt(0, QColor(0, 0, 0, 0))
    vignette.setColorAt(.6, QColor(0, 4, 5, 26))
    vignette.setColorAt(1, QColor(0, 3, 4, 175))
    p.fillRect(rect, vignette)
    p.end()
    return pixmap


def scene_pixmap(size):
    return _build_scene(max(1, size.width()), max(1, size.height()))


# ------------------------------------------------------------------ panels
def _flare(p, rect, big, tone, alpha, width, *, top_left=True):
    """Light caught on one of the large corners, fading into both edges."""
    length = max(10.0, min(rect.width() * .3, rect.height() * .5, 70.0))
    path = QPainterPath()
    x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    if top_left:
        a, b = QPointF(x0, y0 + big + length * .55), QPointF(x0 + big + length, y0)
        path.moveTo(a)
        path.lineTo(x0, y0 + big)
        path.arcTo(QRectF(x0, y0, 2 * big, 2 * big), 180, -90)
        path.lineTo(b)
    else:
        a, b = QPointF(x1, y1 - big - length * .55), QPointF(x1 - big - length, y1)
        path.moveTo(a)
        path.lineTo(x1, y1 - big)
        path.arcTo(QRectF(x1 - 2 * big, y1 - 2 * big, 2 * big, 2 * big), 0, -90)
        path.lineTo(b)
    gradient = QLinearGradient(a, b)
    gradient.setColorAt(0, color(tone, 0))
    gradient.setColorAt(.30, color(tone, alpha * .8))
    gradient.setColorAt(.5, color('#ffffff', min(255, alpha * 1.1)))
    gradient.setColorAt(.70, color(tone, alpha * .8))
    gradient.setColorAt(1, color(tone, 0))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QBrush(gradient), width, Qt.SolidLine, Qt.RoundCap))
    p.drawPath(path)


def paint_panel(p, widget, rect, *, strong=False, compact=False, active=False):
    from .glass import draw_frosted_backdrop
    pal = palette()
    series = pal['series']
    path = shape(rect, compact)
    p.save()
    p.setClipPath(path)
    p.fillPath(path, color(pal['card']))
    draw_frosted_backdrop(p, widget, rect, .64)
    wash = QLinearGradient(rect.topLeft(), rect.bottomRight())
    wash.setColorAt(0, color(pal['card'], 160))
    wash.setColorAt(.5, color(pal['bg'], 205))
    wash.setColorAt(1, color(pal['card'], 214))
    p.fillPath(path, wash)
    # Mint light from the sweeping upper-left corner, coral warmth opposite.
    upper = QRadialGradient(rect.topLeft(), max(40, rect.width() * .62))
    upper.setColorAt(0, color(series[0], 50 if strong or active else 30))
    upper.setColorAt(1, color(series[0], 0))
    p.fillPath(path, upper)
    lower = QRadialGradient(rect.bottomRight(), max(40, rect.width() * .55))
    lower.setColorAt(0, color(series[1], 40 if strong or active else 22))
    lower.setColorAt(1, color(series[1], 0))
    p.fillPath(path, lower)
    sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    sheen.setColorAt(0, color(pal['text'], 26))
    sheen.setColorAt(.12, color(pal['text'], 4))
    sheen.setColorAt(1, color(pal['text'], 0))
    p.fillPath(path, sheen)
    if not compact and rect.height() > 96 and rect.width() > 120:
        # A single silk ribbon crossing the tile, clear of any readable data.
        ribbon = QPainterPath(QPointF(rect.left(), rect.bottom() - rect.height() * .16))
        ribbon.cubicTo(rect.left() + rect.width() * .30, rect.bottom() - rect.height() * .42,
                       rect.left() + rect.width() * .62, rect.bottom() + rect.height() * .02,
                       rect.right(), rect.bottom() - rect.height() * .34)
        silk = QLinearGradient(rect.left(), 0, rect.right(), 0)
        silk.setColorAt(0, color(series[0], 0))
        silk.setColorAt(.4, color(series[2], 34 if strong else 22))
        silk.setColorAt(1, color(series[1], 0))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QBrush(silk), 1.1))
        p.drawPath(ribbon)
    p.restore()

    big, _small = radii(rect, compact)
    edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
    edge.setColorAt(0, color(series[0], 150 if active else 96))
    edge.setColorAt(.35, color(pal['border'], 58))
    edge.setColorAt(.65, color(pal['border'], 52))
    edge.setColorAt(1, color(series[1], 150 if active else 96))
    p.setBrush(Qt.NoBrush)
    if active:
        halo = QLinearGradient(rect.topLeft(), rect.bottomRight())
        _spectrum(halo, 34)
        p.setPen(QPen(QBrush(halo), 6))
        p.drawPath(path)
    p.setPen(QPen(QBrush(edge), 1.3 if active else .85))
    p.drawPath(path)
    p.setPen(QPen(color(pal['text'], 12), .7))
    p.drawPath(shape(rect.adjusted(2, 2, -2, -2), compact))
    if rect.width() > 40 and rect.height() > 30:
        _flare(p, rect, big, series[0], 235 if active else (190 if strong else 150),
               2.2 if active else 1.7, top_left=True)
        _flare(p, rect, big, series[1], 205 if active else 130, 1.9 if active else 1.4,
               top_left=False)


# ---------------------------------------------------------------- navigation
def paint_navigation(button):
    from .nav_icons import paint_icon
    pal = palette()
    series = pal['series']
    p = QPainter(button)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(button.rect()).adjusted(3, 3, -3, -3)
    selected = button.isChecked()
    path = shape(rect, True)
    if selected:
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0, color(series[0], 66))
        fill.setColorAt(.55, color(series[2], 42))
        fill.setColorAt(1, color(series[1], 58))
        p.fillPath(path, fill)
        glow = QRadialGradient(QPointF(rect.left(), rect.center().y()), rect.width() * .8)
        glow.setColorAt(0, color(series[0], 70))
        glow.setColorAt(1, color(series[0], 0))
        p.save()
        p.setClipPath(path)
        p.fillRect(rect, glow)
        p.restore()
        edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
        _spectrum(edge, 225)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QBrush(edge), 1.15))
        p.drawPath(path)
        # The aurora marker: a short vertical beam on the leading edge.
        beam = QLinearGradient(0, rect.top() + 6, 0, rect.bottom() - 6)
        beam.setColorAt(0, color(series[0]))
        beam.setColorAt(1, color(series[1]))
        p.setPen(Qt.NoPen)
        p.setBrush(beam)
        p.drawRoundedRect(QRectF(rect.left() + 5, rect.top() + 9, 3, rect.height() - 18), 1.5, 1.5)
    elif button._hover_amount > .01 or button.hasFocus():
        p.fillPath(path, color(series[0], 10 + 24 * button._hover_amount))
    ink = color(pal['text'] if selected or button._hover_amount > .3 else pal['muted'])
    compact = button._compact
    x = rect.center().x() - 10 if compact else rect.left() + 18
    paint_icon(p, button.icon_key, QRectF(x, rect.center().y() - 10, 20, 20),
               color(series[0]) if selected else ink)
    if not compact:
        font = QFont(button.font())
        font.setPixelSize(12)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        p.setFont(font)
        p.setPen(ink)
        caption = button.text().split('    ', 1)[-1]
        p.drawText(QRectF(rect.left() + 46, rect.top(), rect.width() - 54, rect.height()),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(caption, Qt.ElideRight, max(1, round(rect.width() - 54))))
    button.paint_notice_and_focus(p, rect, shape(rect.adjusted(1, 1, -1, -1), True))
    p.end()


# --------------------------------------------------------------- stylesheet
def _corners(big, small):
    return (f'border-top-left-radius:{big}px;border-bottom-right-radius:{big}px;'
            f'border-top-right-radius:{small}px;border-bottom-left-radius:{small}px;')


def stylesheet():
    pal = palette()
    series = pal['series']
    field = _corners(20, 5)
    return f'''
    #heroTitle {{font-size:20px;font-weight:650;color:{pal['text']};}}
    #pageTitle {{font-size:30px;font-weight:750;}}
    #cardTitle {{font-size:10px;font-weight:700;letter-spacing:2px;color:{pal['accent']};}}
    #chipValue {{font-size:11px;font-weight:650;color:{pal['text']};}}
    #chipTitle {{font-size:9px;color:{pal['muted']};}}
    QLineEdit,QComboBox,QSpinBox,QTextEdit,QListWidget,QTableWidget {{
        background:{pal['sidebar']};color:{pal['text']};border:1px solid {pal['border']};{field}}}
    QPushButton,QToolButton {{ {field} }}
    QHeaderView::section {{background:{pal['sidebar']};color:{pal['muted']};border:none;padding:8px;}}
    QTableWidget::item {{padding:6px;border-bottom:1px solid {pal['grid']};}}
    QTableWidget::item:selected {{background:{pal['track']};color:{pal['text']};}}
    QComboBox::drop-down {{{_corners(0, 0)}border-top-right-radius:5px;border-bottom-right-radius:20px;background:{pal['card']};}}
    QPushButton#ghostBtn,QPushButton#langBtn,QToolButton#layoutAction {{
        border:1px solid {pal['border']};{field}background:{pal['sidebar']};color:{pal['text']};}}
    QPushButton#ghostBtn:hover,QPushButton#langBtn:hover,QToolButton#layoutAction:hover {{
        border-color:{pal['accent']};background:{pal['track']};}}
    QPushButton#primaryBtn,QPushButton#langBtn:checked {{
        background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {series[0]},stop:.55 #7ad9ff,stop:1 {series[1]});
        {field}border:1px solid {pal['accent']};color:#03130f;}}
    QProgressBar,QProgressBar::chunk {{border-radius:9px;}}
    QScrollBar::handle:vertical {{background:{pal['border']};border-radius:3px;}}
    '''


# ----------------------------------------------------------- design preview


# -------------------------------------------------------------- instruments
def _smooth(points):
    path = QPainterPath(points[0])
    if len(points) == 1:
        return path
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6, p1.y() + (p2.y() - p0.y()) / 6)
        c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6, p2.y() - (p3.y() - p1.y()) / 6)
        path.cubicTo(c1, c2, p2)
    return path


SEGMENTS = 48
SWEEP = 270.0


def _ring(p, box, value, *, level_tone=None):
    """Segmented bloom ring: lit petals along a 270-degree sweep."""
    pal = palette()
    series = pal['series']
    cx, cy = box.center().x(), box.center().y()
    outer = box.width() / 2
    thick = max(5.0, outer * .15)
    arc = box.adjusted(thick + 5, thick + 5, -thick - 5, -thick - 5)
    radius = arc.width() / 2
    fraction = 0 if value is None else max(0, min(100, value)) / 100

    # Soft bloom inside the ring, tinted by the current reading.
    tone = level_tone and QColor(level_tone) or spectrum_at(fraction * .8)
    inner = QRadialGradient(QPointF(cx, cy), radius)
    inner.setColorAt(0, color(tone, 38 if value is not None else 10))
    inner.setColorAt(.7, color(tone, 10 if value is not None else 4))
    inner.setColorAt(1, color(tone, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(inner)
    p.drawEllipse(QPointF(cx, cy), radius, radius)
    # Hairline orbits that frame the instrument.
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(color(pal['accent'], 36), .7))
    p.drawEllipse(QPointF(cx, cy), outer - 1, outer - 1)
    p.setPen(QPen(color(pal['grid'], 170), .7, Qt.DotLine))
    p.drawEllipse(QPointF(cx, cy), radius - thick - 5, radius - thick - 5)

    step = SWEEP / SEGMENTS
    span = step * .58
    for i in range(SEGMENTS):
        start = 225 - i * step
        position = (i + .5) / SEGMENTS
        lit = value is not None and position <= fraction + .0005
        partial = value is not None and not lit and (i / SEGMENTS) < fraction
        if lit or partial:
            base_tone = QColor(level_tone) if level_tone else spectrum_at(position * .85)
            if partial:
                base_tone.setAlpha(120)
            glow = QColor(base_tone)
            glow.setAlpha(38 if lit else 20)
            p.setPen(QPen(glow, thick * 1.9, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(arc, round((start - span / 2) * 16), round(-span * 16 * .9))
            p.setPen(QPen(base_tone, thick, Qt.SolidLine, Qt.FlatCap))
        else:
            p.setPen(QPen(color(pal['track'], 230), thick * .8, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(arc, round((start - span / 2) * 16), round(-span * 16))
    if value is None or fraction <= .01:
        return
    a = math.radians(225 - SWEEP * fraction)
    tip = QPointF(cx + math.cos(a) * radius, cy - math.sin(a) * radius)
    tip_tone = QColor(level_tone) if level_tone else spectrum_at(fraction * .85)
    halo = QRadialGradient(tip, thick * 1.7)
    halo.setColorAt(0, color('#ffffff', 235))
    halo.setColorAt(.3, color(tip_tone, 130))
    halo.setColorAt(1, color(tip_tone, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(halo)
    p.drawEllipse(tip, thick * 1.7, thick * 1.7)
    p.setBrush(color('#ffffff'))
    p.drawEllipse(tip, thick * .3, thick * .3)


def paint_center(p, box, shown, unit, font, text_color, muted_color):
    """Large value with a small, baseline-aligned unit, centred in the ring."""
    side = box.width()
    size = round(side * .24)
    big = QFont(font)
    big.setPixelSize(size)
    big.setWeight(QFont.DemiBold)
    small = QFont(font)
    small.setPixelSize(max(9, round(size * .46)))
    small.setWeight(QFont.DemiBold)
    p.setFont(big)
    number_w = p.fontMetrics().horizontalAdvance(shown)
    p.setFont(small)
    unit_w = p.fontMetrics().horizontalAdvance(unit) + 2 if unit else 0
    left = box.center().x() - (number_w + unit_w) / 2
    area = QRectF(left, box.center().y() - size * .8, number_w + 4, size * 1.6)
    p.setFont(big)
    p.setPen(text_color)
    p.drawText(area, Qt.AlignLeft | Qt.AlignVCenter, shown)
    if unit:
        p.setFont(small)
        p.setPen(muted_color)
        p.drawText(QRectF(left + number_w + 2, area.top() + size * .08, unit_w + 6, area.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, unit)


def paint_sparkline(p, rect, history):
    """A silk area-line for the compact CPU/GPU history strip."""
    pal = palette()
    series = pal['series']
    if rect.width() < 12 or rect.height() < 6:
        return
    n = len(history)
    runs, run = [], []
    for i, value in enumerate(history):
        if value is None or not math.isfinite(float(value)):
            if run:
                runs.append(run)
            run = []
            continue
        run.append(QPointF(rect.right() - (n - 1 - i) * rect.width() / max(59, n - 1),
                           rect.bottom() - max(0, min(100, value)) * rect.height() / 100))
    if run:
        runs.append(run)
    line = QLinearGradient(rect.left(), 0, rect.right(), 0)
    line.setColorAt(0, color(series[2]))
    line.setColorAt(.6, color(series[0]))
    line.setColorAt(1, color('#eafff8'))
    p.setBrush(Qt.NoBrush)
    for points in runs:
        if len(points) == 1:
            p.setPen(Qt.NoPen)
            p.setBrush(color(series[0]))
            p.drawEllipse(points[0], 2, 2)
            continue
        curve = _smooth(points)
        area = QPainterPath(curve)
        area.lineTo(points[-1].x(), rect.bottom())
        area.lineTo(points[0].x(), rect.bottom())
        area.closeSubpath()
        fill = QLinearGradient(0, rect.top(), 0, rect.bottom())
        fill.setColorAt(0, color(series[0], 90))
        fill.setColorAt(1, color(series[2], 0))
        p.fillPath(area, fill)
        p.setPen(QPen(color(series[0], 40), 4.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(curve)
        p.setPen(QPen(QBrush(line), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(curve)


def palette():
    from . import theme
    return theme.palette_for(KEY)

