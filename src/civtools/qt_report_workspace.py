"""Compact presentation for the Excel publisher; publishing logic stays on its page."""
from pathlib import Path
from functools import lru_cache

from PySide6.QtCore import Qt, QSize, QTimer, QUrl, QRect, Signal, QEvent
from PySide6.QtGui import QAction, QIcon, QDesktopServices, QPixmap, QPainter, QColor, QPen, QDrag, QIntValidator
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QFrame, QPushButton, QToolButton, QMenu, QDialog, QDialogButtonBox, QTabWidget,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter, QScrollArea,
    QStackedWidget, QListWidget, QProgressBar, QSizePolicy, QStyle, QMessageBox)
from .qt_widgets import ComboBox, CheckBox, DoubleSpinBox, SpinBox, button


STYLE = '''
QWidget#reportPublisher { background: #F5F8FA; }
QWidget#reportPublisher, QDialog#reportSettings { font-size: 12px; }
QWidget#reportPublisher QLabel#publisherTitle { font-size: 19px; font-weight: 600; color: #193E58; }
QWidget#reportPublisher QLabel#publisherCaption { color: #748895; font-size: 11px; }
QWidget#reportPublisher QPushButton, QWidget#reportPublisher QToolButton,
QDialog#reportSettings QPushButton, QDialog#reportSettings QToolButton { padding: 5px 11px; min-height: 21px; border-radius: 5px; }
QWidget#reportPublisher QToolButton { background: white; color: #245B7A; border: 1px solid #D5E4EC; }
QWidget#reportPublisher QToolButton::menu-button { border-left: 1px solid #D5E4EC; width: 18px; }
QWidget#reportPublisher QToolButton#overflow { padding: 5px 3px; }
QWidget#reportPublisher QToolButton#overflow::menu-indicator { width: 0; height: 0; }
QWidget#reportPublisher QPushButton#orderMove { background: white; color: #607D90; border: 1px solid #D5E4EC; padding: 5px 3px; }
QWidget#reportPublisher QMenu { background: white; color: #233B4A; border: 1px solid #D5E4EC; padding: 4px; }
QWidget#reportPublisher QMenu::item { padding: 7px 18px; }
QWidget#reportPublisher QMenu::item:selected { background: #E6F3FA; color: #176FA5; }
QWidget#reportPublisher QLineEdit, QWidget#reportPublisher QComboBox,
QWidget#reportPublisher QAbstractSpinBox, QDialog#reportSettings QLineEdit,
QDialog#reportSettings QComboBox, QDialog#reportSettings QAbstractSpinBox { padding: 4px 7px; min-height: 20px; border-radius: 5px; }
QWidget#reportPublisher QAbstractSpinBox QLineEdit,
QDialog#reportSettings QAbstractSpinBox QLineEdit { border: none; padding: 0; min-height: 0; }
QWidget#reportPublisher QLineEdit#reportPageNumber { background: #FFFFFF; color: #193E58; border: 1px solid #B8CCD7; padding: 4px 8px; font-weight: 600; selection-background-color: #C9E6F5; selection-color: #193E58; }
QWidget#reportPublisher QCheckBox, QDialog#reportSettings QCheckBox { padding: 3px 0; spacing: 7px; }
QWidget#reportPublisher QCheckBox::indicator, QDialog#reportSettings QCheckBox::indicator { width: 15px; height: 15px; }
QFrame#reportList { background: white; border: 1px solid #DEE7ED; border-radius: 7px; }
QWidget#reportPublisher QTreeWidget { border: none; background: white; outline: none; font-size: 12px; }
QWidget#reportPublisher QTreeWidget::item { padding: 7px 2px; border: none; }
QWidget#reportPublisher QTreeWidget::item:selected { background: #E9F3FA; color: #194865; }
QWidget#reportPublisher QTreeWidget::item:hover { background: #F3F8FC; }
QWidget#reportPublisher QTreeWidget::indicator { width: 14px; height: 14px; }
QWidget#reportPublisher QHeaderView::section { background: white; padding: 5px; font-size: 10px; color: #899BA7; border: none; }
QFrame#previewSurface { background: #EAF0F4; border: 1px solid #DEE7ED; border-radius: 7px; }
QFrame#previewSurface QScrollArea, QFrame#previewSurface QScrollArea > QWidget { background: transparent; border: none; }
QLabel#emptyTitle { font-size: 19px; font-weight: 600; color: #38576C; }
QLabel#emptyCopy { color: #8094A1; font-size: 12px; }
QWidget#reportPublisher QListWidget { background: transparent; border: none; border-radius: 0; }
QWidget#reportPublisher QListWidget::item { padding: 3px; color: #6A8495; border-radius: 4px; }
QWidget#reportPublisher QListWidget::item:selected { background: #D9E8F2; }
QWidget#reportPublisher QSplitter::handle { background: transparent; width: 9px; }
QWidget#reportPublisher QPushButton#textAction { background: transparent; border: none; color: #607D90; padding: 3px 6px; font-weight: 400; }
QWidget#reportPublisher QPushButton#textAction:hover { background: #E8F1F7; color: #176FA5; }
QWidget#reportPublisher QLabel#reportStatus { font-size: 11px; color: #738997; }
QDialog#reportSettings { background: #F5F8FA; }
QDialog#reportSettings QTabWidget::pane { background: white; }
QDialog#reportSettings QTabBar::tab { padding: 6px 16px; font-size: 12px; }
QDialog#reportSettings QLabel#settingsScope { color: #627E91; font-size: 11px; padding-bottom: 5px; }
'''


