from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout,QVBoxLayout,QWidget,QButtonGroup

from . import APP_NAME, __version__, changelog, settings, theme, profiles, versions
from .i18n import tr
from .pages import Page
from .ui_locale import QLabel, QPushButton, QComboBox
from .update_progress import UpdateProgress
from .changelog_view import ChangelogView
from .widgets import Card, KeyValue, label

AUTHOR_URL = "https://github.com/PAAAUUULLOOOH"
CREDIT_URL = "https://github.com/TimBooH"
CREDIT_TEXT = "Danke an: TimBooH für die Unterstützung bei der Integration eigener Hintergrundbilder und der Grafikausgabe (OpenGL/CPU-Rendering)."

STATUS_TEXT = {
    'preview': 'Lokale Designvorschau · Updates sind deaktiviert.',
    "idle": "Die Updateprüfung startet automatisch.",
    "checking": "Prüfe GitHub auf eine neue Vitalux-Version …",
    "uptodate": "Vitalux ist auf dem neuesten Stand.",
    "available": "Eine neue Vitalux-Version ist verfügbar!",
    "installing": "Update wird heruntergeladen und geprüft …",
    "installed": "Update geprüft. Vitalux wird automatisch neu gestartet.",
}

class UpdatePage(Page):
    """Keep running status, channel browsing and one installation action inline."""

    def __init__(self, manager):
        super().__init__("Updates", "Vitalux automatisch über GitHub aktualisieren")
        self.m=manager
        self._history_choice={};self._history={}
        overview=Card("Vitalux")
        self.current=KeyValue("Installierte Version")
        self.current.set(self._installed_name())
        overview.body.addWidget(self.current)
        self.status=label('', 'strong',wrap=True);self.status.setTextFormat(Qt.PlainText)
        self.check_error=label('', 'muted',wrap=True);self.check_error.setTextFormat(Qt.PlainText)
        overview.body.addWidget(self.status);overview.body.addWidget(self.check_error)
        promotion=QHBoxLayout()
        self.stable_notice=label('Deine Teständerungen sind jetzt in Stable verfügbar.','muted',wrap=True)
        self.return_stable=QPushButton('Stable ansehen',self);self.return_stable.setObjectName('ghostBtn')
        self.return_stable.clicked.connect(lambda:self._channel('stable'))
        promotion.addWidget(self.stable_notice,1);promotion.addWidget(self.return_stable)
        overview.body.addLayout(promotion)
        self.check_button=QPushButton('Nach Updates suchen',self);self.check_button.setObjectName('ghostBtn')
        self.check_button.clicked.connect(self.m.check)
        overview.body.addWidget(self.check_button,0,Qt.AlignLeft)
        self.checked_at=label('', 'muted',wrap=True);overview.body.addWidget(self.checked_at)
        self.content.addWidget(overview)

        self.channel_card=Card('Updatekanäle')
        self.channel_group=QButtonGroup(self);self.channel_buttons={}
        row=QHBoxLayout()
        for key,title in (('stable','Stable'),('unstable','Unstable')):
            button=QPushButton(title,self);button.setCheckable(True);button.setObjectName('langBtn')
            button.setToolTip('Changelog ansehen; ein Wechsel wird separat gestartet.')
            self.channel_group.addButton(button)
            button.clicked.connect(lambda checked=False,key=key:self._channel(key))
            self.channel_buttons[key]=button;row.addWidget(button)
        row.addStretch(1);self.channel_card.body.addLayout(row)
        self.channel_description=label('', 'muted',wrap=True)
        self.channel_status=label('', 'muted',wrap=True)
        self.channel_card.body.addWidget(self.channel_description)
        self.channel_card.body.addWidget(self.channel_status)

        self.action_panel=QWidget(self)
        actions=QVBoxLayout(self.action_panel);actions.setContentsMargins(0,4,0,0);actions.setSpacing(10)
        self.latest=KeyValue('Zielversion');actions.addWidget(self.latest)
        self.install_button=QPushButton('Jetzt aktualisieren',self);self.install_button.setObjectName('primaryBtn')
        self.install_button.clicked.connect(self.m.install);actions.addWidget(self.install_button,0,Qt.AlignLeft)
        self.progress_bar=UpdateProgress()
        self.phase=label('', 'muted',wrap=True)
        actions.addWidget(self.progress_bar);actions.addWidget(self.phase)
        self.cancel_button=QPushButton('Download abbrechen',self);self.cancel_button.setObjectName('ghostBtn')
        self.cancel_button.clicked.connect(self.m.cancel_install);actions.addWidget(self.cancel_button,0,Qt.AlignLeft)
        self.install_retry=QPushButton('Download erneut versuchen',self);self.install_retry.setObjectName('ghostBtn')
        self.install_retry.clicked.connect(self.m.retry_install);actions.addWidget(self.install_retry,0,Qt.AlignLeft)
        self.restart_hint=label('Hintergrundaufgaben werden beendet. Anschließend startet Vitalux automatisch mit der vorbereiteten Version.','muted',wrap=True)
        actions.addWidget(self.restart_hint)
        self.retry_button=QPushButton('Neustart erneut versuchen',self);self.retry_button.setObjectName('ghostBtn')
        self.retry_button.clicked.connect(self.m.retry_restart)
        actions.addWidget(self.retry_button,0,Qt.AlignLeft)
        self.channel_card.body.addWidget(self.action_panel)

        self.changelog_card=QWidget(self)
        notes=QVBoxLayout(self.changelog_card);notes.setContentsMargins(0,16,0,0);notes.setSpacing(10)
        notes.addWidget(label('CHANGELOG','cardTitle'))
        history_row=QHBoxLayout()
        history_row.addWidget(label('Version','muted'))
        self.history_combo=QComboBox(self.changelog_card)
        self.history_combo.setMinimumWidth(220)
        self.history_combo.setAccessibleName(tr('Versionsverlauf'))
        self.history_combo.currentIndexChanged.connect(self._history_selected)
        history_row.addWidget(self.history_combo);history_row.addStretch(1)
        notes.addLayout(history_row)
        self.changelog_heading=label('', 'strong',wrap=True)
        self.changelog_summary=label('', 'muted',wrap=True)
        self.changelog_details=label('', 'muted',wrap=True)
        self.changelog_details.setTextFormat(Qt.PlainText)
        self.changelog_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for widget in (self.changelog_heading,self.changelog_summary):notes.addWidget(widget)
        self.changelog_scroll=ChangelogView(self.changelog_details,self.changelog_card)
        notes.addWidget(self.changelog_scroll)
        self.channel_card.body.addWidget(self.changelog_card)
        self.content.addWidget(self.channel_card)
        self.m.changed.connect(self.sync);self.m.progress.connect(self._progress)
        self.sync()

    @staticmethod
    def _installed_name():
        return ('Stable' if profiles.installed()=='stable' else 'Unstable')+' · v'+__version__

    def _channel(self,channel):self.m.set_channel(channel)

    def _history_selected(self,index):
        version=self.history_combo.itemData(index)
        if version:self._history_choice[self.m.channel]=version
        self._show_history()

    def _show_history(self):
        version=self.history_combo.currentData()
        self.changelog_heading.setText(('Stable' if self.m.channel=='stable' else 'Unstable')+' · v'+version if version else '')
        body=self._history.get(version,'')
        lines=[]
        for line in body.splitlines():
            if line.startswith('[Changelog '):continue
            line=line.lstrip('#').strip()
            if line.startswith('- '):line='• '+line[2:]
            lines.append(line)
        from .i18n import lang
        self.changelog_scroll.set_notes(
            '\n'.join(lines).strip() or tr('Für diese Version ist noch kein Changelog verfügbar.'),
            (self.m.channel,version,lang()))

    def _sync_history(self,record):
        items=changelog.channel_history(self.m.channel,record)
        self._history=dict(items)
        selected=self._history_choice.get(self.m.channel)
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        for version,_ in items:self.history_combo.addItem('v'+version,version)
        index=self.history_combo.findData(selected)
        self.history_combo.setCurrentIndex(index if index>=0 else 0)
        self.history_combo.blockSignals(False)
        self.history_combo.setEnabled(bool(items))
        self.history_combo.setAccessibleName(tr('Versionsverlauf'))
        self.changelog_summary.setText(tr('Die Versionsauswahl zeigt nur Hinweise und ändert nicht das Installationsziel.'))
        self._show_history()

    def _name(self,channel,record):
        if channel=='stable':return 'Stable · v'+record.get('latest','–')
        if not record or record.get('stale') or not record.get('ok',True) or record.get('stable_verified') is False:
            return tr('Unstable · Verfügbarkeit nicht bestätigt')
        if not record.get('eligible',False):
            version=record.get('stable_version') or self.m.records.get('stable',{}).get('latest','')
            if version and (record.get('same_as_stable',False) or record.get('stable_contains_test',False)):return tr('Keine neuen Updates · Wechsel zu Unstable nicht möglich')
            return tr('Unstable · derzeit kein neuerer Teststand')
        from .versions import parse
        try:base='.'.join(map(str,parse(record.get('latest',''))[0]))
        except ValueError:base=record.get('latest','–')
        return tr('Unstable · Teststand für v{version}').format(version=base)

    def _progress(self,value):
        self.progress_bar.set_value(value)
        text='Paket herunterladen …' if value<80 else 'Paket prüfen …' if value<85 else 'Installation vorbereiten …'
        self.phase.setText(tr('Download wird abgebrochen …' if self.m.cancelling else text))
        self.cancel_button.setVisible(self.m.status=='installing' and value<80)
        self.cancel_button.setEnabled(not self.m.cancelling)

    def retranslate(self):self.sync()

    def _running_status(self):
        m=self.m
        if m.pending_restart or m.status=='installed':
            if m.restart_retrying:return tr('Neustart wird automatisch erneut vorbereitet …')
            return tr('Neustart fehlgeschlagen. Bitte unter Updates erneut versuchen.' if m.error else STATUS_TEXT['installed'])
        if m.status in ('preview','installing') or m.checking:
            return tr(STATUS_TEXT['checking' if m.checking else m.status])
        if m.error and m.error_kind!='check':return tr('Vorgang fehlgeschlagen.')
        running=m.records.get(profiles.installed(),{})
        if not running.get('ok') or running.get('stale'):
            return tr('Prüfung nicht möglich.' if m.error or running.get('error') else STATUS_TEXT['idle'])
        return tr(STATUS_TEXT['available' if m.available else 'uptodate'])

    def sync(self):
        from datetime import datetime
        from .i18n import lang
        m=self.m;record=m.records.get(m.channel,{})
        pending=m.pending_restart or m.status=='installed'
        busy=m.status=='installing'
        for key,button in self.channel_buttons.items():
            button.setChecked(key==m.channel);button.setEnabled(not busy)
        self.current.set(self._installed_name())
        self.check_button.setEnabled(not busy and not m.checking and not pending and m.status!='preview')
        self.status.setText(self._running_status())
        self.check_error.setText(tr('Hinweis: {reason}').format(reason=tr(m.error)) if m.error else '')
        self.check_error.setVisible(bool(self.check_error.text()))
        running=m.records.get(profiles.installed(),{})
        stamp=running.get('checked_at',m.last_checked)
        if stamp:
            pattern='%d.%m.%Y %H:%M' if lang()=='de' else '%Y-%m-%d %H:%M'
            text=tr('Zuletzt geprüft: {time}').format(time=datetime.fromtimestamp(stamp).strftime(pattern))
        else:text=tr('Noch nicht geprüft.')
        if running.get('stale'):text+=' · '+tr('Gespeicherter Stand; offline lesbar.')
        self.checked_at.setText(text)
        automatic=m.automatic_stable_return and m.status=='installing'
        self.stable_notice.setText(tr('Stable enthält alle Teständerungen. Die App wechselt automatisch zu Stable.' if automatic else 'Deine Teständerungen sind jetzt in Stable verfügbar.'))
        self.stable_notice.setVisible((automatic or bool(m.stable_has_test_changes)) and not pending)
        self.return_stable.setVisible(bool(m.stable_has_test_changes) and not pending and not automatic)
        self.channel_description.setText(tr('Stabile Versionen für den täglichen Einsatz.' if m.channel=='stable'
                                           else 'Testversionen mit neuen Änderungen vor dem Stable-Release.'))
        channel_message=''
        if record and (record.get('stale') or not record.get('ok') or record.get('stable_verified') is False):
            channel_message='Verfügbarkeit nicht bestätigt. Gespeicherte Changelogs bleiben lesbar.'
        elif m.channel=='unstable' and record and not record.get('eligible',False):
            channel_message='Derzeit gibt es keinen neueren Unstable-Teststand.'
        elif m.channel=='stable' and m.can_install and not pending:
            try:
                if not versions.has_automatic_restart(record.get('latest','')):
                    channel_message=tr('Dieser Wechsel startet automatisch neu. Stable v{version} verwendet bei späteren Updates noch „Jetzt neu starten“.').format(version=record['latest'])
            except ValueError:
                pass
        self.channel_status.setText(tr(channel_message));self.channel_status.setVisible(bool(channel_message))
        destination=m.pending if pending else record
        target_channel=destination.get('channel',m.channel)
        if pending:destination=dict(destination,latest=destination.get('version',''),eligible=True)
        self.latest.set(self._name(target_channel,destination))
        self.latest.setVisible(pending or busy or m.can_install)
        switching=m.channel!=profiles.installed()
        self.install_button.setText(tr(('Zu Unstable wechseln' if m.channel=='unstable' else 'Zu Stable zurückkehren') if switching else 'Jetzt aktualisieren'))
        show_disabled=(m.channel=='unstable' and not record.get('eligible',False))
        self.install_button.setVisible(not pending and m.can_install)
        self.install_button.setEnabled(m.can_install)
        self.install_button.setStyleSheet(f'QPushButton#primaryBtn:disabled {{ background: {theme.CARD}; color: {theme.MUTED}; border: 1px solid {theme.BORDER}; }}')
        self.install_button.setToolTip(tr('Ein Wechsel ist nur mit einem geprüften, neueren Teststand möglich.') if show_disabled else '')
        self.progress_bar.setVisible(busy);self.phase.setVisible(busy)
        self._progress(m.progress_value)
        retry_install=m.status=='error' and m.error_kind=='install'
        self.install_retry.setVisible(retry_install)
        self.restart_hint.setVisible(pending and not m.error)
        self.retry_button.setVisible(pending and bool(m.error) and m.error_kind=='restart' and not m.restart_retrying)
        self.action_panel.setVisible(pending or busy or m.can_install or show_disabled or retry_install)
        self._sync_history(record)


