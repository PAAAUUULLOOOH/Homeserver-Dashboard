"""Vitalux Diagnostic Center: explicit, read-only, asynchronous Linux diagnostics."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTabWidget, QFileDialog, QComboBox)
from .ui_locale import QPushButton, QCheckBox, QMessageBox
from .widgets import Card, label
from . import diagnostic_engine as engine, settings, events
from .i18n import tr
from .pages import Page


class DiagnosticWorker(QThread):
    completed = Signal(str, str)

    def __init__(self, section, sample, parent=None):
        super().__init__(parent)
        self.section, self.sample = section, sample

    def run(self):
        try:
            result = engine.run(self.section, self.sample)
        except Exception as exc:
            result = f'Diagnose nicht verfügbar: {type(exc).__name__}: {exc}'
        self.completed.emit(self.section, result)


class DiagnosticCenter(Page):
    EMPTY = 'Keine Untersuchung durchgeführt.\nDie Auswertung wird auf Wunsch gestartet.'
    SECTIONS = (
        ('all', 'Gesamtcheck', 'Alle lokalen Diagnosen auf einmal (ohne externen Verbindungstest).'),
        ('system', 'Systemcheck', 'Aktuelle Sensorwerte und konfigurierbare Warnschwellen.'),
        ('displays', 'DisplayDoctor', 'Display-Verbindungen, Modi, Wayland und KScreen-Auskunft.'),
        ('pcie', 'PCIe Guardian', 'PCIe-GPU-Link, ausgehandelte Geschwindigkeit und Breite.'),
        ('thermal', 'Thermal Compass', 'Temperatursensoren und Abstand zu gesetzten Warnwerten.'),
        ('crashes', 'Crash Investigator', 'Kernel- und Treiberfehler aus dem erreichbaren Systemjournal.'),
        ('network', 'NetworkPulse', 'Schnittstellen und IP-Konfiguration. Verbindungstest nur auf Klick.'),
        ('processes', 'Process Spotlight', 'CPU- und RAM-intensive Prozesse in einer kurzen Stichprobe.'),
        ('compare', 'ChangeRadar', 'Aktuellen Kernel, Desktop, Mesa und Hardware mit eigener Basis vergleichen.'),
        ('blackbox', 'Blackbox', 'Opt-in-Ereignisprotokoll mit Warnwertüberschreitungen.'),
    )

    CATEGORIES = (
        ('quick', 'Schnellcheck'),
        ('hardware', 'Hardwarediagnose'),
        ('system', 'Systemdiagnose'),
        ('reports', 'Berichte'),
    )
    GROUPS = {
        'all': 'quick', 'system': 'quick',
        'displays': 'hardware', 'pcie': 'hardware', 'thermal': 'hardware',
        'crashes': 'system', 'network': 'system', 'processes': 'system',
        'compare': 'history', 'blackbox': 'history',
    }

    def __init__(self):
        super().__init__('Diagnostic Center', 'Systemanalyse, Diagnose und lokale Berichte')
        self.last_sample = None
        self.worker = None
        self._reports = {}
        self.texts = {}
        self._empty_keys = set()
        self.tabs = QTabWidget()
        self.tabs.setObjectName('diagnosticsTabs')
        self.tabs.setMinimumHeight(350)
        self.section_tabs = {}
        self.last_section = 'all'
        intro = Card('Diagnostic Center · Linux-Systemanalyse')
        intro.body.addWidget(label('Gezielte, ausschließlich lesende Hardware- und Systemprüfungen. '
                                   'Die Ergebnisse sind Hinweise, keine automatischen Fehlerursachen. '
                                   'Alle Prüfungen werden erst durch Klick gestartet.', 'muted', wrap=True))
        action_row = QHBoxLayout()
        self.scan_btn = QPushButton('Vollständige Diagnose starten')
        self.scan_btn.setObjectName('primaryBtn')
        self.scan_btn.clicked.connect(lambda: self.start_check('all'))
        action_row.addWidget(self.scan_btn)
        action_row.addStretch()
        intro.body.addLayout(action_row)
        self.status = label('Bereit · bisher keine Diagnose gestartet', 'muted', wrap=True)
        intro.body.addWidget(self.status)
        # Each functional area is a separate card in the vertical page.

        # Unified destination for every export previously in Settings.
        reports_card = QWidget()
        reports_card.body = QVBoxLayout(reports_card)
        reports_card.body.setContentsMargins(0, 0, 0, 0)
        reports_card.body.addWidget(label('Diagnose & Berichte', 'cardTitle'))
        self.report_source = QComboBox()
        self.report_source.setObjectName('diagnosticReportSource')
        self.report_source.setMaximumWidth(360)
        for key, title, _description in self.SECTIONS:
            self.report_source.addItem(tr(title), key)
        reports_card.body.addWidget(label('Diagnose für Export auswählen', 'strong'))
        reports_card.body.addWidget(self.report_source)
        reports_card.body.addWidget(label(
            'Systemberichte, Fehlerdiagnose und die aktuelle Untersuchung als TXT/JSON – '
            'ausschließlich lokal gespeichert, ohne automatischen Upload.', 'muted', wrap=True))
        reports_row = QHBoxLayout()
        self.save_btn = QPushButton('Aktuelle Diagnose exportieren …')
        self.save_btn.setObjectName('ghostBtn')
        self.save_btn.clicked.connect(self.export_report)
        reports_row.addWidget(self.save_btn)
        self.system_report_btn = QPushButton('Systembericht exportieren …')
        self.system_report_btn.setObjectName('ghostBtn')
        self.system_report_btn.clicked.connect(self.export_system_report)
        reports_row.addWidget(self.system_report_btn)
        self.error_report_btn = QPushButton('Fehlerdiagnose exportieren …')
        self.error_report_btn.setObjectName('ghostBtn')
        self.error_report_btn.clicked.connect(self.export_error_report)
        reports_row.addWidget(self.error_report_btn)
        reports_row.addStretch(1)
        reports_card.body.addLayout(reports_row)
        # Reports remain after the diagnostic results and performance tools.

        for key, title, description in self.SECTIONS:
            pane = QWidget()
            layout = QVBoxLayout(pane)
            layout.setContentsMargins(6, 12, 6, 6)
            layout.setSpacing(10)
            explanation = label(description, 'muted', wrap=True)
            layout.addWidget(explanation)
            if key not in ('all', 'blackbox'):
                line = QHBoxLayout()
                go = QPushButton('Prüfung starten' if key != 'compare' else 'Mit gespeichertem Stand vergleichen')
                go.setObjectName('ghostBtn')
                go.clicked.connect(lambda _=False, k=key: self.start_check(k))
                line.addWidget(go)
                if key == 'network':
                    probe = QPushButton('Externen Ping ausdrücklich starten')
                    probe.setObjectName('ghostBtn')
                    probe.setToolTip('Sendet drei ICMP-Echoanfragen an 1.1.1.1; keine Verbindung ohne Klick.')
                    probe.clicked.connect(lambda: self.start_check('ping'))
                    line.addWidget(probe)
                if key == 'compare':
                    baseline = QPushButton('Aktuellen Stand merken')
                    baseline.setObjectName('ghostBtn')
                    baseline.clicked.connect(self.save_baseline)
                    line.addWidget(baseline)
                line.addStretch()
                layout.addLayout(line)
            if key == 'blackbox':
                self.blackbox_toggle = QCheckBox('Blackbox-Ereignisaufzeichnung aktivieren')
                self.blackbox_toggle.setChecked(bool(settings.get('diag_blackbox_enabled', False)))
                self.blackbox_toggle.toggled.connect(self.toggle_blackbox)
                layout.addWidget(self.blackbox_toggle)
                buttons = QHBoxLayout()
                refresh = QPushButton('Ereignisse anzeigen')
                refresh.clicked.connect(lambda: self.start_check('blackbox'))
                buttons.addWidget(refresh)
                clear = QPushButton('Aufzeichnungen löschen …')
                clear.clicked.connect(self.clear_blackbox)
                buttons.addWidget(clear)
                buttons.addStretch()
                layout.addLayout(buttons)
            readout = QPlainTextEdit()
            readout.setReadOnly(True)
            readout.setLineWrapMode(QPlainTextEdit.WidgetWidth)
            readout.setObjectName('diagnosticReadout')
            readout.setPlainText(tr(self.EMPTY))
            self._empty_keys.add(key)
            readout.setMinimumHeight(180)
            layout.addWidget(readout, 1)
            self.texts[key] = readout
            self.section_tabs[key] = self.tabs.count()
            self.tabs.addTab(pane, tr(title))
        self.content.addWidget(intro)
        recent = Card('Letzte Ereignisse')
        self.recent_events = label('', 'muted', wrap=True)
        self.recent_events.setTextFormat(Qt.PlainText)
        recent.body.addWidget(self.recent_events)
        self._event_revision = None
        self._refresh_events()
        self.content.addWidget(recent)
        diagnostics_card = Card('Einzeldiagnosen · gezielte Prüfungen')
        diagnostics_card.body.addWidget(label('Wähle eine Prüfung aus; die Ergebnisse erscheinen direkt darunter.', 'muted', wrap=True))
        diagnostics_card.body.addWidget(self.tabs)
        self.content.addWidget(diagnostics_card)
        reports_section = Card('Diagnose & Berichte')
        reports_section.body.addWidget(reports_card)
        reports_section.body.addWidget(label(
            'Berichte werden nur auf ausdrücklichen Klick gespeichert. '
            'Journal- und Prozessdaten können persönliche Informationen enthalten.',
            'muted', wrap=True))
        reports_section.body.addWidget(label(
            'Der externe Ping wird nur über die separate Schaltfläche gestartet.',
            'muted', wrap=True))
        self.content.addWidget(reports_section)

    def refresh(self, data, _hist):
        self.last_sample = data
        self._refresh_events()

    def _refresh_events(self):
        revision, rows = events.snapshot()
        if revision == self._event_revision:return
        self._event_revision = revision
        self.recent_events.setText('\n'.join(events.timestamp(row)+'  ·  '+events.describe(row)
                                             for row in rows) or tr('Noch keine Ereignisse'))

    def select_area(self, category, section=None):
        """Open an existing diagnostic tab without extra category buttons."""
        if section in self.section_tabs:
            self.tabs.setCurrentIndex(self.section_tabs[section])
            self.last_section = section

    def start_check(self, section):
        if self.worker is not None and self.worker.isRunning():
            self.status.setText('Eine Diagnose läuft bereits. Bitte kurz warten.')
            return
        actual = 'network' if section == 'ping' else section
        self.status.setText(tr('Diagnose läuft: {}').format(tr(dict((key, title) for key, title, _ in self.SECTIONS).get(actual, actual))))
        self.scan_btn.setEnabled(False)
        self.worker = DiagnosticWorker(section, self.last_sample or {}, self)
        self.worker.completed.connect(self._complete)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _complete(self, section, result):
        key = 'network' if section == 'ping' else section
        self._reports[key] = result
        self._empty_keys.discard(key)
        self.texts[key].setPlainText(result)
        self.status.setText(tr('Abgeschlossen · {} · {}').format(datetime.now().strftime('%H:%M:%S'),
                            tr(dict((a,b) for a,b,_ in self.SECTIONS).get(key,key))))
        self.scan_btn.setEnabled(True)
        self.last_section = key
        self.report_source.setCurrentIndex(self.report_source.findData(key))
        self.select_area(self.GROUPS.get(key, 'quick'), key)
        # QThread is deleted after its finished signal, never during execution.
        self.worker = None

    def toggle_blackbox(self, on):
        self._empty_keys.discard('blackbox')
        settings.set('diag_blackbox_enabled', bool(on))
        self.texts['blackbox'].setPlainText(
            'Blackbox aktiviert. Neue Warnwert-Übergänge werden lokal aufgezeichnet.' if on else
            'Blackbox deaktiviert. Bereits gespeicherte Daten bleiben bis zum Löschen erhalten.')

    def save_baseline(self):
        if self.worker and self.worker.isRunning():
            return
        self._empty_keys.discard('compare')
        try:
            text = engine.baseline_save()
        except (OSError, ValueError) as exc:
            text = f'Vergleichsbasis konnte nicht gespeichert werden: {exc}'
        self.texts['compare'].setPlainText(text)
        self.select_area('history', 'compare')

    def clear_blackbox(self):
        answer = QMessageBox.question(self, 'Vitalux Blackbox', 'Alle gespeicherten Blackbox-Ereignisse lokal löschen?',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._empty_keys.discard('blackbox')
        self.texts['blackbox'].setPlainText(engine.blackbox_clear())

    def export_report(self):
        key = self.report_source.currentData() or self.last_section
        content = self._reports.get(key)
        if not content:
            content = self.texts[key].toPlainText()
        if not content or key in self._empty_keys:
            QMessageBox.information(self, 'Vitalux', 'Bitte zuerst eine Diagnose durchführen.')
            return
        path, chosen = QFileDialog.getSaveFileName(self, 'Diagnosebericht speichern',
            f'Vitalux-Diagnose-{datetime.now().strftime("%Y%m%d-%H%M%S")}.txt',
            'Textbericht (*.txt);;JSON-Bericht (*.json)')
        if not path:
            return
        try:
            if path.lower().endswith('.json') or 'JSON' in chosen:
                if not path.lower().endswith('.json'):
                    path += '.json'
                data = {'source':'Vitalux Diagnostic Center', 'created_at':engine.now(),
                        'section':key, 'text':content}
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            else:
                if not path.lower().endswith('.txt'):
                    path += '.txt'
                Path(path).write_text(content + '\n', encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self, 'Vitalux', f'Bericht konnte nicht gespeichert werden: {exc}')

    def export_system_report(self):
        """Export the existing TXT/JSON system snapshot; never upload it."""
        from . import __version__
        from .monitoring import report_data, write_report
        from .sensors import system_static
        from .ui_locale import QMessageBox
        if not self.last_sample:
            QMessageBox.information(self, 'Vitalux', tr('Warte auf die erste Messung.'))
            return
        path, chosen = QFileDialog.getSaveFileName(
            self, tr('Systembericht speichern'),
            f'Vitalux-Bericht-{datetime.now():%Y%m%d-%H%M%S}.txt',
            'Text (*.txt);;JSON (*.json)')
        if not path:
            return
        if not path.lower().endswith(('.json', '.txt')):
            path += '.json' if 'JSON' in chosen else '.txt'
        sample = self.last_sample
        report = report_data(sample, system_static(), __version__, sample.get('session_extrema'))
        try:
            write_report(path, report)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Vitalux', tr('Export fehlgeschlagen: {}').format(exc))
        else:
            QMessageBox.information(self, 'Vitalux', tr('Systembericht gespeichert.'))

    def export_error_report(self):
        """Explicit local export of existing versioned application errors."""
        from .diagnostics import export_report
        path, _chosen = QFileDialog.getSaveFileName(
            self, tr('Fehlerbericht speichern'),
            f'Vitalux-Diagnose-{datetime.now():%Y%m%d-%H%M%S}.json',
            'JSON (*.json)')
        if not path:
            return
        try:
            export_report(path, include_errors=True, sample=self.last_sample)
        except OSError as exc:
            QMessageBox.warning(self, 'Vitalux', f'Export fehlgeschlagen: {exc}')
        else:
            QMessageBox.information(self, 'Vitalux', tr('Fehlerbericht gespeichert.'))

    def retranslate(self):
        for key in self._empty_keys:self.texts[key].setPlainText(tr(self.EMPTY))
        self._event_revision = None
        self._refresh_events()
        for key, title, _description in self.SECTIONS:
            self.tabs.setTabText(self.section_tabs[key], tr(title))
            position = self.report_source.findData(key)
            if position >= 0:
                self.report_source.setItemText(position, tr(title))
