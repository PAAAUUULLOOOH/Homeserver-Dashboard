"""All designs share a multi-row gallery and responsive settings columns."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea,QFrame,QGridLayout,QWidget
from . import signature_designs


class Gallery(QScrollArea):
    """All designs share the same visible multi-row grid."""
    def __init__(self,content,tiles,parent=None):
        super().__init__(parent)
        self.tiles=tiles
        self.setObjectName('glassScroll')
        self.setFrameShape(QFrame.NoFrame)
        self.setWidget(content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sync()

    def sync(self):
        grid=self.widget().layout()
        for tile in self.tiles:grid.removeWidget(tile)
        for column in range(len(self.tiles)):grid.setColumnStretch(column,0)
        for index,tile in enumerate(self.tiles):
            tile.setMinimumWidth(125);tile.setMaximumWidth(16777215)
            grid.addWidget(tile,index//3,index%3)
        self.widget().setMinimumWidth(0);self.widget().setMaximumWidth(16777215)
        height=((len(self.tiles)+2)//3)*112+((len(self.tiles)-1)//3)*grid.spacing()
        self.widget().setFixedHeight(height);self.setFixedHeight(height+2)


class CardDeck(QWidget):
    def __init__(self,cards,parent=None):
        super().__init__(parent)
        self.cards=list(cards)
        self._columns=0
        self.grid=QGridLayout(self)
        self.grid.setContentsMargins(0,0,0,0)
        self.grid.setSpacing(16)
        self.sync()

    def sync(self):
        columns=2 if signature_designs.active() and self.width()>=1000 else 1
        if columns==self._columns:return
        self._columns=columns
        for card in self.cards:self.grid.removeWidget(card)
        for index,card in enumerate(self.cards):self.grid.addWidget(card,index//columns,index%columns)
        self.grid.setColumnStretch(0,1)
        self.grid.setColumnStretch(1,1 if columns==2 else 0)
        self.updateGeometry()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.sync()