class PageNumberBox(QLineEdit):
    """A directly painted, editable page field without a spin box's nested editor."""
    valueChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self._value = 1
        self._maximum = 1
        self.editing = False
        self.setObjectName('reportPageNumber')
        self.setValidator(QIntValidator(0,2147483647,self))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName('Current page')
        self.setText('1')
        self.textEdited.connect(self.begin_edit)
        self.editingFinished.connect(self.commit)
        self.update_size()

    def begin_edit(self, text):
        self.editing = True

    def value(self):
        return self._value

    def maximum(self):
        return self._maximum

    def setValue(self, number):
        number = max(1,min(int(number),self._maximum))
        changed = number != self._value
        self._value = number
        self.editing = False
        self.setText(str(number))
        if changed:
            self.valueChanged.emit(number)

    def commit(self):
        if not self.editing:
            return
        draft = self.text().strip()
        number = max(1,min(int(draft),self._maximum)) if draft else self._value
        self.editing = False
        self._value = number
        self.setText(str(number))
        if draft:
            self.valueChanged.emit(number)

    def set_current_page(self, number):
        self._value = max(1,min(number,self._maximum))
        if not self.editing and self.text() != str(self._value):
            self.setText(str(self._value))

    def set_page_count(self, count):
        self._maximum = max(1,count)
        self.set_current_page(self._value)
        self.setToolTip(f'Type a page number from 1 to {self._maximum} and press Enter')
        self.update_size()

    def update_size(self):
        digits = max(2,len(str(self._maximum)))
        self.setFixedWidth(max(60,self.fontMetrics().horizontalAdvance('8'*digits)+28))
        self.setMinimumHeight(max(32,self.fontMetrics().height()+14))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange) and hasattr(self,'_maximum'):
            self.update_size()

    def focusOutEvent(self, event):
        self.commit()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
            self.commit()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.editing = False
            self.setText(str(self._value))
            event.accept()
        else:
            super().keyPressEvent(event)


