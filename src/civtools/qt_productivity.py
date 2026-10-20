"""Local STAAD productivity suite, with reviewable command/file outputs."""
import csv
import io
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QSpinBox, QFileDialog, QMessageBox, QGridLayout, QToolButton, QMainWindow)

from .qt_pages import ToolPage, combo, number as numeric_field
from .qt_widgets import label, button, CheckBox
from .core.staad_productivity import (CATEGORIES, DOFS, ModelSnapshot, classify_members,
    group_commands, release_commands, renumber_plan, renumber_csv, combination_commands,
    read_combination_csv, tapered_commands, id_list)
from .core import staad_productivity_com as live


def number(*args):
    field = numeric_field(*args)
    # Keep native buttons: on some Windows Qt builds NoButtons + QSS collapses
    # the embedded line editor to a single pixel, hiding all numeric values.
    field.setButtonSymbols(field.ButtonSymbols.UpDownArrows)
    return field


from .qt_link_artwork import link_icon
from .core.link_generators import matrix_contributions

FEATURES = (
    ('select', 'Select'), ('renumber', 'Renum'), ('groups', 'Groups'),
    ('releases', 'Releases'), ('parameters', 'Dgn Prm'), ('tables', 'Tables'),
    ('combinations', 'Load Comb'), ('girders', 'Plate Grdrs'), ('rack', 'Pipe Rack'),
)
TITLES = dict(FEATURES)


class WorkflowWindow(QMainWindow):
    def __init__(self, palette, key):
        super().__init__()
        self.palette, self.key = palette, key
        self.page = WorkflowPage(palette.window, key, palette)
        self.setWindowTitle(TITLES[key] + ' | CivTools')
        self.setWindowIcon(link_icon(key))
        self.setCentralWidget(self.page)
        self.resize(700, 760)
        self.setMinimumSize(520, 480)
        geometry = palette.window.settings.value('windows/productivity/' + key)
        if geometry:
            self.restoreGeometry(geometry)

    def save_state(self):
        self.page.save_state()
        self.palette.window.settings.setValue('windows/productivity/' + self.key, self.saveGeometry())

    def closeEvent(self, event):
        self.save_state()
        event.ignore()
        self.hide()


