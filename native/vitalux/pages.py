from collections import deque
import platform

import PySide6
from PySide6.QtCore import Qt, QEvent, QPoint, QTimer, qVersion, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QThread, Signal
from PySide6.QtWidgets import QBoxLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget, QMenu, QToolButton, QGraphicsOpacityEffect, QStackedWidget, QTabWidget, QLayout

from . import theme, motion
from .ui_locale import QPushButton
from .dashboard import DashboardBoard, TITLES
from .benchmark_ui import BenchmarkPanel
from .i18n import tr
from .measurement_status import unavailable
from .sensors import drives, fmt_bytes, fmt_duration, fmt_rate, system_static
from .monitor_extra import graphics_runtime, system_gpu_device
from . import smart_monitor
from .smart_ui import SmartPane
from PySide6.QtWidgets import QLabel, QSizePolicy
from .widgets import (Card, ChipsGrid, GaugeBox, GaugeCard, ChartPanel, KeyValue,
                      Meter, label, SidebarToggle)
from .sensor_ui import SensorPanel, optional, power_text, reflow
from .hardware_sensors import number
from .power_display import component_power, disk_power, gpu_power, power_limit, source_text
from .product_ui import ProductHeader


class Page(QWidget):
    def refresh(self, d, h):
        pass

    def __init__(self, title, sub=""):
        super().__init__()
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(30, 24, 30, 30)
        self.root.setSpacing(16)
        # Die linke Navigation zeigt bereits klar den aktuellen Bereich an.
        # Zusätzliche Seitenüberschriften oben würden nur Fläche verbrauchen
        # und die Oberfläche unnötig wiederholen.
        self.content = QVBoxLayout()
        self.content.setSpacing(16)
        self.root.addLayout(self.content)
        self.root.addStretch(1)


def _row(*widgets):
    lay = QHBoxLayout()
    lay.setSpacing(16)
    for w in widgets:
        lay.addWidget(w, 1)
    return lay


def _temp_freq(c):
    parts = []
    if c["temp"] is not None:
        parts.append(f"{c['temp']:.0f} °C")
    if c["freq"]:
        parts.append(f"{c['freq'] / 1000:.2f} GHz")
    return " · ".join(parts) or f"{c['cores']} {tr('Kerne')} / {c['threads']} {tr('Threads')}"


def _vram_text(g):
    if g["vram_total"]:
        return f"{fmt_bytes(g['vram_used'])} / {fmt_bytes(g['vram_total'])}"
    return None


def _system_state(sample):
    """Resource-pressure score using *observed* signals only, not a benchmark rank.

    100 represents no identified pressure amongst the available measurements,
    rather than a warranty of hardware health. SMART is evaluated only after a
    real disk scan, and benchmark throughput is never assigned a fabricated
    expected speed (HDD/SSD, cache, controller and workload differ).
    """
    from .monitoring import valid_number

    sample = sample or {}
    cpu = sample.get("cpu") or {}
    ram = sample.get("ram") or {}
    gpu = next(iter(sample.get("gpus") or ()), {}) or {}
    disks = sample.get("disks") or []
    smart = sample.get("smart_reports") or []
    score = 100.0
    issues = []
    observed = 0

    def severity(value, low, high, limit, description):
        nonlocal score, observed
        if not valid_number(value):
            return
        observed += 1
        if value <= low:
            return
        impact = limit * min(1.0, max(0.0, (value - low) / max(1, high-low)))
        score -= impact
        if impact >= 1:
            issues.append((impact, description))

    severity(cpu.get('temp'), 72, 94, 24,
             f"CPU {cpu['temp']:.0f} °C" if valid_number(cpu.get('temp')) else "")
    severity(cpu.get('usage'), 84, 100, 8,
             f"CPU-Auslastung {cpu['usage']:.0f} %" if valid_number(cpu.get('usage')) else "")
    severity(gpu.get('temp'), 72, 92, 22,
             f"GPU {gpu['temp']:.0f} °C" if valid_number(gpu.get('temp')) else "")
    severity(gpu.get('hotspot'), 88, 108, 13,
             f"GPU-Hotspot {gpu['hotspot']:.0f} °C" if valid_number(gpu.get('hotspot')) else "")
    # Sustained GPU load in a game is normal; penalize primarily thermal / memory pressure.
    severity(gpu.get('usage'), 96, 100, 3,
             f"GPU-Auslastung {gpu['usage']:.0f} %" if valid_number(gpu.get('usage')) else "")
    severity(ram.get('percent'), 76, 97, 22,
             f"RAM {ram['percent']:.0f} %" if valid_number(ram.get('percent')) else "")
    severity(ram.get('swap_percent'), 45, 95, 9,
             f"Swap {ram['swap_percent']:.0f} %" if valid_number(ram.get('swap_percent')) else "")
    if valid_number(gpu.get('vram_used')) and valid_number(gpu.get('vram_total')) and gpu['vram_total'] > 0:
        vram = 100 * gpu['vram_used'] / gpu['vram_total']
        severity(vram, 83, 98, 12, f"VRAM {vram:.0f} %")

    # Include every mounted disk, not only /. Bound the combined contribution:
    # ten similarly full mountpoints should not create tenfold punishment.
    disk_penalties = []
    for disk in disks:
        pct = disk.get('percent')
        if not valid_number(pct):
            continue
        observed += 1
        penalty = 16 * min(1., max(0., (pct - 80) / 18))
        if penalty >= 1:
            disk_penalties.append((penalty, f"Laufwerk {disk.get('mount') or disk.get('device') or '?'}: {pct:.0f} % belegt"))
    if disk_penalties:
        disk_penalties.sort(reverse=True)
        score -= min(22, disk_penalties[0][0] + sum(p[0] for p in disk_penalties[1:]) * .25)
        issues.extend(disk_penalties[:2])

    seen_drives = set()
    for drive in smart:
        name = drive.get('name')
        if not name or name in seen_drives or drive.get('_pending'):
            continue
        seen_drives.add(name)
        health = drive.get('health', 'Unbekannt')
        remaining = drive.get('health_percent')
        if health == 'Warnung':
            observed += 1
            score -= 32
            issues.append((32, f"SMART-Warnung {name}"))
        elif health == 'Gut':
            observed += 1
        if valid_number(remaining):
            observed += 1
            penalty = 20 * min(1., max(0., (30 - remaining) / 25))
            if penalty >= 1:
                score -= penalty
                issues.append((penalty, f"SMART {name}: {remaining:.0f} % Restlebensdauer"))
        # Failed SMART attributes are actual evidence even if the generic status says OK.
        attributes = drive.get('attributes') or []
        if any(isinstance(attr, dict) and attr.get('failed') for attr in attributes):
            score -= 23
            issues.append((23, f"SMART-Attributfehler {name}"))
            observed += 1

    if not observed:
        return None, tr('Beobachten'), tr('Noch nicht genügend Sensordaten')
    score = max(0, min(100, round(score)))
    issue = max(issues, key=lambda row: row[0])[1] if issues else ""
    # A missing SMART scan does not mean that disks were checked and are good.
    if not smart and score > 89:
        score = 89
    if not smart and not issue:
        issue = tr('SMART noch nicht geprüft')
    if score >= 90:
        return score, tr('Sehr gut'), issue or tr('Alles im grünen Bereich')
    if score >= 76:
        return score, tr('Stabil'), issue or tr('Leichte Last, aber unkritisch')
    if score >= 58:
        return score, tr('Beobachten'), issue or tr('Einzelne Werte im Blick behalten')
    return score, tr('Auffällig'), issue or tr('Mehrere Werte prüfen')