class PreviewLabel(QWidget):
    """Continuous PDF canvas with a bounded cache of visible page images."""
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.path = ''
        self.rects = []
        self.images = {}
        self.pending = set()
        self.generation = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.load_visible)

    def clear(self):
        self.generation += 1
        self.path = ''
        self.rects = []
        self.images.clear()
        self.pending.clear()
        self.timer.stop()
        self.update()

    def setText(self, text):
        self.owner.preview_stack.setCurrentIndex(0)
        self.owner.empty_title.setText('Prepare to preview' if self.owner.records else 'Drop your Excel reports')
        self.owner.empty_copy.setText('Choose Prepare to check the page layouts.' if self.owner.records else 'Add a folder or drop files here to get started.')
        self.owner.preview_nav.hide()
        self.clear()

    def pixmap(self):
        return self.images.get(self.owner.page.value()-1)

    def set_document(self, path, sizes, zoom, fit_width):
        self.clear()
        self.path = path
        self.scales = [max(.15,min(2.5,fit_width/w)) if fit_width else zoom for w,h in sizes]
        dimensions = [(round(w*s),round(h*s)) for (w,h),s in zip(sizes,self.scales)]
        width = max((w for w,h in dimensions),default=0)+36
        y = 18
        for w,h in dimensions:
            self.rects.append(QRect((width-w)//2,y,w,h))
            y += h+18
        self.setFixedSize(width,y)
        self.owner.preview_stack.setCurrentIndex(1)
        self.owner.preview_nav.show()
        self.go_to_page(self.owner.page.value())

    def go_to_page(self, number):
        if self.rects:
            index = max(0,min(number-1,len(self.rects)-1))
            self.owner.preview_scroll.verticalScrollBar().setValue(self.rects[index].top()-18)
            self.timer.start()

    def visible_pages(self):
        if not self.path or self.path != self.owner.preview_path:
            return []
        scroll = self.owner.preview_scroll
        top = scroll.verticalScrollBar().value()
        bottom = top+scroll.viewport().height()
        return [i for i,r in enumerate(self.rects) if r.bottom()>=top and r.top()<=bottom]

    def update_current_page(self):
        visible = self.visible_pages()
        if not visible:
            return
        top = self.owner.preview_scroll.verticalScrollBar().value()
        bottom = top+self.owner.preview_scroll.viewport().height()
        current = max(visible,key=lambda i:min(bottom,self.rects[i].bottom())-max(top,self.rects[i].top()))
        self.owner.page.set_current_page(current+1)
        self.owner.thumbnails.setCurrentRow(current)

    def scrolled(self, *args):
        self.update_current_page()
        self.timer.start()

    def load_visible(self):
        visible = self.visible_pages()
        if not visible:
            return
        self.update_current_page()
        keep = set(range(max(0,visible[0]-1),min(len(self.rects),visible[-1]+2)))
        self.images = {i:image for i,image in self.images.items() if i in keep}
        for index in visible:
            if index in self.images or index in self.pending:
                continue
            self.pending.add(index)
            generation = self.generation
            payload = dict(path=self.path,page=index,zoom=self.scales[index])
            def done(result,index=index,generation=generation):
                if generation != self.generation:
                    return
                self.pending.discard(index)
                pixmap = QPixmap()
                pixmap.loadFromData(result['image'])
                self.images[index] = pixmap
                self.update(self.rects[index])
                self.timer.start()
            self.owner.run_job(lambda report,payload=payload:self.owner.window.pdf.call('report',report,'preview',payload),done,False)
        self.update()

    def paintEvent(self,event):
        painter = QPainter(self)
        for index,rect in enumerate(self.rects):
            if not rect.intersects(event.rect()):
                continue
            painter.fillRect(rect,Qt.GlobalColor.white)
            if index in self.images:
                painter.drawPixmap(rect,self.images[index])
            else:
                painter.setPen(QColor('#748895'))
                painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,f'Page {index+1}')


class StatusLabel(QLabel):
    """Elide dynamic text cleanly and retain its complete value for tooltips."""
    def __init__(self,text='',parent=None):
        super().__init__('',parent)
        self.full_text = text
        self.setText(text)

    def setText(self, text):
        self.full_text = text
        self.setToolTip(text)
        self.refresh_text()

    def refresh_text(self):
        super().setText(self.fontMetrics().elidedText(self.full_text,Qt.TextElideMode.ElideRight,max(0,self.contentsRect().width())))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.refresh_text()


class ReportTree(QTreeWidget):
    """Reorder siblings without allowing sheets to move into another workbook."""
    def __init__(self,owner):
        super().__init__()
        self.owner = owner
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def startDrag(self, supported_actions):
        # dropEvent moves the records and rebuilds the tree. Qt's default
        # startDrag would then remove the original rows a second time.
        if self.owner.busy or len(self.selectedItems()) != 1:
            return
        drag = QDrag(self)
        drag.setMimeData(self.mimeData(self.selectedItems()))
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            drag.deleteLater()

    def dropEvent(self,event):
        if self.owner.busy or event.source() is not self:
            event.ignore()
            return
        items = self.selectedItems()
        if len(items)!=1:
            event.ignore()
            return
        item = items[0]
        source,name = self.owner.key(item)
        target = self.itemAt(event.position().toPoint())
        if not name and target is not None and target.parent() is not None:
            target = target.parent()
        parent = item.parent()
        if target is not None and target.parent() is not parent:
            event.ignore()
            return
        siblings = [parent.child(i) for i in range(parent.childCount())] if parent else [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        old = siblings.index(item)
        index = len(siblings) if target is None else siblings.index(target)+(event.position().y()>self.visualItemRect(target).center().y())
        if index>old:
            index-=1
        self.owner.reorder_item(source,name,index)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()


@lru_cache(maxsize=8)
def control_icon(kind):
    """Small vector marks share the same stroke and colour as suite controls."""
    pixmap = QPixmap(32,32)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('#527A94'),1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    if kind=='more':
        painter.setBrush(QColor('#527A94'))
        painter.setPen(Qt.PenStyle.NoPen)
        for x in (3,7,11):
            painter.drawEllipse(x,7,2,2)
    else:
        points = ((9,4,5,8),(5,8,9,12)) if kind=='previous' else ((6,4,10,8),(10,8,6,12))
        for coords in points:
            painter.drawLine(*coords)
    painter.end()
    return QIcon(pixmap)


def action(menu, text, callback):
    item = menu.addAction(text)
    item.triggered.connect(lambda checked=False:callback())
    return item


@lru_cache(maxsize=8)
def status_icon(color):
    pixmap = QPixmap(20,20)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(2,2,6,6)
    painter.end()
    return QIcon(pixmap)


def tool(text, parent=None):
    result = QToolButton(parent)
    result.setText(text)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    return result


def build_workspace(page):
    p = page
    p.setObjectName('reportPublisher')
    p.setStyleSheet(STYLE)
    root = QVBoxLayout(p)
    root.setContentsMargins(14,10,14,12)
    root.setSpacing(10)
    p.navigation = QHBoxLayout()
    title = QLabel('Excel to PDF')
    title.setObjectName('publisherTitle')
    p.navigation.addWidget(title)
    p.navigation.addStretch()
    root.addLayout(p.navigation)

    p.input_bar = QWidget()
    toolbar = QHBoxLayout(p.input_bar)
    toolbar.setContentsMargins(0,0,0,0)
    toolbar.setSpacing(7)
    # A plain content-sized button avoids the split-button arrow stealing label space.
    p.add_reports_button = button('Add reports',p.add_folder,True)
    p.add_reports_button.setIcon(QIcon())
    p.add_reports_button.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Fixed)
    p.add_reports_button.setToolTip('Add a folder of Excel reports. Use More for individual files.')
    toolbar.addWidget(p.add_reports_button)
    p.clear_button = button('Remove all',p.remove_all,True)
    p.clear_button.setToolTip('Remove all reports and return to the start screen')
    p.clear_button.hide()
    toolbar.addWidget(p.clear_button)
    p.drop_hint = StatusLabel('A4  ·  Auto orientation  ·  Fit all columns')
    p.drop_hint.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
    p.drop_hint.setObjectName('publisherCaption')
    toolbar.addWidget(p.drop_hint,1)
    p.layout_toggle = button('Settings',lambda:show_settings(p),True)
    p.layout_toggle.setIcon(QIcon())
    toolbar.addWidget(p.layout_toggle)
    more = tool('')
    more.setIcon(control_icon('more'))
    more.setIconSize(QSize(16,16))
    more.setObjectName('overflow')
    more.setFixedWidth(32)
    more.setAccessibleName('More report actions')
    more.setToolTip('More report actions')
    menu = QMenu(more)
    action(menu,'Add files…',p.add_files)
    menu.addSeparator()
    p.retry_button = action(menu,'Retry exceptions',lambda:p.prepare(exceptions_only=True))
    p.quick_button = action(menu,'Prepare and export',lambda:p.prepare(True))
    action(menu,'Undo layout change',p.undo_layout)
    menu.addSeparator()
    p.open_folder_action = action(menu,'Open output folder',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(p.output.text())))
    more.setMenu(menu)
    more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    toolbar.addWidget(more)
    root.addWidget(p.input_bar)

    p.splitter = QSplitter()
    p.splitter.setChildrenCollapsible(False)
    sidebar = QFrame()
    p.report_sidebar = sidebar
    sidebar.setObjectName('reportList')
    sidebar.setMinimumWidth(220)
    sidebar.setMaximumWidth(340)
    side = QVBoxLayout(sidebar)
    side.setContentsMargins(10,10,10,7)
    side.setSpacing(6)
    p.search = QLineEdit()
    p.search.setPlaceholderText('Find a report…')
    p.search.setClearButtonEnabled(True)
    p.search.textChanged.connect(p.filter_tree)
    side.addWidget(p.search)
    p.filter = ComboBox()
    p.filter.addItems(['All reports','Needs review','Failed'])
    p.filter.currentTextChanged.connect(p.filter_tree)
    side.addWidget(p.filter)
    p.tree = ReportTree(p)
    p.tree.setToolTip('Drag to reorder reports or sheets. Alt+Up / Alt+Down also moves the selection.')
    p.tree.setHeaderLabels(['REPORTS',''])
    p.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    p.tree.header().setStretchLastSection(False)
    p.tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.Fixed)
    p.tree.setColumnWidth(1,22)
    p.tree.setIconSize(QSize(10,10))
    p.tree.setIndentation(14)
    p.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    p.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
    p.tree.currentItemChanged.connect(p.selection_changed)
    p.tree.itemChanged.connect(p.inclusion_changed)
    p.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    p.tree.customContextMenuRequested.connect(lambda pos:tree_menu(p,pos))
    side.addWidget(p.tree,1)
    p.report_count = QLabel('No reports yet')
    p.report_count.setObjectName('publisherCaption')
    list_footer = QHBoxLayout()
    list_footer.addWidget(p.report_count,1)
    for direction,delta in [('previous',-1),('next',1)]:
        move = button('',lambda delta=delta:p.move_item(delta),True)
        move.setObjectName('orderMove')
        # Use the same small vector strokes, rotated for vertical movement.
        pixmap = control_icon(direction).pixmap(16,16)
        from PySide6.QtGui import QTransform
        move.setIcon(QIcon(pixmap.transformed(QTransform().rotate(90))))
        move.setToolTip('Move up' if delta<0 else 'Move down')
        move.setAccessibleName(move.toolTip())
        move.setFixedWidth(34)
        list_footer.addWidget(move)
    side.addLayout(list_footer)
    p.splitter.addWidget(sidebar)
    sidebar.hide()

    surface = QFrame()
    surface.setObjectName('previewSurface')
    canvas = QVBoxLayout(surface)
    canvas.setContentsMargins(6,6,6,6)
    canvas.setSpacing(3)
    p.preview_nav = QWidget()
    nav = QHBoxLayout(p.preview_nav)
    nav.setContentsMargins(5,0,5,3)
    p.preview_name = StatusLabel('Preview')
    p.preview_name.setObjectName('publisherCaption')
    p.preview_name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
    nav.addWidget(p.preview_name,1)
    previous = button('',lambda:p.page.setValue(p.page.value()-1),True)
    previous.setIcon(control_icon('previous'))
    previous.setToolTip('Previous page')
    previous.setAccessibleName('Previous page')
    previous.setMinimumWidth(36)
    nav.addWidget(previous)
    page_caption = QLabel('Page')
    page_caption.setObjectName('publisherCaption')
    nav.addWidget(page_caption)
    p.page = PageNumberBox()
    p.page.set_page_count(1)
    p.page.valueChanged.connect(lambda value:p.preview.go_to_page(value))
    nav.addWidget(p.page)
    p.page_total = QLabel('/ 1')
    p.page_total.setObjectName('publisherCaption')
    nav.addWidget(p.page_total)
    following = button('',lambda:p.page.setValue(p.page.value()+1),True)
    following.setIcon(control_icon('next'))
    following.setToolTip('Next page')
    following.setAccessibleName('Next page')
    following.setMinimumWidth(36)
    nav.addWidget(following)
    p.zoom = ComboBox()
    p.zoom.addItems(['Fit width','75%','100%','125%','150%'])
    p.zoom.setCurrentText('Fit width')
    p.zoom.setSizeAdjustPolicy(ComboBox.SizeAdjustPolicy.AdjustToContents)
    p.zoom.setMinimumContentsLength(9)
    p.zoom.currentTextChanged.connect(p.render_preview)
    nav.addWidget(p.zoom)
    open_pdf = button('Open',p.open_pdf,True)
    nav.addWidget(open_pdf)
    canvas.addWidget(p.preview_nav)
    p.preview_nav.hide()
    p.preview_stack = QStackedWidget()
    empty = QWidget()
    el = QVBoxLayout(empty)
    el.setSpacing(9)
    el.addStretch()
    mark = QLabel()
    from .qt_artwork import product_icon
    mark.setPixmap(product_icon('excel',48).pixmap(48,48))
    mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
    el.addWidget(mark)
    p.empty_title = QLabel('Drop your Excel reports')
    p.empty_title.setObjectName('emptyTitle')
    p.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    el.addWidget(p.empty_title)
    p.empty_copy = QLabel('Add a folder or drop files here to get started.')
    p.empty_copy.setObjectName('emptyCopy')
    p.empty_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
    p.empty_copy.setWordWrap(True)
    el.addWidget(p.empty_copy)
    el.addStretch()
    p.preview_stack.addWidget(empty)
    document = QWidget()
    dl = QHBoxLayout(document)
    dl.setContentsMargins(0,0,0,0)
    dl.setSpacing(0)
    p.thumbnails = QListWidget()
    p.thumbnails.setFixedWidth(77)
    p.thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
    p.thumbnails.setFlow(QListWidget.Flow.TopToBottom)
    p.thumbnails.setWrapping(False)
    p.thumbnails.setMovement(QListWidget.Movement.Static)
    p.thumbnails.setGridSize(QSize(64,108))
    p.thumbnails.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    p.thumbnails.setIconSize(QSize(54,76))
    p.thumbnails.itemClicked.connect(lambda item:p.page.setValue(int(item.data(Qt.ItemDataRole.UserRole))+1))
    p.thumbnails.verticalScrollBar().valueChanged.connect(p.request_thumbnails)
    dl.addWidget(p.thumbnails)
    p.preview_scroll = QScrollArea()
    p.preview_scroll.setWidgetResizable(False)
    p.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
    p.preview = PreviewLabel(p)
    p.preview_scroll.setWidget(p.preview)
    p.preview_scroll.verticalScrollBar().valueChanged.connect(p.preview.scrolled)
    dl.addWidget(p.preview_scroll,1)
    p.preview_stack.addWidget(document)
    canvas.addWidget(p.preview_stack,1)
    p.reason = QLabel('')
    p.reason.setWordWrap(True)
    p.reason.hide()
    p.details_button = button('Layout details',lambda:QMessageBox.information(p,'Layout details',p.reason.text()),True)
    p.details_button.setObjectName('textAction')
    p.details_button.hide()
    detail_row = QHBoxLayout()
    detail_row.addWidget(p.details_button)
    detail_row.addStretch()
    canvas.addLayout(detail_row)
    p.reason.setParent(surface)
    p.splitter.addWidget(surface)
    p.splitter.setStretchFactor(1,1)
    p.splitter.setSizes([250,730])
    root.addWidget(p.splitter,1)
    p.thumbnail_path = ''
    p.thumbnail_pending = set()
    p.thumbnail_timer = QTimer(p)
    p.thumbnail_timer.setSingleShot(True)
    p.thumbnail_timer.setInterval(120)
    p.thumbnail_timer.timeout.connect(p.load_thumbnails)
    p.preview_resize_timer = QTimer(p)
    p.preview_resize_timer.setSingleShot(True)
    p.preview_resize_timer.setInterval(180)
    p.preview_resize_timer.timeout.connect(lambda:p.render_preview() if p.preview_path and p.zoom.currentText()=='Fit width' else None)
    p.preview_scroll.viewport().installEventFilter(p)
    p.splitter.splitterMoved.connect(lambda *args:p.preview_resize_timer.start())

    build_settings(p)
    p.combined_toggle = CheckBox('Combined report')
    p.combined_toggle.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Fixed)
    p.combined_toggle.setChecked(p.combined.isChecked())
    toolbar.insertWidget(2,p.combined_toggle)
    p.combined_toggle.toggled.connect(p.combined.setChecked)
    p.combined.toggled.connect(p.combined_toggle.setChecked)
    for signal in (p.combined.toggled,p.contents.toggled,p.numbering.toggled,p.per_sheet.toggled,p.reviewed.toggled,p.cover.textChanged):
        signal.connect(p.schedule_combined_preview)
    p.combined_timer = QTimer(p)
    p.combined_timer.setSingleShot(True)
    p.combined_timer.setInterval(180)
    p.combined_timer.timeout.connect(lambda:p.preview_combined(automatic=True) if p.combined.isChecked() else None)
    from PySide6.QtGui import QKeySequence, QShortcut
    p.order_shortcuts = []
    for keys,delta in [('Alt+Up',-1),('Alt+Down',1)]:
        shortcut = QShortcut(QKeySequence(keys),p)
        shortcut.activated.connect(lambda delta=delta:p.move_item(delta))
        p.order_shortcuts.append(shortcut)
    p.progress = QProgressBar()
    p.progress.setTextVisible(False)
    p.progress.hide()
    root.addWidget(p.progress)
    footer = QHBoxLayout()
    footer.setSpacing(7)
    p.destination_button = button('Choose output folder',p.choose_output,True)
    p.destination_button.setObjectName('textAction')
    p.output.textChanged.connect(lambda text:update_destination(p,text))
    footer.addWidget(p.destination_button)
    p.feedback = StatusLabel('Add reports to begin')
    p.feedback.setObjectName('reportStatus')
    p.feedback.setMinimumWidth(0)
    p.feedback.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
    footer.addWidget(p.feedback,1)
    p.stop_button = tool('Stop')
    stop_default = QAction('Stop',p)
    stop_default.triggered.connect(p.stop.set)
    p.stop_button.setDefaultAction(stop_default)
    p.stop_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
    footer.addWidget(p.stop_button)
    p.kill_button = QAction('Stop now',p)
    p.kill_button.triggered.connect(p.stop_now.set)
    stop_menu = QMenu(p.stop_button)
    stop_menu.addAction(p.kill_button)
    p.stop_button.setMenu(stop_menu)
    p.prepare_button = button('Prepare',p.prepare,True)
    footer.addWidget(p.prepare_button)
    p.export_button = button('Export PDFs',p.export)
    footer.addWidget(p.export_button)
    root.addLayout(footer)