class ProductivityPage(QWidget):
    """Compact launcher; each action retains its own independent workflow."""
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.children_windows = {}
        self.shared_snapshot = None
        self.snapshot_source = None
        self.buttons = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(label('STAAD tools', 'title'))
        layout.addWidget(label('CivTools | modeling utilities', 'muted'))
        grid = QGridLayout()
        grid.setSpacing(8)
        for index, (key, title) in enumerate(FEATURES):
            item = self.palette_button(key, title)
            grid.addWidget(item, index // 3, index % 3)
        layout.addLayout(grid)
        layout.addWidget(label('PEB structures', 'muted'))
        row = QHBoxLayout()
        row.setSpacing(6)
        for variant in 'ABCD':
            row.addWidget(self.palette_button('peb' + variant, 'PEB-' + variant))
        layout.addLayout(row)
        self.model_status = label('No model scanned. Open a utility or refresh STAAD.', 'muted', True)
        layout.addWidget(self.model_status)
        layout.addWidget(button('Refresh STAAD', self.refresh_model, True))
        layout.addStretch()

    @property
    def busy(self):
        return any(child.page.busy for child in self.children_windows.values())

    def palette_button(self, key, title):
        from PySide6.QtCore import QSize
        item = QToolButton()
        item.setText(title)
        item.setIcon(link_icon(key))
        item.setIconSize(QSize(80, 42))
        item.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        item.setMinimumSize(88, 82)
        item.setSizePolicy(item.sizePolicy().Policy.Expanding, item.sizePolicy().Policy.Preferred)
        item.setAccessibleName('Open ' + title)
        item.setStyleSheet('QToolButton { background: #F8F7EF; color: #245B4D; border: 1px solid #D4DFD4; border-radius: 9px; padding: 5px; } QToolButton:hover { background: #E6F0E6; border-color: #629780; } QToolButton:disabled { color: #8B968D; background: #F0F0E8; }')
        if key == 'rack' or key.startswith('peb'):
            item.setEnabled(False)
            item.setToolTip('Deferred: this structure generator will be added in a later update.')
        else:
            item.clicked.connect(lambda checked=False, k=key: self.open_feature(k))
            item.setToolTip('Open ' + title + ' in its own window')
        self.buttons[key] = item
        return item

    def open_feature(self, key):
        if key not in self.children_windows:
            self.children_windows[key] = WorkflowWindow(self, key)
            if self.shared_snapshot is not None:
                self.children_windows[key].page.set_snapshot(self.shared_snapshot, publish=False)
        child = self.children_windows[key]
        child.showNormal()
        child.raise_()
        child.activateWindow()
        return child.page

    def refresh_model(self):
        self.open_feature('select').scan()

    def share_snapshot(self, snapshot, source, owner=None):
        self.shared_snapshot, self.snapshot_source = snapshot, source
        self.model_status.setText(source + ': ' + snapshot.path)
        self.model_status.setToolTip('Cached model data. Live operations recheck the active STAAD model.')
        for child in self.children_windows.values():
            if child.page is not owner:
                child.page.set_snapshot(snapshot, publish=False)

    def invalidate_snapshot(self, reason):
        self.shared_snapshot = None
        self.snapshot_source = None
        self.model_status.setText(reason)
        for child in self.children_windows.values():
            page = child.page
            page.snapshot, page.categories = None, {}
            page.members.setRowCount(0)
            page.invalidate_mapping()
            page.model_caption.setText(reason)
            page.result_caption.setText('Scan the model again.')

    def restore_state(self, key):
        pass

    def save_state(self):
        for child in self.children_windows.values():
            child.save_state()
        # Application exit calls this after all workers finish. Closing just the
        # palette also hides its child windows while preserving their inputs.
        self.close_children()

    def close_children(self, *args):
        for child in self.children_windows.values():
            child.hide()


class WorkflowPage(ToolPage):
    def __init__(self, window, feature, palette=None):
        super().__init__(window, TITLES[feature], 'STAAD tools | ' + TITLES[feature], 'Modeling', artwork='productivity')
        self.feature = feature
        self.palette = palette
        self.snapshot_source = "Offline snapshot"
        self.active_categories = None
        self.mutating = False
        self.snapshot, self.categories, self.mapping = None, {}, None
        self.output_extension = '.txt'
        self.state_widgets = {}
        self.setObjectName('productivityWorkflow')
        self.setStyleSheet('QWidget#productivityWorkflow QAbstractSpinBox QLineEdit { border: none; padding: 0; min-height: 0; background: transparent; }')
        self.model_caption = label('Scan the active model or load a saved geometry snapshot.', 'muted', True)
        self.result_caption = label('', 'muted', True)
        self.result_nodes, self.result_cases = QLineEdit(), QLineEdit()
        self.members = QTableWidget(0, 6)
        self.members.setHorizontalHeaderLabels(['Member', 'Start', 'End', 'Category', 'Mid Y', 'Length'])
        self.members.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.members.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.members.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.members.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.members.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find member ID or category')
        self.category_filter = combo(['All categories', *CATEGORIES])
        self.search.textChanged.connect(self.filter_members)
        self.category_filter.currentTextChanged.connect(self.filter_members)
        self.apply_button = button('Apply renumber plan', self.apply_renumber)
        self.apply_button.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(button('Process Members' if feature == 'parameters' else 'Scan STAAD', self.scan))
        row.addWidget(button('Load snapshot', self.load_snapshot, True))
        row.addWidget(button('Save snapshot', self.save_snapshot, True))
        self.body.addLayout(row)
        self.body.addWidget(self.model_caption)
        if feature == 'select':
            self.build_selection_controls()
        if feature in ('select', 'renumber', 'groups', 'releases'):
            row = QHBoxLayout()
            row.addWidget(self.search, 1)
            row.addWidget(self.category_filter)
            self.body.addLayout(row)
            self.body.addWidget(self.members)
            row = QHBoxLayout()
            row.addWidget(button('Select visible', self.select_visible, True))
            row.addWidget(button('Select in STAAD', self.select_in_staad))
            self.body.addLayout(row)
        if feature == 'select':
            self.body.addWidget(button('Select support nodes', self.select_supports))
            self.role = combo(CATEGORIES)
            self.body.addWidget(self.role)
            self.body.addWidget(button('Assign role to selected rows', self.assign_role))
        elif feature == 'renumber':
            self.renumber_start = QSpinBox()
            self.renumber_start.setRange(1, 1_000_000_000)
            self.state_widgets['renumber_start'] = self.renumber_start
            self.renumber_start.valueChanged.connect(self.invalidate_mapping)
            self.body.addWidget(label('Starting member number'))
            self.body.addWidget(self.renumber_start)
            self.body.addWidget(button('Preview renumbering', self.preview_renumber))
            self.body.addWidget(self.apply_button)
        elif feature == 'groups':
            self.group_prefix = QLineEdit('CIV')
            self.state_widgets['group_prefix'] = self.group_prefix
            self.body.addWidget(label('Group prefix'))
            self.body.addWidget(self.group_prefix)
            self.body.addWidget(button('Preview groups', self.preview_groups))
            self.body.addWidget(button('Apply groups to STAAD', self.apply_groups))
        elif feature == 'releases':
            self.release_end = combo(['START', 'END', 'BOTH'])
            self.state_widgets['release_end'] = self.release_end
            self.body.addWidget(self.release_end)
            self.release_dofs = {}
            row = QHBoxLayout()
            for dof in DOFS:
                field = CheckBox(dof)
                field.setChecked(dof == 'MZ')
                self.release_dofs[dof] = field
                self.state_widgets[dof] = field
                row.addWidget(field)
            self.body.addLayout(row)
            self.body.addWidget(button('Preview releases for selected members', self.preview_releases))
            self.body.addWidget(button('Apply releases to STAAD', self.apply_releases))
        elif feature == 'tables':
            self._results_tab()
            self.state_widgets['result_kind'] = self.result_kind
            self.state_widgets.update(self.pedestal_dimensions)
            self.state_widgets.update(nodes=self.result_nodes, cases=self.result_cases)
        elif feature == 'girders':
            self._girder_tab()
            self.state_widgets.update(self.girder_dimensions)
            self.state_widgets.update(girder_ids=self.girder_ids, unit=self.girder_unit)
        elif feature == 'combinations':
            self.combination_csv = QPlainTextEdit('combination,title,case,factor\n101,ULS DL LL,1,1.5\n101,ULS DL LL,2,1.5')
            self.body.addWidget(label('Excel LOAD_COMB: case IDs on row 2, symbols on row 3, types on row 4; combination numbers in column A from row 5.', 'muted', True))
            row = QHBoxLayout()
            row.addWidget(button('Save Excel template', self.save_combination_template, True))
            row.addWidget(button('Import CSV / Excel', self.import_combinations, True))
            self.body.addLayout(row)
            self.body.addWidget(self.combination_csv)
            self.body.addWidget(button('Preview combinations', self.preview_combinations))
            self.state_widgets['csv'] = self.combination_csv
        elif feature == 'parameters':
            self.body.addWidget(label('Process Members first, then choose the design-parameter operation.', 'muted', True))
            self.body.addWidget(label('LY/LZ values are geometric length candidates. Each end joint is assumed restrained; review actual restraints before use. LX, UNL and LT depend on the design code and are omitted.', 'muted', True))
            self.design_actions = {}
            for key, title in [('columns', 'Columns LY / LZ candidates'), ('beams_dj', 'Beams DJ1 / DJ2'), ('beams_lengths', 'Beams LY / LZ candidates')]:
                action = button(title, lambda checked=False, mode=key: self.design_parameters(mode))
                self.body.addWidget(action)
                self.design_actions[key] = action
        self.output_caption = label('Generated output appears below for review.', 'muted', True)
        self.body.addWidget(self.output_caption)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(130)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.body.addWidget(self.output)
        row = QHBoxLayout()
        row.addWidget(button('Copy', self.copy_output, True))
        row.addWidget(button('Export preview', self.export_output))
        self.body.addLayout(row)
        self.restore_inputs()

    def _tab(self, title):
        return self.form, self.body

    def design_parameters(self, mode):
        def start():
            model = self.require_model()
            operation = getattr(live, 'process_design_parameters', None)
            if operation is None:
                raise ValueError('This design-parameter operation is awaiting backend validation.')
            self.run(lambda report: operation(model, mode, report), cad=True)
        self.guard(start)

    def restore_inputs(self):
        try:
            data = json.loads(str(self.window.settings.value('forms/productivity/' + self.feature, '{}')))
            for name, field in self.state_widgets.items():
                if name not in data:
                    continue
                value = data[name]
                if isinstance(field, QPlainTextEdit): field.setPlainText(str(value))
                elif isinstance(field, QLineEdit): field.setText(str(value))
                elif isinstance(field, CheckBox): field.setChecked(value is True)
                elif hasattr(field, 'setCurrentText'): field.setCurrentText(str(value))
                elif math.isfinite(float(value)): field.setValue(float(value) if not isinstance(field, QSpinBox) else int(value))
        except (ValueError, TypeError, AttributeError):
            self.feedback_text('Saved inputs could not be restored.', 'warning')
        for field in self.state_widgets.values():
            signal = field.textChanged if isinstance(field, (QLineEdit, QPlainTextEdit)) else field.toggled if isinstance(field, CheckBox) else field.currentTextChanged if hasattr(field, 'currentTextChanged') else field.valueChanged
            signal.connect(self.save_state)

    def save_state(self, *args):
        data = {}
        for name, field in self.state_widgets.items():
            data[name] = field.toPlainText() if isinstance(field, QPlainTextEdit) else field.text() if isinstance(field, QLineEdit) else field.isChecked() if isinstance(field, CheckBox) else field.currentText() if hasattr(field, 'currentText') else field.value()
        self.window.settings.setValue('forms/productivity/' + self.feature, json.dumps(data))

    def save_combination_template(self):
        def save():
            from openpyxl import Workbook
            path, _ = QFileDialog.getSaveFileName(self, 'Save LOAD_COMB template', self.last_folder() + '/load-combinations.xlsx', 'Excel workbook (*.xlsx)')
            if not path: return
            wb = Workbook()
            try:
                ws = wb.active
                ws.title = 'LOAD_COMB'
                for row in [('Combination', 'Primary load cases'), (None, 1, 2), (None, 'DL', 'LL'), (None, 'Dead', 'Live'), (101, 1.5, 1.5), (102, 1., 1.)]: ws.append(row)
                ws.freeze_panes = 'B5'
                wb.save(path)
            finally: wb.close()
            self.remember_folder(path)
            self.feedback_text('Saved template: ' + path, 'success')
        self.guard(save)

    def import_combinations(self):
        def load():
            path, _ = QFileDialog.getOpenFileName(self, 'Import load combinations', self.last_folder(), 'Load combinations (*.csv *.xlsx)')
            if not path: return
            if Path(path).suffix.lower() == '.xlsx':
                from openpyxl import load_workbook
                wb = load_workbook(path, read_only=True, data_only=False)
                try:
                    if 'LOAD_COMB' not in wb.sheetnames: raise ValueError('Workbook requires a LOAD_COMB worksheet.')
                    ws = wb['LOAD_COMB']
                    if ws.max_row > 204 or ws.max_column > 51: raise ValueError('Use at most 50 cases and 200 combinations.')
                    contributions = matrix_contributions(ws.iter_rows(values_only=True))
                    stream = io.StringIO()
                    writer = csv.writer(stream)
                    writer.writerow(['combination', 'title', 'case', 'factor'])
                    writer.writerows(contributions)
                    text = stream.getvalue()
                finally: wb.close()
            else:
                if Path(path).stat().st_size > 2_000_000: raise ValueError('CSV exceeds 2 MB.')
                text = Path(path).read_text(encoding='utf-8-sig')
            combination_commands(read_combination_csv(text))
            self.combination_csv.setPlainText(text)
            self.remember_folder(path)
        self.guard(load)

    def _results_tab(self):
        _, layout = self._tab('Results')
        layout.addWidget(label('Scan the active model first. Results are read from STAAD in its base units; '
                               'the workbook includes units and signed component envelopes.', 'muted', True))
        form = QFormLayout()
        self.result_kind = combo(['Reactions', 'Displacements', 'Pedestal'])
        self.result_nodes = QLineEdit()
        self.result_nodes.setPlaceholderText('Blank: supports for reactions, all nodes for displacements')
        self.result_cases = QLineEdit()
        self.result_cases.setPlaceholderText('Blank: all scanned cases; or 1, 2, 10 TO 15')
        form.addRow('Results', self.result_kind)
        form.addRow('Node IDs', self.result_nodes)
        form.addRow('Load case IDs', self.result_cases)
        layout.addLayout(form)
        self.result_caption = label('No model scanned.', 'muted', True)
        layout.addWidget(self.result_caption)
        self.pedestal_panel = QWidget()
        form = QFormLayout(self.pedestal_panel)
        self.pedestal_dimensions = {}
        for name, title, default in [('height', 'Height', 1.5), ('width_x', 'Width X', .6),
                                     ('width_z', 'Width Z', .6), ('density', 'Weight density (force / lengthÂ³)', 24)]:
            field = number(default, .000001, 1e9)
            field.setDecimals(6)
            self.pedestal_dimensions[name] = field
            form.addRow(title, field)
        layout.addWidget(self.pedestal_panel)
        layout.addWidget(label('Pedestal: use the displayed STAAD base units. Global Y is vertical. '
                               'Transfers signed reactions downward, adds pedestal weight to Fy, and retains torsion My. '
                               'Negate reactions for loads acting on the foundation.', 'muted', True))
        layout.addWidget(button('Export result workbook', self.export_results))
        layout.addStretch()
        self.result_kind.currentTextChanged.connect(lambda text: self.pedestal_panel.setEnabled(text == 'Pedestal'))
        self.pedestal_panel.setEnabled(False)

    def _girder_tab(self):
        _, layout = self._tab('Plate girders')
        layout.addWidget(label('Generate tapered-I section properties for specified members. '
                               'Dimensions describe the section, without a strength or buckling check.', 'muted', True))
        form = QFormLayout()
        self.girder_ids = QLineEdit('1 TO 5')
        self.girder_unit = combo(['METER', 'INCHES'])
        form.addRow('Member IDs', self.girder_ids)
        form.addRow('Dimension units', self.girder_unit)
        self.girder_dimensions = {}
        for key, title, default in [('d1', 'Depth at start', .8), ('tw', 'Web thickness', .01),
            ('d2', 'Depth at end', .6), ('bt', 'Top flange width', .3), ('tt', 'Top flange thickness', .02),
            ('bb', 'Bottom flange width', .3), ('tb', 'Bottom flange thickness', .02)]:
            field = number(default, .000001, 100000)
            field.setDecimals(6)
            self.girder_dimensions[key] = field
            form.addRow(title, field)
        layout.addLayout(form)
        layout.addWidget(button('Preview plate-girder property', self.preview_girder))
        layout.addStretch()

    def guard(self, operation):
        try:
            operation()
        except Exception as exc:
            self.invalid(str(exc))

    def require_model(self):
        if self.snapshot is None:
            raise ValueError('Scan STAAD or load a model snapshot first.')
        return self.snapshot

    def scan(self):
        self.snapshot_source = 'STAAD scan (cached)'
        self.run(live.scan, cad=True)

    def on_success(self, result):
        super().on_success(result)
        if isinstance(result, ModelSnapshot):
            self.set_snapshot(result)
        elif isinstance(result, str):
            self.show_output(result, 'Generated design parameters for review.')
        elif self.mapping is not None and getattr(result, 'output_path', ''):
            # A successful renumber changes every cached model reference.
            self.invalidate_mapping()

    def set_snapshot(self, snapshot, publish=True):
        self.snapshot = snapshot
        self.categories = classify_members(snapshot, overrides=snapshot.classifications)
        self.invalidate_mapping()
        self.model_caption.setText(str(snapshot) + '\n' + snapshot.path)
        self.result_caption.setText(f'Length: {snapshot.length_unit}; force: {snapshot.force_unit}; '
                                    f'moments: {snapshot.force_unit} {snapshot.length_unit}; rotations: rad.\n'
                                    'Load cases: ' + ', '.join(map(str, snapshot.load_cases)))
        if hasattr(self, 'level'):
            current = self.level.currentText()
            self.level.blockSignals(True)
            self.level.clear()
            self.level.addItems(['All levels', *[f'{y:.6g}' for y in sorted({round(xyz[1], 6) for xyz in snapshot.nodes.values()})]])
            if self.level.findText(current) >= 0: self.level.setCurrentText(current)
            self.level.blockSignals(False)
        self.populate_members()
        if publish and self.palette is not None:
            self.palette.share_snapshot(snapshot, self.snapshot_source, self)

    def populate_members(self):
        model = self.require_model()
        self.members.setUpdatesEnabled(False)
        try:
            self.members.setRowCount(len(model.members))
            for row, (mid, (a, b)) in enumerate(sorted(model.members.items())):
                values = (mid, a, b, self.categories[mid],
                          f'{(model.nodes[a][1] + model.nodes[b][1]) / 2:.5g}',
                          f'{math.dist(model.nodes[a], model.nodes[b]):.5g}')
                for col, value in enumerate(values):
                    self.members.setItem(row, col, QTableWidgetItem(str(value)))
        finally:
            self.members.setUpdatesEnabled(True)
        self.filter_members()

    def build_selection_controls(self):
        grid = QGridLayout()
        self.category_buttons = {}
        choices = [('Columns', ('Columns',)), ('Pri.Beams', ('Primary beams X', 'Primary beams Z')),
                   ('Sec.Beams', ('Secondary beams X', 'Secondary beams Z', 'Other horizontal')),
                   ('Vrt.Bracing', ('Vertical bracing',)), ('Plan.Bracing', ('Plan diagonals',)),
                   ('Pri.X', ('Primary beams X',)), ('Pri.Z', ('Primary beams Z',)),
                   ('Sec/Ter.X', ('Secondary beams X',)), ('Sec/Ter.Z', ('Secondary beams Z',)),
                   ('Sup.Nodes', None), ('Rafters', ('Rafters',)), ('Raf.Bracing', ('Rafter bracing',))]
        for index, (title, categories) in enumerate(choices):
            action = button(title, self.select_supports if categories is None else lambda checked=False, cats=categories: self.quick_category(cats), True)
            self.category_buttons[title] = action
            grid.addWidget(action, index // 4, index % 4)
        self.body.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(label('Level'))
        self.level = combo(['All levels'])
        self.level.currentTextChanged.connect(self.filter_members)
        row.addWidget(self.level, 1)
        row.addWidget(button('Members', self.select_level_members))
        row.addWidget(button('Main Nodes', self.select_main_nodes, True))
        self.body.addLayout(row)
        self.body.addWidget(label('Main Nodes selects column joints at the chosen level. Sec/Ter uses the secondary-beam classification; tertiary members can be assigned a role below.', 'muted', True))
        self.category_filter.currentTextChanged.connect(self.clear_quick_category)

    def clear_quick_category(self, *args):
        self.active_categories = None
        self.filter_members()

    def quick_category(self, categories):
        self.category_filter.setCurrentText('All categories')
        self.active_categories = set(categories)
        self.filter_members()
        self.select_visible()

    def select_level_members(self):
        self.select_visible()
        self.select_in_staad()

    def select_main_nodes(self):
        def start():
            model = self.require_model()
            nodes = {node for mid, pair in model.members.items() if self.categories[mid] == 'Columns' for node in pair}
            if self.level.currentText() != 'All levels':
                elevation = float(self.level.currentText())
                nodes = {node for node in nodes if abs(model.nodes[node][1] - elevation) <= .001}
            if not nodes: raise ValueError('No column joints found at this level.')
            self.run(lambda report: live.select_members(model, sorted(nodes), report, nodes=True), cad=True)
        self.guard(start)

    def filter_members(self, *args):
        term, category = self.search.text().strip().casefold(), self.category_filter.currentText()
        for row in range(self.members.rowCount()):
            role = self.members.item(row, 3).text()
            mid = int(self.members.item(row, 0).text())
            match = term in (str(mid) + ' ' + role).casefold()
            match = match and (role in self.active_categories if self.active_categories else category == 'All categories' or role == category)
            if hasattr(self, 'level') and self.level.currentText() != 'All levels' and self.snapshot:
                elevation = float(self.level.currentText())
                match = match and any(abs(self.snapshot.nodes[node][1] - elevation) <= .001 for node in self.snapshot.members[mid])
            self.members.setRowHidden(row, not match)

    def selected_ids(self):
        self.require_model()
        ids = [int(self.members.item(index.row(), 0).text())
               for index in self.members.selectionModel().selectedRows()
               if not self.members.isRowHidden(index.row())]
        if not ids:
            raise ValueError('Select member rows first; use Select visible for a whole category.')
        return sorted(ids)

    def select_visible(self):
        from PySide6.QtCore import QItemSelection, QItemSelectionModel
        selection = QItemSelection()
        for row in range(self.members.rowCount()):
            if not self.members.isRowHidden(row):
                selection.select(self.members.model().index(row, 0), self.members.model().index(row, 5))
        self.members.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)

    def assign_role(self):
        def assign():
            for mid in self.selected_ids():
                self.categories[mid] = self.role.currentText()
                self.snapshot.classifications[mid] = self.role.currentText()
            self.invalidate_mapping()
            self.populate_members()
            if self.palette is not None:
                self.palette.share_snapshot(self.snapshot, self.palette.snapshot_source or self.snapshot_source, self)
        self.guard(assign)

    def select_in_staad(self):
        def start():
            model, ids = self.require_model(), self.selected_ids()
            self.run(lambda report: live.select_members(model, ids, report), cad=True)
        self.guard(start)

    def select_supports(self):
        def start():
            model = self.require_model()
            self.run(lambda report: live.select_members(model, model.supports, report, nodes=True), cad=True)
        self.guard(start)

    def show_output(self, text, caption, extension='.txt'):
        if extension != '.csv':
            self.invalidate_mapping()
        self.output.setPlainText(text)
        self.output_caption.setText(caption)
        self.output_extension = extension
        self.feedback_text(caption, 'success')

    def preview_groups(self):
        self.guard(lambda: self.show_output(group_commands(self.require_model(), self.categories, self.group_prefix.text().strip()),
                                            'Group commands for ' + self.snapshot.path))

    def preview_releases(self):
        self.guard(lambda: self.show_output(release_commands(self.selected_ids(), self.release_end.currentText(),
                      [k for k, field in self.release_dofs.items() if field.isChecked()]),
                      'Release commands in LOCAL member axes for ' + self.snapshot.path))

    def confirm_model_change(self, title, model, preview, effect):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(title + '\n\nTarget: ' + model.path)
        box.setInformativeText(effect + '\n\nCivTools will save the current model and create a backup before applying these commands. Review the refreshed preview below; Details contains the complete commands.')
        box.setDetailedText(preview)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def run_model_change(self, operation):
        if self.busy:
            return
        self.mutating = True
        def execute(report):
            result = operation(report)
            report('model_changed', True)
            return result
        self.run(execute, cad=True)

    def apply_groups(self):
        def start():
            model = self.require_model()
            categories, prefix = dict(self.categories), self.group_prefix.text().strip()
            preview = group_commands(model, categories, prefix)
            self.show_output(preview, 'Fresh group preview for ' + model.path)
            if self.confirm_model_change('Apply groups to STAAD', model, preview,
                                         'Creates the previewed member groups. Existing group-name collisions are refused.'):
                self.run_model_change(lambda report: live.apply_groups(model, categories, prefix, report))
        self.guard(start)

    def apply_releases(self):
        def start():
            model, ids = self.require_model(), tuple(self.selected_ids())
            end = self.release_end.currentText()
            dofs = tuple(key for key, field in self.release_dofs.items() if field.isChecked())
            preview = release_commands(ids, end, dofs)
            self.show_output(preview, 'Fresh local-axis release preview for ' + model.path)
            if self.confirm_model_change('Apply releases to STAAD', model, preview,
                                         f'Replaces releases at selected ends ({end}) of {len(ids):,} selected members with the previewed local-axis releases.'):
                self.run_model_change(lambda report: live.apply_releases(model, ids, end, dofs, report))
        self.guard(start)

    def invalidate_mapping(self, *args):
        self.mapping = None
        if hasattr(self, 'apply_button'):
            self.apply_button.setEnabled(False)

    def preview_renumber(self):
        def generate():
            self.mapping = renumber_plan(self.require_model(), self.renumber_start.value(), self.categories)
            self.show_output(renumber_csv(self.mapping), 'Renumber plan: category, then Y/Z/X midpoint order. ' + self.snapshot.path, '.csv')
            self.apply_button.setEnabled(True)
        self.guard(generate)

    def apply_renumber(self):
        if self.mapping is None:
            self.invalid('Generate a fresh renumber plan first.')
            return
        model, mapping = self.snapshot, dict(self.mapping)
        answer = QMessageBox.question(self, 'Apply member renumbering',
            f'Save and renumber {len(mapping):,} members in:\n{model.path}\n\n'
            'CivTools will save the current model, create a backup and a numbering journal, '
            'then apply the previewed plan. Existing analysis results and saved selections may become invalid. '
            'Close the STAAD editor before continuing.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            def operation(report):
                result = live.apply_renumber(model, mapping, report)
                report('renumbered', True)
                return result
            self.run(operation, cad=True)

    def on_event(self, kind, value):
        if kind == 'model_changed':
            if self.palette is not None:
                self.palette.invalidate_snapshot('Model changed. Refresh STAAD before continuing.')
            else:
                self.snapshot, self.categories = None, {}
                self.members.setRowCount(0)
                self.invalidate_mapping()
            self.mutating = False
        elif kind == 'renumbered':
            if self.palette is not None:
                self.palette.invalidate_snapshot('Model renumbered. Refresh STAAD before continuing.')
            self.snapshot = None
            self.categories = {}
            self.members.setRowCount(0)
            self.invalidate_mapping()
            self.model_caption.setText('Model renumbered. Scan again before using member tools.')
            self.result_caption.setText('Scan the renumbered model again.')
        else:
            super().on_event(kind, value)

    def on_failure(self, message):
        if self.mutating or self.mapping is not None:
            if self.palette is not None:
                self.palette.invalidate_snapshot('Operation failed. Inspect STAAD and refresh before continuing.')
            # An interrupted renumber must never leave an applicable stale plan.
            self.snapshot = None
            self.categories = {}
            self.members.setRowCount(0)
            self.invalidate_mapping()
            self.model_caption.setText('Operation failed. Inspect STAAD and scan again before continuing.')
        self.mutating = False
        super().on_failure(message)

    def export_results(self):
        def start():
            model = self.require_model()
            kind = self.result_kind.currentText()
            allowed = model.nodes if kind == 'Displacements' else model.supports
            nodes = id_list(self.result_nodes.text(), allowed) if self.result_nodes.text().strip() else sorted(allowed)
            cases = id_list(self.result_cases.text(), model.load_cases) if self.result_cases.text().strip() else list(model.load_cases)
            if not nodes or not cases:
                raise ValueError('The scanned model has no matching nodes or load cases.')
            pedestal = tuple(field.value() for field in self.pedestal_dimensions.values()) if kind == 'Pedestal' else None
            path, _ = QFileDialog.getSaveFileName(self, 'Export STAAD results', self.last_folder() + '/staad-results.xlsx', 'Excel workbook (*.xlsx)')
            if path:
                self.remember_folder(path)
                self.run(lambda report: live.export_results(model, kind, nodes, cases, path, report, pedestal), cad=True)
        self.guard(start)

    def preview_combinations(self):
        self.guard(lambda: self.show_output(combination_commands(read_combination_csv(self.combination_csv.toPlainText()),
                          self.snapshot.load_cases if self.snapshot else None,
                          self.snapshot.primary_cases if self.snapshot else None), 'Linear load-combination commands from your factors.'))

    def preview_girder(self):
        self.guard(lambda: self.show_output(tapered_commands(id_list(self.girder_ids.text(),
                         self.snapshot.members if self.snapshot else None),
                         [field.value() for field in self.girder_dimensions.values()], self.girder_unit.currentText()),
                         'Tapered-I property commands; check incidence and restore input units after insertion.'))

    def last_folder(self):
        return str(self.window.settings.value('folders/productivity', str(Path.home() / 'Documents')))

    def remember_folder(self, path):
        self.window.settings.setValue('folders/productivity', str(Path(path).parent))

    def copy_output(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.output.toPlainText())
        self.feedback_text('Copied preview.', 'success')

    def export_output(self):
        def save():
            if not self.output.toPlainText().strip():
                raise ValueError('Generate a preview first.')
            ext = self.output_extension
            path, _ = QFileDialog.getSaveFileName(self, 'Export preview', self.last_folder() + '/civtools-output' + ext,
                                                 f'Generated output (*{ext})')
            if path:
                if Path(path).suffix.lower() != ext:
                    raise ValueError(f'Use the {ext} extension for this output.')
                if self.snapshot and Path(path).resolve() == Path(self.snapshot.path).resolve():
                    raise ValueError('Choose a new output file; keep the source STAAD model.')
                Path(path).write_text(self.output.toPlainText(), encoding='utf-8')
                self.remember_folder(path)
                self.feedback_text('Exported ' + path, 'success')
        self.guard(save)

    def save_snapshot(self):
        def save():
            model = self.require_model()
            path, _ = QFileDialog.getSaveFileName(self, 'Save geometry snapshot', self.last_folder() + '/staad-snapshot.json', 'JSON (*.json)')
            if path:
                if Path(path).suffix.lower() != '.json':
                    raise ValueError('Save the snapshot as .json.')
                Path(path).write_text(model.to_json(), encoding='utf-8')
                self.remember_folder(path)
        self.guard(save)

    def load_snapshot(self):
        def load():
            path, _ = QFileDialog.getOpenFileName(self, 'Load geometry snapshot', self.last_folder(), 'JSON (*.json)')
            if path:
                if Path(path).stat().st_size > 16_000_000:
                    raise ValueError('Snapshot exceeds 16 MB.')
                self.snapshot_source = 'Offline snapshot'
                self.set_snapshot(ModelSnapshot.from_json(Path(path).read_text(encoding='utf-8')))
                self.remember_folder(path)
                self.feedback_text('Loaded offline geometry snapshot. Live actions recheck the active model.', 'success')
        self.guard(load)
