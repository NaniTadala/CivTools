"""Compact productivity dialogs following the documented STAAD helper workflows."""
from dataclasses import dataclass
import json
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QDialog,
    QDialogButtonBox, QPlainTextEdit, QLineEdit, QSpinBox, QListWidget,
    QAbstractItemView, QFileDialog, QMessageBox, QApplication, QTableWidget, QTableWidgetItem, QHeaderView)

from .qt_pages import ToolPage, combo
from .qt_widgets import button, label, CheckBox, SpinBox as QSpinBox
from .qt_productivity import WorkflowPage, number
from .core.staad_productivity import ModelSnapshot
from .core.results import OperationResult
from .core import staad_productivity_com as live


TITLES = {'renumber': 'Renumber members', 'groups': 'Member groups',
          'releases': 'Member releases', 'parameters': 'Design parameters',
          'tables': 'Analysis Results Tables', 'combinations': 'Load Combinations',
          'girders': 'Custom Plate Girders', 'rack': 'Pipe Rack',
          **{'peb' + key: 'PEB - ' + key for key in 'ABCD'}}


@dataclass
class PreparedAction:
    model: ModelSnapshot
    kind: str
    data: object
    details: str
    effect: str

    def __str__(self):
        return self.effect


class StructureSketch(QWidget):
    """Original dimension sketch for the structure wizard inputs."""
    def __init__(self, variant, parent=None):
        super().__init__(parent)
        self.variant = variant
        self.setMinimumSize(210, 210)
        self.setAccessibleName(('Pipe rack' if variant == 'rack' else 'PEB ' + variant) + ' geometry sketch')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        left, right, base, eave, ridge = 30, width - 30, height - 45, height * .4, height * .22
        painter.setPen(QPen(QColor('#245B7A'), 3))
        def line(a, b):
            painter.drawLine(QPointF(*a), QPointF(*b))
        line((left, base), (left, eave))
        if self.variant == 'rack':
            line((right, base), (right, eave))
            line((left, eave), (right, eave))
            line((left, (base + eave) / 2), (right, (base + eave) / 2))
        elif self.variant == 'D':
            line((right, base), (right, ridge))
            line((left, eave), (right, ridge))
        else:
            middle = (left + right) / 2
            line((right, base), (right, eave))
            line((left, eave), (middle, ridge))
            line((middle, ridge), (right, eave))
            if self.variant == 'B':
                line((middle, base), (middle, ridge))
            elif self.variant == 'C':
                for fraction in (.25, .75):
                    x = left + fraction * (right - left)
                    y = ridge + (eave - ridge) * abs(fraction - .5) * 2
                    line((x, base), (x, y))
        painter.setPen(QPen(QColor('#7B94A3'), 1))
        line((left, base + 14), (right, base + 14))
        painter.drawText(int(width / 2 - 5), int(base + 32), 'W')
        painter.drawText(6, int((base + eave) / 2), 'H1' if self.variant != 'rack' else 'T1…Tn')
        if self.variant != 'rack':
            painter.drawText(int(width / 2 + 8), int(ridge - 8), 'H2')
        painter.drawText(30, 20, 'N frames · S frame spacing')


class OutputDialog(QDialog):
    def __init__(self, page, text, *, assign=None, suffix='.txt'):
        super().__init__(page)
        self.setWindowTitle(page.windowTitle() or TITLES[page.feature])
        self.resize(660, 480)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(text)
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.text)
        row = QHBoxLayout()
        row.addWidget(button('Copy', lambda: QApplication.clipboard().setText(text), True))
        row.addWidget(button('Save', lambda: page.save_text(text, suffix), True))
        row.addStretch()
        if assign is not None:
            def apply():
                self.accept()
                assign()
            row.addWidget(button('Assign', apply))
        row.addWidget(button('Close', self.accept, True))
        layout.addLayout(row)


class ReleaseSketch(QWidget):
    """Explain local member incidence without implying a physical support type."""
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(100)
        self.setAccessibleName('Member local X axis runs from START node to END node. Releases use local axes.')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, right, y = 40, self.width() - 40, 43
        painter.setPen(QPen(QColor('#1682BC'), 3))
        painter.drawLine(left, y, right, y)
        painter.setBrush(QColor('#FFFFFF'))
        for x in (left, right):
            painter.drawEllipse(QPointF(x, y), 5, 5)
        middle = self.width() // 2
        painter.setPen(QPen(QColor('#536C7B'), 1))
        painter.drawLine(middle - 35, y - 19, middle + 35, y - 19)
        painter.drawLine(middle + 35, y - 19, middle + 28, y - 23)
        painter.drawText(middle - 18, y - 27, 'local X')
        painter.drawText(left - 20, y + 27, 'START')
        painter.drawText(right - 12, y + 27, 'END')


