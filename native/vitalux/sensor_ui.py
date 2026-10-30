"""Compact current sensor and power rows without empty placeholders."""
from PySide6.QtWidgets import QGridLayout, QVBoxLayout, QWidget
from .hardware_sensors import number
from .power_display import power_records, short_name, source_text
from .i18n import tr
from .widgets import Card, KeyValue, label


def reflow(grid, widgets, columns=2):
    while grid.count():
        grid.takeAt(0)
    visible = [w for w in widgets if not w.isHidden()]
    parent=grid.parentWidget()
    if parent is not None and parent.width()<640:
        columns=1
    for i, widget in enumerate(visible):
        grid.addWidget(widget, i//columns, i % columns)


def sensor_row(title, parent):
    row=KeyValue(title)
    row.setParent(parent)
    row.layout().itemAt(0).widget().setWordWrap(True)
    return row


def optional(row, value, unit='', places=1):
    valid = number(value) is not None
    row.setVisible(valid)
    if valid:
        row.set(watts(value) if unit=='W' and places==1 else f'{value:.{places}f} {tr(unit)}'.strip())
    else:
        row.set('')  # Do not leave the previous reading available as current text.


def watts(value):
    return f'{value:.1f}'.rstrip('0').rstrip('.')+' W'


def power_text(record):
    value=number((record or {}).get('value'))
    return tr('Leistung')+': '+watts(value) if value is not None else ''


class PowerDetails(QWidget):
    def __init__(self):
        super().__init__()
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 6, 0, 12)
        self.title = label('', 'strong', wrap=True)
        self.body.addWidget(self.title)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(24)
        self.rows = {}
        self.body.addLayout(self.grid)

    def sync(self, record,show_title=False):
        self.title.setText(short_name(record))
        self.title.setVisible(show_title)
        self.setToolTip(source_text(record))
        entries = [('Leistung', record.get('value'))]
        entries += list(record.get('limits') or ())
        active = set()
        for title, value in entries:
            active.add(title)
            row = self.rows.get(title)
            if row is None:
                row = self.rows[title] = sensor_row(title,self)
            optional(row, value, 'W')
        for title, row in self.rows.items():
            if title not in active:
                optional(row, None)
        reflow(self.grid, list(self.rows.values()),1)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        reflow(self.grid,list(self.rows.values()),1)


class SensorPanel(Card):
    def __init__(self,include_power=True):
        super().__init__('Sensoren & Leistungsaufnahme' if include_power else 'Sensoren')
        self.include_power=include_power
        self.powers, self.rows = {}, {}
        self.power_layout=QVBoxLayout()
        self.body.addLayout(self.power_layout)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(24)
        self.body.addLayout(self.grid)
        self.hide()

    def sync(self, records):
        records=list(records)
        present, power_ids = set(), set()
        selected=[r for r in power_records(records) if number(r.get('value')) is not None or r.get('limits')] if self.include_power else []
        for record in selected:
            key = record['id']
            power_ids.add(key)
            widget = self.powers.get(key)
            if widget is None:
                widget = self.powers[key] = PowerDetails()
                self.power_layout.addWidget(widget)
            widget.sync(record,len(selected)>1)
            widget.show()
        for record in records:
            key=record['id']
            if record['kind']!='powers' and number(record.get('value')) is not None:
                present.add(key)
                row = self.rows.get(key)
                if row is None:
                    row = self.rows[key] = sensor_row(record['name'],self)
                optional(row, record['value'], record['unit'], 0 if record['kind'] == 'fans' else 2 if record['kind'] == 'voltages' else 1)
                row.setToolTip(record.get('source', ''))
        for key, row in self.rows.items():
            if key not in present:
                optional(row, None)
        for key, widget in self.powers.items():
            widget.setVisible(key in power_ids)
        reflow(self.grid, list(self.rows.values()))
        self.setVisible(bool(present or power_ids))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        reflow(self.grid,list(self.rows.values()))
