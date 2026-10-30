"""Qt widgets that respect Vitalux's runtime DE/EN localization.

The project uses dynamically constructed Python widgets rather than .ui files.
Central wrappers ensure buttons, combo entries, dialogs and dynamically updated
labels all pass through the same translation function.
"""
from PySide6.QtWidgets import (QLabel as _QLabel, QPushButton as _QPushButton,
    QCheckBox as _QCheckBox, QComboBox as _QComboBox, QDialog as _QDialog,
    QListView as _QListView, QFrame as _QFrame, QStyleFactory as _QStyleFactory,
    QListWidgetItem as _QListWidgetItem, QMessageBox as _QMessageBox,
    QFileDialog as _QFileDialog)
from .i18n import tr
from PySide6.QtCore import Qt, QRectF, QSize, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPalette


def localized(x):
    return tr(x) if isinstance(x, str) else x

class QLabel(_QLabel):
    def __init__(self, text='', *args, **kwargs):
        self._original = original_text(text)
        self._tip_original = None
        super().__init__(localized(text), *args, **kwargs)
    def setText(self, text):
        self._original = original_text(text)
        super().setText(localized(text))
    def setToolTip(self, text):
        self._tip_original = original_text(text)
        super().setToolTip(localized(text))
    def retranslate(self):
        _QLabel.setText(self, localized(self._original))
        if self._tip_original is not None:
            _QLabel.setToolTip(self, localized(self._tip_original))

class QPushButton(_QPushButton):
    def __init__(self, text='', *args, **kwargs):
        self._original = original_text(text)
        self._tip_original = None
        self._edge_amount = 0.0
        self._edge_animation = None
        super().__init__(localized(text), *args, **kwargs)
    def _edge_frame(self, value):
        self._edge_amount = float(value)
        self.update()
    def _edge_to(self, value):
        if type(self) is not QPushButton:
            return  # Custom-painted navigation has its own hover compositor.
        from . import motion
        if self._edge_animation is None:
            self._edge_animation = QVariantAnimation(self)
            self._edge_animation.setEasingCurve(QEasingCurve.OutCubic)
            self._edge_animation.valueChanged.connect(self._edge_frame)
        self._edge_animation.stop()
        duration = motion.duration(160)
        if not duration:
            self._edge_frame(value)
            return
        self._edge_animation.setDuration(duration)
        self._edge_animation.setStartValue(self._edge_amount)
        self._edge_animation.setEndValue(float(value))
        self._edge_animation.start()
    def enterEvent(self, event):
        self._edge_to(1.0)
        super().enterEvent(event)
    def leaveEvent(self, event):
        self._edge_to(0.0)
        super().leaveEvent(event)
    def paintEvent(self, event):
        super().paintEvent(event)
        if self._edge_amount > .01 and self.isEnabled():
            from . import theme
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            color = QColor(theme.accent())
            color.setAlpha(round((155 if self.isDown() else 70)*self._edge_amount))
            painter.setPen(QPen(color, 1.1))
            painter.setBrush(Qt.NoBrush)
            radius = 10
            painter.drawRoundedRect(rect, radius, radius)
            painter.end()
    def setText(self, text):
        self._original = original_text(text)
        super().setText(localized(text))
    def setToolTip(self, text):
        self._tip_original = original_text(text)
        super().setToolTip(localized(text))
    def retranslate(self):
        _QPushButton.setText(self, localized(self._original))
        if self._tip_original is not None:
            _QPushButton.setToolTip(self, localized(self._tip_original))