class ProductivityToolPage(WorkflowPage):
    """Tool-specific forms; processing, output review and mutation stay separate."""
    def __init__(self, window, feature, palette=None):
        ToolPage.__init__(self, window, TITLES[feature], '', 'Modeling', artwork='productivity')
        self.feature, self.palette = feature, palette
        self.snapshot, self.categories, self.mapping = None, {}, None
        self.snapshot_source = 'STAAD scan (cached)'
        self.state_widgets = {}
        self.mutating = False
        self._after_finished = None
        self.model_caption = label('No model processed.', 'muted', True)
        self.result_caption = label('', 'muted', True)
        self.output = QPlainTextEdit(self)
        self.output.hide()
        self.output_extension = '.txt'
        self.header_art.hide()
        heading = self.layout().itemAt(0).layout().itemAt(0).layout()
        heading.itemAt(1).widget().hide()
        self.log_toggle.hide()
        self.body.setSpacing(8)
        self.body.setContentsMargins(0, 0, 0, 0)
        if feature in ('renumber', 'groups', 'releases', 'parameters', 'tables'):
            self.body.addWidget(self.model_caption)
        getattr(self, 'build_' + ('structure' if feature == 'rack' or feature.startswith('peb') else feature))()
        self.body.addStretch()
        self.restore_inputs()

    def tracked(self, name, field):
        self.state_widgets[name] = field
        return field

    def set_snapshot(self, snapshot, publish=True):
        from .core.staad_productivity import classify_members
        self.snapshot = snapshot
        self.categories = classify_members(snapshot, overrides=snapshot.classifications)
        self.mapping = None
        self.model_caption.setText(Path(snapshot.path).name)
        self.model_caption.setToolTip(snapshot.path)
        if self.feature == 'releases':
            self.clear_release_review()
            self.define_releases_button.setEnabled(True)
        elif self.feature == 'parameters':
            for action in self.design_actions.values():
                action.setEnabled(True)
        if publish and self.palette is not None:
            self.palette.share_snapshot(snapshot, self.snapshot_source, self)

    def scan(self):
        if self.feature == 'releases':
            self.clear_release_review()
        self.run(live.scan, cad=True)

    def invalidate_mapping(self, *args):
        self.mapping = None
        if self.feature == 'releases':
            self.clear_release_review()
        if self.snapshot is None:
            if self.feature == 'releases':
                self.define_releases_button.setEnabled(False)
            elif self.feature == 'parameters':
                for action in self.design_actions.values():
                    action.setEnabled(False)

    def on_event(self, kind, value):
        if kind == 'tables_model':
            self.set_snapshot(value)
        elif kind in ('model_changed', 'renumbered'):
            if self.palette is not None:
                self.palette.invalidate_snapshot('Model changed. Process members again.')
            self.snapshot = None
            self.mutating = False
            self.invalidate_mapping()
        elif kind not in ('log', 'target', 'stage'):
            ToolPage.on_event(self, kind, value)

    def on_success(self, result):
        ToolPage.on_success(self, result)
        if isinstance(result, ModelSnapshot):
            self.set_snapshot(result)
        elif isinstance(result, PreparedAction):
            self.set_snapshot(result.model)
            self.output.setPlainText(result.details)
            if self.feature == 'releases':
                self.show_release_review(result)
            else:
                self._after_finished = lambda: self.review_action(result)
        elif self.feature == 'parameters' and isinstance(result, str):
            self.output.setPlainText(result)
            text, model, code = result, self.snapshot, self.design_code.currentText()
            self._after_finished = lambda: OutputDialog(self, text, assign=lambda: self.assign_parameters(model, text, code)).exec()
        elif self.feature == 'tables' and isinstance(result, list):
            self.available_cases.clear()
            self.selected_cases.clear()
            for case, kind, title in result:
                self.add_case(self.available_cases, case, f'{case} · {kind}' + (f' · {title}' if title else ''))
            self.feedback_text(f'{len(result)} load cases available.', 'success')

    def on_failure(self, message):
        if self.mutating:
            if self.palette is not None:
                self.palette.invalidate_snapshot('Operation failed. Check STAAD and process again.')
            self.snapshot = None
            self.invalidate_mapping()
        self.mutating = False
        ToolPage.on_failure(self, message)
        self.log.hide()

    def on_finished(self):
        ToolPage.on_finished(self)
        self.log.hide()
        self.runtime.hide()
        self.target.hide()
        action, self._after_finished = self._after_finished, None
        if action:
            self.guard(action)
        if self.feature == 'releases':
            self.apply_release_button.setEnabled(self.prepared_release is not None)
            self.define_releases_button.setEnabled(self.snapshot is not None)

    def confirm(self, title, details, effect, target=None):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText(effect + ('\n\nModel: ' + target if target else ''))
        dialog.setInformativeText('The active STAAD model will be saved and backed up before applying the change.')
        dialog.setDetailedText(details)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def run_change(self, operation):
        self.mutating = True
        def execute(report):
            result = operation(report)
            report('model_changed', True)
            return result
        self.run(execute, cad=True)

    def save_path(self, title, default_name, file_filter):
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path(self.last_folder()) / default_name), file_filter)
        if path:
            self.remember_folder(path)
        return path

    def save_text(self, text, suffix='.txt'):
        path = self.save_path('Save output', self.feature + suffix, f'Output (*{suffix})')
        if path:
            Path(path).write_text(text, encoding='utf-8')
            self.feedback_text('Saved ' + path, 'success')

    def build_renumber(self):
        self.body.addWidget(label('SCOPE · Entire active model', 'navHeading'))
        self.body.addWidget(label('Renumber members by floor and member type. Review the proposed numbers before applying.', 'muted', True))
        self.action_bar.addWidget(button('Review renumbering', self.prepare_renumber))

    def prepare_renumber(self):
        from .core.productivity_model_tools import floor_renumber_plan
        def prepare(report):
            model = live.scan(report)
            for block in (1000, 10000):
                try:
                    mapping = floor_renumber_plan(model, floor_block=block)
                    break
                except ValueError as exc:
                    if block == 10000 or 'too many members' not in str(exc):
                        raise
            details = '\n'.join(f'{old} → {new}' for old, new in mapping.items())
            return PreparedAction(model, 'renumber', mapping, details,
                                  f'Renumber {len(mapping):,} members by floor and member type?')
        self.run(prepare, cad=True)

    def build_groups(self):
        self.body.addWidget(label('SCOPE · Entire active model', 'navHeading'))
        self.body.addWidget(label('Create member, column-node and floor groups. Review the generated groups before applying.', 'muted', True))
        self.action_bar.addWidget(button('Review groups', self.prepare_groups))

    def prepare_groups(self):
        from .core.productivity_model_tools import predefined_group_plan, group_plan_commands
        def prepare(report):
            model = live.scan(report)
            plan = predefined_group_plan(model)
            return PreparedAction(model, 'groups', plan, group_plan_commands(plan), 'Create predefined member, column-node and floor groups?')
        self.run(prepare, cad=True)

    def review_action(self, prepared):
        if not self.confirm(TITLES[self.feature], prepared.details, prepared.effect, target=prepared.model.path):
            return
        if prepared.kind == 'renumber':
            self.run_change(lambda report: live.apply_renumber(prepared.model, prepared.data, report))
        elif prepared.kind == 'groups':
            from .core.productivity_model_tools import apply_predefined_groups
            self.run_change(lambda report: apply_predefined_groups(prepared.model, report))
        elif prepared.kind == 'releases':
            from .core.productivity_model_tools import apply_selected_releases
            data = prepared.data
            self.run_change(lambda report: apply_selected_releases(prepared.model, report, end=data['end'],
                dofs=data['dofs'], proceed_skipped=True, plan=data['plan']))

    def build_releases(self):
        self.prepared_release = None
        self.body.addWidget(label('SCOPE · Current member selection in STAAD', 'navHeading'))
        self.setToolTip('Select complete beam chains in STAAD, then scan the model and review their exterior ends.')
        row = QHBoxLayout()
        row.addWidget(button('Scan active model', self.scan))
        self.release_end = self.tracked('release_end', combo(['BOTH', 'START', 'END']))
        row.addWidget(label('Release ends'))
        row.addWidget(self.release_end)
        self.body.addLayout(row)
        self.body.addWidget(label('LOCAL AXIS DEGREES OF FREEDOM', 'navHeading'))
        row = QHBoxLayout()
        self.release_dofs = {}
        for key in ('FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'):
            field = self.tracked('release_' + key, CheckBox(key))
            field.setChecked(key == 'MZ')
            field.setToolTip(('Translation' if key.startswith('F') else 'Rotation') + ' about/along local ' + key[-1])
            self.release_dofs[key] = field
            field.toggled.connect(self.clear_release_review)
            row.addWidget(field)
        self.release_end.currentTextChanged.connect(self.clear_release_review)
        self.body.addLayout(row)
        self.release_end.setToolTip('Checked degrees of freedom are released. Intermediate chain joints remain continuous.')
        self.define_releases_button = button('Review selected members', self.review_selected_releases)
        self.define_releases_button.setEnabled(False)
        self.body.addWidget(self.define_releases_button)
        self.release_summary = label('No changes reviewed yet.', 'scopeSummary', True)
        self.body.addWidget(self.release_summary)
        self.release_table = QTableWidget(0, 4)
        self.release_table.setHorizontalHeaderLabels(['Member', 'Start end', 'End end', 'Review status'])
        self.release_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.release_table.setAlternatingRowColors(True)
        self.release_table.verticalHeader().hide()
        self.release_table.verticalHeader().setDefaultSectionSize(32)
        self.release_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for column, width in enumerate((72, 76, 76)):
            self.release_table.setColumnWidth(column, width)
        self.release_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.release_table.setMinimumHeight(170)
        details, self.release_details_toggle = self.section('Review details / local axes')
        details.addWidget(ReleaseSketch())
        details.addWidget(self.release_table)
        preview = details
        self.output.setMinimumHeight(100)
        self.output.setMaximumHeight(150)
        preview.addWidget(self.output)
        self.output.show()
        self.log_toggle.show()
        self.apply_release_button = button('Apply reviewed releases', self.apply_reviewed_releases)
        self.apply_release_button.setEnabled(False)
        self.action_bar.addWidget(self.apply_release_button)

    def clear_release_review(self, *args):
        self.prepared_release = None
        if hasattr(self, 'apply_release_button'):
            self.apply_release_button.setEnabled(False)
            self.release_summary.setText('Selection or settings changed · Review selected members again.')
            self.release_table.setRowCount(0)
            self.output.clear()

    def review_selected_releases(self):
        self.guard(lambda: self.prepare_releases(self.release_end.currentText(),
            tuple(key for key, field in self.release_dofs.items() if field.isChecked())))

    def show_release_review(self, prepared):
        self.prepared_release = prepared
        plan = prepared.data['plan']
        self.release_summary.setText(plan.summary)
        self.release_table.setRowCount(len(plan.selected))
        for row, mid in enumerate(plan.selected):
            values = (mid, ' / '.join(plan.assignments.get((mid, 0), ())) or 'Retained',
                      ' / '.join(plan.assignments.get((mid, 1), ())) or 'Retained',
                      plan.skipped.get(mid, 'Ready'))
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.release_table.setItem(row, col, item)
        self.release_table.setFixedHeight(36 + min(6, len(plan.selected)) * 32)
        self.apply_release_button.setEnabled(True)
        self.feedback_text('Review the affected ends and skipped members, then apply when ready.')

    def apply_reviewed_releases(self):
        if self.prepared_release is not None:
            self.guard(lambda: self.review_action(self.prepared_release))

    def release_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Define releases on selected beams')
        layout = QVBoxLayout(dialog)
        ends = QHBoxLayout()
        start, end = CheckBox('START'), CheckBox('END')
        start.setChecked(True)
        end.setChecked(True)
        ends.addWidget(start)
        ends.addWidget(end)
        layout.addLayout(ends)
        row = QHBoxLayout()
        dofs = {}
        for key in ('FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'):
            dofs[key] = CheckBox(key)
            dofs[key].setChecked(key == 'MZ')
            row.addWidget(dofs[key])
        layout.addLayout(row)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Ok).setText('Assign')
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not start.isChecked() and not end.isChecked():
            self.invalid('Choose START, END or both.')
            return
        location = 'BOTH' if start.isChecked() and end.isChecked() else 'START' if start.isChecked() else 'END'
        self.guard(lambda: self.prepare_releases(location, tuple(key for key, field in dofs.items() if field.isChecked())))

    def prepare_releases(self, end='BOTH', dofs=('MZ',)):
        from .core.productivity_model_tools import selected_release_plan, release_plan_commands
        model = self.require_model()
        self.clear_release_review()
        def prepare(report):
            staad = live.connect()
            live.require_snapshot(staad, model, report)
            ids = sorted(live._selected_ids(staad.Geometry))
            plan = selected_release_plan(model, ids, end, dofs)
            if not plan.assignments:
                raise ValueError('No complete primary or secondary beam chains are selected.')
            details = release_plan_commands(plan)
            if plan.skipped:
                details += '\n* Skipped members:\n' + '\n'.join(f'* {mid}: {reason}' for mid, reason in plan.skipped.items())
            data = {'plan': plan, 'end': end, 'dofs': dofs}
            return PreparedAction(model, 'releases', data, details,
                                  plan.summary + ('\nProceed while skipping the invalid/incomplete members?' if plan.skipped else '\nAssign releases?'))
        self.run(prepare, cad=True)

    def build_parameters(self):
        from .core.productivity_design_results import DESIGN_CODES
        row = QHBoxLayout()
        row.addWidget(label('Design code'))
        self.design_code = self.tracked('design_code', combo(DESIGN_CODES))
        row.addWidget(self.design_code, 1)
        row.addWidget(button('Process Members', self.scan))
        self.body.addLayout(row)
        self.design_actions = {}
        for key, title in [('columns', 'Column lengths'), ('beams_dj', 'Beams DJ1 / DJ2'),
                           ('beams_lengths', 'Beam lengths')]:
            action = button(title, lambda mode=key: self.design_parameters(mode), True)
            action.setEnabled(False)
            self.design_actions[key] = action
            self.body.addWidget(action)
        def update_labels():
            lateral = 'LX' if self.design_code.currentText() == 'IS 800:2007' else 'UNL'
            self.design_actions['columns'].setText('Columns LY / LZ / ' + lateral)
            self.design_actions['beams_lengths'].setText('Beams LY / LZ / ' + lateral)
        self.design_code.currentTextChanged.connect(update_labels)
        update_labels()
        self.body.addWidget(label('Review restraint assumptions before assigning lengths.', 'muted', True))

    def design_parameters(self, mode):
        from .core.productivity_design_results import process_design_parameters
        model, code = self.require_model(), self.design_code.currentText()
        self.run(lambda report: process_design_parameters(model, mode, code, report), cad=True)

    def assign_parameters(self, model, text, code):
        from .core.productivity_design_results import apply_design_parameters
        if self.confirm('Assign design parameters', text, 'Assign these restraint candidates to ' + Path(model.path).name +
                        '?\nSTAAD will save, close and reopen the model. Review actual restraint assumptions first.', target=model.path):
            self.run_change(lambda report: apply_design_parameters(model, text, code, report))

    def build_tables(self):
        self.body.addWidget(button('Read load cases', self.load_cases, True))
        row = QHBoxLayout()
        available, chosen = QVBoxLayout(), QVBoxLayout()
        available.addWidget(label('Available'))
        chosen.addWidget(label('Selected'))
        self.available_cases, self.selected_cases = QListWidget(), QListWidget()
        for field in (self.available_cases, self.selected_cases):
            field.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            field.setMinimumHeight(120)
            field.setTextElideMode(Qt.TextElideMode.ElideRight)
            field.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        available.addWidget(self.available_cases)
        chosen.addWidget(self.selected_cases)
        row.addLayout(available, 1)
        controls = QVBoxLayout()
        controls.addStretch()
        for title, source, target, all_items in [('>', self.available_cases, self.selected_cases, False),
                ('>>', self.available_cases, self.selected_cases, True), ('<', self.selected_cases, self.available_cases, False),
                ('<<', self.selected_cases, self.available_cases, True)]:
            controls.addWidget(button(title, lambda s=source, t=target, a=all_items: self.move_cases(s, t, a), True))
        controls.addStretch()
        row.addLayout(controls)
        row.addLayout(chosen, 1)
        self.body.addLayout(row)
        self.result_kind = self.tracked('result_kind', combo(['Support reactions', 'Node displacements', 'Pedestal forces']))
        self.result_kind.setAccessibleName('Result type to export')
        self.body.addWidget(label('Export result', 'muted'))
        self.body.addWidget(self.result_kind)
        self.action_bar.addWidget(button('Export Excel', lambda: self.export_table(
            ('Reactions', 'Displacements', 'Pedestal')[self.result_kind.currentIndex()])))

    @staticmethod
    def add_case(target, case, title):
        from PySide6.QtWidgets import QListWidgetItem
        item = QListWidgetItem(title)
        item.setToolTip(title)
        item.setData(Qt.ItemDataRole.UserRole, case)
        target.addItem(item)

    def move_cases(self, source, target, all_items=False):
        rows = range(source.count()) if all_items else [source.row(item) for item in source.selectedItems()]
        items = [source.takeItem(row) for row in sorted(rows, reverse=True)]
        for item in reversed(items):
            target.addItem(item)

    def load_cases(self):
        from .core.productivity_design_results import load_case_inventory
        def load(report):
            model = live.scan(report)
            report('tables_model', model)
            return load_case_inventory(model, report)
        self.run(load, cad=True)

    def export_table(self, kind):
        from .core.productivity_design_results import export_results
        def export():
            model = self.require_model()
            cases = [self.selected_cases.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.selected_cases.count())]
            if not cases:
                raise ValueError('Choose load cases first.')
            nodes = sorted(model.nodes if kind == 'Displacements' else model.supports)
            path = self.save_path('Save analysis results', kind.lower() + '.xlsx', 'Excel workbook (*.xlsx)')
            if path:
                self.run(lambda report: export_results(model, kind, nodes, cases, path, report), cad=True)
        self.guard(export)

    def build_combinations(self):
        self.body.addWidget(button('Download Template', self.save_template, True))
        self.combination_file = self.tracked('combination_file', QLineEdit())
        self.combination_file.setReadOnly(True)
        self.combination_file.setPlaceholderText('Select a completed LOAD_COMB workbook')
        self.body.addWidget(self.combination_file)
        self.body.addWidget(button('Select Load Comb File', self.choose_combination_file, True))
        self.action_bar.addWidget(button('Export Word report', self.generate_combinations))

    def save_template(self):
        from .core.productivity_generators import load_combination_template
        path = self.save_path('Save load combination template', 'load-combinations.xlsx', 'Excel workbook (*.xlsx)')
        if path:
            self.guard(lambda: (load_combination_template(path), self.feedback_text('Saved ' + path, 'success')))

    def choose_combination_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select load combination file', self.last_folder(), 'Load combinations (*.xlsx *.csv)')
        if path:
            self.combination_file.setText(path)
            self.remember_folder(path)

    def generate_combinations(self):
        from .core.productivity_generators import load_combination_report
        def generate():
            source = self.combination_file.text().strip()
            if not source or not Path(source).is_file():
                raise ValueError('Select a completed load combination file.')
            path = self.save_path('Save load case and combination report', 'load-combinations.docx', 'Word document (*.docx)')
            if path:
                def write(report):
                    load_combination_report(source, path)
                    return OperationResult('Saved load case scripts, combinations and tables: ' + path, path)
                self.run(write)
        self.guard(generate)

    def build_girders(self):
        self.custom_sections = self.tracked('custom_sections', QLineEdit('[]', self))
        self.custom_sections.hide()
        self.action_bar.addWidget(button('Export girder catalogue', self.generate_girders))
        self.body.addWidget(button('Add Custom Section', self.custom_girder_dialog, True))
        self.body.addWidget(label('Creates a STAAD USER TABLE catalogue of built-up I sections.', 'muted', True))

    def custom_girder_dialog(self):
        from dataclasses import asdict
        from .core.productivity_generators import PlateGirder
        dialog = QDialog(self)
        dialog.setWindowTitle('Custom I section — dimensions in mm')
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        name = QLineEdit('PG_CUSTOM')
        form.addRow('Section name', name)
        fields = {}
        for key, title, value in [('depth_mm', 'Depth', 800), ('flange_width_mm', 'Flange width', 300),
                ('flange_thickness_mm', 'Flange thickness', 25), ('web_thickness_mm', 'Web thickness', 16)]:
            fields[key] = number(value, .001, 100000)
            form.addRow(title, fields[key])
        layout.addLayout(form)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(controls)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            def add():
                section = PlateGirder(name.text().strip(), **{key: field.value() for key, field in fields.items()})
                section.properties()
                data = json.loads(self.custom_sections.text())
                data.append(asdict(section))
                self.custom_sections.setText(json.dumps(data))
                self.feedback_text(f'Added {section.name}; included when generating the catalogue.', 'success')
            self.guard(add)

    def generate_girders(self):
        from .core.productivity_generators import PlateGirder, predefined_plate_girders, plate_girder_catalogue
        path = self.save_path('Save plate girder catalogue', 'plate-girders.txt', 'Text file (*.txt)')
        if path:
            def generate():
                custom = [PlateGirder(**values) for values in json.loads(self.custom_sections.text())]
                text = plate_girder_catalogue([*predefined_plate_girders(), *custom])
                Path(path).write_text(text, encoding='utf-8')
                self.feedback_text('Saved ' + path, 'success')
            self.guard(generate)

    def build_structure(self):
        variant = 'rack' if self.feature == 'rack' else self.feature[-1]
        row = QHBoxLayout()
        preview_title = {'A': 'Gable frame', 'B': 'Ridge column frame',
                         'C': 'Internal column frame', 'D': 'Single slope frame',
                         'rack': 'Pipe rack'}[variant]
        sketch, self.geometry_preview_toggle = self.section(preview_title + ' preview')
        sketch.addWidget(StructureSketch(variant))
        form = QFormLayout()
        self.geometry_fields = {}
        self.geometry_unit = self.tracked('unit', combo(['METER', 'INCHES']))
        form.addRow('Units', self.geometry_unit)
        fields = [('width', 'Width, W', 6 if variant == 'rack' else 20), ('frames', 'Frames, N', 4),
                  ('frame_spacing', 'Frame spacing, S', 6)]
        if variant == 'rack':
            fields += [('tier_spacings', 'Tier spacings, T', '4,3'), ('longitudinal_spacings', 'Longitudinal spacings, L', '4,3')]
        else:
            fields += [('eave_height', 'Column height, H1' if variant != 'D' else 'Column A height', 6),
                       ('ridge_height', 'Ridge height, H2' if variant != 'D' else 'Column B height', 9),
                       ('tie_spacing', 'Tie max spacing, Ts', 3), ('purlin_spacing', 'Purlin max spacing, Ps', 1.5)]
            if variant == 'C':
                fields += [('inner_left', 'Column spacing, W1', 5), ('inner_right', 'Column spacing, W2', 5)]
        for key, title, default in fields:
            if isinstance(default, str):
                field = QLineEdit(default)
            elif key == 'frames':
                field = QSpinBox()
                field.setRange(2, 500)
                field.setValue(default)
            else:
                field = number(default, .000001, 1e6)
                field.setDecimals(4)
            self.geometry_fields[key] = self.tracked(key, field)
            form.addRow(title, field)
        if variant not in ('rack', 'D'):
            self.roof_mode = self.tracked('roof_mode', combo(['Ridge height', 'Slope 1:x']))
            self.roof_slope = self.tracked('roof_slope', number(10, .01, 10000))
            form.addRow('Roof definition', self.roof_mode)
            form.addRow('Slope, x', self.roof_slope)
            def roof_definition():
                slope = self.roof_mode.currentText() == 'Slope 1:x'
                self.roof_slope.setEnabled(slope)
                self.geometry_fields['ridge_height'].setEnabled(not slope)
            self.roof_mode.currentTextChanged.connect(roof_definition)
            roof_definition()
        row.addLayout(form, 1)
        self.body.addLayout(row)
        self.action_bar.addWidget(button('Export STAAD file', self.generate_structure))

    def generate_structure(self):
        from .core.productivity_generators import PipeRackConfig, ProductivityPebConfig, pipe_rack_commands, peb_commands
        def generate():
            values = {key: field.text() if isinstance(field, QLineEdit) else field.value() for key, field in self.geometry_fields.items()}
            values['unit'] = self.geometry_unit.currentText()
            if self.feature == 'rack':
                config = PipeRackConfig(**values)
                text = pipe_rack_commands(config)
            else:
                if hasattr(self, 'roof_mode') and self.roof_mode.currentText() == 'Slope 1:x':
                    values['roof_slope'] = self.roof_slope.value()
                config = ProductivityPebConfig(variant=self.feature[-1], **values)
                text = peb_commands(config)
            path = self.save_path('Save STAAD geometry', self.feature + '.std', 'STAAD model (*.std)')
            if path:
                Path(path).write_text(text, encoding='utf-8')
                self.feedback_text('Saved ' + path, 'success')
        self.guard(generate)
