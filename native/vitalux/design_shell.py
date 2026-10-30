"""Rearrange existing accessible navigation without rebuilding running pages."""
from PySide6.QtCore import QObject, Qt, QEvent, QTimer
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QScrollArea, QFrame
from . import theme, __version__
from .i18n import tr
from .widgets import label
from .signature_designs import KEYS, Surface


class FloatingDock(Surface):
    """Translucent live dock: page cards remain visible through its material."""
    def paintEvent(self,event):
        if theme.mode()!='nebula_prism':return super().paintEvent(event)
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QBrush,QColor,QLinearGradient,QPainter,QPen
        from . import nebula_prism
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(self.rect()).adjusted(1.5,1.5,-1.5,-1.5)
        path=nebula_prism.shape(rect,compact=True)
        wash=QLinearGradient(rect.topLeft(),rect.bottomRight())
        for position,value in ((0,theme.CARD),(1,theme.BG)):
            color=QColor(value);color.setAlpha(155);wash.setColorAt(position,color)
        painter.fillPath(path,QBrush(wash))
        rim=QLinearGradient(rect.topLeft(),rect.bottomRight())
        palette=nebula_prism.palette()
        for index,value in enumerate((palette['accent'],palette['secondary'],palette['accent'])):
            color=QColor(value);color.setAlpha(210);rim.setColorAt(index/2,color)
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(QBrush(rim),1.5))
        painter.drawPath(path);painter.end()