def build_settings(p):
    p.settings_dialog = QDialog(p)
    p.settings_dialog.setObjectName('reportSettings')
    p.settings_dialog.setStyleSheet(STYLE)
    p.settings_dialog.setWindowTitle('Report settings')
    p.settings_dialog.resize(430,510)
    outer = QVBoxLayout(p.settings_dialog)
    outer.setContentsMargins(16,14,16,14)
    p.scope = QLabel('All reports')
    p.scope.setObjectName('settingsScope')
    p.scope.setWordWrap(True)
    outer.addWidget(p.scope)
    p.editor = QTabWidget()
    outer.addWidget(p.editor,1)
    layout_page = QWidget()
    form = QFormLayout(layout_page)
    form.setSpacing(10)
    p.orientation = ComboBox()
    p.orientation.addItems(['Auto','Portrait','Landscape'])
    form.addRow('Orientation',p.orientation)
    p.paper = ComboBox()
    p.paper.addItems(['A4','A3'])
    form.addRow('Paper',p.paper)
    p.a3 = CheckBox('Allow A3 when needed')
    form.addRow('',p.a3)
    p.font = DoubleSpinBox()
    p.font.setRange(5,20)
    p.font.setSuffix(' pt')
    form.addRow('Minimum text',p.font)
    p.margin = DoubleSpinBox()
    p.margin.setRange(5,40)
    p.margin.setSuffix(' mm')
    form.addRow('Margins',p.margin)
    p.keep_sections = CheckBox('Keep sections together')
    form.addRow('',p.keep_sections)
    p.repeat_headings = CheckBox('Repeat table headings')
    form.addRow('',p.repeat_headings)
    hint = QLabel('All columns fit the page width.')
    hint.setObjectName('publisherCaption')
    form.addRow(hint)
    p.editor.addTab(layout_page,'Layout')

    export_page = QWidget()
    ef = QFormLayout(export_page)
    ef.setSpacing(10)
    p.combined = CheckBox('Combine into one report')
    p.contents = CheckBox('Contents page')
    p.numbering = CheckBox('Page numbers')
    p.per_sheet = CheckBox('Separate PDFs for sheets')
    p.cover = QLineEdit()
    p.cover.setPlaceholderText('Optional cover title')
    for control in (p.combined,p.contents,p.numbering,p.per_sheet):
        ef.addRow(control)
    ef.addRow('Cover',p.cover)
    p.combined_preview_button = button('Preview combined report',p.preview_combined,True)
    p.combined_preview_button.clicked.connect(p.settings_dialog.accept)
    ef.addRow(p.combined_preview_button)
    p.reviewed = CheckBox('Include reviewed exceptions')
    p.reviewed.setToolTip('Include prepared reports with warnings after reviewing their PDF previews.')
    ef.addRow(p.reviewed)
    p.output = QLineEdit()
    p.output.setPlaceholderText('Choose an output folder')
    out = QHBoxLayout()
    out.addWidget(p.output,1)
    out.addWidget(button('…',p.choose_output,True))
    ef.addRow('Save to',out)
    p.editor.addTab(export_page,'Export')

    advanced_page = QWidget()
    af = QFormLayout(advanced_page)
    af.setSpacing(9)
    p.area_mode = ComboBox()
    p.area_mode.addItems(['Existing or detect','Existing area','Detected content'])
    af.addRow('Print bounds',p.area_mode)
    p.area = QLineEdit()
    p.area.setPlaceholderText('Auto, or A1:L120')
    af.addRow('Print area',p.area)
    p.titles = QLineEdit()
    p.titles.setPlaceholderText('Keep existing, or 1:4')
    af.addRow('Title rows',p.titles)
    p.breaks = QLineEdit()
    p.breaks.setPlaceholderText('e.g. 40, 80, 120')
    af.addRow('Section rows',p.breaks)
    p.repair = CheckBox('Repair table row heights')
    p.recalculate = CheckBox('Recalculate before export')
    p.recalculate.setToolTip('May change calculation results. External connections and macros stay disabled.')
    p.recursive = CheckBox('Include subfolders')
    p.recursive.setChecked(True)
    for control in (p.repair,p.recalculate,p.recursive):
        af.addRow(control)
    p.preset = ComboBox()
    p.preset.setSizeAdjustPolicy(ComboBox.SizeAdjustPolicy.AdjustToContents)
    p.preset.addItem('Design calculation report')
    def preset_changed(name):
        if p.settings_dialog.isVisible():
            preset = getattr(p,'presets',{}).get(name,{})
            from .core.report_models import resolve_settings
            p.set_editor(resolve_settings(preset.get('batch',preset)))
        else:
            p.load_preset(name)
    p.preset.currentTextChanged.connect(preset_changed)
    presets = QHBoxLayout()
    presets.addWidget(p.preset,1)
    presets.addWidget(button('Save',p.save_preset,True))
    af.addRow('Preset',presets)
    p.editor.addTab(advanced_page,'Advanced')
    buttons = QHBoxLayout()
    def reset_editor():
        from .core.report_models import resolve_settings
        current = p.key(p.tree.currentItem())
        parent = p.records[current[0]]['overrides'] if current and current[1] else None
        p.set_editor(resolve_settings(p.batch,parent))
    reset = button('Reset',reset_editor,True)
    buttons.addWidget(reset)
    buttons.addStretch()
    buttons.addWidget(button('Cancel',p.settings_dialog.reject,True))
    def apply():
        try:
            settings = p.editor_settings()
        except ValueError as error:
            QMessageBox.information(p.settings_dialog,'Check settings',str(error))
            return
        current = p.key(p.tree.currentItem())
        inherited = p.effective(*current) if current else p.batch
        if settings != inherited:
            if p.tree.selectedItems():
                p.apply_selected()
            else:
                p.apply_batch()
        preset = getattr(p,'presets',{}).get(p.preset.currentText(),{})
        p.template_rules = preset.get('templates',p.template_rules)
        p.drop_hint.setText(f"{settings['paper']}  ·  {settings['orientation']} orientation  ·  Fit all columns")
        p.settings_dialog.accept()
    buttons.addWidget(button('Apply',apply))
    outer.addLayout(buttons)