def paint_check_indicator(painter, bounds, checked, hovered=False, focused=False):
    """One consistent outlined-square + real checkmark for every checkbox."""
    from . import theme
    area = QRectF(bounds)
    stroke = QColor(theme.accent() if checked else theme.MUTED if hovered else theme.BORDER)
    background = QColor(theme.CARD)
    background.setAlpha(38 if theme.mode()=='glass' else 110)
    painter.setPen(QPen(stroke, 1.45 if checked else 1.2))
    painter.setBrush(background)
    painter.drawRoundedRect(area, 3.3, 3.3)
    if checked:
        x, y, side = area.x(), area.y(), area.width()
        tick = QPainterPath()
        tick.moveTo(x + side * .22, y + side * .52)
        tick.lineTo(x + side * .42, y + side * .72)
        tick.lineTo(x + side * .81, y + side * .28)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(theme.accent()), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(tick)
    if focused:
        painter.setPen(QPen(QColor(theme.accent()), 1, Qt.DotLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(area.adjusted(-1.5, -1.5, 1.5, 1.5), 4, 4)


class QCheckBox(_QCheckBox):
    """Themed on/off switches; selectionControl retains multiple-choice checks."""
    def __init__(self, text='', *args, **kwargs):
        self._original = original_text(text)
        super().__init__(localized(text), *args, **kwargs)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self._toggle_progress=float(self.isChecked())
        self._toggle_animation=QVariantAnimation(self)
        self._toggle_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._toggle_animation.valueChanged.connect(self._toggle_frame)
        self.toggled.connect(self._animate_toggle)

    def _toggle_frame(self,value):
        self._toggle_progress=float(value)
        self.update()

    def setChecked(self,value):
        result=super().setChecked(value)
        if self.signalsBlocked() and hasattr(self,'_toggle_animation'):
            self._toggle_animation.stop()
            self._toggle_progress=float(bool(value))
            self.update()
        return result

    def _animate_toggle(self,checked):
        from . import motion
        self._toggle_animation.stop()
        duration=motion.duration(160)
        if not self.isVisible() or not duration:
            return self._toggle_frame(float(checked))
        self._toggle_animation.setDuration(duration)
        self._toggle_animation.setStartValue(self._toggle_progress)
        self._toggle_animation.setEndValue(float(checked))
        self._toggle_animation.start()

    def hideEvent(self,event):
        self._toggle_animation.stop()
        self._toggle_progress=float(self.isChecked())
        super().hideEvent(event)

    def sizeHint(self):
        hint=super().sizeHint()
        if self.property('selectionControl'):
            return QSize(self.fontMetrics().horizontalAdvance(self.text())+28,max(25,hint.height()))
        return QSize(max(48,self.fontMetrics().horizontalAdvance(self.text())+56),max(27,hint.height()))

    def hitButton(self,position):
        return self.rect().contains(position)

    def setText(self, text):
        self._original = original_text(text)
        super().setText(localized(text))

    def retranslate(self):
        _QCheckBox.setText(self, localized(self._original))

    def paintEvent(self, event):
        from . import theme
        from . import signature_designs
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(.45)
        if self.property('selectionControl'):
            paint_check_indicator(painter,QRectF(2,(self.height()-15)/2,15,15),self.isChecked(),self.underMouse(),self.hasFocus())
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(QRectF(25,0,max(0,self.width()-27),self.height()),Qt.AlignLeft|Qt.AlignVCenter,self.text())
            painter.end();return
        rect=QRectF(2,(self.height()-22)/2,40,22)
        if signature_designs.active():signature_designs.paint_toggle(painter,rect,self.isChecked(),self._toggle_progress)
        else:
            from .switch_material import paint_switch
            paint_switch(painter,rect,self._toggle_progress,self.hasFocus())
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(QRectF(52, 0, max(0, self.width()-54), self.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, self.text())
        painter.end()

class QComboBox(_QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        from . import theme
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(theme.TEXT if self.isEnabled() else theme.MUTED),1.5,
                            Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        x=14 if self.layoutDirection()==Qt.RightToLeft else self.width()-14
        y=self.height()/2
        path=QPainterPath()
        path.moveTo(x-4,y-2);path.lineTo(x,y+2);path.lineTo(x+4,y-2)
        painter.drawPath(path)
        painter.end()

    def __init__(self,*args,**kwargs):
        self._source_items = []
        super().__init__(*args,**kwargs)
        self.setFocusPolicy(Qt.StrongFocus)
        # KDE/Wayland native popup styles sometimes show black top and bottom
        # scroll strips. A regular Fusion list popup avoids native menu bands.
        self._popup_style = _QStyleFactory.create("Fusion")
        if self._popup_style is not None:
            self.setStyle(self._popup_style)
        view = _QListView(self)
        view.setFrameShape(_QFrame.NoFrame)
        view.setSpacing(0)
        view.setUniformItemSizes(True)
        view.setVerticalScrollMode(_QListView.ScrollPerPixel)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setAutoFillBackground(True)
        view.viewport().setAutoFillBackground(True)
        self.setView(view)
        self.setMaxVisibleItems(10)
        self.setSizeAdjustPolicy(_QComboBox.AdjustToContents)
        self.currentIndexChanged.connect(self._update_selection_tooltip)

    def wheelEvent(self, event):
        # Wheel gestures belong to the page until the user opens the selector.
        if not self.view().isVisible():
            event.ignore()
            return
        super().wheelEvent(event)

    def sizeHint(self):
        # Trim just a few pixels without forcing a width that would truncate
        # longer localized dropdown values or user-named accent colors.
        preferred = super().sizeHint()
        return QSize(max(88, preferred.width()), preferred.height())

    def _update_selection_tooltip(self, *_):
        self.setToolTip(self.currentText())

    def showPopup(self):
        # The popup list should fit full translated labels, not just the
        # width of the closed selector. Narrow displays get item tooltips.
        from PySide6.QtWidgets import QApplication
        if self.count():
            widest = max(self.fontMetrics().horizontalAdvance(self.itemText(i))
                         for i in range(self.count()))
            screen = self.screen() or QApplication.primaryScreen()
            limit = max(self.width(), screen.availableGeometry().width() - 60) if screen else 1024
            self.view().setMinimumWidth(min(max(self.width(), widest + 52), limit))
        # The popup is a native Qt window; style its whole frame and viewport
        # to avoid unthemed black strips above/below the option rows.
        from . import theme
        surface = theme.blend(theme.accent(), theme.CARD, .05)
        border = theme.BORDER
        accent = theme.accent()
        view = self.view()
        container = view.window()
        # Qt Wayland/Fusion can render popup padding using the palette rather
        # than QSS. Explicit matching colors remove unmatched dark gutters.
        popup_palette = container.palette()
        popup_palette.setColor(QPalette.Window, QColor(surface))
        popup_palette.setColor(QPalette.Base, QColor(surface))
        popup_palette.setColor(QPalette.Text, QColor(theme.TEXT))
        popup_palette.setColor(QPalette.Highlight, QColor(theme.blend(accent, surface, .24)))
        popup_palette.setColor(QPalette.HighlightedText, QColor(theme.TEXT))
        container.setPalette(popup_palette)
        view.setPalette(popup_palette)
        view.viewport().setPalette(popup_palette)
        container.setAutoFillBackground(True)
        container.setObjectName("vitaluxComboPopup")
        container.setStyleSheet(
            f"QFrame#vitaluxComboPopup {{ background: {surface}; "
            f"border: 1px solid {border}; border-radius: 9px; padding: 2px; }}"
            f"QListView {{ background: {surface}; color: {theme.TEXT}; "
            f"border: none; outline: none; padding: 0px; }}"
            f"QListView::item {{ color: {theme.TEXT}; border: none; "
            f"padding: 7px 10px; min-height: 22px; }}"
            f"QListView::item:selected {{ background: {theme.blend(accent, surface, .24)}; "
            f"color: {theme.TEXT}; }}"
            f"QListView::item:hover {{ background: {theme.blend(accent, surface, .14)}; }}"
        )
        super().showPopup()

    def addItem(self, *args, **kwargs):
        source = original_text(args[0]) if args and isinstance(args[0],str) else None
        if source is not None:
            key = args[1] if len(args) > 1 else kwargs.get('userData')
            # Guard against duplicate options when rebuilding a localized tab.
            # Distinct values with identical labels are still permitted.
            if any((self.itemData(i) == key if key is not None
                    else self.itemText(i) == localized(source))
                   for i in range(self.count())):
                return
            args = (localized(source), *args[1:])
        result = super().addItem(*args, **kwargs)
        self._source_items.append(source)
        if source is not None:
            self.setItemData(self.count()-1, localized(source), Qt.ToolTipRole)
        self._update_selection_tooltip()
        return result
    def addItems(self, items):
        for item in items:self.addItem(item)
    def clear(self):
        self._source_items.clear()
        return super().clear()
    def removeItem(self, index):
        if 0 <= index < len(self._source_items):
            self._source_items.pop(index)
        return super().removeItem(index)
    def setItemText(self, index, text):
        source = original_text(text)
        if index < len(self._source_items):self._source_items[index] = source
        value = localized(source)
        self.setItemData(index, value, Qt.ToolTipRole)
        return super().setItemText(index, value)
    def setPlaceholderText(self, text):
        return super().setPlaceholderText(localized(text))
    def retranslate(self):
        for i,source in enumerate(self._source_items):
            if i < self.count() and source is not None:
                value = localized(source)
                _QComboBox.setItemText(self,i,value)
                self.setItemData(i, value, Qt.ToolTipRole)
        self._update_selection_tooltip()

class QDialog(_QDialog):
    def setWindowTitle(self, text):
        return super().setWindowTitle(localized(text))

class QListWidgetItem(_QListWidgetItem):
    def __init__(self, text='', *args, **kwargs):
        super().__init__(localized(text), *args, **kwargs)

class QMessageBox(_QMessageBox):
    """Locale-aware Qt dialogs, including buttons from the application locale.

    On some Plasma builds the bundled Qt runtime has no German qm catalog, so
    native QMessageBox.question() falls back to English Yes/No even when the
    application labels are German. Use standard buttons with explicit text.
    """

    @staticmethod
    def _localized_dialog(icon, parent, title, message, buttons, default):
        dialog = _QMessageBox(parent)
        dialog.setIcon(icon)
        dialog.setWindowTitle(localized(title))
        dialog.setText(localized(message))
        dialog.setStandardButtons(buttons)
        texts = {
            _QMessageBox.Yes: ('Ja', 'Yes'),
            _QMessageBox.No: ('Nein', 'No'),
            _QMessageBox.Ok: ('OK', 'OK'),
            _QMessageBox.Cancel: ('Abbrechen', 'Cancel'),
            _QMessageBox.Save: ('Speichern', 'Save'),
            _QMessageBox.Discard: ('Verwerfen', 'Discard'),
            _QMessageBox.Retry: ('Erneut versuchen', 'Retry'),
            _QMessageBox.Close: ('Schließen', 'Close'),
        }
        from .i18n import lang
        for button, (de, en) in texts.items():
            widget = dialog.button(button)
            if widget is not None:
                widget.setText(en if lang() == 'en' else de)
        if default != _QMessageBox.NoButton and dialog.button(default):
            dialog.setDefaultButton(default)
        result = dialog.exec()
        return _QMessageBox.StandardButton(result)

    @staticmethod
    def warning(parent, title, text, buttons=_QMessageBox.Ok,
                defaultButton=_QMessageBox.NoButton):
        return QMessageBox._localized_dialog(_QMessageBox.Warning, parent, title,
                                              text, buttons, defaultButton)

    @staticmethod
    def information(parent, title, text, buttons=_QMessageBox.Ok,
                    defaultButton=_QMessageBox.NoButton):
        return QMessageBox._localized_dialog(_QMessageBox.Information, parent, title,
                                              text, buttons, defaultButton)

    @staticmethod
    def question(parent, title, text, buttons=_QMessageBox.Yes | _QMessageBox.No,
                 defaultButton=_QMessageBox.NoButton):
        return QMessageBox._localized_dialog(_QMessageBox.Question, parent, title,
                                              text, buttons, defaultButton)

    @staticmethod
    def critical(parent, title, text, buttons=_QMessageBox.Ok,
                 defaultButton=_QMessageBox.NoButton):
        return QMessageBox._localized_dialog(_QMessageBox.Critical, parent, title,
                                              text, buttons, defaultButton)


class QFileDialog(_QFileDialog):
    @staticmethod
    def getSaveFileName(parent=None, caption='', *args, **kwargs):
        return _QFileDialog.getSaveFileName(parent, localized(caption), *args, **kwargs)
    @staticmethod
    def getExistingDirectory(parent=None, caption='', *args, **kwargs):
        return _QFileDialog.getExistingDirectory(parent, localized(caption), *args, **kwargs)

# v0.9.3.10: retranslate existing widgets in place. We deliberately do not
# reconstruct pages, which would reset scrollbars and destroy running workers.
def original_text(text):
    if not isinstance(text, str):
        return text
    from .i18n import EN, EN_MORE
    reverse = {english: german for mapping in (EN, EN_MORE) for german, english in mapping.items()}
    reverse.update({english.upper(): german.upper() for mapping in (EN, EN_MORE)
                    for german, english in mapping.items()})
    return reverse.get(text, text)


def retranslate_widgets(root):
    from PySide6.QtWidgets import QWidget
    for widget in [root, *root.findChildren(QWidget)]:
        handler = getattr(widget, 'retranslate', None)
        if callable(handler):
            handler()
