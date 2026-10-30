"""App traffic, socket details and explicit session network controls."""
from PySide6.QtCore import Qt,Signal,QItemSelectionModel
import ipaddress
from PySide6.QtNetwork import QDnsLookup
from PySide6.QtWidgets import (QAbstractItemView,QHeaderView,QHBoxLayout,QInputDialog,
    QLineEdit,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget)
from . import settings
from .i18n import tr
from .ui_locale import QPushButton
from .widgets import Card,label
from .sensors import fmt_bytes,fmt_rate
from .network_monitor import TrafficLedger,NetworkSampler,HelperClient
from .expandable import ExpandableCard
from .soft_controls import SoftReveal


class NumberItem(QTableWidgetItem):
    def __init__(self,text,value=None):
        super().__init__(text)
        self.setData(Qt.UserRole,-1 if value is None else value)

    def __lt__(self,other):
        return (self.data(Qt.UserRole) or 0)<(other.data(Qt.UserRole) or 0)


class NetworkWatch(QWidget):
    alert=Signal(str,str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.ledger=TrafficLedger()
        self.worker=None
        self.client=HelperClient(self)
        self.client.sample.connect(self._helper_sample)
        self.client.state.connect(self._helper_state)
        self.client.error.connect(self._error)
        self.client.rules.connect(self._rules_changed)
        self.client.connection_rules.connect(self._connection_rules_changed)
        self._closing=False
        self._last_notice=''
        self._key=None
        self._names={}
        self._lookups={}
        self._pending=None
        self._inflight=None
        self._busy=False
        self._action_errors={}
        self._limits=self._read_limits()
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(14)
        controls=Card('Programme & Verbindungen')
        self.state_label=label('Messung wird beim Öffnen gestartet.','strong',wrap=True)
        self.state_label.setTextFormat(Qt.PlainText)
        self.scope=label('Ohne Freigabe: TCP-Nutzdaten der erkennbaren Verbindungen. UDP-Verbrauch ist nicht verfügbar. Werte gelten ab Messbeginn.','muted',wrap=True)
        controls.body.addWidget(self.state_label)
        controls.body.addWidget(self.scope)
        buttons=QHBoxLayout()
        self.full=QPushButton('Vollständige Messung freigeben')
        self.full.setObjectName('ghostBtn')
        self.full.clicked.connect(self._toggle_helper)
        self.clear=QPushButton('Alle Sperren aufheben')
        self.clear.setObjectName('ghostBtn')
        self.clear.clicked.connect(lambda:self.client.command('clear'))
        self.clear.setEnabled(False)
        self.reset=QPushButton('Messung zurücksetzen')
        self.reset.setObjectName('ghostBtn')
        self.reset.clicked.connect(self._reset)
        for button in (self.full,self.clear,self.reset):buttons.addWidget(button)
        buttons.addStretch(1)
        controls.body.addLayout(buttons)
        self.filter=QLineEdit()
        self.filter.setPlaceholderText(tr('Programme oder Pfade filtern'))
        self.filter.textChanged.connect(self._render)
        controls.body.addWidget(self.filter)
        self.table=QTableWidget(0,7)
        self.table.setObjectName('networkApplications')
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(245)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for column in range(1,7):self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection)
        controls.body.addWidget(self.table)
        self.empty=label('Noch keine zuordenbaren Netzwerkverbindungen. Öffne eine Anwendung mit Netzwerkzugriff.','muted',wrap=True)
        controls.body.addWidget(self.empty)
        layout.addWidget(controls)
        details=Card('Verbindungsdetails')
        self.details=details
        self.application=label('Programm auswählen','strong',wrap=True)
        self.application.setTextFormat(Qt.PlainText)
        self.path=label('','muted',wrap=True)
        self.path.setTextFormat(Qt.PlainText)
        self.path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details.body.addWidget(self.application)
        self.advanced=ExpandableCard()
        self.advanced.header.setText('Erweiterte Verbindungen')
        self.advanced.addWidget(self.path)
        actions=QHBoxLayout()
        self.block=QPushButton('Netzwerk sperren')
        self.block.setObjectName('ghostBtn')
        self.block.clicked.connect(self._block)
        self.budget=QPushButton('Verbrauchswarnung …')
        self.budget.setObjectName('ghostBtn')
        self.budget.clicked.connect(self._budget)
        self.resolve=QPushButton('Hostnamen ermitteln')
        self.resolve.setObjectName('ghostBtn')
        self.resolve.clicked.connect(self._resolve)
        for button in (self.block,self.budget):actions.addWidget(button)
        actions.addStretch(1)
        details.body.addLayout(actions)
        self.limit_label=label('','muted',wrap=True)
        details.body.addWidget(self.limit_label)
        self.connections=QTableWidget(0,5)
        self.connections.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.connections.setSelectionMode(QAbstractItemView.SingleSelection)
        self.connections.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.connections.setShowGrid(False)
        self.connections.verticalHeader().hide()
        self.connections.setMinimumHeight(180)
        self.connections.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.connections.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        self.connections.itemSelectionChanged.connect(self._connection_selection)
        self.advanced.addWidget(self.connections)
        connection_actions=QWidget();connection_row=QHBoxLayout(connection_actions)
        connection_row.setContentsMargins(0,0,0,0)
        self.connection_block=QPushButton('Verbindung sperren')
        self.connection_block.setObjectName('ghostBtn')
        self.connection_block.clicked.connect(self._block_connection)
        connection_row.addWidget(self.connection_block);connection_row.addWidget(self.resolve);connection_row.addStretch(1)
        self.advanced.addWidget(connection_actions)
        details.body.addWidget(self.advanced)
        details.body.addWidget(label('Sperren betreffen die laufenden Prozesse dieses Programms und gelten nur während der freigegebenen Vitalux-Sitzung. Hostnamen werden erst auf Klick über die Systemauflösung angefragt; ein PTR-Name bestätigt nicht die Identität eines Ziels.','muted',wrap=True))
        self.details_reveal=SoftReveal(details)
        layout.addWidget(self.details_reveal)
        self.advanced.animation.valueChanged.connect(lambda _value:self.details_reveal._frame(self.details_reveal.progress))
        self.advanced.settled.connect(lambda:self.details_reveal._frame(self.details_reveal.progress))
        self.retranslate()
        self._selection()

    @staticmethod
    def _read_limits():
        value=settings.get('network_app_limits',{})
        if not isinstance(value,dict):return {}
        return {key:limit for key,limit in list(value.items())[:4096]
                if isinstance(key,str) and len(key)<=4096 and type(limit) is int and 0<limit<=1024**5}

    def showEvent(self,event):
        super().showEvent(event)
        self._start_sampler()

    def _start_sampler(self):
        if not self._closing and self.worker is None:
            self.worker=NetworkSampler(self)
            self.worker.sampled.connect(self._normal_sample)
            self.worker.failed.connect(self._error)
            self.worker.start()
            self.state_label.setText(tr('TCP-Messung aktiv · nur Programme des aktuellen Benutzers'))

    def resume_after_shutdown(self):
        had_worker=self.worker is not None
        if had_worker:
            self.worker.deleteLater()
            self.worker=None
        self._closing=False
        self.full.setEnabled(True)
        if had_worker:self._start_sampler()

    def _normal_sample(self,sample):
        if not self.client.active and not self._closing:self._ingest(sample)

    def _helper_sample(self,sample):
        if not self._closing:self._ingest(sample)

    def _ingest(self,sample):
        try:notifications=self.ledger.ingest(sample,self._limits)
        except (ValueError,TypeError,KeyError) as exc:
            self._error(str(exc))
            return
        for key,total,limit in notifications:
            app=self.ledger.apps[key]
            name=app['name'] or app['exe'] or tr('Nicht zugeordnet')
            self.alert.emit(tr('Verbrauchswarnung'),f'{name}: {fmt_bytes(total)} / {fmt_bytes(limit)}')
        self._render()
        self.clear.setEnabled(bool(self.ledger.rules or self.ledger.connection_rules) and self.client.active)
        if self.ledger.errors:
            self.state_label.setText(tr('Messung teilweise verfügbar. Details stehen im Hinweis.'))
            self.state_label.setToolTip('\n'.join(self.ledger.errors))

    def _render(self,*_):
        scroll=(self.table.verticalScrollBar().value(),self.table.horizontalScrollBar().value())
        needle=self.filter.text().casefold()
        rows=[row for row in self.ledger.apps.values() if not needle or needle in
              (row['name']+' '+row['exe']).casefold()]
        rows.sort(key=lambda row:row['total_down']+row['total_up'],reverse=True)
        selected=self._key
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        selected_item=None
        for index,row in enumerate(rows):
            name=row['name'] or (row['exe'].rsplit('/',1)[-1] if row['exe'] else tr('Nicht zugeordnet'))
            item=QTableWidgetItem(name)
            item.setData(Qt.UserRole,row['key'])
            item.setToolTip(row['exe'] or tr('Prozess konnte nicht zugeordnet werden.'))
            self.table.setItem(index,0,item)
            for column,key in ((1,'down'),(2,'up')):
                value=row.get(key)
                shown='–' if value is None else fmt_rate(value)
                self.table.setItem(index,column,NumberItem(shown,value))
            total=row['total_down']+row['total_up']
            self.table.setItem(index,3,NumberItem(fmt_bytes(total) if row['measured'] or total else '–',total))
            self.table.setItem(index,4,NumberItem(str(row['connections']),row['connections']))
            pending=(self._pending or self._inflight or {}).get('key')==row['key']
            state=tr('Wird geändert …') if pending else tr('Fehler') if row['key'] in self._action_errors else tr('Gesperrt') if row['blocked'] else tr('Teilweise') if row['partial'] else tr('Aktiv') if row['pids'] else tr('Beendet')
            self.table.setItem(index,5,QTableWidgetItem(state))
            button=self.table.cellWidget(index,6)
            if button is None or button.property('appkey')!=row['key']:
                button=QPushButton('');button.setObjectName('ghostBtn');button.setProperty('appkey',row['key'])
                button.setStyleSheet('QPushButton#ghostBtn { padding: 4px 10px; min-height: 22px; }')
                button.clicked.connect(lambda checked=False,key=row['key']:self._block_key(key))
                self.table.setCellWidget(index,6,button)
            button.setText(tr('Entsperren' if row['blocked'] else 'Sperren'))
            button.setEnabled(bool(row['pids'] or row['blocked']) and not self._busy and not pending)
            button.setToolTip(self._action_errors.get(row['key'],'') or tr('Ein- und ausgehenden Netzwerkverkehr dieser App sperren oder freigeben.'))
            if row['key']==selected:selected_item=item
        self.table.setSortingEnabled(True)
        self._restore_selection(self.table,selected_item)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.empty.setVisible(not rows)
        self._selection()
        self.table.verticalScrollBar().setValue(scroll[0]);self.table.horizontalScrollBar().setValue(scroll[1])

    @staticmethod
    def _restore_selection(table,item):
        # selectRow also scrolls to the row, even when the user is browsing elsewhere.
        selection=table.selectionModel();selection.clearSelection()
        if item is not None:
            index=table.model().index(item.row(),0)
            selection.select(index,QItemSelectionModel.Select|QItemSelectionModel.Rows)
            selection.setCurrentIndex(index,QItemSelectionModel.NoUpdate)

    def _selection(self):
        selected=self.table.selectionModel().selectedRows()
        item=self.table.item(selected[0].row(),0) if selected else None
        self._key=item.data(Qt.UserRole) if item else None
        row=self.ledger.apps.get(self._key)
        self.budget.setEnabled(bool(row) and self._key!='@unassigned')
        self.resolve.setEnabled(bool(row and row['connections']))
        self.details_reveal.setRevealed(bool(row))
        pending=(self._pending or self._inflight or {}).get('key')==self._key
        self.block.setEnabled(bool(row and (row['pids'] or row['blocked'])) and not self._busy and not pending)
        self.block.setText(tr('Netzwerk freigeben' if row and row['blocked'] else 'Netzwerk sperren'))
        self.block.setToolTip('' if self.client.active else tr('Bei Bedarf wird die Systemfreigabe direkt angefragt.'))
        self.application.setText((row['name'] or row['exe'] or tr('Nicht zugeordnet')) if row else tr('Programm auswählen'))
        self.path.setText(row['exe'] if row else '')
        limit=self._limits.get(self._key)
        self.limit_label.setText((tr('Verbrauchswarnung')+': '+fmt_bytes(limit)+tr(' pro Messsitzung')) if limit else tr('Keine Verbrauchswarnung für dieses Programm.'))
        self._render_connections()

    def _render_connections(self):
        scroll=(self.connections.verticalScrollBar().value(),self.connections.horizontalScrollBar().value())
        current=self._selected_connection()
        selected=current.get('cookie') if current else None
        rows=[row for row in self.ledger.connections if row.get('key')==self._key]
        self.connections.blockSignals(True)
        self.connections.setRowCount(len(rows))
        selected_item=None
        for index,row in enumerate(rows):
            address=row['remote']
            remote=f"[{address}]:{row['remote_port']}" if ':' in address else f"{address}:{row['remote_port']}"
            local=f"{row['local']}:{row['local_port']}"
            name=self._names.get(address,tr('Nicht aufgelöst'))
            blocked=row['cookie'] in self.ledger.connection_rules or self._key in self.ledger.rules
            values=(row['protocol'],str(row.get('pid') or '–'),remote,name,tr('Gesperrt') if blocked else row['state'])
            for column,value in enumerate(values):
                item=QTableWidgetItem(value)
                if column==0:item.setData(Qt.UserRole,row['cookie'])
                item.setToolTip(local if column==2 else value)
                self.connections.setItem(index,column,item)
            if row['cookie']==selected:selected_item=self.connections.item(index,0)
        self._restore_selection(self.connections,selected_item)
        self.connections.blockSignals(False)
        self._connection_selection()
        self.connections.verticalScrollBar().setValue(scroll[0]);self.connections.horizontalScrollBar().setValue(scroll[1])

    def _selected_connection(self):
        selected=self.connections.selectionModel().selectedRows() if hasattr(self,'connections') else []
        item=self.connections.item(selected[0].row(),0) if selected else None
        cookie=item.data(Qt.UserRole) if item else None
        return next((row for row in self.ledger.connections if row['cookie']==cookie and row.get('key')==self._key),None)

    def _connection_selection(self):
        if not hasattr(self,'connection_block'):return
        row=self._selected_connection()
        app_blocked=self._key in self.ledger.rules
        blocked=bool(row and row['cookie'] in self.ledger.connection_rules)
        self.connection_block.setText(tr('Verbindung entsperren' if blocked else 'Verbindung sperren'))
        self.connection_block.setEnabled(bool(row and row.get('pid') and row['cookie']>0) and not app_blocked and not self._busy and not self._inflight)
        self.connection_block.setToolTip(tr('Zuerst die vollständige App-Sperre aufheben.') if app_blocked else
            tr('Für einzelne Verbindungen ist eine vollständige Messung mit Kernel-Socketkennung erforderlich.') if row and row['cookie']<=0 else '')

    def _toggle_helper(self):
        self._last_notice=''
        if self.client.active:self.client.stop()
        else:self.client.start()

    def _helper_state(self,state):
        if self.worker is not None:self.worker.paused=state=='ready'
        busy=state in ('installing','authenticating')
        self._busy=busy
        self.full.setEnabled(not busy and not self._closing)
        self.full.setText(tr('Freigabe beenden' if state=='ready' else 'Vollständige Messung freigeben'))
        texts=dict(installing='Netzwerk-Helfer wird eingerichtet · Systemfreigabe erforderlich',
            authenticating='Systemfreigabe für die Netzwerkmessung wird angefragt …',
            ready='Vollständige Messung aktiv · TCP und UDP · IP-Bytes einschließlich Protokoll-Header',
            stopped='TCP-Messung aktiv · nur Programme des aktuellen Benutzers')
        self.state_label.setText(tr(texts.get(state,'')))
        self.scope.setText(tr('Session-Sperren werden beim Beenden der Freigabe oder von Vitalux aufgehoben. Verbrauch gilt ab Beginn dieser Messung.' if state=='ready' else
            'Ohne Freigabe: TCP-Nutzdaten der erkennbaren Verbindungen. UDP-Verbrauch ist nicht verfügbar. Werte gelten ab Messbeginn.'))
        if state=='stopped':
            self._pending=None;self._inflight=None
            self.ledger.rules.clear()
            self.ledger.connection_rules.clear()
            for row in self.ledger.apps.values():row['blocked']=False
            self.clear.setEnabled(False)
            if self._last_notice:self._error(self._last_notice)
        if state=='ready' and self._pending:
            action=self._pending;self._pending=None;self._send_action(action)
        self._render()

    def _rules_changed(self,rules):
        self._pending=None;self._inflight=None
        self.ledger.rules=set(rules)
        for key,row in self.ledger.apps.items():row['blocked']=key in self.ledger.rules
        self.clear.setEnabled(bool(rules or self.ledger.connection_rules))
        self._render()

    def _connection_rules_changed(self,rules):
        self.ledger.connection_rules=set(rules)
        self.clear.setEnabled(bool(rules or self.ledger.rules))
        self._render_connections()

    def _error(self,message):
        action=self._pending or self._inflight
        if action:self._action_errors[action['key']]=str(message)
        self._pending=None;self._inflight=None
        self._last_notice=message
        short=tr('Der Netzwerk-Helfer konnte nicht gestartet werden. Die Basisansicht bleibt verfügbar.') if len(message)>160 or '\n' in message else tr(message)
        self.state_label.setText(tr('Netzwerk-Hinweis')+': '+short)
        self.state_label.setToolTip(message)
        self._render()

    def _block(self):
        row=self.ledger.apps.get(self._key)
        if not row or self._busy:return
        if row['blocked']:
            self._request_action(dict(op='allow',key=row['key']))
        elif row['pids']:
            pid,start=next(iter(row['pids'].items()))
            if type(start) is int:self._request_action(dict(op='block',pid=pid,start=start,key=row['key']))

    def _block_key(self,key):
        if key not in self.ledger.apps:return
        for index in range(self.table.rowCount()):
            if self.table.item(index,0).data(Qt.UserRole)==key:self.table.selectRow(index);break
        self._key=key;self._block()

    def _block_connection(self):
        row=self._selected_connection()
        if not row or row['cookie']<=0:return
        op='allow_connection' if row['cookie'] in self.ledger.connection_rules else 'block_connection'
        self._request_action(dict(op=op,pid=row['pid'],start=row['start'],cookie=row['cookie'],key=self._key))

    def _request_action(self,action):
        self._action_errors.pop(action['key'],None)
        if self.client.active:self._send_action(action)
        else:
            self._pending=action
            self.client.start()
        self._render()

    def _send_action(self,action):
        self._inflight=action
        self.client.command(**action)

    def _budget(self):
        if not self._key or self._key=='@unassigned':return
        value,ok=QInputDialog.getInt(self,tr('Verbrauchswarnung'),
            tr('Warnung ab MiB pro Messsitzung (0 = aus):'),self._limits.get(self._key,0)//(1024**2),0,1000000,1)
        if not ok:return
        if value:self._limits[self._key]=value*1024**2
        else:self._limits.pop(self._key,None)
        settings.set('network_app_limits',self._limits)
        window=self.window()
        if hasattr(window,'pages'):
            preferences=next((page for title,page in window.pages if title=='Einstellungen'),None)
            if preferences is not None:preferences._refresh_restore_button()
        self._selection()

    def _resolve(self):
        addresses={row['remote'] for row in self.ledger.connections if row.get('key')==self._key
                   and row.get('remote') not in ('0.0.0.0','::')}
        for address in sorted(addresses)[:32]:
            if len(self._lookups)>=32:break
            if address in self._lookups or address in self._names:continue
            lookup=QDnsLookup(QDnsLookup.PTR,ipaddress.ip_address(address).reverse_pointer,self)
            self._lookups[address]=lookup
            def result(address=address,lookup=lookup):
                self._lookups.pop(address,None)
                if self._closing:return
                if len(self._names)>=512:self._names.pop(next(iter(self._names)))
                records=lookup.pointerRecords() if lookup.error()==QDnsLookup.NoError else []
                self._names[address]=records[0].value().rstrip('.') if records else tr('Unbekannt')
                lookup.deleteLater()
                self._render_connections()
            lookup.finished.connect(result)
            lookup.lookup()

    def _reset(self):
        rules=set(self.ledger.rules)
        connections=set(self.ledger.connection_rules)
        self.ledger.reset()
        self.ledger.rules=rules
        self.ledger.connection_rules=connections
        self._render()

    def retranslate(self):
        self.table.setHorizontalHeaderLabels([tr(value) for value in
            ('Programm','Download','Upload','Erfasst','Verbindungen','Status','Netzwerkzugriff')])
        self.connections.setHorizontalHeaderLabels([tr(value) for value in
            ('Protokoll','PID','Zieladresse','PTR-Hostname','Zustand')])
        self.filter.setPlaceholderText(tr('Programme oder Pfade filtern'))
        if self.worker is not None:self._helper_state('ready' if self.client.active else 'stopped')
        self._render()

    def shutdown(self):
        if not self._closing:
            self._closing=True
            if self.worker is not None:self.worker.stop()
            self.client.stop()
            for lookup in list(self._lookups.values()):
                lookup.abort()
                lookup.deleteLater()
            self._lookups.clear()
        return (self.worker is None or not self.worker.isRunning()) and self.client.is_stopped()
