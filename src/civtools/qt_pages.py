"""Consistent tool workflows inside the Qt workspace."""
from collections import OrderedDict
import json
import math
import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLineEdit,
    QDoubleSpinBox, QSpinBox, QComboBox, QFileDialog, QListWidget,
    QPlainTextEdit, QProgressBar, QScrollArea, QMessageBox, QTableView,
    QHeaderView, QAbstractItemView, QSplitter, QInputDialog, QTableWidget, QTableWidgetItem,
)
from .jobs import Job, run_quantities, run_mapper, run_piperack, run_dj, scan_pdfs, render_pdf
from .qt_widgets import label, button, panel, RackPreview, ComboBox, CheckBox as QCheckBox
from .qt_artwork import ToolIllustration, product_icon
from .core.geometry import rack_size
from .core.results import OperationResult
from .core.spreadsheet import inspect_mapping


def data_root():
    import sys
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]


def config_root():
    if os.environ.get("CIVTOOLS_CONFIG_DIR"):
        return Path(os.environ["CIVTOOLS_CONFIG_DIR"])
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "CivTools"


def number(value, minimum=-100000, maximum=100000):
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setDecimals(3)
    field.setValue(value)
    field.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    return field


def combo(items):
    field = ComboBox()
    field.addItems(items)
    return field


class ToolPage(QWidget):
    def __init__(self, window, title, description, category):
        super().__init__()
        self.window = window
        self.busy = False
        self.job = None
        self.state_key = None
        self.current_stage = ""
        self.operation_progress = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.update_elapsed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 12)
        layout.setSpacing(8)
        key = {"DXF quantity extractor": "quantities", "AutoCAD smart mapper": "mapper",
               "DJ parameter assigner": "dj", "Pipe rack modeler": "rack", "EIL standards library": "library"}[title]
        heading = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(4)
        copy.addWidget(label(title, "title"))
        copy.addWidget(label(description, "subtitle", True))
        heading.addLayout(copy, 1)
        self.header_art = ToolIllustration(key)
        heading.addWidget(self.header_art)
        layout.addLayout(heading)
        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        self.form = QWidget()
        self.body = QVBoxLayout(self.form)
        self.body.setContentsMargins(0, 6, 0, 6)
        self.body.setSpacing(10)
        scroll.setWidget(self.form)
        layout.addWidget(scroll, 1)
        self.feedback = label("Ready when you are.", "hint", True)
        self.feedback.setAccessibleName("Operation status")
        self.feedback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.feedback)
        self.target = label("", "muted", True)
        self.target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.target.hide()
        layout.addWidget(self.target)
        self.runtime = label("", "muted", True)
        self.runtime.hide()
        layout.addWidget(self.runtime)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.log_toggle = button("Activity", self.toggle_log, True)
        actions.addWidget(self.log_toggle)
        actions.addStretch()
        self.action_bar = actions
        layout.addLayout(actions)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMaximumHeight(150)
        self.log.hide()
        layout.addWidget(self.log)

    def restore_state(self, key):
        self.state_key = key
        names = {
            "quantities": ("workbook",), "mapper": ("workbook", "height", "offset", "sample_toggle"),
            "rack": ("trans", "long", "trans_levels", "long_levels", "base", "depth", "support", "bracing", "preview_toggle", "saved_toggle"),
            "dj": ("brief", "brief_number", "code", "scope", "material"),
            "library": ("search", "preview_toggle"),
        }
        self.state_fields = names[key]
        try:
            state = json.loads(str(self.window.settings.value(f"forms/{key}", "{}")))
            if not isinstance(state, dict):
                state = {}
        except (TypeError, ValueError):
            state = {}
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_state)
        for name in self.state_fields:
            field = getattr(self, name)
            if isinstance(field, FileField):
                field.settings = self.window.settings
                field = field.edit
            value = state.get(name)
            try:
                if isinstance(field, QLineEdit):
                    if value is not None:
                        field.setText(str(value))
                    signal = field.textChanged
                elif isinstance(field, QCheckBox):
                    if value is not None:
                        field.setChecked(bool(value))
                    signal = field.toggled
                elif isinstance(field, QComboBox):
                    if value is not None:
                        field.setCurrentText(str(value))
                    signal = field.currentTextChanged
                else:
                    if value is not None:
                        field.setValue(float(value) if isinstance(field, QDoubleSpinBox) else int(value))
                    signal = field.valueChanged
                signal.connect(lambda *args: self.save_timer.start())
            except (TypeError, ValueError, OverflowError):
                continue
        if key == "quantities":
            self.add_files([p for p in state.get("files", []) if isinstance(p, str) and Path(p).is_file()])
        if key == "mapper":
            self.preferred_sheet = str(state.get("sheet", ""))
        if key == "library" and isinstance(state.get("folder"), str):
            self.folder = state["folder"]
            self.folder_label.setText(self.folder)

    def save_state(self):
        if not self.state_key:
            return
        state = {}
        for name in self.state_fields:
            field = getattr(self, name)
            if isinstance(field, FileField):
                field = field.edit
            if isinstance(field, QLineEdit):
                value = field.text()
            elif isinstance(field, QCheckBox):
                value = field.isChecked()
            elif isinstance(field, QComboBox):
                value = field.currentText()
            else:
                value = field.value()
            state[name] = value
        if self.state_key == "quantities":
            state["files"] = self.files
        elif self.state_key == "library":
            state["folder"] = self.folder
        elif self.state_key == "mapper":
            state["sheet"] = self.sheet.currentText() or self.preferred_sheet
        self.window.settings.setValue(f"forms/{self.state_key}", json.dumps(state))

    def update_elapsed(self):
        elapsed = int(time.monotonic() - self.started)
        percent = f" · {self.operation_progress}%" if self.operation_progress is not None else ""
        self.runtime.setText(f"{self.current_stage}{percent} · {elapsed // 60}:{elapsed % 60:02d} elapsed")

    def toggle_log(self):
        visible = not self.log.isVisible()
        self.log.setVisible(visible)
        self.log_toggle.setText("Hide activity" if visible else "Activity")

    def feedback_text(self, text, kind="hint"):
        self.feedback.setText("\n".join(str(text).splitlines()[:3]))
        self.feedback.setToolTip(str(text))
        self.feedback.setObjectName(kind)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def run(self, operation, *, cad=False):
        if self.busy:
            return
        self.busy = True
        self.save_state()
        self.form.setEnabled(False)
        for i in range(self.action_bar.count()):
            widget = self.action_bar.itemAt(i).widget()
            if widget and widget is not self.log_toggle:
                widget.setEnabled(False)
        self.log.clear()
        self.feedback_text("Operation in progress. Other tools remain available.")
        self.target.hide()
        self.started = time.monotonic()
        self.current_stage = "Queued for CAD" if cad else "Starting…"
        self.operation_progress = None
        self.runtime.show()
        self.update_elapsed()
        self.elapsed_timer.start()
        self.progress.setRange(0, 0)
        self.progress.show()
        self.job = Job(operation, cad=cad)
        self.job.signals.event.connect(self.on_event)
        self.job.signals.succeeded.connect(self.on_success)
        self.job.signals.failed.connect(self.on_failure)
        self.job.signals.finished.connect(self.on_finished)
        (self.window.cad_pool if cad else self.window.pool).start(self.job)
        self.window.update_status()

    def on_event(self, kind, value):
        if kind == "progress":
            self.operation_progress = max(0, min(100, int(value)))
            self.progress.setRange(0, 100)
            self.progress.setValue(int(value))
            self.update_elapsed()
        elif kind == "target":
            self.target.setText(f"Target: {value}")
            self.target.show()
            self.log.appendPlainText(f"Target: {value}")
        elif kind == "stage":
            self.current_stage = str(value)
            self.update_elapsed()
            self.log.appendPlainText(str(value))
        else:
            self.log.appendPlainText(str(value))

    def on_success(self, result):
        warning = isinstance(result, OperationResult) and (result.failed or result.skipped)
        self.feedback_text(str(result), "warning" if warning else "success")
        self.current_stage = "Completed with issues" if warning else "Completed"
        self.log.appendPlainText(str(result))

    def on_failure(self, message):
        self.current_stage = "Failed"
        self.feedback_text(message, "error")
        self.log.appendPlainText(f"Error: {message}")
        self.log.show()
        self.log_toggle.setText("Hide activity")

    def on_finished(self):
        self.busy = False
        self.elapsed_timer.stop()
        self.update_elapsed()
        self.job = None
        self.form.setEnabled(True)
        for i in range(self.action_bar.count()):
            widget = self.action_bar.itemAt(i).widget()
            if widget:
                widget.setEnabled(True)
        self.progress.hide()
        self.window.update_status()

    def invalid(self, message):
        self.feedback_text(message, "error")