class AuthorCredit(QLabel):
    """Theme-aware, accessible hyperlink to the developer's profile."""

    def __init__(self):
        super().__init__()
        self.setObjectName('madeBy')
        self.setAlignment(Qt.AlignHCenter)
        self.setTextFormat(Qt.RichText)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
        self.setOpenExternalLinks(True)
        self.retranslate()

    def retranslate(self):
        self.setText(f'Made by <a href="{AUTHOR_URL}" style="color: {theme.accent()}; '
                     f'text-decoration: underline;">PAAAUUULLOOOH</a>')
        self.setAccessibleName('Made by PAAAUUULLOOOH')


class SupportCredit(QLabel):
    """Translated acknowledgement linking only to the fixed GitHub profile."""

    def __init__(self):
        super().__init__()
        self.setObjectName("supportCredit")
        self.setAlignment(Qt.AlignHCenter)
        self.setWordWrap(True)
        self.setTextFormat(Qt.RichText)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
        self.setOpenExternalLinks(True)
        self.retranslate()

    def retranslate(self):
        # Translated content is escaped; only this fixed URL becomes HTML.
        heading, separator, remainder = tr(CREDIT_TEXT).partition(":")
        before, name, after = remainder.partition("TimBooH")
        if not separator or not name:
            raise ValueError("Invalid TimBooH credit translation")
        self.setText(
            f"<b>{escape(heading)}:</b>{escape(before)}"
            f'<a href="{CREDIT_URL}" style="color: {theme.accent()}; '
            f'text-decoration: underline;">TimBooH</a>{escape(after)}'
        )
        self.setAccessibleName(tr(CREDIT_TEXT))


