from collections import deque
from threading import Event
import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QVariantAnimation, QEasingCurve, QPoint, QRect, QEventLoop
from PySide6.QtGui import QRegion, QAction
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QScrollArea, QStackedWidget, QVBoxLayout, QWidget, QSystemTrayIcon, QGraphicsDropShadowEffect, QMenu)
from .ui_locale import QPushButton, retranslate_widgets

from . import APP_NAME, __version__, i18n, sensors, settings, theme, motion, eco
from .i18n import tr
from .pages import CpuPage, DiskPage, GpuPage, MemoryPage, NetworkPage, OverviewPage, SystemPage
from .pages_extra import InfoPage, UpdatePage
from .control import SensorsPage, PreferencesPage
from .brand import PulseCore, TrayPulse, Wordmark, app_icon, sync_installed_icon
from .widgets import NavButton, SidebarToggle, ChartPanel, Gauge, label
from .glass import GlassSidebar, GlassSurface, create_ambient_scene
from .sidebar_transition import SidebarTransition, SidebarFreeze
from .smooth_scroll import AdaptiveScrollArea
from .alerts import AlertMonitor, readings_from_sample
from .tray_tooltip import tray_tooltip
from .wallpaper_accents import resolve_accent
from .monitoring import GpuHistory, SessionExtrema
from .diagnostics import log_exception
from .diagnostic_center import DiagnosticCenter
from .diagnostic_engine import BlackboxRecorder
from .mini_hud import MiniHUD
from .sample_clock import sampling_gap


class Sampler(QThread):
    sample = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.interval = eco.interval()
        self._last_error = None
        self._stopped = Event()
        self._sample_clock = None

    def start(self, *args):
        self._stopped.clear()
        super().start(*args)

    def stop(self):
        self.requestInterruption()
        self._stopped.set()

    def run(self):
        while not self.isInterruptionRequested():
            try:
                gap = sampling_gap(self._sample_clock, (time.time(), time.monotonic()), self.interval)
                if gap:
                    sensors.prime()
                data = sensors.collect()
                self._sample_clock = (time.time(), time.monotonic())
                data['timestamp'] = self._sample_clock[0]
                data['_gap_before'] = gap
                if not self.isInterruptionRequested():
                    self.sample.emit(data)
                self._last_error = None
            except Exception as exc:
                # Retain one timestamped, versioned traceback per distinct
                # failure instead of flooding logs at one-second intervals.
                error = (type(exc), str(exc))
                if error != self._last_error:
                    log_exception(type(exc), exc, exc.__traceback__)
                    self._last_error = error
            self._stopped.wait(max(1, self.interval))


