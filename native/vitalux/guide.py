"""Native, bilingual presentation-style Vitalux tour; no browser or external images."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QSizePolicy
)

from . import theme
from .i18n import tr
from .ui_locale import QPushButton


# Title, concise introduction, three factual tips, focus region.
# Texts are German source keys and are translated in translations_extra.py.
SLIDES = [
    (
        "Willkommen bei Vitalux",
        "Dein Linux-System auf einen Blick – diese Tour erklärt die wichtigsten Bereiche.",
        "Vitalux zeigt Hardware- und Systemdaten direkt von deinem Linux-Rechner.",
        "Die Werte werden regelmäßig aktualisiert; nicht unterstützte Sensoren bleiben leer.",
        "Beim Start bereitet Vitalux Oberfläche und erste Daten vor. Eine Animation mit Statuszeile begleitet die Initialisierung; Ultra Eco und ausgeschaltete Animationen bleiben statisch.",
        "hero",
    ),
    (
        "Die Live-Übersicht",
        "Der kompakte Systemkopf lässt auf der Startseite mehr Platz für Messwerte und Diagramme.",
        "Du siehst unter anderem Prozessor, Grafik, RAM, Systemlaufwerk und den Systemzustand.",
        "Diagramme zeigen, wie sich die Auslastung im Zeitverlauf verändert.",
        "Übersichtskacheln zeigen mittige Texte in gleicher Reihenfolge. Lange Namen werden gekürzt; beim Darüberfahren erscheint der volle Name. Im Bearbeitungsmodus bleiben Verschieben und das X sichtbar.",
        "overview",
    ),
    (
        "Die Navigation links",
        "Die Seitenleiste ist wieder fest links angeordnet und lässt sich für mehr Platz ein- und ausklappen.",
        "Jeder Reiter öffnet einen anderen Teil der Systemüberwachung.",
        "Kreislogo und Vitalux-Schriftzug passen sich dem Design an; Außenbögen, Herzschlag und Lichtreflex laufen unabhängig.",
        "Unten wechselst du jederzeit zwischen Deutsch und Englisch.",
        "navigation",
    ),
    (
        "CPU, GPU und Arbeitsspeicher",
        "Hier erfährst du, wie stark deine Hardware gerade beansprucht wird.",
        "Der Prozessor zeigt alle logischen CPUs in Reihenfolge, einschließlich abgeschalteter CPUs; die Kacheln wachsen mit.",
        "Komponenteninformationen bleiben mit und ohne Bild mittig. Prozessor, Grafik und Mainboard bieten kurze Specs und Alle Spezifikationen: ein scrollbares Datenblatt mit Herstellerlink und Offline-Cache.",
        "Gezielte Hardware- und Systemprüfungen findest du im Diagnostic Center.",
        "hardware",
    ),
    (
        "Netzwerk und Laufwerke",
        "Behalte Datenverkehr und Speichergeräte im Blick.",
        "Netzwerk → Programme & Verbindungen zeigt laufende Apps und Verbrauch. Sperren und Entsperren stehen direkt in der App-Liste; die Systemfreigabe wird bei Bedarf angefragt. Einzelne TCP-/UDP-Sockets findest du unter Erweiterte Verbindungen.",
        "Laufwerke zeigt Datenträger, Partitionen, Belegung und Datenraten.",
        "Die verfügbaren Laufwerke werden direkt angezeigt; beim Öffnen startet die SMART-Prüfung automatisch im Hintergrund. Bei Bedarf kannst du erneut prüfen.",
        "drives",
    ),
    (
        "Laufwerks-Benchmark verstehen",
        "Mit dem Benchmark misst Vitalux die Leistung ausgewählter Laufwerke.",
        "MB/s beschreibt die übertragene Datenmenge pro Sekunde.",
        "IOPS zählt Ein- und Ausgabevorgänge pro Sekunde; Latenz bezeichnet die Verzögerung.",
        "Schreibtests erzeugen vorübergehend Daten und belasten das Laufwerk. Sichere wichtige Daten vorher.",
        "benchmark",
    ),
    (
        "Sensoren und Warnungen",
        "Die Sensorseite zeigt Messwerte, die Linux tatsächlich bereitstellt.",
        "Dazu gehören je nach Gerät Temperaturen, Lüfterdrehzahlen und Spannungen.",
        "Unter Einstellungen aktivierst du Hardware-Warnungen; die schmalen Zahlenfelder stehen rechts neben der Bezeichnung.",
        "Der Prozessor bündelt Auslastung, Temperatur und Takt in einer Diagrammkachel mit eigenen Einheitenskalen. Mit Häkchen wählst du Kurven für 60 Sekunden, 5 oder 15 Minuten. Bei Grafik stehen aktuelle Leistung und Leistungsgrenze bei den Live-Werten. Fehlende Messungen bleiben unbekannt, echte Nullwerte sichtbar. Spezifikationen folgen der App-Sprache; verfügbare Übersetzungen bleiben offline erhalten.",
        "sensors",
    ),
    (
        "Darstellung und Einstellungen",
        "Sechs Designs stehen zur Auswahl: Obsidian Gold, Glass, Crystal Glass, Nebula Prism, Quantum Core und Light. Alle unterstützen eigene Akzentfarben und Hintergründe.",
        "Originalfarben und Originalhintergrund stellen die Vorgaben des aktiven Designs wieder her. Farben und Hintergründe früherer Designs bleiben als Vorlagen erhalten. Design zurücksetzen betrifft nur das aktuelle Design. Komponentenbilder anzeigen schaltet die Bilder gemeinsam um und behält den Cache.",
        "Die Suche erkennt auch unvollständige Namen wie MiniH oder MiniHU und gleitet zum passenden Bereich. Nach einer Auswahl bleibt sie fünf Sekunden sichtbar und schließt weich. Erweiterte Einstellungen öffnen sich bei passenden Treffern automatisch.",
        "Unter Erweiterte Einstellungen → Wartung setzt „Standardwerte wiederherstellen“ das gesamte aktive Profil zurück. Einstellungen, eigene Farben, Layouts, importierte Bildkopien und Cache werden gelöscht. Originalbilder und das andere Updateprofil bleiben erhalten; Vitalux startet neu und öffnet die Anleitung.",
        "settings",
    ),
    (
        "Diagnostic Center und MiniHUD",
        "Die letzten fünf App-Ereignisse stehen im Diagnosezentrum: Warnwerte, Updatefehler und automatische Renderer-Wechsel.",
        "Im Diagnostic Center kannst du System- und Fehlerberichte lokal als TXT/JSON exportieren. Externer Ping nur per Klick.",
        "Das MiniHUD lässt sich in den Einstellungen oder über die Systemleiste aktivieren. Drei Größen, Sensoren und 50–100 % Deckkraft sind wählbar.",
        "Das MiniHUD nutzt bestehende Messwerte. Wayland/KWin entscheidet, ob es über einem Vollbildspiel sichtbar bleibt.",
        "diagnostics",
    ),
    (
        "Updates und Informationen",
        "Im Updates-Reiter stehen laufender Stand, Stable/Unstable und dauerhaft sichtbare Changelogs zusammen. Die Versionsauswahl blättert durch die Historie des Kanals, ohne das Installationsziel zu ändern; nur die separate Installationsaktion wechselt den Kanal.",
        "Enthält Stable alle Unstable-Neuerungen, wechselt Vitalux nach bestätigter Prüfung automatisch zu Stable. Neue Testversionen erfordern anschließend wieder einen manuellen Wechsel zu Unstable.",
        "Nach einer geprüften Installation startet Vitalux automatisch neu. Vorübergehende Fehler bei der Neustartvorbereitung werden bis zu drei Mal automatisch versucht; danach wird ein Fehler mit Wiederholungsaktion angezeigt. Stable v0.9.6.2 besitzt noch seinen älteren manuellen Updater.",
        "Die Prozentzahl steht mittig im Update-Ladebalken. Downloads lassen sich abbrechen und bei Fehlern erneut versuchen. Changelogs folgen deiner Sprache und bleiben offline lesbar. Lange Texte haben eine eigene Scrollleiste; passt der Text, bleibt sie unsichtbar. Beim Versionswechsel beginnt der Text oben.",
        "updates",
    ),
]


class GuideIllustration(QWidget):
    """Draw a scalable *schematic* dashboard with callout arrows, not fake live data."""

    NAV = [
        "Übersicht", "Prozessor", "Grafik", "Arbeitsspeicher", "Laufwerke",
        "Netzwerk", "Sensoren", "Diagnostic Center", "System", "Einstellungen", "Updates", "Info",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step = 0
        self.setMinimumHeight(270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        return QSize(900, 390)

    def set_step(self, step):
        self.step = max(0, min(step, len(SLIDES) - 1))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        view = QRectF(4, 4, self.width()-8, self.height()-8)
        scale = min(view.width()/940.0, view.height()/380.0)
        p.translate(view.left()+(view.width()-940*scale)/2,
                    view.top()+(view.height()-380*scale)/2)
        p.scale(scale, scale)

        accent = QColor(theme.accent())
        muted = QColor(theme.MUTED)
        text = QColor(theme.TEXT)
        backdrop = QColor(theme.BG)
        sidebar = QColor(theme.SIDEBAR)
        panel = QColor(theme.CARD)
        border = QColor(theme.BORDER)

        p.setPen(QPen(border, 1.2))
        p.setBrush(backdrop)
        p.drawRoundedRect(QRectF(4, 3, 932, 370), 18, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(sidebar)
        p.drawRoundedRect(QRectF(14, 13, 185, 350), 12, 12)

        font = QFont()
        font.setPixelSize(21)
        font.setWeight(QFont.Bold)
        p.setFont(font)
        p.setPen(accent)
        p.drawText(QRectF(29, 27, 150, 35), Qt.AlignLeft | Qt.AlignVCenter, "VITALUX")

        nav_rects = {}
        font.setWeight(QFont.Normal)
        font.setPixelSize(12)
        p.setFont(font)
        for idx, title in enumerate(self.NAV):
            y = 69 + idx * 23
            r = QRectF(24, y, 164, 23)
            nav_rects[title] = r
            p.setPen(Qt.NoPen)
            if idx == 0:
                selected = QColor(accent)
                selected.setAlpha(32)
                p.setBrush(selected)
                p.drawRoundedRect(r, 6, 6)
            p.setPen(text if idx == 0 else muted)
            p.drawText(r.adjusted(11, 0, -2, 0),
                       Qt.AlignLeft | Qt.AlignVCenter, tr(title))

        header = QRectF(213, 18, 702, 67)
        self._panel(p, header, panel, border, 13)
        p.setPen(text)
        font.setPixelSize(17)
        font.setWeight(QFont.Bold)
        p.setFont(font)
        p.drawText(QRectF(232, 23, 650, 32), Qt.AlignLeft | Qt.AlignVCenter,
                   tr("Live-Übersicht"))
        font.setPixelSize(12)
        font.setWeight(QFont.Normal)
        p.setFont(font)
        p.setPen(muted)
        p.drawText(QRectF(232, 51, 655, 25), Qt.AlignLeft | Qt.AlignVCenter,
                   tr("Beispielansicht – keine echten Messwerte"))

        tiles = [
            ("CPU", "Prozessor", QRectF(216, 100, 215, 97)),
            ("GPU", "Grafik", QRectF(444, 100, 215, 97)),
            ("RAM", "Arbeitsspeicher", QRectF(673, 100, 236, 97)),
            ("NET", "Netzwerk", QRectF(216, 210, 215, 105)),
            ("SSD", "Laufwerke", QRectF(444, 210, 215, 105)),
            ("HWMON", "Sensoren", QRectF(673, 210, 236, 105)),
        ]
        tile_rects = {}
        for icon, title, rect in tiles:
            tile_rects[icon] = rect
            self._panel(p, rect, panel, border, 11)
            font.setPixelSize(13)
            font.setWeight(QFont.Bold)
            p.setFont(font)
            p.setPen(accent)
            p.drawText(rect.adjusted(14, 10, -9, -47), Qt.AlignVCenter, icon)
            font.setWeight(QFont.Normal)
            font.setPixelSize(12)
            p.setFont(font)
            p.setPen(text)
            p.drawText(rect.adjusted(14, 42, -5, -25), Qt.AlignVCenter, tr(title))
            p.setPen(QPen(accent, 2.0))
            y = rect.bottom() - 14
            p.drawLine(QPointF(rect.left()+16, y),
                       QPointF(rect.left()+rect.width()*.68, y))

        # Each section points to the *actual* corresponding area of the drawing.
        focus = SLIDES[self.step][-1]
        targets = {
            "hero": header,
            "overview": QRectF(211, 95, 704, 225),
            "navigation": QRectF(19, 64, 175, 279),
            "hardware": QRectF(211, 95, 702, 107),
            "drives": QRectF(211, 205, 453, 116),
            "benchmark": tile_rects["SSD"],
            "sensors": nav_rects["Sensoren"],
            "diagnostics": nav_rects["Diagnostic Center"],
            "settings": nav_rects["Einstellungen"],
            "updates": nav_rects["Updates"],
        }
        box = targets[focus].adjusted(-3, -3, 3, 3)
        bright = QColor(accent)
        bright.setAlpha(30)
        p.setPen(QPen(accent, 3))
        p.setBrush(bright)
        p.drawRoundedRect(box, 12, 12)

        # Curved annotation arrow ends exactly on the highlighted target.
        target = QPointF(box.right() - min(40, box.width()*.28), box.center().y())
        start = QPointF(883, 340)
        if target.y() > 290:
            start = QPointF(860, 31)
        mid = QPointF((start.x()+target.x())*.5, target.y()-38)
        curve = QPainterPath(start)
        curve.quadTo(mid, target)
        p.setPen(QPen(accent, 3.1, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(curve)
        angle = math.atan2(target.y()-mid.y(), target.x()-mid.x())
        length = 12
        tip = QPolygonF([
            target,
            QPointF(target.x()-length*math.cos(angle-.55), target.y()-length*math.sin(angle-.55)),
            QPointF(target.x()-length*math.cos(angle+.55), target.y()-length*math.sin(angle+.55)),
        ])
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        p.drawPolygon(tip)
        p.end()

    @staticmethod
    def _panel(p, rect, fill, outline, radius):
        p.setPen(QPen(outline, 0.9))
        p.setBrush(fill)
        p.drawRoundedRect(rect, radius, radius)


class GuideDialog(QDialog):
    """Qt modal slideshow: arrow key support, page counter and native controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("vitaluxGuide")
        self.setWindowTitle(tr("Vitalux-Anleitung"))
        self.setModal(True)
        self.setMinimumSize(790, 650)
        self.resize(950, 770)
        self._step = 0
        self._render_ui()

    def _render_ui(self):
        accent = theme.accent()
        self.setStyleSheet(
            f'QDialog#vitaluxGuide {{background: {theme.BG}; color: {theme.TEXT};}}'
            f'QFrame#guideDetails {{background: {theme.CARD}; '
            f'border: 1px solid {theme.BORDER}; border-radius: 14px;}}'
            f'QLabel#guideTitle {{font-size: 23px; font-weight: 800; color: {theme.TEXT};}}'
            f'QLabel#guideSummary {{font-size: 14px; color: {theme.MUTED};}}'
            f'QLabel#guideBullet {{font-size: 13px; color: {theme.TEXT};}}'
            f'QLabel#guideCounter {{color: {accent}; font-weight: 700;}}'
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(25, 19, 25, 22)
        outer.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel(tr("Vitalux entdecken"))
        title.setObjectName("guideTitle")
        top.addWidget(title)
        top.addStretch()
        self.counter = QLabel()
        self.counter.setObjectName("guideCounter")
        top.addWidget(self.counter)
        outer.addLayout(top)

        self.illustration = GuideIllustration(self)
        outer.addWidget(self.illustration, 5)

        details = QFrame(self)
        details.setObjectName("guideDetails")
        v = QVBoxLayout(details)
        v.setContentsMargins(21, 18, 21, 17)
        v.setSpacing(8)
        self.heading = QLabel()
        self.heading.setStyleSheet(f"font-weight: 800; font-size: 17px; color: {accent};")
        v.addWidget(self.heading)
        self.summary = QLabel()
        self.summary.setObjectName("guideSummary")
        self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        self.bullets = []
        for _ in range(3):
            bullet = QLabel()
            bullet.setObjectName("guideBullet")
            bullet.setWordWrap(True)
            v.addWidget(bullet)
            self.bullets.append(bullet)
        outer.addWidget(details, 3)

        bottom = QHBoxLayout()
        self.back_btn = QPushButton(tr("Zurück"))
        self.next_btn = QPushButton(tr("Weiter"))
        self.close_btn = QPushButton(tr("Anleitung schließen"))
        self.back_btn.setObjectName("ghostBtn")
        self.close_btn.setObjectName("ghostBtn")
        self.next_btn.setObjectName("primaryBtn")
        for btn in (self.close_btn, self.back_btn, self.next_btn):
            btn.setCursor(Qt.PointingHandCursor)
        bottom.addWidget(self.close_btn)
        bottom.addStretch()
        bottom.addWidget(self.back_btn)
        bottom.addWidget(self.next_btn)
        outer.addLayout(bottom)
        self.back_btn.clicked.connect(lambda: self.show_step(self._step - 1))
        self.next_btn.clicked.connect(self._advance)
        self.close_btn.clicked.connect(self.accept)
        self.show_step(0)

    def show_step(self, step):
        self._step = max(0, min(int(step), len(SLIDES)-1))
        title, intro, *rest = SLIDES[self._step]
        for bullet, source in zip(self.bullets, rest[:3]):
            bullet.setText("➜  " + tr(source))
        self.heading.setText(tr(title))
        self.summary.setText(tr(intro))
        self.counter.setText(tr("Schritt {current} von {total}").format(
            current=self._step+1, total=len(SLIDES)))
        self.illustration.set_step(self._step)
        self.back_btn.setEnabled(self._step > 0)
        self.next_btn.setText(tr("Fertig") if self._step == len(SLIDES)-1 else tr("Weiter"))

    def _advance(self):
        if self._step == len(SLIDES) - 1:
            self.accept()
        else:
            self.show_step(self._step+1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self._advance()
            return
        if event.key() == Qt.Key_Left:
            self.show_step(self._step-1)
            return
        super().keyPressEvent(event)


def offer_first_start_guide(parent):
    """Automatically show the guide once on the first successful launch."""
    from . import settings
    if getattr(parent,'_shutdown_pending',False) or getattr(parent,'restart_requested',False):
        return
    if settings.get("guide_intro_choice") in ("completed", "never"):
        return
    dialog = GuideDialog(parent)
    dialog.exec()
    # Persist only after the required first-run guide was actually opened.
    settings.set("guide_intro_choice", "completed")