class FileField(QWidget):
    def __init__(self, caption="Choose a workbook…", file_filter="Excel workbooks (*.xlsx *.xlsm)"):
        super().__init__()
        self.file_filter = file_filter
        self.setAcceptDrops(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        workbook_icon = label("")
        workbook_icon.setPixmap(product_icon("excel", 26).pixmap(26, 26))
        workbook_icon.setToolTip("Excel workbook (.xlsx / .xlsm)")
        row.addWidget(workbook_icon)
        self.edit = QLineEdit()
        self.edit.setAcceptDrops(False)
        self.edit.setPlaceholderText(caption)
        self.edit.setAccessibleName(caption)
        row.addWidget(self.edit, 1)
        row.addWidget(button("Browse", self.browse, True))

    def dragEnterEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        if len(paths) == 1 and Path(paths[0]).suffix.lower() in (".xlsx", ".xlsm"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        if len(paths) == 1 and Path(paths[0]).is_file() and Path(paths[0]).suffix.lower() in (".xlsx", ".xlsm"):
            self.edit.setText(paths[0])
            event.acceptProposedAction()

    def browse(self):
        settings = getattr(self, "settings", None)
        initial = self.edit.text() or (str(settings.value("folders/workbooks", "")) if settings else "")
        path, _ = QFileDialog.getOpenFileName(self, "Select workbook", initial, self.file_filter)
        if path:
            self.edit.setText(path)
            if settings:
                settings.setValue("folders/workbooks", str(Path(path).parent))

    def path(self):
        path = Path(self.edit.text().strip())
        if not path.is_file() or path.suffix.lower() not in (".xlsx", ".xlsm"):
            raise ValueError("Select an existing .xlsx or .xlsm workbook.")
        return str(path)


class QuantityPage(ToolPage):
    def __init__(self, window):
        super().__init__(window, "DXF quantity extractor", "Drawing quantities, organized. Extract tables and produce a consolidated material takeoff.", "Quantities")
        self.files = []
        frame, layout = panel("01  Drawing files", "Choose DXF drawings containing Approximate Quantities tables.")
        row = QHBoxLayout()
        row.addWidget(button("Add DXF files", self.browse))
        row.addWidget(button("Remove", self.remove_selected, True))
        row.addWidget(button("Clear all", self.clear, True))
        row.addStretch()
        self.count = label("0 drawings selected", "muted")
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setMinimumHeight(70)
        self.list.setMaximumHeight(110)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.list.setStyleSheet("QListWidget { background: #F8FBF7; border: 1px solid #E1E9E0; border-radius: 8px; padding: 8px; } QListWidget::item { padding: 6px; }")
        self.list.hide()
        layout.addWidget(self.list)
        self.empty_files = label("Drop DXF files here, or use Add DXF files.", "hint", True)
        layout.addWidget(self.empty_files)
        layout.addWidget(self.count)
        self.body.addWidget(frame)
        frame, layout = panel("02  Mapping workbook", "Consolidation requires a Drawing_Structure_Mapping sheet. Extraction creates DXF_Extracted_Data.")
        self.workbook = FileField()
        layout.addWidget(self.workbook)
        layout.addWidget(label("Save results to a workbook you choose.", "muted", True))
        self.body.addWidget(frame)
        self.body.addStretch()
        self.consolidate_button = button("Consolidate", lambda: self.start(True), True)
        self.extract_button = button("Extract quantities  →", lambda: self.start(False))
        self.action_bar.addWidget(self.consolidate_button)
        self.action_bar.addWidget(self.extract_button)
        self.workbook.edit.textChanged.connect(self.update_ready)
        self.output_path = ""
        self.result_actions = QWidget()
        result_row = QHBoxLayout(self.result_actions)
        result_row.setContentsMargins(0, 0, 0, 0)
        result_row.addWidget(button("Open workbook", lambda: self.open_output(False), True))
        result_row.addWidget(button("Show in folder", lambda: self.open_output(True), True))
        result_row.addStretch()
        self.body.insertWidget(self.body.count() - 1, self.result_actions)
        self.result_actions.hide()
        self.update_ready()

    def browse(self):
        initial = str(self.window.settings.value("folders/drawings", ""))
        paths, _ = QFileDialog.getOpenFileNames(self, "Add drawings", initial, "DXF drawings (*.dxf)")
        if paths:
            self.window.settings.setValue("folders/drawings", str(Path(paths[0]).parent))
        self.add_files(paths)

    def add_files(self, paths):
        self.files = list(dict.fromkeys(self.files + paths))
        self.list.clear()
        for path in self.files:
            self.list.addItem(Path(path).name)
            self.list.item(self.list.count() - 1).setToolTip(path)
        self.count.setText(f"{len(self.files)} drawings selected")
        self.list.setVisible(bool(self.files))
        self.empty_files.setVisible(not self.files)
        self.update_ready()
        self.save_state()

    def remove_selected(self):
        for index in sorted((self.list.row(item) for item in self.list.selectedItems()), reverse=True):
            self.files.pop(index)
            self.list.takeItem(index)
        self.count.setText(f"{len(self.files)} drawings selected")
        self.list.setVisible(bool(self.files))
        self.empty_files.setVisible(not self.files)
        self.update_ready()
        self.save_state()

    def update_ready(self, *args):
        path = Path(self.workbook.edit.text().strip())
        ready = path.is_file() and path.suffix.lower() in (".xlsx", ".xlsm") and not self.busy
        self.consolidate_button.setEnabled(ready)
        self.extract_button.setEnabled(ready and bool(self.files))
        self.extract_button.setToolTip("Extract the selected drawings" if ready and self.files else "Add DXF drawings and choose a workbook first")
        self.consolidate_button.setToolTip("Consolidate extracted data" if ready else "Choose a workbook first")

    def on_finished(self):
        super().on_finished()
        self.update_ready()

    def on_success(self, result):
        super().on_success(result)
        if isinstance(result, OperationResult) and result.output_path:
            self.output_path = result.output_path
            self.result_actions.show()
            self.workbook.edit.setText(result.output_path)

    def open_output(self, folder):
        path = Path(self.output_path)
        target = path.parent if folder else path
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            self.invalid("The output could not be opened. Check its location and default application.")

    def dragEnterEvent(self, event):
        if not self.busy and any(Path(url.toLocalFile()).suffix.lower() in (".dxf", ".xlsx", ".xlsm") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.busy:
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile() and Path(url.toLocalFile()).is_file()]
        drawings = [p for p in paths if Path(p).suffix.lower() == ".dxf"]
        workbooks = [p for p in paths if Path(p).suffix.lower() in (".xlsx", ".xlsm")]
        if workbooks:
            self.workbook.edit.setText(workbooks[0])
        self.add_files(drawings)
        event.acceptProposedAction()

    def clear(self):
        self.files.clear()
        self.list.clear()
        self.count.setText("0 drawings selected")
        self.list.hide()
        self.empty_files.show()
        self.update_ready()
        self.save_state()

    def start(self, consolidate):
        try:
            source = self.workbook.path()
            if not consolidate and not self.files:
                raise ValueError("Add at least one DXF drawing to extract.")
            if not consolidate and any(not Path(p).is_file() for p in self.files):
                raise ValueError("A selected drawing is no longer available. Choose the files again.")
            suggested = str(Path(source).with_stem(Path(source).stem + "_civtools"))
            suffix = Path(source).suffix
            destination, _ = QFileDialog.getSaveFileName(self, "Save results workbook", suggested, f"Excel workbook (*{suffix})")
            if not destination:
                return
            if not Path(destination).suffix:
                destination += suffix
            if Path(destination).suffix.lower() != suffix.lower():
                raise ValueError("Use the same workbook extension to preserve its format and macros.")
            files = self.files.copy()
            self.result_actions.hide()
            self.run(lambda report: run_quantities(source, destination, files, consolidate, report))
        except ValueError as error:
            self.invalid(str(error))


class MapperPage(ToolPage):
    def __init__(self, window):
        super().__init__(window, "AutoCAD smart mapper", "Preview worksheet data, then plot labeled boxes into the active drawing.", "Drawings")
        self.preview_job = None
        self.pending_inspection = False
        self.mapping = None
        self.preferred_sheet = ""
        self.inspection_request = None
        frame, layout = panel("Drawing data", "Columns A–E: X, Y, width, height, label. Data starts at row 2.")
        self.workbook = FileField()
        layout.addWidget(self.workbook)
        row = QHBoxLayout()
        row.addWidget(label("Worksheet"))
        self.sheet = ComboBox()
        self.sheet.setAccessibleName("Worksheet to plot")
        self.sheet.setEnabled(False)
        row.addWidget(self.sheet, 1)
        self.inspect_button = button("Refresh", self.schedule_inspection, True)
        row.addWidget(self.inspect_button)
        layout.addLayout(row)
        self.validation = label("Choose a workbook to validate its rows.", "muted", True)
        layout.addWidget(self.validation)
        self.sample_toggle = QCheckBox("Show sample rows")
        layout.addWidget(self.sample_toggle)
        self.sample = QTableWidget(0, 7)
        self.sample.setHorizontalHeaderLabels(["Row", "X", "Y", "Width", "Height", "Label", "Check"])
        self.sample.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sample.setAlternatingRowColors(True)
        self.sample.verticalHeader().hide()
        self.sample.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.sample.setMinimumHeight(130)
        self.sample.setMaximumHeight(210)
        self.sample.hide()
        self.sample_toggle.toggled.connect(self.sample.setVisible)
        layout.addWidget(self.sample)
        self.body.addWidget(frame)
        frame, layout = panel("Label settings (drawing units)")
        form = QGridLayout()
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        self.height = number(250, .001)
        self.offset = number(125, 0)
        self.height.setAccessibleName("Text height in drawing units")
        self.offset.setAccessibleName("Offset below box in drawing units")
        for column, (caption, field) in enumerate((("Text height", self.height), ("Offset below box", self.offset))):
            form.addWidget(label(caption), 0, column)
            form.addWidget(field, 1, column)
        layout.addLayout(form)
        self.body.addWidget(frame)
        self.body.addStretch()
        self.plot_button = button("Plot to AutoCAD  →", self.start)
        self.plot_button.setEnabled(False)
        self.action_bar.addWidget(self.plot_button)
        self.inspection_timer = QTimer(self)
        self.inspection_timer.setSingleShot(True)
        self.inspection_timer.setInterval(300)
        self.inspection_timer.timeout.connect(self.inspect_workbook)
        self.workbook.edit.textChanged.connect(self.workbook_changed)
        self.sheet.currentTextChanged.connect(self.schedule_inspection)
        self.feedback_text("Open the target drawing in AutoCAD before plotting.")

    def workbook_changed(self, *args):
        self.preferred_sheet = ""
        self.sheet.blockSignals(True)
        self.sheet.clear()
        self.sheet.blockSignals(False)
        self.schedule_inspection()

    def schedule_inspection(self, *args):
        self.mapping = None
        self.plot_button.setEnabled(False)
        self.validation.setText("Checking worksheet…")
        self.inspection_timer.start()

    def inspect_workbook(self):
        if self.preview_job is not None:
            self.pending_inspection = True
            return
        self.pending_inspection = False
        try:
            path = self.workbook.path()
        except ValueError as error:
            self.validation.setText(str(error))
            self.sample.setRowCount(0)
            return
        sheet = self.sheet.currentText() or self.preferred_sheet or None
        self.inspection_request = (path, sheet)
        self.preview_job = Job(lambda report: inspect_mapping(path, sheet, report))
        self.preview_job.signals.succeeded.connect(self.inspection_ready)
        self.preview_job.signals.failed.connect(self.inspection_failed)
        self.preview_job.signals.finished.connect(self.inspection_finished)
        self.window.pool.start(self.preview_job)

    def inspection_current(self):
        return self.inspection_request == (self.workbook.edit.text().strip(), self.sheet.currentText() or self.preferred_sheet or None) and not self.inspection_timer.isActive() and not self.pending_inspection

    def inspection_ready(self, result):
        if not self.inspection_current():
            return
        self.mapping = result
        self.sheet.blockSignals(True)
        self.sheet.clear()
        self.sheet.addItems(result["sheet_names"])
        self.sheet.setCurrentText(result["sheet"])
        self.sheet.blockSignals(False)
        self.sheet.setEnabled(True)
        self.preferred_sheet = result["sheet"]
        self.validation.setText(f"{result['valid']:,} valid · {result['invalid']:,} invalid · {result['skipped']:,} blank rows. Invalid and blank rows will be skipped.")
        self.sample.setRowCount(len(result["sample"]))
        for row, (number, values, status) in enumerate(result["sample"]):
            for column, value in enumerate((number,) + values + (status,)):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setToolTip(item.text())
                self.sample.setItem(row, column, item)
        self.plot_button.setEnabled(result["valid"] > 0 and not self.busy)
        self.save_state()

    def inspection_failed(self, message):
        if self.inspection_current():
            self.mapping = None
            self.validation.setText(f"Workbook unavailable: {message}")
            self.sample.setRowCount(0)

    def inspection_finished(self):
        self.preview_job = None
        if self.pending_inspection:
            self.inspect_workbook()

    def on_finished(self):
        super().on_finished()
        self.plot_button.setEnabled(bool(self.mapping and self.mapping["valid"]))

    def start(self):
        try:
            path = self.workbook.path()
            if not self.mapping or not self.mapping["valid"]:
                raise ValueError("Choose a worksheet with valid rows before plotting.")
            height, offset, sheet = self.height.value(), self.offset.value(), self.sheet.currentText()
            self.run(lambda report: run_mapper(path, height, offset, report, sheet), cad=True)
        except ValueError as error:
            self.invalid(str(error))


class DJPage(ToolPage):
    def __init__(self, window):
        super().__init__(window, "DJ parameter assigner", "Assign member end-node design parameters to physical members in STAAD.Pro.", "Modeling")
        frame, layout = panel("Design brief", "Keep the STAAD model open. Assignment applies DJ1 and DJ2 to analytical members within each physical member.")
        form = QFormLayout()
        form.setSpacing(16)
        self.brief = combo(["New", "Existing"])
        self.brief_number = QSpinBox()
        self.brief_number.setRange(1, 99999)
        self.brief_number.setValue(2)
        self.code = combo(["IS800 LSD", "IS800 WSD", "IS800 1984", "AISC 360-05", "AISC 360-10", "AISC 360-16", "AISC"])
        form.addRow("Design brief", self.brief)
        form.addRow("Existing brief number", self.brief_number)
        form.addRow("Design code", self.code)
        self.brief_form = form
        layout.addLayout(form)
        self.body.addWidget(frame)
        frame, layout = panel("Member scope")
        form = QFormLayout()
        form.setSpacing(16)
        self.scope = combo(["All Member with Material", "All Members"])
        self.material = combo(["STEEL", "CONCRETE", "ALUMINUM", "TIMBER"])
        form.addRow("Assign to", self.scope)
        form.addRow("Material", self.material)
        layout.addLayout(form)
        self.body.addWidget(frame)
        self.body.addStretch()
        self.brief.currentTextChanged.connect(self.update_fields)
        self.scope.currentTextChanged.connect(self.update_fields)
        self.load_settings()
        self.update_fields()
        self.action_bar.addWidget(button("Assign DJ parameters  →", self.start))

    def update_fields(self, *args):
        existing = self.brief.currentText() == "Existing"
        self.brief_number.setEnabled(existing)
        self.code.setEnabled(not existing)
        self.brief_form.setRowVisible(self.brief_number, existing)
        self.brief_form.setRowVisible(self.code, not existing)
        self.material.setEnabled(self.scope.currentIndex() == 0)

    def load_settings(self):
        paths = [config_root() / "staad_dj_settings.json", data_root() / "staad_dj_settings.json"]
        for path in paths:
            if not path.is_file():
                continue
            try:
                settings = json.loads(path.read_text(encoding="utf-8"))
                for field, key in ((self.brief, "design_brief"), (self.code, "design_code"), (self.scope, "member_selection"), (self.material, "material")):
                    index = field.findText(str(settings.get(key, "")))
                    if index >= 0:
                        field.setCurrentIndex(index)
                self.brief_number.setValue(int(settings.get("brief_number", 2)))
            except (OSError, ValueError, TypeError):
                self.invalid("Saved DJ settings could not be read. Defaults are available.")
            break

    def start(self):
        config = {"brief_option": self.brief.currentText(), "existing_brief_number": self.brief_number.value(),
                  "design_code": self.code.currentText(), "member_selection": self.scope.currentText(), "material_filter": self.material.currentText()}
        settings = {"design_brief": config["brief_option"], "brief_number": config["existing_brief_number"],
                    "design_code": config["design_code"], "member_selection": config["member_selection"], "material": config["material_filter"]}
        try:
            root = config_root()
            root.mkdir(parents=True, exist_ok=True)
            (root / "staad_dj_settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except OSError as error:
            self.invalid(f"Cannot save settings: {error}")
            return
        self.run(lambda report: run_dj(config, report), cad=True)

    def on_finished(self):
        super().on_finished()
        self.update_fields()


def parse_series(text, title, minimum):
    try:
        values = [float(v.strip()) for v in text.split(",")]
    except ValueError:
        raise ValueError(f"{title}: enter numbers separated by commas.") from None
    if len(values) < minimum:
        raise ValueError(f"{title}: enter at least {minimum} values.")
    if any(not math.isfinite(v) for v in values) or any(a >= b for a, b in zip(values, values[1:])):
        raise ValueError(f"{title}: values must be finite and strictly increasing.")
    return values


class RackPage(ToolPage):
    def __init__(self, window):
        super().__init__(window, "Pipe rack modeler", "Define your structure. Preview the geometry. Generate it directly in STAAD.Pro.", "Modeling")
        self.saved_configs = []
        top = QVBoxLayout()
        frame, layout = panel("Geometry", "Use absolute grid positions and elevations, in meters, separated by commas.")
        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        self.trans = QLineEdit("0, 6")
        self.long = QLineEdit("0, 8, 16, 24")
        self.trans_levels = QLineEdit("3, 6")
        self.long_levels = QLineEdit("3, 6")
        self.base = number(0)
        self.depth = number(1.5, .001)
        self.support = combo(["Fixed", "Pinned"])
        self.bracing = QCheckBox("Include longitudinal V-bracing")
        self.bracing.setChecked(True)
        for index, (caption, field) in enumerate((("Transverse grids", self.trans), ("Longitudinal grids", self.long),
                               ("Transverse tiers", self.trans_levels), ("Longitudinal tiers", self.long_levels),
                               ("Base elevation", self.base), ("Foundation depth", self.depth), ("Supports", self.support))):
            field.setAccessibleName(caption)
            row, column = (index // 2) * 2, index % 2
            form.addWidget(label(caption), row, column)
            form.addWidget(field, row + 1, column)
        layout.addLayout(form)
        self.bracing.setText("Longitudinal V-bracing")
        form.addWidget(self.bracing, 6, 1, 2, 1)
        top.addWidget(frame)
        self.geometry_status = label("", "muted", True)
        top.addWidget(self.geometry_status)
        self.preview_toggle = QCheckBox("Show geometry preview")
        self.preview_controls = QHBoxLayout()
        self.preview_controls.addWidget(self.preview_toggle)
        top.addLayout(self.preview_controls)
        frame, layout = panel("Structure preview")
        self.preview_panel = frame
        frame.hide()
        self.preview_toggle.toggled.connect(frame.setVisible)
        self.preview = RackPreview()
        layout.addWidget(self.preview, 1)
        self.summary = label("", "muted", True)
        layout.addWidget(self.summary)
        layout.addWidget(label("Geometry preview • not a design check", "muted", True))
        self.preview.setMaximumHeight(230)
        top.addWidget(frame)
        self.body.addLayout(top)
        frame, layout = panel("Saved configurations")
        self.saved_toggle = QCheckBox("Saved configurations")
        self.saved_toggle.toggled.connect(frame.setVisible)
        frame.hide()
        self.preview_controls.addWidget(self.saved_toggle)
        row = QHBoxLayout()
        self.saved = combo(["Choose a configuration…"])
        row.addWidget(self.saved, 1)
        row.addWidget(button("Load", self.load_config, True))
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button("Save current", self.save_config, True))
        row.addWidget(button("Delete", self.delete_config, True))
        row.addStretch()
        layout.addLayout(row)
        self.body.addWidget(frame)
        self.feedback_text("Open a blank STAAD model before generating. Positions and elevations are in meters.")
        self.body.addStretch()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(150)
        self.preview_timer.timeout.connect(self.update_preview)
        for field in (self.trans, self.long, self.trans_levels, self.long_levels):
            field.textChanged.connect(lambda: self.preview_timer.start())
        for field in (self.base, self.depth):
            field.valueChanged.connect(lambda: self.preview_timer.start())
        self.bracing.toggled.connect(lambda: self.preview_timer.start())
        self.generate_button = button("Generate in STAAD  →", self.start)
        self.action_bar.addWidget(self.generate_button)
        self.read_configs()
        self.update_preview()

    def configuration(self):
        trans = parse_series(self.trans.text(), "Transverse grids", 2)
        long = parse_series(self.long.text(), "Longitudinal grids", 2)
        trans_levels = parse_series(self.trans_levels.text(), "Transverse tiers", 1)
        long_levels = parse_series(self.long_levels.text(), "Longitudinal tiers", 1)
        if min(trans_levels[0], long_levels[0]) <= self.base.value():
            raise ValueError("Beam elevations must be above the base elevation.")
        if len(trans) > 100 or len(long) > 100 or len(trans_levels) > 50 or len(long_levels) > 50:
            raise ValueError("Use up to 100 grids per direction and 50 tiers per direction.")
        config = {"num_transverse_grids": len(trans), "num_longitudinal_grids": len(long),
                "transverse_spacing": trans, "longitudinal_spacing": long,
                "num_trans_tiers": len(trans_levels), "num_long_tiers": len(long_levels),
                "trans_beam_elevations": trans_levels, "long_beam_elevations": long_levels,
                "base_elevation": self.base.value(), "foundation_depth": self.depth.value(),
                "support_type": self.support.currentText(), "bracing_enabled": self.bracing.isChecked()}
        rack_size(config)
        return config

    def update_preview(self):
        errors = []
        for field, title, minimum in ((self.trans, "Transverse grids", 2), (self.long, "Longitudinal grids", 2),
                                      (self.trans_levels, "Transverse tiers", 1), (self.long_levels, "Longitudinal tiers", 1)):
            try:
                values = parse_series(field.text(), title, minimum)
                if "tiers" in title and values[0] <= self.base.value():
                    raise ValueError(f"{title}: absolute elevations must be above the base.")
                message = ""
            except ValueError as error:
                message = str(error)
                errors.append(message)
            field.setProperty("invalid", bool(message))
            field.setToolTip(message or "Absolute positions / elevations in meters, separated by commas")
            field.style().unpolish(field)
            field.style().polish(field)
        try:
            if errors:
                raise ValueError("\n".join(errors))
            config = self.configuration()
            self.preview.set_config(config)
            nodes, beams, calls = rack_size(config)
            self.geometry_status.setText(f"{nodes:,} nodes · {beams:,} beams · approximately {calls:,} CAD calls")
            self.geometry_status.setObjectName("muted")
            self.generate_button.setEnabled(not self.busy)
            if getattr(self, "geometry_invalid", False) and not self.busy:
                self.feedback_text("Open a blank STAAD model before generating. All elevations are absolute, in meters.")
            self.geometry_invalid = False
            self.summary.setText(f"{config['num_transverse_grids']} × {config['num_longitudinal_grids']} grids\n"
                                 f"{config['num_trans_tiers']} transverse / {config['num_long_tiers']} longitudinal tiers")
        except ValueError as error:
            self.geometry_invalid = True
            if not self.busy:
                self.feedback_text(str(error), "error")
            self.preview.set_config(None)
            self.generate_button.setEnabled(False)
            self.geometry_status.setText(str(error))
            self.geometry_status.setObjectName("error")
            self.summary.setText(str(error))
        self.geometry_status.style().unpolish(self.geometry_status)
        self.geometry_status.style().polish(self.geometry_status)

    def on_finished(self):
        super().on_finished()
        self.update_preview()

    def read_configs(self):
        path = config_root() / "pipe_rack_configs.json"
        try:
            if path.is_file():
                values = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(values, list):
                    raise ValueError("Expected a list of configurations")
                self.saved_configs = [v for v in values if isinstance(v, dict) and "name" in v]
        except (OSError, ValueError):
            self.invalid("Saved pipe rack configurations could not be read.")
        self.refresh_configs()

    def refresh_configs(self):
        self.saved.clear()
        self.saved.addItem("Choose a configuration…")
        self.saved.addItems([str(c["name"]) for c in self.saved_configs])

    def persist_configs(self):
        root = config_root()
        root.mkdir(parents=True, exist_ok=True)
        path = root / "pipe_rack_configs.json"
        staging = path.with_suffix(".tmp")
        staging.write_text(json.dumps(self.saved_configs, indent=2), encoding="utf-8")
        staging.replace(path)
        self.refresh_configs()

    def save_config(self):
        try:
            config = self.configuration()
            name, accepted = QInputDialog.getText(self, "Save configuration", "Configuration name")
            if not accepted or not name.strip():
                return
            config["name"] = name.strip()
            self.saved_configs.append(config)
            try:
                self.persist_configs()
            except OSError:
                self.saved_configs.pop()
                raise
            self.feedback_text(f"Saved configuration: {name.strip()}", "success")
        except (OSError, ValueError) as error:
            self.invalid(str(error))

    def load_config(self):
        index = self.saved.currentIndex() - 1
        if index < 0:
            self.invalid("Choose a saved configuration first.")
            return
        config = self.saved_configs[index]
        # Older versions stored the geometry in a nested 'config' object.
        config = config.get("config", config)
        try:
            for field, key in ((self.trans, "transverse_spacing"), (self.long, "longitudinal_spacing"),
                               (self.trans_levels, "trans_beam_elevations"), (self.long_levels, "long_beam_elevations")):
                field.setText(", ".join(str(v) for v in config[key]))
            self.base.setValue(float(config.get("base_elevation", 0)))
            self.depth.setValue(float(config.get("foundation_depth", 1.5)))
            self.support.setCurrentText(config.get("support_type", "Fixed"))
            self.bracing.setChecked(bool(config.get("bracing_enabled", False)))
            self.configuration()
            self.feedback_text("Configuration loaded.", "success")
        except (KeyError, TypeError, ValueError) as error:
            self.invalid(f"Invalid saved configuration: {error}")

    def delete_config(self):
        index = self.saved.currentIndex() - 1
        if index < 0:
            return
        if QMessageBox.question(self, "Delete configuration", f"Delete '{self.saved_configs[index]['name']}'?") != QMessageBox.StandardButton.Yes:
            return
        removed = self.saved_configs.pop(index)
        try:
            self.persist_configs()
        except OSError as error:
            self.saved_configs.insert(index, removed)
            self.invalid(str(error))

    def start(self):
        try:
            config = self.configuration()
            self.run(lambda report: run_piperack(config, report), cad=True)
        except ValueError as error:
            self.invalid(str(error))


class DocumentModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.documents = []

    def set_documents(self, documents):
        self.beginResetModel()
        self.documents = documents
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.documents)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        document = self.documents[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (document[0], f"{document[2] / 1048576:.2f} MB", str(document[3]))[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return document[index.column() + 1] if index.column() > 0 else document[0].casefold()
        if role == Qt.ItemDataRole.ToolTipRole:
            return document[1]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("Document", "Size", "Pages")[section]


class LibraryPage(ToolPage):
    def __init__(self, window):
        super().__init__(window, "EIL standards library", "Your engineering reference desk. Find a standard and preview it without leaving the workspace.", "Documents")
        self.folder = str(data_root() / "data" / "EIL STD")
        self.cache = OrderedDict()
        self.selected = None
        self.preview_job = None
        self.pending_preview = None
        self.preview_generation = 0
        self.rendered_pixmap = None
        frame, layout = panel("Document collection")
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search document names…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        row.addWidget(button("Choose folder", self.choose_folder, True))
        row.addWidget(button("Refresh", self.refresh, True))
        self.preview_toggle = QCheckBox("Preview")
        row.addWidget(self.preview_toggle)
        layout.addLayout(row)
        self.folder_label = label(self.folder, "muted", True)
        layout.addWidget(self.folder_label)
        splitter = QSplitter()
        self.table = QTableView()
        self.model = DocumentModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(0)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 95)
        self.table.setColumnWidth(2, 65)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.selectionModel().selectionChanged.connect(self.select_document)
        self.table.doubleClicked.connect(self.open_document)
        splitter.addWidget(self.table)
        preview_frame, preview_layout = panel("Preview")
        self.preview_panel = preview_frame
        preview_frame.hide()
        self.preview_toggle.toggled.connect(self.preview_visibility_changed)
        self.preview_label = label("Select a document to preview", "muted", True)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(180, 200)
        preview_layout.addWidget(self.preview_label, 1)
        self.details = label("", "muted", True)
        preview_layout.addWidget(self.details)
        self.open_button = button("Open document  ↗", self.open_document)
        self.open_button.setEnabled(False)
        self.action_bar.addWidget(self.open_button)
        splitter.addWidget(preview_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([550, 350])
        splitter.setMinimumHeight(240)
        self.splitter = splitter
        layout.addWidget(splitter, 1)
        self.body.addWidget(frame, 1)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(150)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.search_timer.timeout.connect(self.apply_search)
        self.scale_timer = QTimer(self)
        self.scale_timer.setSingleShot(True)
        self.scale_timer.setInterval(60)
        self.scale_timer.timeout.connect(self.scale_preview)
        self.splitter.splitterMoved.connect(lambda *args: self.scale_timer.start())
        QTimer.singleShot(0, self.refresh)

    def preview_visibility_changed(self, checked):
        self.preview_panel.setVisible(checked)
        if checked:
            self.select_document()
            self.scale_timer.start()
        else:
            self.pending_preview = None

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Standards folder", self.folder)
        if path:
            self.folder = path
            self.folder_label.setText(path)
            self.save_state()
            self.refresh()

    def refresh(self):
        self.preview_generation += 1
        self.cache.clear()
        self.selected = None
        self.pending_preview = None
        self.rendered_pixmap = None
        self.preview_label.clear()
        self.preview_label.setText("Select a document to preview")
        self.open_button.setEnabled(False)
        self.details.clear()
        folder = self.folder
        cache_path = config_root() / "pdf_metadata_cache.json"
        self.run(lambda report: self.window.pdf.call("scan", report, folder, str(cache_path)))

    def on_success(self, documents):
        self.current_stage = "Library ready"
        self.model.set_documents(documents)
        self.apply_search()

    def on_finished(self):
        super().on_finished()
        self.open_button.setEnabled(self.selected is not None)

    def apply_search(self):
        self.proxy.setFilterFixedString(self.search.text())
        total = len(self.model.documents)
        if total:
            self.feedback_text(f"{self.proxy.rowCount()} of {total} documents  ·  Double-click to open.")
        else:
            self.feedback_text("No PDF documents found. Choose a folder containing your engineering standards.")

    def select_document(self, *args):
        rows = self.table.selectionModel().selectedRows()
        self.selected = self.model.documents[self.proxy.mapToSource(rows[0]).row()] if rows else None
        self.open_button.setEnabled(self.selected is not None)
        if not self.selected:
            self.pending_preview = None
            self.rendered_pixmap = None
            self.preview_label.clear()
            self.preview_label.setText("Select a document to preview")
            self.details.clear()
            return
        doc = self.selected
        self.details.setText(f"{doc[0]}\n{doc[3]} pages  ·  {doc[2] / 1048576:.2f} MB")
        if not self.preview_toggle.isChecked():
            self.pending_preview = None
            return
        self.rendered_pixmap = None
        self.preview_label.clear()
        self.preview_label.setText("Rendering preview…")
        key = (doc[1], doc[2], doc[4])
        if key in self.cache:
            self.cache.move_to_end(key)
            self.show_preview(self.cache[key])
            self.pending_preview = None
        else:
            # One active render and only the latest requested selection queued.
            self.pending_preview = (doc, key, self.preview_generation)
            self.start_preview()

    def start_preview(self):
        if self.preview_job is not None or self.pending_preview is None or not self.preview_toggle.isChecked():
            return
        doc, key, generation = self.pending_preview
        self.pending_preview = None
        self._render_request = (doc, key, generation)
        self.preview_job = Job(lambda report: self.window.pdf.call("render", report, doc[1]))
        self.preview_job.signals.succeeded.connect(self.preview_ready)
        self.preview_job.signals.failed.connect(self.preview_failed)
        self.preview_job.signals.finished.connect(self.preview_finished)
        self.window.pool.start(self.preview_job)

    def preview_ready(self, image):
        doc, key, generation = self._render_request
        if generation != self.preview_generation:
            return
        self.cache[key] = image
        self.cache.move_to_end(key)
        while len(self.cache) > 12:
            self.cache.popitem(last=False)
        if self.selected == doc:
            self.show_preview(image)

    def preview_failed(self, message):
        doc, key, generation = self._render_request
        if generation == self.preview_generation and self.selected == doc:
            self.preview_label.setText(f"Preview unavailable\n{message}")

    def preview_finished(self):
        self.preview_job = None
        self.start_preview()

    def show_preview(self, image):
        pixmap = QPixmap()
        pixmap.loadFromData(image)
        self.rendered_pixmap = pixmap
        self.scale_preview()

    def scale_preview(self):
        if self.rendered_pixmap:
            self.preview_label.setPixmap(self.rendered_pixmap.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "splitter"):
            self.splitter.setOrientation(Qt.Orientation.Vertical if self.width() < 720 else Qt.Orientation.Horizontal)
        if hasattr(self, "scale_timer"):
            self.scale_timer.start()

    def open_document(self, *args):
        if self.selected:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(self.selected[1])):
                self.invalid("The document could not be opened. Check your default PDF application.")