# ------------------------------------------------------------------ Übersicht
class OverviewPage(Page):
    def __init__(self, distro, logo):
        super().__init__("Übersicht", "Live-Status deines Systems")
        self.static = system_static()
        self.distro_version = distro.get("version") or "–"

        # Auf der Übersicht steht nur die erkannte Distribution. Der App-Name
        # bleibt in der Seitenleiste; Systemversionen stehen ausschließlich in
        # den Kacheln direkt unter dem Distro-Kopf.
        head = Card(hero=True)
        # A compact system header leaves more room for the telemetry below.
        # Keep all eight system-info chips and the original title typography.
        head.layout().setContentsMargins(20, 14, 20, 14)
        head.body.setSpacing(10)
        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 4, 2)
        row.setSpacing(20)
        # The distribution logo is an independent visibility option *inside*
        # the hero tile: its name and system-information chips stay intact.
        self.distro_logo_host = QWidget(head)
        self.distro_logo_host.setFixedSize(76, 76)
        pic = label()
        pic.setParent(self.distro_logo_host)
        self.distro_pic=pic
        pic.setGeometry(0, 0, 76, 76)
        pic.setAlignment(Qt.AlignCenter)
        pic.setPixmap(logo.scaled(round(76*max(1.,logo.devicePixelRatioF())), round(76*max(1.,logo.devicePixelRatioF())), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.distro_logo_remove = QToolButton(self.distro_logo_host)
        self.distro_logo_remove.setObjectName('tileRemoveHint')
        self.distro_logo_remove.setProperty('distroLogoRemove', True)
        self.distro_logo_remove.setText('×')
        self.distro_logo_remove.setToolTip(tr('Distributionslogo ausblenden'))
        self.distro_logo_remove.setCursor(Qt.PointingHandCursor)
        self.distro_logo_remove.setFixedSize(25, 25)
        self.distro_logo_remove.move(50, 1)
        self.distro_logo_remove.raise_()
        row.addWidget(self.distro_logo_host, 0, Qt.AlignVCenter)
        from .overview_text import ElidedLabel
        distro_name = ElidedLabel(distro["name"]);distro_name.setObjectName("heroTitle")
        self.distro_name=distro_name
        distro_name.setAlignment(Qt.AlignCenter)
        row.addWidget(distro_name, 1, Qt.AlignVCenter)
        self.distro_balance=QWidget();self.distro_balance.setFixedWidth(76)
        row.addWidget(self.distro_balance)
        # Equal side widths keep the name centered on the whole card.
        head.body.addLayout(row)

        # Restored 0.9.3.30 chip sizing: natural text/layout height and
        # standard Qt grid column sizing, without any fixed 80px tiles.
        # Uptime stays in the last small tile; the OS updater is gone.
        self.chips = ChipsGrid(["Kernel", "KDE", "Mesa", "Distributionsversion", "Sitzung", "Architektur", "Treiber", "Laufzeit"], columns=4)
        for chip in self.chips.chips.values():
            old=chip.value;chip.value=ElidedLabel(old.text());chip.value.setObjectName('chipValue')
            chip.layout().replaceWidget(old,chip.value);old.hide();old.deleteLater()
            chip.layout().setContentsMargins(14, 10, 14, 10)
            chip.setMinimumHeight(58)
        self.chips.grid.setVerticalSpacing(10)
        head.body.addWidget(self.chips)
        self.hero_card = head
        # Restore the ORIGINAL centered telemetry cards (v0.9.3.29).
        # Wrap the full GPU model; keep all four load instruments the same size.
        self.g_cpu, self.g_gpu = GaugeCard("Prozessor"), GaugeCard("Grafik", compact_caption=True)
        self.g_ram, self.g_disk = GaugeCard("Arbeitsspeicher"), GaugeCard("System-Laufwerk")
        for card in (self.g_cpu,self.g_gpu,self.g_ram,self.g_disk):
            card.box.gauge.setFixedHeight(180)
            card.box.layout().setAlignment(Qt.AlignTop)
            card.body.setAlignment(Qt.AlignTop)
        self.g_health = GaugeCard("Systemzustand", gauge_semantic='score')
        self.g_health.box.gauge.setFixedHeight(180)
        c1, c2 = Card("Auslastung"), Card("Netzwerk-Verlauf")
        self.graph_load = ChartPanel(['CPU', 'GPU', 'RAM'], [theme.accent(), theme.secondary_accent(), theme.TEAL])
        self.graph_net = ChartPanel(['Download', 'Upload'], [theme.accent(), theme.secondary_accent()], mode='rate')
        c1.body.addWidget(self.graph_load)
        c2.body.addWidget(self.graph_net)

        net = Card("Netzwerk")
        from .overview_text import OverviewValue
        self.net_name = OverviewValue("Aktive Schnittstelle")
        self.net_down, self.net_up = OverviewValue("Download"), OverviewValue("Upload")
        self.net_total = OverviewValue("Daten gesamt")
        net.body.addWidget(self.net_name)
        net.body.addWidget(self.net_down)
        net.body.addWidget(self.net_up)
        net.body.addWidget(self.net_total)
        self.disks_card = Card("Laufwerke")
        self.disk_meters = {}

        # The editor is an OVERLAY aligned with the left sidebar arrow (y=13).
        # It takes no layout row, so the original dashboard moves back up.
        # The overlay arrow ends at y=43; place the first glass card just
        # below it, without wasting space on an extra header/toolbar row.
        self.root.setContentsMargins(30,45,30,30)
        self.layout_toggle = SidebarToggle(self, orientation='horizontal')
        self.layout_toggle.setToolTip(tr('Dashboard-Layout'))
        self.layout_toggle.setAccessibleName(tr('Dashboard-Layout'))

        self.layout_actions = QWidget(self)
        self.layout_actions.setObjectName('layoutActions')
        self.layout_actions.setAttribute(Qt.WA_TranslucentBackground, True)
        strip = QHBoxLayout(self.layout_actions)
        strip.setContentsMargins(0,0,0,0)
        strip.setSpacing(5)
        self._editor_buttons = []
        for key, icon, text, handler, width in (
            ('add', '+', 'Kacheln hinzufügen', self._show_hidden_tiles, 136),
            ('undo', '↶', 'Rückgängig', self._undo_layout, 109),
            ('reset', '↺', 'Standardlayout', self.reset_editor, 123),
            ('discard', '×', 'Verwerfen', self.discard_edit, 108),
            ('save', '✓', 'Speichern', self.save_editor, 105),
        ):
            action = QToolButton(self.layout_actions)
            action.setObjectName('layoutAction')
            action.setFixedSize(width,30)
            action.setCursor(Qt.PointingHandCursor)
            action.setFocusPolicy(Qt.StrongFocus)
            action.setProperty('layoutName',key)
            action.setText(f'{icon}  {tr(text)}')
            action.clicked.connect(handler)
            strip.addWidget(action)
            self._editor_buttons.append((key,icon,text,action))
        self._strip_width = sum(item[3].width() for item in self._editor_buttons) + strip.spacing()*4
        self.layout_actions.setFixedSize(self._strip_width,30)
        self._strip_open = False
        self._strip_anim = None
        self._strip_fraction = 0.0
        self._strip_effect = QGraphicsOpacityEffect(self.layout_actions)
        self._strip_effect.setOpacity(0.0)
        self.layout_actions.setGraphicsEffect(self._strip_effect)
        self.layout_actions.hide()
        self.board = DashboardBoard(self)
        from .signature_designs import Metric
        self.design_metrics={}
        self.design_metric_hosts={}
        from .overview_text import OverviewInfo
        self.power_labels={}
        self.overview_info={}
        def metric_host(key,classic):
            host=QStackedWidget()
            host.addWidget(classic)
            classic.box.sub.hide()
            classic.box.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
            face=Card(TITLES[key])
            face.layout().setContentsMargins(20,16,20,18)
            instrument=Metric(TITLES[key],key)
            face.body.addWidget(instrument)
            self.overview_info[key]=[]
            for card in (classic,face):
                card.layout().setAlignment(Qt.AlignTop)
                card.body.setAlignment(Qt.AlignTop)
                for heading in card.findChildren(QLabel):
                    if heading.objectName()=='cardTitle':heading.setAlignment(Qt.AlignCenter)
                info=OverviewInfo();card.body.addWidget(info)
                self.overview_info[key].append(info)
                if key in ('cpu','ram','disk'):self.power_labels.setdefault(key,[]).append(info.power)
            host.addWidget(face)
            self.design_metrics[key]=instrument
            self.design_metric_hosts[key]=host
            return host
        for key, widget in (
            ('hero',head), ('cpu',metric_host('cpu',self.g_cpu)), ('gpu',metric_host('gpu',self.g_gpu)),
            ('ram',metric_host('ram',self.g_ram)), ('disk',metric_host('disk',self.g_disk)),
            ('graph_load',c1), ('graph_net',c2),
            ('health',metric_host('health',self.g_health)), ('network',net), ('drives',self.disks_card),
        ):
            self.board.register(key,widget)
        for card in (head,c1,c2,net,self.disks_card):
            card.layout().setAlignment(Qt.AlignTop)
            for text in card.findChildren(QLabel):
                if text.objectName() in ('cardTitle','chipTitle','chipValue'):text.setAlignment(Qt.AlignCenter)
        self.content.addWidget(self.board)
        self.layout_toggle.clicked.connect(self.toggle_editor)
        self.board.changed.connect(self._refresh_editor_actions)
        self.board.changed.connect(self._sync_distro_logo)
        self.distro_logo_remove.clicked.connect(self.board.hide_distro_logo)
        self._sync_distro_logo()
        self._position_editor_controls()
        self.refresh_design()
        QTimer.singleShot(0,self.board.refresh_geometry)

    def refresh_design(self):
        from .signature_designs import active
        selected=active()
        for host in self.design_metric_hosts.values():
            host.setCurrentIndex(1 if selected else 0)
        self.root.setContentsMargins(16 if selected else 30,45,16 if selected else 30,24 if selected else 30)
        self.root.setStretch(0,0)
        self.root.setStretch(1,1)
        self.board.show()
        self.layout_toggle.show()
        self._sync_distro_logo()
        self.distro_logo_host.setFixedSize(76,76)
        for chip in self.chips.chips.values():
            chip.layout().setContentsMargins(14,10,14,10)
        self.chips.grid.setVerticalSpacing(10)
        self.board.refresh_geometry(animate=False)
        for panel in (self.graph_load,self.graph_net):
            panel.graph.setMinimumHeight(110 if selected else 185)
            panel.graph.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self,'layout_actions'):
            self._position_editor_controls()

    def _position_editor_controls(self):
        # Dashboard toolbar remains on the outer right edge of content.
        x = self.width()-self.layout_toggle.width()-5
        self.layout_toggle.move(x,13)
        # Shift just the small action strip, not its children or an animated
        # clipping mask. Widgets retain their full width throughout movement.
        target_x = x-self._strip_width-7
        if self._strip_anim is None:
            self.layout_actions.move(target_x+round(22*(1-self._strip_fraction)),13)
        self.layout_toggle.raise_()
        if self._strip_open:
            self.layout_actions.raise_()
            self.layout_toggle.raise_()

    def _reveal_strip(self, opening):
        """Slide one lightweight action row; never clip/repaint its text.

        The old QRegion mask was rebuilt on every frame and visibly sheared
        button labels, especially at fractional scaling on KDE/Wayland.
        Here button geometries never change. We animate only the containing
        QWidget's position and opacity with one synchronized animation group.
        """
        previous = self._strip_anim
        if previous is not None:
            previous.stop()
            previous.deleteLater()
            self._strip_anim = None
        start = self._strip_fraction
        finish = 1.0 if opening else 0.0
        if opening:
            self.layout_actions.show()
            self.layout_actions.raise_()
            self.layout_toggle.raise_()
        if not motion.enabled() or abs(finish-start) < .001:
            self._strip_fraction = finish
            self._strip_effect.setOpacity(finish)
            self._position_editor_controls()
            if not opening:
                self.layout_actions.hide()
            return
        # Keep the strip in one row with stable letter spacing. A property
        # animation on the opacity effect avoids a per-frame pixel mask.
        fade = QPropertyAnimation(self._strip_effect, b'opacity', self)
        fade.setStartValue(self._strip_effect.opacity())
        fade.setEndValue(finish)
        travel = QPropertyAnimation(self.layout_actions, b'pos', self)
        travel.setStartValue(self.layout_actions.pos())
        x=self.width()-self.layout_toggle.width()-5
        target=x-self._strip_width-7
        travel.setEndValue(QPoint(target+round(22*(1-finish)),13))
        group=QParallelAnimationGroup(self)
        for animation in (fade,travel):
            animation.setDuration(motion.duration(round(235*abs(finish-start))))
            animation.setEasingCurve(QEasingCurve.InOutCubic)
            group.addAnimation(animation)
        self._strip_anim=group
        fade.valueChanged.connect(lambda opacity: setattr(self, '_strip_fraction', float(opacity)))
        def completed():
            if self._strip_anim is not group:return
            self._strip_anim=None
            self._strip_fraction=finish
            if not opening:
                self.layout_actions.hide()
            self._position_editor_controls()
            group.deleteLater()
        group.finished.connect(completed)
        group.start()

    def _sync_distro_logo(self):
        visible = self.board.distro_logo_visible
        self.distro_logo_host.setVisible(visible)
        self.distro_balance.setVisible(visible)
        self.distro_logo_remove.setVisible(visible and self.board.editing)

    def _refresh_editor_actions(self):
        for key, _icon, _txt, action in self._editor_buttons:
            if key=='undo':action.setEnabled(bool(self.board.history))
            if key=='add':action.setEnabled(bool(self.board.available_hidden()))

    def _show_hidden_tiles(self):
        menu = QMenu(self)
        hidden=self.board.available_hidden()
        for key,title in hidden:
            item=menu.addAction(title)
            item.triggered.connect(lambda _=False,k=key:self.board.show_tile(k))
        if not hidden:
            item=menu.addAction(tr('Alle Kacheln sind bereits sichtbar'))
            item.setEnabled(False)
        add = next(a for k,_,_,a in self._editor_buttons if k=='add')
        menu.exec(add.mapToGlobal(QPoint(0,add.height())))
        self._refresh_editor_actions()

    def _undo_layout(self):
        self.board.undo()
        self._refresh_editor_actions()

    def toggle_editor(self):
        # A second arrow click commits the edited arrangement, closes the
        # actions AND exits edit mode (same semantics as the Save control).
        if self.board.editing:
            self.save_editor()
            return
        self.board.begin_edit()
        self._sync_distro_logo()
        self._refresh_editor_actions()
        self._strip_open = True
        self.layout_toggle.set_collapsed(True)
        self.layout_toggle.setToolTip(tr('Dashboard-Layout'))
        self._reveal_strip(True)

    def _finish_editor(self, save):
        if not self.board.editing:return
        self.board.finish_edit(save=save)
        self._sync_distro_logo()
        self._strip_open=False
        self.layout_toggle.set_collapsed(False)
        self.layout_toggle.reset_highlight()
        self.layout_toggle.setToolTip(tr('Dashboard-Layout'))
        self._reveal_strip(False)

    def save_editor(self):
        self._finish_editor(True)

    def discard_edit(self):
        self._finish_editor(False)

    def reset_editor(self):
        if not self.board.editing:return
        self.board.reset()
        self._finish_editor(True)

    def retranslate(self):
        self.layout_toggle.setToolTip(tr('Dashboard-Layout'))
        self.layout_toggle.setAccessibleName(tr('Dashboard-Layout'))
        for _,icon,source,action in self._editor_buttons:
            action.setText(f'{icon}  {tr(source)}')
        for tile in self.board.tiles.values():
            tile.drag.setText(tr('Zum Verschieben halten'))
            tile.drag.setToolTip(tr('Kachel verschieben'))
            tile.remove.setToolTip(tr('Kachel ausblenden'))
        self.distro_logo_remove.setToolTip(tr('Distributionslogo ausblenden'))

    def apply_layout(self):
        if not self.board.editing:
            self.board.refresh_geometry()

    def refresh(self, d, h):
        c, r, gpus, disks = d["cpu"], d["ram"], d["gpus"], d["disks"]
        records=d.get('hardware') or []
        root = next((x for x in disks if x['mount']=='/'),disks[0] if disks else None)
        readings={'cpu':component_power(records,'cpu'),'ram':component_power(records,'ram'),
                  'gpu':gpu_power(gpus[0]) if gpus else None,'disk':disk_power(records,root)}
        for key,widgets in self.power_labels.items():
            record=readings[key]
            text=power_text(record)
            for widget in widgets:
                widget.setText(text);widget.setVisible(bool(text))
                widget.setToolTip(source_text(record) if text else '')
        net = d["net"]
        primary = net.get("primary") or {}
        driver = next((g.get("driver") for g in gpus if g.get("driver")), "amdgpu / drm" if gpus and gpus[0]["vendor"] == "AMD" else "–")
        self.chips.set("Kernel", self.static["kernel"])
        self.chips.set("KDE", f"Plasma {self.static['plasma']}")
        self.chips.set("Mesa", self.static["mesa"])
        self.chips.set("Distributionsversion", self.distro_version)
        self.chips.set("Sitzung", self.static["session"])
        self.chips.set("Architektur", self.static["arch"])
        self.chips.set("Treiber", driver)
        self.chips.set("Laufzeit", fmt_duration(d['uptime']))

        self.g_cpu.set(c["usage"], _temp_freq(c))
        if gpus:
            g = gpus[0]
            vt = _vram_text(g)
            self.g_gpu.set(g["usage"], g["name"] + (f"\nVRAM {vt}" if vt else ""))
            self.g_gpu.box.sub.setToolTip(g["name"] + (f"\nVRAM {vt}" if vt else ""))
        else:
            self.g_gpu.set(None, "Keine GPU-Daten verfügbar")
        self.g_ram.set(r["percent"], f"{fmt_bytes(r['used'])} / {fmt_bytes(r['total'])}")
        root = next((x for x in disks if x["mount"] == "/"), disks[0] if disks else None)
        if root:
            self.g_disk.set(root["percent"], f"{fmt_bytes(root['used'])} / {fmt_bytes(root['total'])}")
        else:
            self.g_disk.set(None, 'Keine Laufwerksdaten verfügbar')

        score, state, detail = _system_state(d)
        self.g_health.set(score, f"{state}\n{detail}",
                          text=f"{score:.0f}" if score is not None else "–")
        self.design_metrics['cpu'].set(c['usage'],_temp_freq(c),extra=c.get('model',''),history=h['cpu'])
        gpu=gpus[0] if gpus else {}
        self.design_metrics['gpu'].set(gpu.get('usage'),
            f"{gpu['temp']:.0f} °C" if gpu.get('temp') is not None else tr('Keine GPU-Daten verfügbar'),
            extra=gpu.get('name',tr('Keine GPU-Daten verfügbar')),history=h['gpu'])
        self.design_metrics['ram'].set(r['percent'],f"{fmt_bytes(r['used'])} / {fmt_bytes(r['total'])}")
        self.design_metrics['disk'].set(root['percent'] if root else None,
            f"{fmt_bytes(root['used'])} / {fmt_bytes(root['total'])}" if root else tr('Keine Laufwerksdaten verfügbar'))
        self.design_metrics['health'].set(score,f'{state} · {detail}')

        captions={
            'cpu':(c.get('model',''),_temp_freq(c)),
            'gpu':(gpu.get('name',''),(' · '.join(x for x in (
                f"{gpu['temp']:.0f} °C" if gpu.get('temp') is not None else '',
                f"VRAM {_vram_text(gpu)}" if _vram_text(gpu) else '') if x)) if gpu else tr('Keine GPU-Daten verfügbar')),
            'ram':('',f"{fmt_bytes(r['used'])} / {fmt_bytes(r['total'])}"),
            'disk':('',f"{fmt_bytes(root['used'])} / {fmt_bytes(root['total'])}" if root else tr('Keine Laufwerksdaten verfügbar')),
            'health':(tr(state),detail),
        }
        for key,infos in self.overview_info.items():
            name,details=captions[key]
            for info in infos:info.set(name,details,power_text(readings.get(key)) if key in self.power_labels else '')

        self.graph_load.set_series([(h["cpu"], theme.accent()), (h["gpu"], theme.secondary_accent()), (h["ram"], theme.TEAL)])
        self.graph_net.set_series([(h["net_down"], theme.accent()), (h["net_up"], theme.secondary_accent())])
        self.net_name.set(primary.get("name", "–") + (f"  ·  {primary.get('speed', 0)} Mbit/s" if primary.get("speed") else ""))
        self.net_down.set(fmt_rate(net["down"]))
        self.net_up.set(fmt_rate(net["up"]))
        self.net_total.set(f"↓ {fmt_bytes(net['total_down'])}   ·   ↑ {fmt_bytes(net['total_up'])}")
        for x in disks[:6]:
            m = self.disk_meters.get(x["mount"])
            if m is None:
                from .overview_text import OverviewMeter
                m = self.disk_meters[x["mount"]] = OverviewMeter(x["mount"])
                self.disks_card.body.addWidget(m)
            m.set(x["percent"], f"{fmt_bytes(x['used'])} / {fmt_bytes(x['total'])}")


# ------------------------------------------------------------------ Prozessor
class CpuPage(Page):
    def __init__(self):
        super().__init__("Prozessor", "Auslastung, Takt und Temperatur")
        top = Card()
        self.name = label("–", "bigName", wrap=True)
        self.meta = label('', 'muted', wrap=True)
        self.product_header = ProductHeader(self.name, self.meta, 'cpu')
        top.body.addWidget(self.product_header)
        self.content.addWidget(top)
        graph=Card('CPU-Messwerte · Verlauf')
        self.graph=ChartPanel(['Auslastung','Temperatur','Takt'],
                             [theme.accent(),theme.secondary_accent(),theme.TEAL],mode='mixed',
                             series_modes=['percent','temperature','frequency'])
        graph.body.addWidget(self.graph)
        graph.body.addWidget(label('Jede Messgröße hat eine eigene farbige Skala.','muted',wrap=True))
        self.content.addWidget(graph)

        self.cores_card = Card("Kerne / Threads · Auslastung")
        self.cores_card.body.addWidget(label(
            'Alle logischen Prozessoren in CPU-Reihenfolge; abgeschaltete CPUs bleiben sichtbar.',
            'muted', wrap=True))
        self.cores_grid = QGridLayout()
        self.cores_grid.setHorizontalSpacing(24)
        self.cores_grid.setVerticalSpacing(12)
        self.cores_card.body.addLayout(self.cores_grid)
        self.content.addWidget(self.cores_card)
        self.core_meters = []
        self._core_columns = 0
        self.root.setSizeConstraint(QLayout.SetMinimumSize)
        self.cores_card.layout().setSizeConstraint(QLayout.SetMinimumSize)

    def showEvent(self,event):
        super().showEvent(event)
        if self.parentWidget() is not None:self.parentWidget().installEventFilter(self)
        self._arrange_cores()

    def eventFilter(self,watched,event):
        if watched is self.parentWidget() and event.type()==QEvent.Resize:
            self._arrange_cores()
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._arrange_cores()

    def _arrange_cores(self):
        # A large grid's minimum width can prevent the page from shrinking.
        # Follow its viewport too, so columns reflow before that constraint.
        parent=self.parentWidget()
        available=min(self.width(),parent.width()) if parent is not None else self.width()
        columns = max(1, min(4, (available - 100) // 200))
        if columns == self._core_columns:
            return
        for i, meter in enumerate(self.core_meters):
            self.cores_grid.addWidget(meter, i // columns, i % columns)
        self._core_columns = columns
        self.cores_card.updateGeometry()
        self.updateGeometry()

    def refresh(self, d, h):
        c = d["cpu"]
        self.name.setText(c["model"])
        self.meta.setText(c.get('manufacturer') or '')
        self.product_header.set_product(c.get('product'))
        self.product_header.set_specs([
            ('Kerne / Threads', f'{c["cores"]} / {c["threads"]}'),
            ('Maximaler Takt', f'{c["freq_max"]/1000:.2f} GHz' if c.get('freq_max') else ''),
            ('Architektur', platform.machine())])
        keys=('cpu','cpu_temp','cpu_clock')
        self.graph.set_series([(h.get(key,()),tone) for key,tone in zip(keys,self.graph.colors)])
        entries = c.get('logical_cpus')
        if entries is None:
            entries = [dict(id=i, usage=v, online=True) for i, v in enumerate(c['per_core'])]
        entries = sorted(entries, key=lambda row: row['id'])
        count_changed = len(self.core_meters) != len(entries)
        while len(self.core_meters) < len(entries):
            i = len(self.core_meters)
            m = Meter(f"CPU {i}")
            m.setMinimumHeight(m.minimumSizeHint().height())
            self.core_meters.append(m)
        while len(self.core_meters) > len(entries):
            meter = self.core_meters.pop()
            self.cores_grid.removeWidget(meter)
            meter.hide()
            meter.deleteLater()
        for meter, row in zip(self.core_meters, entries):
            core = row.get('core')
            text = f'CPU {row["id"]}'
            if core is not None:
                text += ' · ' + tr('Kern {id}').format(id=core)
            meter.name.setText(text)
            package = row.get('package')
            meter.setToolTip(tr('Sockel {id}').format(id=package) if package is not None else '')
            meter.set(row.get('usage'), tr('Offline') if not row.get('online', True) else None)
        if count_changed:
            self._core_columns = 0
        self._arrange_cores()


# ------------------------------------------------------------------ Grafik (schreibgeschützt)
class GpuCard(Card):
    """One coherent read-only GPU card: no privileged service or tuning controls."""

    def __init__(self):
        super().__init__()
        self.name = label("–", "bigName", wrap=True)
        self.meta = label("", "muted", wrap=True)
        self.product_header = ProductHeader(self.name, self.meta, 'gpu')
        self.body.addWidget(self.product_header)


        self.body.addWidget(label("AKTUELLE GPU-WERTE", "cardTitle"))
        self.kv = {key: KeyValue(key) for key in (
            "Auslastung", "Videospeicher", "GPU-Takt", "Speicher-Takt", "Temperatur", "Hotspot",
            "Spannung", "Leistung", 'Leistungsgrenze', "Lüfterdrehzahl", "Lüfter",
            "VRAM-Temperatur", "Speichercontroller", "Video-Engine", "Encoder", "Decoder",
            "Begrenzungsgründe", "Begrenzungsflags (Treiber)",
            "PCIe aktuell", "PCIe maximal", "Datenquelle", "Mesa",
        )}
        live = QGridLayout()
        self.live_grid = live
        self.live_fields = (
            'Auslastung','Videospeicher','Leistung','Leistungsgrenze','GPU-Takt','Speicher-Takt','Temperatur','Hotspot','VRAM-Temperatur',
            'Spannung','Lüfterdrehzahl','Lüfter','Speichercontroller',
            'Video-Engine','Encoder','Decoder','Begrenzungsgründe','Begrenzungsflags (Treiber)')
        live.setHorizontalSpacing(18)
        live.setVerticalSpacing(10)
        for i, name in enumerate((
            "GPU-Takt", "Speicher-Takt", "Temperatur", "Hotspot",
            "Spannung", "Leistung", "Lüfterdrehzahl", "Lüfter",
        )):
            live.addWidget(self.kv[name], i // 2, i % 2)
        self.body.addLayout(live)
        for key in self.live_fields:
            if self.kv[key].parent() is None:
                self.kv[key].setParent(self)
                self.kv[key].hide()
        self.kv['Leistung'].hide();self.kv['Leistungsgrenze'].hide()

        self.load_title=label('AUSLASTUNG UND VIDEOSPEICHER · VERLAUF', "cardTitle")
        self.body.addWidget(self.load_title)
        self.graph = ChartPanel(["Auslastung", "VRAM"], [theme.accent(), theme.secondary_accent()])
        self.body.addWidget(self.graph)
        self.h_use=deque(maxlen=900)
        self.h_vram=deque(maxlen=900)
        self.h_temp=deque(maxlen=900)
        self.h_clock=deque(maxlen=900)

        # Genuine detail-on-demand, not a second duplicate overview.
        self.more_btn = QPushButton("Technische Details anzeigen")
        self.more_btn.setCheckable(True)
        self.more_btn.toggled.connect(self._toggle_details)
        self.body.addWidget(self.more_btn)
        self.details = QWidget()
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(12)
        technical = QGridLayout()
        self.technical_grid=technical
        technical.setHorizontalSpacing(18)
        for i, name in enumerate(("PCIe aktuell", "PCIe maximal", "Datenquelle", "Mesa")):
            technical.addWidget(self.kv[name], i // 2, i % 2)
        detail_layout.addLayout(technical)
        self.sensor_hint = label(
            "Fehlende Werte bedeuten: Der Linux-Treiber liefert dafür momentan keine Daten.",
            "muted", wrap=True)
        detail_layout.addWidget(self.sensor_hint)
        self.temperature_graph = ChartPanel(["GPU-Temperatur"], [theme.accent()], mode="temperature")
        self.clock_graph = ChartPanel(["GPU-Takt"], [theme.secondary_accent()], mode="clock")
        self.temperature_title=label("TEMPERATURVERLAUF", "cardTitle")
        self.clock_title=label("TAKTVERLAUF", "cardTitle")
        detail_layout.addWidget(self.temperature_title)
        detail_layout.addWidget(self.temperature_graph)
        detail_layout.addWidget(self.clock_title)
        detail_layout.addWidget(self.clock_graph)
        self.body.addWidget(self.details)
        self.details.hide()

        self.extrema = KeyValue("GPU-Temperatur · Min/Max seit Start")
        self.body.addWidget(self.extrema)


    def _toggle_details(self, checked):
        self.details.setVisible(checked)
        self.more_btn.setText(tr("Technische Details ausblenden") if checked
                              else tr("Technische Details anzeigen"))

    def refresh(self, g, history=None, extrema=None, mesa=None):
        from .monitoring import format_range, valid_number

        self.name.setText(g.get("name") or tr("nicht verfügbar"))
        vendor = g.get("vendor")
        driver = g.get("driver")
        self.meta.setText(g.get('board_vendor') or '')
        self.product_header.set_product(g.get('product'))
        self.product_header.set_specs([
            ('GPU', vendor), ('Videospeicher', fmt_bytes(g.get('vram_total')) if g.get('vram_total') else ''),
            ('Treiber', driver)])
        reasons = g.get('unavailable') or {}
        optional(self.kv["Auslastung"],g.get("usage"),"%",0)
        used, total = g.get("vram_used"), g.get("vram_total")
        pct = used / total * 100 if valid_number(used) and valid_number(total) and total > 0 else None
        self.kv["Videospeicher"].set(_vram_text(g) if total else "")
        self.kv["Videospeicher"].setVisible(pct is not None)

        for field, source, unit in (
            ("GPU-Takt", "clock", "MHz"), ("Speicher-Takt", "clock_mem", "MHz"),
            ("Temperatur", "temp", "°C"), ("Hotspot", "hotspot", "°C"),
            ("Spannung", "voltage", "mV"),
            ("Lüfterdrehzahl", "fan_rpm", "U/min"), ("Lüfter", "fan", "%"),
            ('VRAM-Temperatur','vram_temp','°C'), ('Speichercontroller','memory_busy','%'),
            ('Video-Engine','video_busy','%'), ('Encoder','encoder_busy','%'), ('Decoder','decoder_busy','%'),
        ):
            optional(self.kv[field],g.get(source),unit,1 if unit=='W' else 0)
        for field,source in (('Begrenzungsgründe','throttle_reasons'),('Begrenzungsflags (Treiber)','throttle_flags')):
            text=g.get(source) or ''
            self.kv[field].set(text);self.kv[field].setVisible(bool(text))
        records=g.get('hardware') or []
        power=gpu_power(g)
        optional(self.kv['Leistung'],(power or {}).get('value'),'W')
        optional(self.kv['Leistungsgrenze'],power_limit(power),'W',0)
        self.kv['Leistung'].setToolTip(source_text(power))
        self.kv['Leistungsgrenze'].setToolTip(source_text(power))
        reflow(self.live_grid,[self.kv[key] for key in self.live_fields])
        for field, source in (("PCIe aktuell", "pcie_current"), ("PCIe maximal", "pcie_max")):
            value=g.get(source)
            visible=bool(value and value not in ('–','-'))
            self.kv[field].set(value if visible else '');self.kv[field].setVisible(visible)
        for field,value in (('Datenquelle',g.get('sensor_source')),('Mesa',mesa)):
            visible=bool(value and value not in ('–','-'))
            self.kv[field].set(value if visible else '');self.kv[field].setVisible(visible)
        reflow(self.technical_grid,[self.kv[k] for k in ('PCIe aktuell','PCIe maximal','Datenquelle','Mesa')])
        self.extrema.set(format_range(extrema or {},'gpu_temp','°C',1))
        self.extrema.setVisible(number(g.get('temp')) is not None and bool((extrema or {}).get('gpu_temp')))
        self.graph.setVisible(number(g.get('usage')) is not None or pct is not None)
        self.load_title.setVisible(not self.graph.isHidden())
        self.temperature_graph.setVisible(number(g.get('temp')) is not None)
        self.clock_graph.setVisible(number(g.get('clock')) is not None)
        self.temperature_title.setVisible(not self.temperature_graph.isHidden())
        self.clock_title.setVisible(not self.clock_graph.isHidden())
        if history is None:
            self.h_use.append(g.get("usage"))
            self.h_vram.append(pct)
            self.h_temp.append(g.get("temp"))
            self.h_clock.append(g.get("clock"))
        if history:
            self.graph.set_series([
                (history.get("gpu", self.h_use), theme.accent()),
                (history.get("vram", self.h_vram), theme.secondary_accent()),
            ])
            self.temperature_graph.set_series([
                (history.get("gpu_temp", self.h_temp), theme.accent())])
            self.clock_graph.set_series([
                (history.get("gpu_clock", self.h_clock), theme.secondary_accent())])
        else:
            self.graph.set_series([(self.h_use, theme.accent()),
                                   (self.h_vram, theme.secondary_accent())])
            self.temperature_graph.set_series([(self.h_temp, theme.accent())])
            self.clock_graph.set_series([(self.h_clock, theme.secondary_accent())])



class GpuPage(Page):
    def __init__(self):
        super().__init__("Grafik", "GPU-Auslastung, Videospeicher und Sensoren")
        self.cards = []
        self._mesa = system_static().get("mesa")
        self.none = Card()
        self.none.body.addWidget(label(
            "Keine GPU-Daten gefunden. Unterstützt werden NVIDIA, AMD und Intel, "
            "soweit Linux entsprechende Sensorwerte liefert.", wrap=True))
        self.content.addWidget(self.none)

    def refresh(self, d, h):
        gpus = d.get("gpus") or []
        self.none.setVisible(not gpus)
        while len(self.cards) < len(gpus):
            card = GpuCard()
            self.content.insertWidget(1 + len(self.cards), card)
            self.cards.append(card)
        recorder=getattr(self.window(),'gpu_history',None)
        for i, card in enumerate(self.cards):
            card.setVisible(i < len(gpus))
            if i < len(gpus):
                card.refresh(
                    gpus[i], history=recorder.get(gpus[i],i) if recorder is not None else h if i==0 else None,
                    extrema=d.get("session_extrema") if i == 0 else None,
                    mesa=self._mesa)


# ------------------------------------------------------------------ Speicher
class MemoryPage(Page):
    def __init__(self):
        super().__init__("Arbeitsspeicher", "RAM und Swap")
        self.module_cards = []
        self.g_ram, self.g_swap = GaugeCard("RAM"), GaugeCard("Swap")
        stats = Card("Details")
        self.kv = {k: KeyValue(k) for k in ('Leistung','Leistungsgrenze',"Gesamt", "In Benutzung", "Verfügbar", "Cache", "Puffer")}
        for w in self.kv.values():
            stats.body.addWidget(w)
        self.kv['Leistung'].hide();self.kv['Leistungsgrenze'].hide()
        self.content.addLayout(_row(self.g_ram, self.g_swap, stats))
        graph = Card("Verlauf")
        self.graph = ChartPanel(['RAM'], [theme.TEAL])
        graph.body.addWidget(self.graph)
        self.content.addWidget(graph)
        self.hardware=SensorPanel(include_power=False)
        self.content.addWidget(self.hardware)

    def refresh(self, d, h):
        r = d["ram"]
        grouped = {}
        for module in r.get('modules', []):
            identity = tuple(module.get(k) for k in ('vendor','model','capacity','memory_type','speed'))
            grouped.setdefault(identity, []).append(module)
        groups = list(grouped.values())
        while len(self.module_cards) < len(groups):
            card = Card()
            name, meta = label('', 'bigName', wrap=True), label('', 'muted', wrap=True)
            header = ProductHeader(name, meta, 'ram')
            card.body.addWidget(header)
            self.content.insertWidget(len(self.module_cards), card)
            self.module_cards.append((card, header, name, meta))
        for index, (card, header, name, meta) in enumerate(self.module_cards):
            card.setVisible(index < len(groups))
            if index >= len(groups):continue
            modules = groups[index];module = modules[0]
            name.setText(module.get('model') or tr('Arbeitsspeicher'))
            meta.setText(module.get('vendor') or '')
            header.set_product(module.get('product'))
            speed = module.get('speed')
            detail = ' · '.join(str(x) for x in (module.get('memory_type'),f'{speed} MT/s' if speed else '') if x)
            header.set_specs([
                ('Kapazität', f'{len(modules)} × {fmt_bytes(module.get("capacity"))}'),
                ('Speichertyp', detail),
                ('Steckplatz', ', '.join(m.get('slot','') for m in modules if m.get('slot')))])
        power=component_power(d.get('hardware',[]),'ram')
        optional(self.kv['Leistung'],(power or {}).get('value'),'W')
        optional(self.kv['Leistungsgrenze'],power_limit(power),'W')
        self.kv['Leistung'].setToolTip(source_text(power))
        self.hardware.sync([r for r in d.get('hardware',[]) if r['component']=='ram'])
        self.g_ram.set(r["percent"], f"{fmt_bytes(r['used'])} / {fmt_bytes(r['total'])}")
        if r["swap_total"]:
            self.g_swap.set(r["swap_percent"], f"{fmt_bytes(r['swap_used'])} / {fmt_bytes(r['swap_total'])}")
        else:
            self.g_swap.set(None, "nicht aktiv")
        self.kv["Gesamt"].set(fmt_bytes(r["total"]))
        self.kv["In Benutzung"].set(fmt_bytes(r["used"]))
        self.kv["Verfügbar"].set(fmt_bytes(r["available"]))
        self.kv["Cache"].set(fmt_bytes(r["cached"]))
        self.kv["Puffer"].set(fmt_bytes(r["buffers"]))
        self.graph.set_series([(h['ram'],theme.TEAL)])


# ------------------------------------------------------------------ Laufwerke
class SmartWorker(QThread):
    completed = Signal(object)

    def run(self):
        try:
            self.completed.emit(smart_monitor.scan(drives()))
        except Exception as exc:
            self.completed.emit([{'name': 'SMART', 'error': str(exc)}])


class DiskPage(Page):
    def __init__(self):
        super().__init__("Laufwerke", "Datenträger, Belegung und Durchsatz")
        self.hw = Card("Physische Datenträger")
        self.hw_rows = {}
        self.parts = Card("Partitionen")
        self.part_meters = {}
        io = Card("Durchsatz")
        self.read, self.write = KeyValue("Lesen"), KeyValue("Schreiben")
        io.body.addWidget(self.read)
        io.body.addWidget(self.write)
        self.content.addLayout(_row(self.hw, self.parts))
        self.content.addWidget(io)
        io_graph = Card('Laufwerksaktivität')
        self.io_graph = ChartPanel(['Lesen','Schreiben'], [theme.accent(),theme.secondary_accent()],mode='rate')
        io_graph.body.addWidget(self.io_graph)
        self.content.addWidget(io_graph)
        self.hardware=SensorPanel()
        self.content.addWidget(self.hardware)
        self.smart_card = SmartPane()
        self.smart_button = self.smart_card.button
        self.smart_status = self.smart_card.status
        self.smart_button.clicked.connect(self.request_smart)
        self.content.addWidget(self.smart_card)
        self._smart_worker = None
        self._smart_loaded = False
        # Disk selectors are already visible while SMART runs in a worker.
        # Do not delay the user's first access to drive details.
        self.smart_card.set_devices(drives())
        # Integrierter Laufwerks-Benchmark unter den Laufwerksdaten.
        self.benchmark = BenchmarkPanel()
        self.content.addWidget(self.benchmark)
        self._tick = 0


    def request_smart(self):
        if self._smart_worker and self._smart_worker.isRunning():
            return
        self.smart_button.setEnabled(False)
        self.smart_status.setText('Lese SMART-Daten im Hintergrund …')
        self._smart_worker = SmartWorker(self)
        self._smart_worker.completed.connect(self.show_smart)
        self._smart_worker.finished.connect(lambda: self.smart_button.setEnabled(True))
        self._smart_worker.start()

    def show_smart(self, reports):
        self._smart_loaded = True
        self.smart_card.set_reports(reports, drives())

    def refresh_appearance(self):
        self.smart_card.refresh_theme()

    def retranslate(self):
        self.smart_card.retranslate()

    def refresh(self, d, h):
        self.hardware.sync([r for r in d.get('hardware',[]) if r['component']=='disks'])
        if self._tick % 30 == 0:
            for dr in drives():
                if dr["name"] not in self.hw_rows:
                    kv = KeyValue(f"{dr['name']}  ·  {dr['kind']}")
                    self.hw.body.addWidget(kv)
                    self.hw_rows[dr["name"]] = kv
                text = (dr["model"] + "  ·  " if dr["model"] else "") + fmt_bytes(dr["size"], 1000)
                self.hw_rows[dr["name"]].set(text)
        self._tick += 1
        self.benchmark.update_volumes(d["disks"])
        self.read.set(fmt_rate(d["io"]["read"]))
        self.write.set(fmt_rate(d["io"]["write"]))
        self.io_graph.set_series([(h['io_read'],theme.accent()),(h['io_write'],theme.secondary_accent())])
        current = {x["mount"] for x in d["disks"]}
        for x in d["disks"]:
            m = self.part_meters.get(x["mount"])
            if m is None:
                m = self.part_meters[x["mount"]] = Meter(f"{x['mount']}   ({x['device']}, {x['fstype']})")
                self.parts.body.addWidget(m)
            m.setVisible(True)
            m.set(x["percent"], f"{fmt_bytes(x['used'])} / {fmt_bytes(x['total'])}   ({x['percent']:.0f}%)")
        for mount, m in self.part_meters.items():
            if mount not in current:
                m.setVisible(False)


# ------------------------------------------------------------------ Netzwerk
class NetworkPage(Page):
    def __init__(self):
        super().__init__("Netzwerk", "Live-Datenverkehr, Schnittstellen und Verbindungsdetails")
        page_content=self.content
        self.tabs=QTabWidget()
        overview=QWidget()
        self.content=QVBoxLayout(overview)
        self.content.setContentsMargins(0,12,0,0)
        self.content.setSpacing(14)
        top = Card(hero=True)
        self.primary = KeyValue("Aktive Schnittstelle")
        self.addr = KeyValue("IPv4")
        self.total = KeyValue("Daten gesamt")
        self.speed = KeyValue("Link-Geschwindigkeit")
        self.gateway = KeyValue('Gateway')
        self.dns = KeyValue('DNS-Server')
        self.mac = KeyValue('MAC-Adresse')
        top.body.addWidget(self.primary)
        top.body.addWidget(self.addr)
        top.body.addWidget(self.total)
        top.body.addWidget(self.speed)
        top.body.addWidget(self.gateway)
        top.body.addWidget(self.dns)
        top.body.addWidget(self.mac)
        self.content.addWidget(top)

        graph = Card("Netzwerk-Verlauf")
        self.graph = ChartPanel(['Download','Upload'],[theme.accent(),theme.secondary_accent()],mode='rate')
        graph.body.addWidget(self.graph)
        rates = Card("Aktuelle Übertragungsraten")
        self.down = KeyValue("Download")
        self.up = KeyValue("Upload")
        rates.body.addWidget(self.down)
        rates.body.addWidget(self.up)

        self.ifaces_card = Card("Netzwerkschnittstellen")
        self.iface_rows = {}
        self.content.addWidget(rates)
        self.content.addWidget(graph)
        self.content.addWidget(self.ifaces_card)
        self.hardware=SensorPanel()
        self.content.addWidget(self.hardware)
        from .network_ui import NetworkWatch
        self.watcher=NetworkWatch()
        self.tabs.addTab(overview,tr('Übersicht'))
        self.tabs.addTab(self.watcher,tr('Programme & Verbindungen').replace('&','&&'))
        self.content=page_content
        self.content.addWidget(self.tabs)

    def retranslate(self):
        self.tabs.setTabText(0,tr('Übersicht'))
        self.tabs.setTabText(1,tr('Programme & Verbindungen').replace('&','&&'))
        self.watcher.retranslate()

    def shutdown(self):
        return self.watcher.shutdown()

    def refresh(self, d, h):
        net = d["net"]
        self.hardware.sync([r for r in d.get('hardware',[]) if r['component']=='network'])
        p = net.get("primary") or {}
        self.primary.set(p.get("name", "–"))
        self.addr.set(p.get("ipv4") or "–")
        self.total.set(f"↓ {fmt_bytes(net['total_down'])}   ·   ↑ {fmt_bytes(net['total_up'])}")
        self.speed.set(f"{p.get('speed', 0)} Mbit/s" if p.get("speed") else "–")
        self.gateway.set(net.get('gateway') or '–')
        self.dns.set(', '.join(net.get('dns', [])) or '–')
        self.mac.set(p.get('mac') or '–')
        self.down.set(fmt_rate(net["down"]))
        self.up.set(fmt_rate(net["up"]))
        self.graph.set_series([(h['net_down'],theme.accent()),(h['net_up'],theme.secondary_accent())])
        for iface in net.get("interfaces", []):
            row = self.iface_rows.get(iface["name"])
            if row is None:
                row = self.iface_rows[iface["name"]] = KeyValue(iface["name"])
                self.ifaces_card.body.addWidget(row)
            state = "UP" if iface["isup"] else "DOWN"
            speed = f"{iface['speed']} Mbit/s" if iface["speed"] else "–"
            ip = iface.get("ipv4") or iface.get("ipv6") or tr('keine IP')
            row.set(f"{state} · {speed} · {ip}")


# ------------------------------------------------------------------ System
class SystemPage(Page):
    def __init__(self, distro):
        super().__init__("System", "Betriebssystem, Hardware und Software")
        s = system_static()
        product = s.get('board_product') or {}
        self.board_card = Card('Mainboard')
        self.board_name = label(product.get('model') or s.get('board') or '–', 'bigName', wrap=True)
        revision = product.get('revision')
        self.board_meta = label(product.get('vendor') or '', 'muted', wrap=True)
        self.board_header = ProductHeader(self.board_name, self.board_meta, 'mainboard')
        self.board_header.set_product(product)
        self.board_header.set_specs([('Revision', revision), ('BIOS', s.get('bios'))])
        self.board_card.body.addWidget(self.board_header)
        self.content.addWidget(self.board_card)
        os_card = Card("Betriebssystem")
        self.uptime = KeyValue("Laufzeit")
        for k, v in (("Distribution", distro["name"]), ("Kernel", s["kernel"]), ("Architektur", s["arch"]),
                     ("Rechnername", s["host"]), ("Benutzer", s["user"]), ("Desktop", s["desktop"]),
                     ("Sitzung", s["session"])):
            kv = KeyValue(k)
            kv.set(v)
            os_card.body.addWidget(kv)
        os_card.body.addWidget(self.uptime)

        hw_card = Card("Hardware")
        self.cpu_kv, self.gpu_kv = KeyValue("Prozessor"), KeyValue("Grafik")
        for k, v in (("Hersteller", s["vendor"]), ("Modell", s["product"]),
                     ("BIOS", s["bios"])):
            kv = KeyValue(k)
            kv.set(v)
            hw_card.body.addWidget(kv)
        hw_card.body.addWidget(self.cpu_kv)
        hw_card.body.addWidget(self.gpu_kv)

        sw_card = Card("Software")
        for k, v in (("Python", platform.python_version()), ("Qt", qVersion()), ("PySide6", PySide6.__version__),
                     ("KDE Plasma", s["plasma"]), ("KWin", s["kwin"]), ("KDE Frameworks", s["frameworks"]),
                     ("Mesa", s["mesa"])):
            kv = KeyValue(k)
            kv.set(v)
            sw_card.body.addWidget(kv)
        self.content.addLayout(_row(os_card, hw_card))
        self.content.addWidget(sw_card)
        graphics_card = Card('Grafiksystem & Anzeigen')
        from PySide6.QtGui import QGuiApplication
        runtime = graphics_runtime(QGuiApplication.platformName(), QGuiApplication.screens())
        for title, value in (('Qt-Grafikbackend', runtime['qt_platform']),
                             ('Display-Server', runtime['runtime']),
                             ('Sitzungstyp', runtime['session'])):
            kv = KeyValue(title)
            kv.set(value)
            graphics_card.body.addWidget(kv)
        for idx, screen in enumerate(runtime['screens'], 1):
            rate = f" · {screen['hz']:g} Hz" if screen['hz'] is not None else ''
            kv = KeyValue(f'Bildschirm {idx} · {screen["name"]}')
            scale = f" · {screen['scale_percent']} % {tr('Skalierung')}" if screen.get('scale_percent', 100) != 100 else ''
            kv.set(f"{screen['width']} × {screen['height']}{rate}{scale}")
            graphics_card.body.addWidget(kv)
        self.render_gpu = KeyValue('Erkannte Grafik / mögliche Render-GPU')
        graphics_card.body.addWidget(self.render_gpu)
        self.render_driver = KeyValue('Grafiktreiber')
        graphics_card.body.addWidget(self.render_driver)
        graphics_card.body.addWidget(label('Bei mehreren GPUs lässt sich das aktive Rendergerät ohne zusätzliche Abfrage nicht immer eindeutig bestimmen.', 'muted', wrap=True))
        self.content.addWidget(graphics_card)
        perf_card = Card('Vitalux · Ressourcenverbrauch')
        self.app_cpu = KeyValue('Vitalux CPU')
        self.app_ram = KeyValue('Vitalux RAM')
        self.app_paint = KeyValue('Messwert-Aktualisierung')
        perf_card.body.addWidget(self.app_cpu)
        perf_card.body.addWidget(self.app_ram)
        perf_card.body.addWidget(self.app_paint)
        self.content.addWidget(perf_card)

        self.status_card = Card("Hardware-Status")
        self.status_rows = {title: KeyValue(title) for title in (
            "CPU", "GPU", "RAM", "Systemlaufwerk")}
        for row in self.status_rows.values():
            self.status_card.body.addWidget(row)
        self.status_card.body.addWidget(label(
            "Status nach realen Messwerten und eingestellten Warnwerten; "
            "keine Schätzung des Hardwarezustands.", "muted", wrap=True))
        self.reset_btn = QPushButton("Min-/Max-Werte zurücksetzen")
        self.reset_btn.clicked.connect(self._reset_session)
        self.status_card.body.addWidget(self.reset_btn)
        self.content.addWidget(self.status_card)
        self.hardware=SensorPanel()
        self.content.addWidget(self.hardware)

    def _reset_session(self):
        main = self.window()
        if hasattr(main, "reset_session_extrema"):
            main.reset_session_extrema()

    def refresh(self, d, h):
        from .monitoring import hardware_status
        self.hardware.sync([r for r in d.get('hardware',[]) if r['component']=='system'])
        from . import settings
        limits = {name: settings.get(name, default) for name, default in (
            ("cpu_temp", 90), ("gpu_temp", 90),
            ("ram_usage", 90), ("disk_usage", 95))}
        status = dict(hardware_status(d, limits))
        for key, row in self.status_rows.items():
            row.set(status.get(key, tr("nicht verfügbar")))
        self.render_gpu.set(system_gpu_device(d['gpus']))
        self.render_driver.set(', '.join(dict.fromkeys(str(g.get('driver')) for g in d['gpus'] if g.get('driver'))) or '–')
        app = d.get('app_resources') or {}
        self.app_cpu.set(f"{app['cpu_percent']:.1f} %" if app.get('cpu_percent') is not None else '–')
        self.app_ram.set(fmt_bytes(app.get('rss_bytes')))
        # The render duration is measured by the main window after paint data dispatch.
        from PySide6.QtWidgets import QApplication
        window = QApplication.activeWindow()
        duration = getattr(window, 'last_render_ms', None)
        self.app_paint.set(f'{duration:.1f} ms' if duration is not None else '–')
        self.uptime.set(fmt_duration(d["uptime"]))
        self.cpu_kv.set(d["cpu"]["model"])
        self.gpu_kv.set(", ".join(g["name"] for g in d["gpus"]) or "–")
