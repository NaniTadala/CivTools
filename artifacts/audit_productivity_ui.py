"""Offline visual audit of all STAAD suite tools, states and native palettes.

Run a fresh process for each QT_SCALE_FACTOR. No COM connections are made.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--theme', choices=['light', 'dark'], default='light')
parser.add_argument('--native', action='store_true')
args = parser.parse_args()
if not args.native:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPalette, QColor, QPixmap, QPainter, QFont
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QToolButton, QAbstractSpinBox, QTableView
from unittest.mock import patch
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
from civtools.qt_productivity import WORKBENCH_TITLES
from civtools.qt_productivity_tools import OutputDialog, PreparedAction
from civtools.core.staad_productivity import ModelSnapshot
from civtools.core.productivity_model_tools import selected_release_plan, release_plan_commands

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
if args.theme == 'dark':
    palette = QPalette()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button, QPalette.ColorRole.AlternateBase):
        palette.setColor(role, QColor('#202020'))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(role, QColor('#eeeeee'))
    app.setPalette(palette)
scale = os.environ.get('QT_SCALE_FACTOR', '1')
output = Path(__file__).parent / 'visual-audit' / (('native-' if args.native else '') + args.theme + '-' + scale)
output.mkdir(parents=True, exist_ok=True)
shots = []
issues = []

def capture(name, widget, audit=True):
    app.processEvents()
    widget.grab().save(str(output / (name + '.png')))
    shots.append((name, widget.grab()))
    if not audit:
        return
    for table in widget.findChildren(QTableView):
        if not table.isVisibleTo(widget):
            continue
        header = table.horizontalHeader()
        for column in range(table.model().columnCount()):
            if table.isColumnHidden(column):
                continue
            caption = str(table.model().headerData(column, Qt.Orientation.Horizontal) or '')
            if header.sectionSize(column) < header.fontMetrics().horizontalAdvance(caption) + 12:
                issues.append([name, caption, header.sectionSize(column), 'table heading too narrow'])
    # Measure controls in their own coordinates, including native spin editors.
    for field in widget.findChildren(QPushButton) + widget.findChildren(QToolButton):
        if not field.isVisibleTo(widget) or not field.text():
            continue
        if field.rect().width() < field.fontMetrics().horizontalAdvance(field.text()) + 14:
            issues.append([name, field.text(), field.width(), 'button text too narrow'])
    for field in widget.findChildren(QAbstractSpinBox):
        if not field.isVisibleTo(widget):
            continue
        editor = field.findChild(__import__('PySide6.QtWidgets', fromlist=['QLineEdit']).QLineEdit)
        if editor and editor.width() < editor.fontMetrics().horizontalAdvance(editor.text()) + 3:
            issues.append([name, editor.text(), editor.width(), 'numeric editor too narrow'])

with tempfile.TemporaryDirectory() as folder:
    os.environ['CIVTOOLS_CONFIG_DIR'] = folder
    window = CivToolsApp()
    window.navigate('productivity')
    suite = window.pages['productivity']
    host = window.utility_windows['productivity']
    model = ModelSnapshot('Example_Shed.std', 'Metric',
        {1: (0, 0, 0), 2: (0, 6, 0), 3: (10, 6, 0), 4: (10, 0, 0)},
        {101: (1, 2), 102: (2, 3), 103: (3, 4)}, [1, 4], [1, 2], primary_cases=[1])
    suite.open_feature('select').set_snapshot(model)
    for key in ('select', 'renumber', 'groups', 'releases', 'parameters', 'rack', 'pebA', 'pebB', 'pebC', 'pebD', 'tables', 'combinations', 'girders'):
        page = suite.open_feature(key)
        capture(key, host)
        if key.startswith('peb'):
            page.content_scroll.verticalScrollBar().setValue(page.content_scroll.verticalScrollBar().maximum())
            capture(key + '-bottom', host)
            page.content_scroll.verticalScrollBar().setValue(0)
    page = suite.open_feature('parameters')
    page.tabs.setCurrentIndex(1)
    capture('parameters-steel', host)
    for menu_name, menu in [('presets-menu', next(button.menu() for button in page.findChildren(QToolButton) if button.text() == 'Presets')), ('options-menu', suite.options_menu)]:
        menu.popup(host.mapToGlobal(QPoint(20, 160)))
        capture(menu_name, menu)
        menu.hide()
    suite.tool_picker.showPopup()
    capture('tool-picker-popup', suite.tool_picker.view().window())
    suite.tool_picker.hidePopup()
    table = page.parameter_tables['steel']
    table.edit(page.models['steel'].index(0, 2))
    capture('parameters-editing', host)
    table.setFocus()
    page.tabs.setCurrentIndex(2)
    page.output.setPlainText('PARAMETER 1\nCODE IS800 LSD\nFYLD 250000 MEMB 101 TO 103\nCHECK CODE MEMB 101 TO 103')
    capture('parameters-preview', host)
    page.tabs.setCurrentIndex(0)
    suite.toggle_expanded()
    capture('parameters-expanded', host)
    suite.show_compact()
    page = suite.open_feature('select')
    page.member_details_toggle.setChecked(True)
    capture('select-details', host)
    page.content_scroll.ensureWidgetVisible(page.members)
    capture('select-member-table', host)
    page.member_details_toggle.setChecked(False)
    page = suite.open_feature('releases')
    plan = selected_release_plan(model, [101, 102, 103], 'BOTH', ('MZ',))
    page.on_success(PreparedAction(model, 'releases', {'plan': plan, 'end': 'BOTH', 'dofs': ('MZ',)}, release_plan_commands(plan), plan.summary))
    capture('releases-reviewed', host)
    page.release_details_toggle.setChecked(True)
    capture('releases-details', host)
    app.processEvents()
    page.content_scroll.verticalScrollBar().setValue(page.content_scroll.verticalScrollBar().maximum())
    capture('releases-details-bottom', host)
    page.content_scroll.ensureWidgetVisible(page.release_table)
    capture('release-member-table', host)
    page = suite.open_feature('tables')
    for case, text in [(1, '1 - Primary - Dead load'), (2, '2 - Primary - Live load'), (101, '101 - Combination - Gravity ULS')]:
        page.add_case(page.available_cases, case, text)
    page.available_cases.item(0).setSelected(True)
    page.move_cases(page.available_cases, page.selected_cases)
    capture('tables-populated', host)
    page = suite.open_feature('rack')
    page.preview_toggle.setChecked(True)
    app.processEvents()
    page.content_scroll.verticalScrollBar().setValue(page.content_scroll.verticalScrollBar().maximum())
    capture('rack-preview', host)
    suite.open_feature('pebC')
    suite.toggle_collapsed()
    capture('folded', host)
    suite.toggle_collapsed()
    suite.favourites = ['parameters', 'combinations', 'rack', 'girders']
    for key, action in suite.buttons.items():
        action.setVisible(key in suite.favourites)
    capture('custom-favourites', host)
    # Modal dialogs are rendered and dismissed without performing operations.
    def capture_dialog(dialog):
        dialog.show()
        capture('custom-girder-dialog', dialog)
        dialog.reject()
        return QDialog.DialogCode.Rejected
    with patch.object(QDialog, 'exec', capture_dialog):
        suite.open_feature('girders').custom_girder_dialog()
    dialog = OutputDialog(suite.children_windows['groups'].page, 'START GROUP DEFINITION\nMEMBER\n_BEAMS 102\nEND GROUP DEFINITION')
    dialog.show()
    capture('output-dialog', dialog)
    dialog.close()
    suite.open_feature('parameters')
    suite.detach_active()
    capture('detached-parameters', suite.children_windows['parameters'])
    suite.dock_active()
    capture('redocked-parameters', host)
    host.resize(360, 480)
    capture('minimum-width-parameters', host)
    page = suite.children_windows['parameters'].page
    page.tabs.setCurrentIndex(1)
    page.parameter_tables['steel'].selectRow(1)
    capture('minimum-width-steel', host)
    host.resize(420, 480)
    suite.open_feature('releases')
    suite.children_windows['releases'].page.clear_release_review()
    suite.children_windows['releases'].page.on_failure('STAAD is unavailable. Open the intended model and try again.')
    capture('error-state', host)
    window.close()
    app.processEvents()

# Contact sheets retain screenshots at their logical size for review.
for start in range(0, len(shots), 8):
    chunk = shots[start:start + 8]
    cell_w, cell_h = 520, 570
    sheet = QPixmap(cell_w * 4, cell_h * 2)
    sheet.fill(QColor('#E3EBF0'))
    painter = QPainter(sheet)
    painter.setFont(QFont('Poppins', 11))
    for index, (name, shot) in enumerate(chunk):
        x, y = (index % 4) * cell_w, (index // 4) * cell_h
        painter.setPen(QColor('#193E58'))
        painter.drawText(x + 12, y + 24, name)
        normalized = shot.scaled(min(cell_w - 24, round(shot.width() / shot.devicePixelRatio())), min(cell_h - 45, round(shot.height() / shot.devicePixelRatio())), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        normalized.setDevicePixelRatio(1)
        painter.drawPixmap(x + 12, y + 35, normalized)
    painter.end()
    sheet.save(str(output / ('contact-' + str(start // 8 + 1) + '.png')))
(output / 'metrics.json').write_text(json.dumps({'screenshots': len(shots), 'issues': issues}, indent=2))
print(str(output), 'screenshots:', len(shots), 'issues:', json.dumps(issues))

raise SystemExit(1 if issues else 0)
