"""Keep the complete existing STAAD workflows inside the productivity suite."""
from pathlib import Path

from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QFileDialog, QToolButton, QMenu, QHeaderView, QSizePolicy, QStyledItemDelegate, QLineEdit

from .qt_pages import DJPage, RackPage
from .jobs import GeneratedParameterCommands
from .qt_widgets import button, label
from .core.geometry import build_rack_plan
from .core.peb import geometry_commands


class ParameterValueDelegate(QStyledItemDelegate):
    """A full-width numeric editor which preserves small engineering values."""
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAccessibleName('Edit parameter value')
        validator = QDoubleValidator(editor)
        validator.setLocale(QLocale.c())
        validator.setDecimals(12)
        editor.setValidator(validator)
        return editor

    def setEditorData(self, editor, index):
        editor.setText(format(float(index.data(Qt.ItemDataRole.EditRole)), '.15g'))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)


class ProductivityParametersPage(DJPage):
    """The existing concrete/steel parameter generator inside the suite."""
    feature = 'parameters'

    def run(self, operation, *, cad=False, cad_system="STAAD"):
        return super().run(operation, cad=cad, cad_system=cad_system)

    def __init__(self, window, palette=None):
        super().__init__(window)
        self.palette = palette
        self.snapshot, self.categories = None, {}
        self.restore_state('dj')
        from .qt_style import staad_palette
        self.form.setObjectName('parameterForm')
        self.form.setPalette(staad_palette())
        self.form.setAutoFillBackground(True)
        toolbar = self.body.itemAt(0).layout()
        menu = QMenu(self)
        while toolbar.count() > 1:
            action = toolbar.takeAt(1).widget()
            action.hide()
            menu.addAction(action.text(), action.click)
        options = QToolButton()
        options.setText('Presets')
        options.setToolTip('Save or load a preset; enable or disable all parameters')
        options.setMenu(menu)
        options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(options)
        self.parameter_context = label('', 'parameterContext', True)
        self.parameter_context.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.body.insertWidget(self.body.indexOf(self.tabs) + 1, self.parameter_context)
        for kind, table in self.parameter_tables.items():
            table.setItemDelegateForColumn(2, ParameterValueDelegate(table))
            table.setWordWrap(True)
            table.verticalHeader().setMinimumSectionSize(32)
            table.selectionModel().currentRowChanged.connect(lambda current, previous, k=kind: self.show_parameter_context(k, current.row()))
            table.selectRow(0)
        self.tabs.currentChanged.connect(self.update_parameter_layout)
        self.parameter_toolbar = toolbar
        self.preview_hint = self.tabs.widget(2).layout().itemAt(0).widget()
        self.output.setMinimumHeight(110)
        # The table already scrolls. Let it fill the editor instead of nesting it
        # inside a second scrolling form with its own preferred height.
        self.layout().removeWidget(self.content_scroll)
        self.content_scroll.takeWidget()
        self.content_scroll.hide()
        self.layout().insertWidget(1, self.form, 1)
        for index in reversed(range(self.body.count())):
            if self.body.itemAt(index).spacerItem():
                self.body.takeAt(index)

    def show_parameter_context(self, kind, row):
        if row < 0:
            return
        parameter = self.models[kind].parameters[row]
        self.parameter_context.setText('Scope: ' + parameter.scope)
        self.parameter_context.setToolTip(parameter.description)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_parameter_layout()

    def update_parameter_layout(self, *args):
        compact = self.width() < 700
        preview = self.tabs.currentIndex() == 2
        if hasattr(self, 'parameter_toolbar'):
            for index in range(self.parameter_toolbar.count()):
                widget = self.parameter_toolbar.itemAt(index).widget()
                if widget:
                    widget.setVisible(not (compact and preview))
            self.preview_hint.setVisible(not compact)
        titles = ('Concrete', 'Steel', 'Preview') if compact else ('Concrete parameters', 'Steel parameters', 'Command preview')
        for index, title in enumerate(titles):
            self.tabs.setTabText(index, title)
            self.tabs.setTabToolTip(index, ('Concrete parameters', 'Steel parameters', 'Command preview')[index])
        for table in self.parameter_tables.values():
            header = table.horizontalHeader()
            table.setColumnHidden(3, compact)
            table.setColumnHidden(4, compact)
            for column in range(5):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(0, 38)
            table.setColumnWidth(2, 120)
            table.setColumnWidth(3, 170)
            if compact:
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                table.setColumnWidth(1, 205)
                header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
                table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.resizeRowsToContents()
        self.parameter_context.setVisible(compact and self.tabs.currentIndex() < 2)
        if self.tabs.currentIndex() < 2:
            kind = ('concrete', 'steel')[self.tabs.currentIndex()]
            self.show_parameter_context(kind, max(0, self.parameter_tables[kind].currentIndex().row()))

    def restore_state(self, key='dj'):
        if getattr(self, '_restored_manual_state', False):
            return
        DJPage.restore_state(self, 'dj')
        self._restored_manual_state = True

    def save_state(self):
        DJPage.save_state(self)

    def set_snapshot(self, snapshot, publish=True):
        self.snapshot = snapshot
        if publish and self.palette is not None:
            self.palette.share_snapshot(snapshot, 'STAAD scan (cached)', self)

    def invalidate_mapping(self, *args):
        pass

    def on_event(self, kind, value):
        super().on_event(kind, value)
        if kind == 'target':
            self.target.hide()  # Full path remains available in Activity.

    def on_success(self, result):
        super().on_success(result)
        if isinstance(result, GeneratedParameterCommands):
            summary = f'{result.member_count:,} members · {result.warning_count:,} warnings'
            self.output_stats.setText(summary)
            self.output_stats.setToolTip(str(result))
            self.target.hide()
            self.feedback_text('Commands ready' if not result.warning_count else 'Commands ready — review warnings',
                               'success' if not result.warning_count else 'warning')
            self.feedback.setToolTip(str(result))

    def on_finished(self):
        super().on_finished()
        self.runtime.hide()