class DesignShell(QObject):
    def __init__(self, window, canvas):
        super().__init__(window)
        self.window=window
        self.mode=None
        self._language_index=window.sidebar_layout.indexOf(window.lang_host)
        self.header=QWidget(canvas.parentWidget())
        vertical=QVBoxLayout(self.header)
        vertical.setContentsMargins(0,0,0,0)
        vertical.setSpacing(7)
        bar=Surface()
        self.bar=bar
        top=QHBoxLayout(bar)
        self.top=top
        top.setContentsMargins(16,7,16,7)
        top.setSpacing(16)
        self.brand=QWidget()
        self.brand_layout=QHBoxLayout(self.brand)
        self.brand_layout.setContentsMargins(0,0,0,0)
        self.brand_layout.setSpacing(10)
        top.addWidget(self.brand)
        top.addStretch(1)
        self.current_page=label('','strong')
        top.addWidget(self.current_page)
        top.addSpacing(10)
        vertical.addWidget(bar)
        self.primary_host=Surface()
        self.primary=QHBoxLayout(self.primary_host)
        self.primary.setContentsMargins(6,3,6,3)
        self.primary.setSpacing(3)
        self.primary_scroll=QScrollArea()
        self.primary_scroll.setFrameShape(QFrame.NoFrame)
        self.primary_scroll.setWidget(self.primary_host)
        self.primary_scroll.setWidgetResizable(True)
        self.primary_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.primary_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.primary_scroll.setFixedHeight(60)
        self.primary_scroll.setObjectName('glassScroll')
        vertical.addWidget(self.primary_scroll)
        self.footer=Surface()
        self.bottom=QHBoxLayout(self.footer)
        self.bottom.setContentsMargins(12,4,12,4)
        self.bottom.setSpacing(4)
        self.version=label(f'Vitalux · {__version__}','muted')
        self.bottom.addWidget(self.version)
        self.bottom.addStretch(1)
        # Nebula Prism: a floating, centred dock instead of a sidebar or bar.
        self.dock_row=QWidget(canvas.parentWidget())
        self.dock_row.setAutoFillBackground(False)
        dock_row=QHBoxLayout(self.dock_row)
        dock_row.setContentsMargins(0,0,0,0)
        self.dock=FloatingDock()
        self.dock_layout=QHBoxLayout(self.dock)
        self.dock_layout.setContentsMargins(10,5,10,5)
        self.dock_layout.setSpacing(4)
        dock_row.addStretch(1)
        dock_row.addWidget(self.dock)
        dock_row.addStretch(1)
        canvas.addWidget(self.footer)
        self.header.hide()
        self.footer.hide()
        self.dock_row.hide()
        self._footer_compact=None
        window.installEventFilter(self)
        for button in window.nav_buttons:button.installEventFilter(self)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Resize and self.mode=='eclipse_crystal':
            QTimer.singleShot(0,self._responsive)
        if event.type()==QEvent.FocusIn and self.mode=='eclipse_crystal' and obj in self.window.nav_buttons[:8]:
            self.primary_scroll.ensureWidgetVisible(obj,12,0)
        return False

    def _responsive(self):
        if self.mode!='eclipse_crystal':return
        compact=self.window.width()<1120
        if compact==self._footer_compact:return
        self._footer_compact=compact
        for button in self.window.nav_buttons[8:]:
            button.set_compact(compact)
            if not compact:
                button.setFixedWidth(max(108,button.fontMetrics().horizontalAdvance(button.text().split('    ',1)[-1])+57))
        self.version.setVisible(not compact)

    def _remove_navigation(self):
        w=self.window
        for button in w.nav_buttons:
            w.nav_host.layout().removeWidget(button)
            self.primary.removeWidget(button)
            self.bottom.removeWidget(button)
            self.dock_layout.removeWidget(button)
            button.setProperty('vitaluxCapabilityHints',False)
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setMinimumHeight(39)
            button.setMaximumHeight(16777215)
            button.set_compact(False)
            button.setToolTip('')

    def sync(self):
        w=self.window
        mode=theme.mode()
        signature=mode in KEYS
        previous=self.mode
        self.mode=mode
        if previous!=mode:
            self._remove_navigation()
            if signature:
                self.brand_layout.addWidget(w.pulse_core)
                self.brand_layout.addWidget(w.brand_mark)
                w.pulse_core.setFixedSize(44,44)
                w.brand_mark.setFixedSize(180,32)
                w.pulse_core.show()
                w.brand_mark.show()
            else:
                w.sidebar_brand.layout().insertWidget(0,w.pulse_core,0,Qt.AlignHCenter)
                w.sidebar_brand.layout().insertWidget(2,w.brand_mark,0,Qt.AlignHCenter)
                w.pulse_core.setFixedSize(132,132)
                w.brand_mark.setFixedSize(200,36)
                w.pulse_core.show()
                w.brand_mark.show()
            eclipse=mode=='eclipse_crystal'
            nebula=mode=='nebula_prism'
            for position,index in enumerate(w.navigation_indices()):
                button=w.nav_buttons[index]
                if nebula:
                    button.set_compact(True)
                    button.setFixedSize(54,46)
                    self.dock_layout.addWidget(button)
                elif eclipse:
                    button.setFixedWidth(max(108,button.fontMetrics().horizontalAdvance(tr(w.pages[index][0]))+57))
                    (self.primary if index<8 else self.bottom).addWidget(button)
                else:
                    w.nav_host.layout().insertWidget(position,button)
                button.show()
            self.bottom.removeWidget(w.lang_host)
            self.top.removeWidget(w.lang_host)
            w.sidebar_layout.removeWidget(w.lang_host)
            if eclipse:
                self.bottom.addWidget(w.lang_host)
            elif nebula:
                index=self.top.indexOf(w.window_frame.titlebar)
                self.top.insertWidget(index if index>=0 else self.top.count(),w.lang_host)
            else:
                w.sidebar_layout.insertWidget(self._language_index,w.lang_host)
        self.header.setVisible(signature)
        self.footer.setVisible(mode=='eclipse_crystal')
        self.primary_scroll.setVisible(mode=='eclipse_crystal')
        self.dock_row.setVisible(mode=='nebula_prism')
        w.sidebar.setVisible(mode not in ('eclipse_crystal','nebula_prism'))
        w.collapse_button.setVisible(not signature)
        if signature:
            w.sidebar_brand.hide()
            w._brand_gap.hide()
            w.sidebar_version.hide()
            w.lang_host.show()
            w.sidebar.setFixedWidth(210)
            w.sidebar_layout.setContentsMargins(12,16,12,12)
            w.nav_host.layout().setContentsMargins(0,0,0,0)
            w._outer_layout.setContentsMargins(0,0,0,0)
            w._outer_layout.setSpacing(10 if mode=='nebula_prism' else 8)
        else:
            w._outer_layout.setContentsMargins(0,0,0,0)
            w._outer_layout.setSpacing(0)
            w._apply_sidebar_state()
        self.retranslate()
        self._footer_compact=None
        self._responsive()
        if w.window_frame.scene is not None:w.window_frame.sync_controls()
        overview=w.pages[0][1]
        overview.refresh_design()
        for _,page in w.pages[1:]:
            page.root.setContentsMargins(*( (18,20,18,26) if signature else (30,24,30,30) ))
        if signature:
            self.header.updateGeometry()
        self.sync_window_geometry()
        w.pulse_core.sync_theme()
        w.brand_mark.sync_theme()

    def sync_window_geometry(self):
        """Fixed navigation overlays the scroll surface; page padding scrolls away."""
        w=self.window
        frame=getattr(w,'window_frame',None)
        if frame is None or frame.scene is None:return
        signature=self.mode in KEYS
        height=self.header.sizeHint().height() if signature else 0
        if signature:
            self.header.setGeometry(0,0,w.width(),height)
            self.header.raise_()
        if self.mode=='nebula_prism':
            count=len(w.nav_buttons)
            button_width=min(54,max(28,(w.width()-60-(count-1)*4)//max(1,count)))
            for button in w.nav_buttons:button.setFixedSize(button_width,46)
            self.dock_layout.activate();self.dock_row.layout().activate()
            size=self.dock.sizeHint()
            self.dock_row.setGeometry((w.width()-size.width())//2,w.height()-size.height()-16,size.width(),size.height())
            self.dock_row.raise_()
        inset=height if signature else frame.titlebar.height()
        top=inset+(16 if signature else 2)
        for index,(_,page) in enumerate(w.pages):
            if index==0:page._frame_top_margin=top
            viewport=w.stack.widget(index).viewport()
            viewport.setProperty('vitaluxTopInset',max(0,inset))
            if hasattr(page,'search_overlay'):page.search_overlay._position()
            old=page.root.contentsMargins()
            bottom=max(26,self.dock_row.height()+32) if self.mode=='nebula_prism' else (26 if signature else 30)
            if old.top()!=top or old.bottom()!=bottom:page.root.setContentsMargins(old.left(),top,old.right(),bottom)
        if not w.sidebar.isHidden():
            old=w.sidebar_layout.contentsMargins()
            w.sidebar._toggle_y=max(13,inset+2)
            side_top=max(55,top,w.sidebar._toggle_y+w.collapse_button.height()+2) if w._sidebar_collapsed and not signature else top
            if old.top()!=side_top:w.sidebar_layout.setContentsMargins(old.left(),side_top,old.right(),old.bottom())
            w.sidebar._position_toggle()
        frame.titlebar.raise_()
        frame.materials.refresh()
        frame._clip_content()
        for _,page in w.pages:
            if hasattr(page,'search_overlay') and page.search_overlay.isVisible():page.search_overlay._position()

    def retranslate(self):
        w=self.window
        if w.pages:
            self.current_page.setText(tr(w.pages[w.stack.currentIndex()][0]))
        if self.mode=='eclipse_crystal':
            for index,button in enumerate(w.nav_buttons):
                button.setFixedWidth(max(108,button.fontMetrics().horizontalAdvance(tr(w.pages[index][0]))+57))
        if self.mode=='nebula_prism':
            for index,button in enumerate(w.nav_buttons):
                caption=tr(w.pages[index][0])
                button.setAccessibleName(caption)
                version=button._update_version if button is w.update_btn else ''
                button.setToolTip(caption+(' '+version if version else ''))

    def select(self,index):
        self.current_page.setText(tr(self.window.pages[index][0]))
        if self.mode=='eclipse_crystal' and index<8:
            self.primary_scroll.ensureWidgetVisible(self.window.nav_buttons[index],12,0)