def show_settings(p):
    original = dict(combined=p.combined.isChecked(),contents=p.contents.isChecked(),
                    numbering=p.numbering.isChecked(),per_sheet=p.per_sheet.isChecked(),
                    reviewed=p.reviewed.isChecked(),cover=p.cover.text(),output=p.output.text(),
                    recursive=p.recursive.isChecked(),preset=p.preset.currentText())
    current = p.key(p.tree.currentItem())
    if current:
        source,name = current
        p.set_editor(p.effective(source,name))
        p.scope.setText(name or Path(source).name)
    else:
        p.set_editor(p.batch)
        p.scope.setText('All reports')
    if p.settings_dialog.exec() != QDialog.DialogCode.Accepted:
        for key in ('combined','contents','numbering','per_sheet','reviewed','recursive'):
            getattr(p,key).setChecked(original[key])
        p.cover.setText(original['cover'])
        p.output.setText(original['output'])
        p.preset.blockSignals(True)
        p.preset.setCurrentText(original['preset'])
        p.preset.blockSignals(False)


def tree_menu(p,pos):
    if p.busy:
        return
    menu = QMenu(p.tree)
    action(menu,'Layout settings…',lambda:show_settings(p))
    action(menu,'Move up',lambda:p.move_item(-1))
    action(menu,'Move down',lambda:p.move_item(1))
    menu.addSeparator()
    action(menu,'Workbook password…',p.set_password)
    action(menu,'Remove',p.remove_selected)
    menu.exec(p.tree.viewport().mapToGlobal(pos))


def update_destination(p,text):
    # Keep a stable, short control; the complete destination stays in its tooltip/settings.
    p.destination_button.setText('Output folder' if text else 'Choose output folder')
    p.destination_button.setToolTip(text or 'Choose where to save your PDFs')