class ProductivityRackPage(RackPage):
    """The full existing rack modeler with an additional standalone export."""
    feature = 'rack'

    def run(self, operation, *, cad=False, cad_system="STAAD"):
        return super().run(operation, cad=cad, cad_system=cad_system)

    def __init__(self, window, palette=None):
        super().__init__(window)
        self.palette = palette
        self.snapshot, self.categories = None, {}
        self.export_button = button('Export STAAD file', self.export_staad, True)
        # Native arrows keep the embedded numeric editor visible on Windows Qt.
        for field in (self.base, self.depth):
            field.setButtonSymbols(field.ButtonSymbols.UpDownArrows)
        self.action_bar.insertWidget(self.action_bar.indexOf(self.generate_button), self.export_button)
        self.restore_state('rack')
        self.update_preview()

    def restore_state(self, key='rack'):
        if getattr(self, '_restored_rack_state', False):
            return
        RackPage.restore_state(self, 'rack')
        self._restored_rack_state = True

    def update_preview(self):
        super().update_preview()
        if hasattr(self, 'export_button'):
            self.export_button.setEnabled(not self.busy and not self.geometry_invalid)

    def set_snapshot(self, snapshot, publish=True):
        # Rack generation uses its own complete configuration and verifies a
        # blank model on execution; it does not use cached selection geometry.
        pass

    def invalidate_mapping(self, *args):
        pass

    def export_staad(self):
        if self.busy:
            return
        try:
            text = geometry_commands(build_rack_plan(self.configuration()), 'METER')
            folder = str(self.window.settings.value('folders/productivity', str(Path.home())))
            path, _ = QFileDialog.getSaveFileName(self, 'Export pipe rack geometry',
                                                 str(Path(folder) / 'pipe-rack.std'),
                                                 'STAAD input files (*.std)')
            if not path:
                return
            destination = Path(path)
            if destination.suffix.lower() != '.std':
                destination = destination.with_suffix('.std')
            destination.write_text(text, encoding='utf-8')
            self.window.settings.setValue('folders/productivity', str(destination.parent))
            self.save_state()
            self.feedback_text('STAAD geometry exported to ' + str(destination), 'success')
        except (OSError, ValueError) as error:
            self.invalid(str(error))