class MainWindow(QMainWindow):
    def __init__(self, distro, logo, manager, *, startup_sample=None, preparing=None):
        super().__init__()
        # Never request per-pixel transparency of the native window.
        # Frosted materials are drawn inside Vitalux;
        # the entire application canvas remains fully opaque.
        self.setAutoFillBackground(True)
        self.distro, self.logo, self.manager = distro, logo, manager
        self._startup_progress=preparing
        self.setWindowTitle(APP_NAME)
        # Accommodate KDE fractional scaling and smaller logical desktops.
        self.setMinimumSize(800, 560)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry().size()
            self.resize(max(800, min(1380, available.width() - 32)),
                        max(560, min(900, available.height() - 32)))
        else:
            self.resize(1380, 900)
        self.hist = {k: deque(maxlen=900) for k in (
            "cpu", "ram", "gpu", "net_down", "net_up", "io_read", "io_write",
            "cpu_temp", "cpu_clock", "time")}
        self._extrema = SessionExtrema()
        self.gpu_history=GpuHistory()
        self._mini_hud = MiniHUD()
        self._mini_hud.hidden_by_user.connect(self._mini_hud_closed)
        self._blackbox = BlackboxRecorder()
        self.last_sample = None
        self.pages = []
        self.update_btn = None
        self._sidebar_collapsed = bool(settings.get('sidebar_collapsed', False))
        self._sidebar_progress = 1.0 if self._sidebar_collapsed else 0.0
        self._sidebar_motion = None
        self._sidebar_overlay = None
        self._alerts = AlertMonitor()
        self._force_quit = False
        self._close_retry = QTimer(self)
        self._close_retry.setSingleShot(True)
        self._close_retry.timeout.connect(self.close)
        self.restart_requested = False
        self._shutdown_pending = False
        self._reset_commit = None
        self._shutdown_not_before = 0.0
        self._update_notice_queued = False
        self._notified_update_version = str(settings.get('last_notified_update_version', ''))
        self._tray_was_maximized = False
        self.last_render_ms = None
        self._last_refresh_error = None
        # Create the tray icon even when Plasma's StatusNotifier host comes up
        # after Vitalux. Qt automatically registers a visible icon when a host
        # becomes available. Checking isSystemTrayAvailable() here loses that.
        self._tray = QSystemTrayIcon(app_icon(), self)
        self._tray.setToolTip(tray_tooltip(None))
        self._tray_glow = TrayPulse(self._tray, self)
        self._tray_menu = QMenu(self)
        self._tray_open_action = QAction(tr('Vitalux öffnen'), self._tray_menu)
        self._tray_quit_action = QAction(tr('Beenden'), self._tray_menu)
        self._tray_open_action.triggered.connect(self.show_from_tray)
        self._tray_quit_action.triggered.connect(self.quit_from_tray)
        self._tray_menu.addAction(self._tray_open_action)
        self._tray_hud_action = QAction(tr('MiniHUD anzeigen'), self._tray_menu)
        self._tray_hud_action.setCheckable(True)
        self._tray_hud_action.setChecked(bool(settings.get('mini_hud_enabled', False)))
        self._tray_hud_action.toggled.connect(self.set_mini_hud_enabled)
        self._tray_menu.addAction(self._tray_hud_action)
        self._tray_update_action = QAction('', self._tray_menu)
        self._tray_update_action.setVisible(False)
        self._tray_update_action.triggered.connect(self._open_updates_from_tray)
        self._tray_menu.addAction(self._tray_update_action)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(self._tray_quit_action)
        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        # A single click normally produces Trigger. A double click may first
        # produce Trigger, so debounce it to avoid hiding an opened window.
        self._tray_click_timer = QTimer(self)
        self._tray_click_timer.setSingleShot(True)
        self._tray_click_timer.setInterval(190)
        self._tray_click_timer.timeout.connect(self._toggle_tray_window)
        self._tray.show()
        manager.changed.connect(self._sync_glow)
        manager.restart.connect(self._restart_after_update)
        self._build(0)
        self._appearance_key = self._appearance_signature()
        self._appearance_overlay = None
        if settings.get('mini_hud_enabled', False) and preparing is None:
            self.set_mini_hud_enabled(True)

        self.sampler = Sampler(self)
        self.sampler.sample.connect(self.on_sample)
        if startup_sample is not None:
            self.on_sample(startup_sample)
            for _,page in self.pages:
                for chart in page.findChildren(ChartPanel):chart.set_timeline(self.hist['time'])
                page.refresh(startup_sample,self.hist)
                page.ensurePolished()
                if page.layout():page.layout().activate()
                if self._startup_progress:self._startup_progress()
            from .product_ui import ProductHeader
            for header in self.findChildren(ProductHeader):
                header.request_specs();header._request()
        self._startup_progress=None
        self.sampler.start()
        # SMART diagnostics are asynchronous and intentionally delayed so app
        # startup stays responsive. The overview incorporates results on the
        # next sensor sample, even if the user never opens the Drives page.
        QTimer.singleShot(8000, self._start_background_smart)

    def _start_background_smart(self):
        disk = next((page for title, page in self.pages if title == 'Laufwerke'), None)
        if disk is not None and not disk._smart_loaded and (
                disk._smart_worker is None or not disk._smart_worker.isRunning()):
            disk.request_smart()

    def _build(self, index):
        # A disk benchmark must not outlive its QWidget when changing the UI theme/language.
        for _name, old_page in self.pages:
            if isinstance(old_page, DiskPage):
                if not old_page.benchmark.stop_and_wait():
                    return  # Never destroy a running QThread.
        distro, logo = self.distro, self.logo
        root = create_ambient_scene()
        self.render_backend_active = root.render_backend
        canvas = QVBoxLayout(root)
        canvas.setContentsMargins(0,0,0,0)
        canvas.setSpacing(0)
        outer = QHBoxLayout()
        canvas.addLayout(outer,1)
        self._outer_layout = outer
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        side = GlassSidebar()
        self.sidebar = side
        side.setFixedWidth(250)
        sl = QVBoxLayout(side)
        self.sidebar_layout = sl
        sl.setContentsMargins(16, 21, 16, 16)
        sl.setSpacing(4)
        # One brand block: its internal spacings vanish completely in icon mode.
        brand = QWidget(side)
        brand.setObjectName('sidebarBrand')
        brand_lay = QVBoxLayout(brand)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(4)
        self.sidebar_brand = brand
        self.pulse_core = PulseCore(size=132, parent=brand)
        brand_lay.addWidget(self.pulse_core, 0, Qt.AlignHCenter)
        brand_lay.addSpacing(4)
        mark = Wordmark()
        mark.setObjectName('wordmarkWrap')
        mark.setFixedSize(200, 42)
        self.brand_mark = mark
        brand_lay.addWidget(mark, 0, Qt.AlignHCenter)
        brand_lay.addSpacing(7)
        self.sidebar_distro = label(distro['short'], 'sidebarDistro', Qt.AlignHCenter, wrap=True)
        brand_lay.addWidget(self.sidebar_distro)
        brand_lay.addSpacing(15)
        sl.addWidget(brand)

        self.stack = QStackedWidget()
        factories=[
            ('Übersicht',lambda:OverviewPage(distro,logo)),('Prozessor',CpuPage),('Grafik',GpuPage),
            ('Arbeitsspeicher',MemoryPage),('Laufwerke',DiskPage),('Netzwerk',NetworkPage),
            ('Sensoren',SensorsPage),('Diagnostic Center',DiagnosticCenter),('System',lambda:SystemPage(distro)),
            ('Einstellungen',lambda:PreferencesPage(self)),('Updates',lambda:UpdatePage(self.manager)),('Info',lambda:InfoPage(distro))]
        self.pages=[]
        for title,factory in factories:
            self.pages.append((title,factory()))
            if self._startup_progress:self._startup_progress()
        # Keep the branding and language switch fixed, while the full glass
        # category list can scroll on shorter screens (e.g. 760px).
        nav_host = QWidget()
        self.nav_host = nav_host
        nav_host.setObjectName('glassNavRail')
        nav_host.setAutoFillBackground(False)
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(1, 2, 3, 2)
        nav_layout.setSpacing(5)
        nav_scroll = AdaptiveScrollArea()
        self.nav_scroll = nav_scroll
        nav_scroll.setObjectName('glassScroll')
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setAutoFillBackground(False)
        nav_scroll.viewport().setAutoFillBackground(False)
        nav_scroll.setWidget(nav_host)

        group = QButtonGroup(side)
        self.nav_buttons = []
        glyph = {"Übersicht":"◈", "Prozessor":"◉", "Grafik":"▣", "Arbeitsspeicher":"▤",
                 "Netzwerk":"◎", "Laufwerke":"▱", "Sensoren":"♨", "Diagnostic Center":"⌕", "System":"⚙",
                 "Einstellungen":"≡", "Updates":"↻", "Info":"ⓘ"}
        for i, (name, page) in enumerate(self.pages):
            btn = NavButton(glyph.get(name, '•') + '    ' + tr(name))
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            group.addButton(btn, i)
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)
            if name == "Updates":
                self.update_btn = btn
            scroll = AdaptiveScrollArea()
            scroll.setObjectName('glassScroll')
            scroll.setWidgetResizable(True)
            scroll.setAutoFillBackground(False)
            scroll.viewport().setAutoFillBackground(False)
            page.setAutoFillBackground(False)
            scroll.setWidget(page)
            if name == 'Einstellungen':
                page.install_search_overlay(scroll)
            self.stack.addWidget(scroll)
        group.idClicked.connect(self._switch_page)
        group.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)

        nav_layout.addStretch(1)
        sl.addWidget(nav_scroll, 1)
        # Border-docked arrow replaces the full-width "Einklappen" button.
        self.collapse_button = SidebarToggle(side)
        self.collapse_button.clicked.connect(self.toggle_sidebar)
        side.set_toggle_button(self.collapse_button)
        sl.addSpacing(8)
        lang_host = QWidget(side)
        self.lang_host = lang_host
        langs = QHBoxLayout(lang_host)
        langs.setContentsMargins(0, 0, 0, 0)
        langs.setSpacing(6)
        langs.addStretch(1)
        for code in ("de", "en"):
            b = QPushButton(code.upper())
            b.setObjectName("langBtn")
            b.setCheckable(True)
            b.setToolTip('Deutsch' if code == 'de' else 'English')
            b.setChecked(i18n.lang() == code)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self.set_language(c))
            langs.addWidget(b)
        langs.addStretch(1)
        self.lang_buttons = langs
        sl.addWidget(lang_host)
        sl.addSpacing(6)
        self.sidebar_version = label(f"{APP_NAME}  ·  {__version__}", 'sidebarVersion', Qt.AlignHCenter)
        sl.addWidget(self.sidebar_version)

        outer.addWidget(side)
        outer.addWidget(self.stack, 1)
        from .design_shell import DesignShell
        self.design_shell=DesignShell(self,canvas)
        self.setCentralWidget(root)
        self._optimize_scroll_surfaces()
        self._apply_sidebar_state()
        self.design_shell.sync()
        self._setup_sidebar_motion()
        self._sync_glow()
        # Apply the lightweight renderer even when Minimalistisch is saved
        network=next(page for title,page in self.pages if title=='Netzwerk')
        network.watcher.alert.connect(self._network_alert)
        # before the application launches, rather than only on theme switches.
        if theme.mode() == "minimal":
            self.apply_appearance()

    def _switch_page(self, index):
        # Leaving edit mode commits the layout; neither the editor nor its
        # unsaved arrangement is silently destroyed on navigation.
        overview = self.pages[0][1]
        if index != 0 and hasattr(overview, 'board') and overview.board.editing:
            overview.save_editor()
        changed = index != self.stack.currentIndex()
        scroll = self.stack.widget(index)
        if changed:
            scroll._cancel_scroll()
            page = self.pages[index][1]
            if hasattr(page, 'search_navigation'):
                page.search_navigation.cancel()
                page.search_overlay.close_search()
            self.nav_buttons[index].setFocus(Qt.OtherFocusReason)
            scroll.verticalScrollBar().setValue(0)
            scroll.horizontalScrollBar().setValue(0)
        self.stack.setCurrentIndex(index)
        if hasattr(self,'design_shell'):
            self.design_shell.select(index)
        if changed:
            QTimer.singleShot(0, lambda: scroll.verticalScrollBar().setValue(0)
                              if self.stack.currentWidget() is scroll else None)
        # Start the read-only SMART scan on first entry, after the device
        # selectors are visible. Subsequent visits keep the last results;
        # users can still rescan using the button.
        page_name, page_widget = self.pages[index]
        if (page_name == 'Laufwerke' and not page_widget._smart_loaded
                and (page_widget._smart_worker is None or
                     not page_widget._smart_worker.isRunning())):
            QTimer.singleShot(0, page_widget.request_smart)
        # Keep sampling while refreshing only the visible page.
        self._refresh_visible_page()

    def set_language(self, code):
        """Translate widgets in place; never rebuild a running benchmark/page."""
        if code == i18n.lang():
            return
        # All source strings are tracked by our Qt widget wrappers.
        scrolls = [(scroll,scroll.verticalScrollBar().value())
                   for scroll in self.findChildren(QScrollArea)]
        i18n.set_lang(code)
        settings.set('lang',code)
        self._tray_open_action.setText(tr('Vitalux öffnen'))
        self._tray_quit_action.setText(tr('Beenden'))
        self._tray_hud_action.setText(tr('MiniHUD anzeigen'))
        self.refresh_mini_hud()
        self._tray.setToolTip(tray_tooltip(self.last_sample))
        retranslate_widgets(self.centralWidget())
        from .spec_ui import SpecificationDialog
        for dialog in self.findChildren(SpecificationDialog):retranslate_widgets(dialog)
        diagnosis = next((page for title, page in self.pages if title == 'Diagnostic Center'), None)
        if diagnosis is not None:
            diagnosis.retranslate()
        glyph = {"Übersicht":"◈", "Prozessor":"◉", "Grafik":"▣", "Arbeitsspeicher":"▤",
                 "Netzwerk":"◎", "Laufwerke":"▱", "Sensoren":"♨", "Diagnostic Center":"⌕", "System":"⚙",
                 "Einstellungen":"≡", "Updates":"↻", "Info":"ⓘ"}
        for btn, (name, _) in zip(self.nav_buttons,self.pages):
            btn.setText(glyph.get(name,'•') + '    ' + tr(name))
            btn.setToolTip('')
            btn.update()
        for btn in self.lang_host.findChildren(QPushButton):
            btn.setChecked(btn.text().lower() == code)
        if hasattr(self.pages[0][1], 'retranslate'):
            self.pages[0][1].retranslate()
        disk = next((p for name, p in self.pages if name == 'Laufwerke'), None)
        if disk is not None and hasattr(disk, 'retranslate'):
            disk.retranslate()
        pref = next((page for title, page in self.pages if title == 'Einstellungen'), None)
        if pref is not None and hasattr(pref, 'refresh_appearance'):
            pref.refresh_appearance()
            pref.retranslate()
        self._sync_glow()
        # Layout reflow may happen when labels grow in English.
        self.design_shell.retranslate()
        network=next((page for title,page in self.pages if title=='Netzwerk'),None)
        if network is not None and hasattr(network,'retranslate'):
            network.retranslate()
        QTimer.singleShot(0,lambda: [scroll.verticalScrollBar().setValue(value)
                                    for scroll,value in scrolls])

    def _sync_glow(self):
        update_version=getattr(self.manager,'notification_version',self.manager.latest)
        on = self.manager.available and bool(update_version)
        animated = on and not eco.enabled()
        version = update_version if on else ''
        if self.update_btn is not None:
            self.update_btn.set_glow(animated)
            self.update_btn.set_update_version('v' + version if on else '')
            # The icon-only Nebula dock needs the label/version on hover.
            self.update_btn.setToolTip(
                tr('Updates') + (' v' + update_version if on else '') if theme.mode()=='nebula_prism' else '')
        if hasattr(self, 'pulse_core'):
            self.pulse_core.set_update_available(animated)
        if hasattr(self, '_tray_glow'):
            self._tray_glow.set_active(animated)
        if self._tray is not None:
            self._tray_update_action.setVisible(on)
            if on:
                self._tray_update_action.setText(
                    tr('Update verfügbar:') + ' v' + version)
        if (on and version != self._notified_update_version
                and not self._update_notice_queued):
            self._update_notice_queued = True
            QTimer.singleShot(1300, self._announce_update)

    def _announce_update(self):
        self._update_notice_queued = False
        if not self.manager.available or not getattr(self.manager,'notification_version',self.manager.latest):
            return
        version = getattr(self.manager,'notification_version',self.manager.latest)
        if version == self._notified_update_version:
            return
        if not (self._tray and self._tray.isVisible()
                and QSystemTrayIcon.isSystemTrayAvailable()
                and QSystemTrayIcon.supportsMessages()):
            return
        self._tray.showMessage(
            APP_NAME + ' · ' + tr('Update verfügbar'),
            tr('Version {} ist verfügbar. Im Reiter Updates ansehen.').format(version),
            QSystemTrayIcon.Information, 7000)
        self._notified_update_version = version
        settings.set('last_notified_update_version', version)

    def _open_updates_from_tray(self):
        self.show_from_tray()
        for index, (name, _page) in enumerate(self.pages):
            if name == 'Updates':
                self.nav_buttons[index].setChecked(True)
                self._switch_page(index)
                return


    def set_interval(self, val):
        val = eco.SAMPLE_INTERVAL if eco.enabled() else max(1, min(5, int(val)))
        self.sampler.interval = val
        for _, page in self.pages:
            for attr in ('graph', 'graph_load', 'graph_net', 'io_graph'):
                graph = getattr(page, attr, None)
                if hasattr(graph, 'set_interval'):
                    graph.set_interval(val)

    def _setup_sidebar_motion(self):
        """A lightweight image-composited transition; no layout work per tick."""
        self._sidebar_overlay = None

    def _capture_dashboard_layers(self, root):
        """Grab the visible dashboard tiles separately from their backdrop.

        The underlying DashboardBoard uses absolute child positioning, so
        temporarily hiding its tiles does not modify the grid geometry.
        Qt's QPixmap.grab() is called only at transition endpoints.
        """
        overview = self.pages[0][1]
        if self.stack.currentIndex() != 0 or not hasattr(overview, 'board'):
            return root.grab(), {}, None
        scroll = self.stack.widget(0)
        viewport = scroll.viewport()
        view_rect = QRect(viewport.mapTo(root, QPoint(0, 0)), viewport.size())
        captured = {}
        hidden = []
        for key, tile in overview.board.tiles.items():
            if tile.isVisible() and tile.geometry().isValid():
                r = QRect(tile.mapTo(root, QPoint(0, 0)), tile.size())
                if not r.intersects(view_rect):
                    continue
                captured[key] = (r, tile.grab())
                hidden.append(tile)
        try:
            for tile in hidden:
                tile.hide()
            frame = root.grab()
        finally:
            for tile in hidden:
                tile.show()
        return frame, captured, view_rect

    def _sidebar_visual_layers(self):
        """Capture moving sidebar children individually without affecting Qt layouts.

        Opacity effects prevent their pixels appearing in the *background*
        snapshot, but never hide widgets or remove them from a layout. This is
        performed only at the two endpoint states, never on animation frames.
        """
        side = self.sidebar
        def sprite(widget):
            if not widget.isVisibleTo(side):
                return None
            return (QRect(widget.mapTo(side, QPoint(0, 0)), widget.size()), widget.grab())
        nav = {i: sprite(btn) for i, btn in enumerate(self.nav_buttons)}
        brand = sprite(self.sidebar_brand)
        language = sprite(self.lang_host)
        version = sprite(self.sidebar_version)
        viewport = QRect(self.nav_scroll.viewport().mapTo(side, QPoint(0,0)),
                         self.nav_scroll.viewport().size())
        # Render ONLY the sidebar's own background, not its children. Avoid
        # attaching 14 QGraphicsOpacityEffects twice per click (slow on HiDPI).
        from PySide6.QtGui import QPixmap, QPainter
        dpr = side.devicePixelRatioF()
        background = QPixmap(round(side.width()*dpr), round(side.height()*dpr))
        background.setDevicePixelRatio(dpr)
        background.fill(Qt.transparent)
        painter = QPainter(background)
        side.render(painter, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawWindowBackground)
        painter.end()
        return dict(background=background, nav=nav, brand=brand,
                    language=language, version=version, viewport=viewport)

    def toggle_sidebar(self):
        """Move the sidebar seam smoothly, without animating the live widget tree.

        The former effect blended two *whole windows* on every animation frame,
        making widgets appear twice and the arrow jump. We now capture the
        layout at each endpoint *without* the arrow, then animate the sidebar,
        the content and the seam-docked arrow as separate layers. Actual Qt
        layouts are recalculated once when the state changes, not every frame.
        """
        # A second click during an unfinished transition used to remove the
        # live overlay and reveal a different layout in a single frame.
        # Complete the current glide before accepting another request.
        if self._sidebar_motion is not None:
            return

        if not motion.enabled():
            self._sidebar_collapsed = not self._sidebar_collapsed
            settings.set('sidebar_collapsed', self._sidebar_collapsed)
            self._apply_sidebar_state()
            self.centralWidget().layout().activate()
            overview = self.pages[0][1]
            if hasattr(overview, 'board'):
                overview.board.refresh_geometry(animate=False)
            return

        root = self.centralWidget()
        toggle = self.collapse_button
        old_width = self.sidebar.width()
        visible = root.isVisible()
        # Guard the FIRST rendered frame, before even hiding the arrow. Qt's
        # processEvents() is needed to settle QScrollArea, but must NEVER expose
        # the temporarily rebuilt destination layout to the compositor.
        freeze = SidebarFreeze(root, root.grab()) if visible else None
        old_arrow = toggle.grab()
        before = after = None
        before_side = after_side = None
        old_tiles = new_tiles = {}
        old_viewport = new_viewport = None
        new_arrow = None
        try:
            if visible:
                # QWidget.grab is synchronous. Briefly remove our guard only
                # while rendering offscreen, never while pumping Qt events.
                toggle.hide()
                freeze.hide()
                try:
                    before, old_tiles, old_viewport = self._capture_dashboard_layers(root)
                    before_side = self._sidebar_visual_layers()
                finally:
                    freeze.show()
                    freeze.raise_()
                    toggle.show()

            self._sidebar_collapsed = not self._sidebar_collapsed
            settings.set('sidebar_collapsed', self._sidebar_collapsed)
            self._sidebar_progress = 1.0 if self._sidebar_collapsed else 0.0
            self._apply_sidebar_state()
            root.layout().activate()
            overview = self.pages[0][1]
            if hasattr(overview, 'board'):
                overview.board._resize_coalesce.stop()
                overview.board.refresh_geometry(animate=False)
            # The first-frame guard remains visible throughout *all* queued
            # paint, resize and child-show events raised by the state change.
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
            root.layout().activate()
            if hasattr(overview, 'board'):
                overview.board._resize_coalesce.stop()
                overview.board.refresh_geometry(animate=False)
            new_width = self.sidebar.width()
            toggle.show()
            toggle.raise_()
            new_arrow = toggle.grab()

            if visible:
                toggle.hide()
                freeze.hide()
                try:
                    after, new_tiles, new_viewport = self._capture_dashboard_layers(root)
                    after_side = self._sidebar_visual_layers()
                finally:
                    freeze.show()
                    freeze.raise_()
                    toggle.show()

            if (before is None or after is None or before.isNull() or
                    after.isNull() or new_width == old_width):
                return

            overlay = SidebarTransition(root, before, after, old_width, new_width,
                                        old_arrow, new_arrow, old_tiles, new_tiles,
                                        old_viewport, new_viewport,
                                        before_side=before_side, after_side=after_side)
            self._sidebar_overlay = overlay
            # A single, opaque overlay now owns the whole visible transition;
            # expose the real destination widgets only after the final frame.
            overlay.raise_()
        finally:
            if freeze is not None:
                freeze.hide()
                freeze.deleteLater()
            toggle.show()
            # Only raise the real arrow if there is no animation overlay.
            # During the animation its ONE snapshot moves with the seam.
            if self._sidebar_overlay is None:
                toggle.raise_()

        # Keep endpoint snapshots untouched until the animation finishes.
        self.collapse_button.setEnabled(False)
        overlay.resized.connect(self._sidebar_finish)
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        # Cache-only rendering during the glide, not 9 freshly re-sized glass
        # panels and charts per animation frame. Keep a single easing curve.
        animation.setDuration(motion.duration(300))
        animation.setEasingCurve(QEasingCurve.InOutCubic)
        animation.valueChanged.connect(overlay.set_progress)
        animation.finished.connect(self._sidebar_finish)
        self._sidebar_motion = animation
        animation.start()

    def _sidebar_finish(self):
        overlay = self._sidebar_overlay
        self._sidebar_overlay = None
        if overlay is not None:
            overlay.hide()
            overlay.deleteLater()
        animation = self._sidebar_motion
        self._sidebar_motion = None
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        # Keep the real, accessible button in the topmost paint layer.
        # The latest sample is redrawn now, not while a cached frame is moving.
        if self.last_sample is not None:
            # The compositor already has a settled destination frame. Refresh
            # only the visible page; repainting all hidden pages caused a burst
            # of expensive glass/sensor paints just as the transition ended.
            self.stack.currentWidget().update()
        self.collapse_button.setEnabled(True)
        if self.last_sample is not None:
            self._refresh_visible_page()
        self.collapse_button.show()
        self.collapse_button.raise_()

    def _apply_sidebar_state(self):
        """Only for initial construction: no animation before the window shows."""
        from .signature_designs import active
        if active() and hasattr(self,'design_shell'):
            return
        compact = self._sidebar_collapsed
        self.sidebar_layout.setContentsMargins(*( (8,55,8,12) if compact else (16,21,16,16) ))
        self.sidebar_brand.setVisible(not compact)
        # Original full-size DE/EN buttons: never squeeze them into a 74px rail.
        self.lang_host.setVisible(not compact)
        self.sidebar_version.setVisible(not compact)
        self.nav_host.layout().setContentsMargins(1,2,1 if compact else 3,2)
        for btn in self.nav_buttons:btn.set_compact(compact)
        self.sidebar.setFixedWidth(74 if compact else 250)
        self.collapse_button.set_collapsed(compact)
        self.sidebar._position_toggle()

    @staticmethod
    def _is_scrolling_card(widget):
        """Qt drop shadows require expensive offscreen redraws on each scroll."""
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return True
            parent = parent.parentWidget()
        return False

    def _optimize_scroll_surfaces(self):
        """Keep frosted cards but avoid offscreen effects within scrolling pages."""
        for card in self.findChildren(GlassSurface):
            fx = card.graphicsEffect()
            if isinstance(fx, QGraphicsDropShadowEffect):
                fx.setEnabled(not self._is_scrolling_card(card)
                              and theme.mode() != 'minimal')

    def _refresh_visible_page(self):
        if self.last_sample is None or not self.pages:
            return
        # While hidden in the tray, keep collecting data and checking alarms,
        # but skip all widget/chart paints until the window is shown again.
        if not self.isVisible() or self.isMinimized():
            return
        page = self.pages[self.stack.currentIndex()][1]
        try:
            for chart in page.findChildren(ChartPanel):
                chart.set_timeline(self.hist['time'])
            page.refresh(self.last_sample, self.hist)
            self._last_refresh_error = None
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            signature = (self.stack.currentIndex(), type(exc), str(exc))
            if signature != self._last_refresh_error:
                log_exception(type(exc), exc, exc.__traceback__)
                self._last_refresh_error = signature

    @staticmethod
    def _appearance_signature():
        return tuple(settings.get_many(dict(theme=theme.DEFAULT_THEME, accent='#4f8cff',
            background_style='theme_default', custom_background_selected='',
            custom_background_fit='cover', ultra_eco=False)).values())

    def apply_appearance(self):
        """Restyle in-place; keep selected page, benchmark worker and scroll intact."""
        from . import design_catalog
        design_catalog.remember()
        next_key = self._appearance_signature()
        before = None
        if (self.isVisible() and not self.isMinimized() and motion.duration(300)
                and getattr(self, '_appearance_key', next_key) != next_key):
            before = self.grab()
        overlay = getattr(self, '_appearance_overlay', None)
        changed = getattr(self, '_appearance_key', next_key) != next_key
        if overlay is not None and (changed or not motion.duration(300) or not self.isVisible()):
            overlay.finish()
            self._appearance_overlay = None
        theme.set_mode(eco.theme_name())
        user_accent = settings.get('accent', '#4f8cff')
        theme.set_accent('#4f8cff' if eco.enabled() else resolve_accent(user_accent, self.distro['color']))
        stylesheet = theme.stylesheet()
        if QApplication.instance().styleSheet() != stylesheet:
            QApplication.instance().setStyleSheet(stylesheet)
        self.design_shell.sync()
        self.brand_mark.sync_theme()
        self.pulse_core.sync_theme()
        current_icon = app_icon()
        QApplication.instance().setWindowIcon(current_icon)
        self.setWindowIcon(current_icon)
        if not self._tray_glow.active:
            self._tray.setIcon(current_icon)
        self._sync_glow()  # Stop/restart all logo, sidebar and tray pulses.
        self._tray_glow.refresh()
        self.refresh_mini_hud()
        sync_installed_icon()
        minimal = theme.mode() == 'minimal'
        self.centralWidget().set_low_power(minimal)
        # _build may call apply_appearance before Sampler has been created.
        if hasattr(self, 'sampler'):
            self.set_interval(eco.interval())
        # Disabling graphics effects (rather than removing them) retains the
        # original glass shadows when switching back to Glass/Dark/Light.
        for card in self.findChildren(GlassSurface):
            fx = card.graphicsEffect()
            if isinstance(fx, QGraphicsDropShadowEffect):
                fx.setEnabled(not minimal and not self._is_scrolling_card(card))
        for gauge in self.findChildren(Gauge):
            if minimal:
                gauge._animate.stop()
                gauge._render_value = gauge.value
        for nav in self.nav_buttons:
            if minimal:
                nav._timer.stop()
            elif nav.glow and nav.isVisible():
                nav._timer.start()
        for graph in self.findChildren(ChartPanel):
            graph.retheme()
        disk = next((p for name, p in self.pages if name == 'Laufwerke'), None)
        if disk is not None and hasattr(disk, 'refresh_appearance'):
            disk.refresh_appearance()
        # Keep the linked credit in sync with the active theme accent.
        info_page = next((page for title, page in self.pages if title == 'Info'), None)
        if info_page is not None:
            info_page.support_credit.retranslate()
            info_page.author_credit.retranslate()
        # QPainter-based glass/rings/navigation read colors directly from theme.
        self.centralWidget().update()
        for widget in self.centralWidget().findChildren(QWidget):
            widget.update()
        pref = next((page for title, page in self.pages if title == 'Einstellungen'), None)
        if pref is not None and hasattr(pref, 'refresh_appearance'):
            pref.refresh_appearance()
        self._appearance_key = next_key
        if before is not None and motion.duration(300):
            from .appearance_transition import AppearanceTransition
            self.layout().activate()
            scene = self.centralWidget()
            if hasattr(scene, 'finish_background_frame'):
                scene.finish_background_frame()
            after = self.grab()
            overlay = AppearanceTransition(self, before, after)
            self._appearance_overlay = overlay
            def clear_overlay():
                if self._appearance_overlay is overlay:
                    self._appearance_overlay = None
            overlay.finished.connect(clear_overlay)
            overlay.start()

    def _network_alert(self,title,message):
        self.statusBar().showMessage(title+' · '+message,16000)
        if self._tray is not None:
            self._tray.showMessage(title,message,QSystemTrayIcon.Warning,8000)

    def _check_alerts(self, sample):
        preferences = settings.get_many(dict(
            cpu_temp=90, gpu_temp=90, ram_usage=90, disk_usage=95,
            alerts_enabled=False))
        limits = {key: preferences[key] for key in (
            'cpu_temp', 'gpu_temp', 'ram_usage', 'disk_usage')}
        friendly = {'cpu_temp': tr('CPU-Temperatur'), 'gpu_temp': tr('GPU-Temperatur'),
                    'ram_usage': tr('RAM-Auslastung'), 'disk_usage': tr('Systemlaufwerk-Belegung')}
        for warning in self._alerts.update(readings_from_sample(sample), limits,
                                           preferences['alerts_enabled']):
            from . import events
            events.record('warning', metric=warning.metric, value=warning.value, limit=warning.limit)
            msg = f'{friendly[warning.metric]}: {warning.value:.0f}{warning.unit}  (≥ {warning.limit:.0f}{warning.unit})'
            self.statusBar().showMessage(tr('Grenzwert überschritten') + ' · ' + msg, 16000)
            if self._tray is not None:
                self._tray.showMessage(APP_NAME + ' · ' + tr('Warnung'), msg,
                                       QSystemTrayIcon.Warning, 8000)


    def _mini_hud_closed(self):
        self._tray_hud_action.blockSignals(True)
        self._tray_hud_action.setChecked(False)
        self._tray_hud_action.blockSignals(False)
        pref = next((p for title, p in self.pages if title == 'Einstellungen'), None)
        if pref is not None:
            pref.sync_hud_controls()

    def set_mini_hud_enabled(self, enabled):
        enabled = bool(enabled)
        settings.set('mini_hud_enabled', enabled)
        self._tray_hud_action.blockSignals(True)
        self._tray_hud_action.setChecked(enabled)
        self._tray_hud_action.blockSignals(False)
        if enabled:
            self._mini_hud.apply_settings()
            self._mini_hud.show()
            self._mini_hud.update_sample(self.last_sample)
        else:
            self._mini_hud.hide()
        pref = next((p for title, p in self.pages if title == 'Einstellungen'), None)
        if pref is not None:
            pref.sync_hud_controls()

    def refresh_mini_hud(self):
        hud = self._mini_hud
        if hud is not None:
            visible = hud.isVisible()
            hud.apply_settings()
            if visible:
                hud.show()
                hud.update_sample(self.last_sample)



    def reset_session_extrema(self):
        """Reset displayed minimum/maximum values without touching hardware."""
        self._extrema.reset()
        if self.last_sample is not None:
            self.last_sample["session_extrema"] = self._extrema.snapshot()
            self._refresh_visible_page()

    def on_sample(self, d):
        if self._shutdown_pending:return
        import time
        started = time.perf_counter()
        d["session_extrema"] = self._extrema.update(d)
        disk_page = next((p for title, p in self.pages if title == 'Laufwerke'), None)
        if disk_page is not None and disk_page._smart_loaded:
            d['smart_reports'] = list(disk_page.smart_card._reports)
        self._blackbox.ingest(d)
        if self._mini_hud.isVisible():
            self._mini_hud.update_sample(d)
        self.last_sample = d
        if not d.get('_gap_before'):
            self._check_alerts(d)
        if self._tray is not None:
            self._tray.setToolTip(tray_tooltip(d))
        # Native, lightweight branding animation driven by the real CPU sample.
        cpu_pct = d.get("cpu", {}).get("usage", 0.0)
        if not eco.enabled():
            self.pulse_core.set_cpu_load(cpu_pct)
        h = self.hist
        stamp = d.get('timestamp', time.time())
        if d.get('_gap_before') and h['time']:
            missing = min(stamp-.001, h['time'][-1]+max(1, self.sampler.interval))
            for key, history in h.items():
                history.append(missing if key == 'time' else None)
        h['time'].append(stamp)
        g = d["gpus"][0] if d["gpus"] else None
        h["cpu"].append(d["cpu"]["usage"])
        h["ram"].append(d["ram"]["percent"])
        h["gpu"].append(g.get("usage") if g else None)
        h["cpu_temp"].append(d.get("cpu", {}).get("temp"))
        h['cpu_clock'].append(d['cpu'].get('freq'))
        h["net_down"].append(d["net"]["down"])
        h["net_up"].append(d["net"]["up"])
        h['io_read'].append(d['io']['read'])
        h['io_write'].append(d['io']['write'])
        self.gpu_history.update(d['gpus'],gap=bool(d.get('_gap_before')))
        # History is populated above; repaint only the selected page.
        # Switching pages immediately uses the latest sample and all history.
        if self._sidebar_motion is None:
            self._refresh_visible_page()
        self.last_render_ms = (time.perf_counter() - started) * 1000

    def _on_tray_activated(self, reason):
        """Plasma uses Trigger for a single left click, Context for right click."""
        if reason == QSystemTrayIcon.Trigger:
            self._tray_click_timer.start()
        elif reason == QSystemTrayIcon.DoubleClick:
            self._tray_click_timer.stop()
            self.show_from_tray()
        # Context is handled by QSystemTrayIcon's persistent QMenu itself.



    def _toggle_tray_window(self):
        if self.isVisible() and not self.isMinimized():
            self._hide_to_tray()
        else:
            self.show_from_tray()

    def _hide_to_tray(self):
        """Only hide when a real system tray is available to reopen the app."""
        if not (self._tray and self._tray.isVisible() and
                QSystemTrayIcon.isSystemTrayAvailable()):
            return False
        self._tray_was_maximized = self.isMaximized()
        self.hide()
        return True

    def show_from_tray(self):
        self._tray_click_timer.stop()
        if self._tray_was_maximized or self.isMaximized():
            self.showMaximized()
        else:
            self.showNormal()
        if eco.enabled():
            self._refresh_visible_page()  # Bring cached data up to date on restore.
        self.raise_()
        self.activateWindow()

    def restart_for_renderer(self, commit=None):
        """Defer reset commits until workers have stopped and a restart is safe."""
        if getattr(self.manager,'pending_restart',False):
            if commit is not None:return False
            self.manager._restart()
            return True
        if self.restart_requested:
            return True
        if getattr(self.manager, 'status', '') == 'installing':
            return False
        for _title, page in self.pages:
            worker = (page.benchmark.thread if isinstance(page, DiskPage) else
                      page.worker if isinstance(page, DiagnosticCenter) else None)
            if worker is not None and worker.isRunning():
                return False
        self._tray_click_timer.stop()
        self._force_quit = True
        self.restart_requested = True
        self._reset_commit = commit
        self._shutdown_not_before = time.monotonic()+motion.duration(260)/1000 if commit else 0
        if self.close() or self._close_retry.isActive():
            return True
        self.restart_requested = self._force_quit = False
        self._reset_commit = None
        return False

    def _restart_after_update(self):
        # AppImages have an external atomic activation helper. ZIP editions
        # restart through the launcher only after this process exits cleanly.
        self.restart_requested = not bool(getattr(self.manager, 'pending_path', None))
        self._force_quit = True
        self.close()

    def _cancel_shutdown(self,message):
        self._shutdown_pending = self.restart_requested = self._force_quit = False
        self.centralWidget().setEnabled(True)
        if not self.sampler.isRunning():self.sampler.start()
        for _title,page in self.pages:
            if isinstance(page,NetworkPage):page.watcher.resume_after_shutdown()
        self.manager.resume_after_shutdown()
        from .lifecycle import resume_product_workers
        resume_product_workers()
        for _title,page in self.pages:
            if isinstance(page,PreferencesPage):page._refresh_restore_button()
        self.statusBar().showMessage(tr(message),8000)

    def quit_from_tray(self):
        self._tray_click_timer.stop()
        self._force_quit = True
        if not self.close() and not self._close_retry.isActive():
            # An active benchmark may refuse to close until its worker stops.
            self._force_quit = False

    def _inform_missing_tray(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, APP_NAME, tr('Die KDE-Systemleiste ist momentan nicht verfügbar. Vitalux bleibt geöffnet. Um es vollständig zu beenden, deaktiviere die Tray-Funktion unter Einstellungen.'))


    def closeEvent(self, event):
        if not self._force_quit and settings.get('close_to_tray', True):
            if self._hide_to_tray():
                event.ignore()
                return
            # On systems without an available system tray, do not silently
            # terminate the process when the user expects X to hide the app.
            # Remain accessible until the user changes the setting or a host
            # is available. Never hide a window that cannot be reopened.
            event.ignore()
            if not getattr(self, '_tray_missing_notice', False):
                self._tray_missing_notice = True
                QTimer.singleShot(0, self._inform_missing_tray)
            return
        if not self._shutdown_pending:
            # Save edits before a reset transaction is committed, never after it.
            if self.pages and hasattr(self.pages[0][1], 'board') and self.pages[0][1].board.editing:
                self.pages[0][1].save_editor()
            self._shutdown_pending = True
            self.sampler.stop()
            self.manager.shutdown()
            for _title, page in self.pages:
                if isinstance(page,NetworkPage):
                    page.shutdown()
                if isinstance(page, DiskPage):
                    worker = page.benchmark.thread
                    if worker is not None and worker.isRunning():
                        worker.stop()
            self.centralWidget().setEnabled(False)
            self.statusBar().showMessage(tr('Vitalux wird neu gestartet …' if self.restart_requested else 'Vitalux wird beendet …'))
        workers_running = any(worker.isRunning() for worker in self.findChildren(QThread))
        network_ready=all(page.shutdown() for _title,page in self.pages if isinstance(page,NetworkPage))
        manager_ready = self.manager.shutdown() is not False
        from .lifecycle import stop_product_workers
        products_ready=stop_product_workers()
        if workers_running or not network_ready or not manager_ready or not products_ready or time.monotonic() < self._shutdown_not_before:
            event.ignore()
            self._close_retry.start(25)
            return
        self._close_retry.stop()
        if self._reset_commit is not None:
            commit, self._reset_commit = self._reset_commit, None
            try:
                committed = commit() is not False
            except Exception as exc:
                log_exception(type(exc), exc, exc.__traceback__)
                committed = False
            if not committed:
                event.ignore()
                self._cancel_shutdown('Einstellungen konnten nicht zurückgesetzt werden.')
                return
        if (getattr(self.manager,'_restart_requested',False)
                and not self.manager.prepare_exit()):
            event.ignore()
            self._cancel_shutdown('Neustart wird automatisch erneut vorbereitet …' if self.manager.restart_retrying
                                  else 'Neustart fehlgeschlagen. Bitte unter Updates erneut versuchen.')
            return
        if self.restart_requested:
            try:
                from .updater import queue_appimage_restart
                queue_appimage_restart()
            except (OSError,RuntimeError):
                event.ignore()
                self._cancel_shutdown('Neustart fehlgeschlagen. Bitte unter Updates erneut versuchen.')
                return
        from .lifecycle import stop_gui_activity
        stop_gui_activity(self)
        self._tray_click_timer.stop()
        self._tray_glow.stop()
        self._mini_hud.hide()
        if self._tray is not None:
            self._tray.hide()
        self.manager.shutdown()
        super().closeEvent(event)
        # quitOnLastWindowClosed(False) keeps the event loop alive when hidden
        # in the tray. An intentional close must end the process explicitly.
        if event.isAccepted():
            QTimer.singleShot(0, QApplication.instance().quit)