class InfoPage(Page):
    def __init__(self, distro):
        super().__init__("Info", "Über diese App")
        c = Card(hero=True)
        c.body.addSpacing(10)
        self.author_credit = AuthorCredit()
        c.body.addWidget(self.author_credit)
        self.support_credit = SupportCredit()
        c.body.addWidget(self.support_credit)
        c.body.addWidget(label(f"{APP_NAME} {__version__}", "muted", Qt.AlignHCenter))
        c.body.addSpacing(10)
        self.content.addWidget(c)
        help_card = Card("Anleitung und Hilfe")
        help_card.body.addWidget(label(
            "Entdecke Vitalux in einer bebilderten Schritt-für-Schritt-Anleitung mit Pfeilen und Beispielen.",
            "muted", wrap=True))
        self.guide_button = QPushButton("Anleitung öffnen")
        self.guide_button.setObjectName("primaryBtn")
        self.guide_button.setCursor(Qt.PointingHandCursor)
        self.guide_button.clicked.connect(self.open_guide)
        help_card.body.addWidget(self.guide_button)
        self.content.addWidget(help_card)
        d = Card("Details")
        for k, v in (("Version", __version__), ("Erkannte Distribution", distro["name"]),
                     ("Einstellungsdatei", settings.PATH)):
            kv = KeyValue(k)
            kv.set(v)
            d.body.addWidget(kv)
        self.content.addWidget(d)

    def open_guide(self):
        from .guide import GuideDialog
        # Visiting the guide counts as opt-in; do not prompt again on next launch.
        settings.set("guide_intro_choice", "completed")
        dlg = GuideDialog(self.window())
        dlg.exec()
