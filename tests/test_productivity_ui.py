"""Integration checks for the documented productivity dialogs (COM mocked)."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('CIVTOOLS_REDUCED_MOTION', '1')
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from civtools.qt_app import CivToolsApp, TOOLS
from civtools.qt_pages import DJPage, RackPage
from civtools.qt_style import STYLE
from civtools.core.staad_productivity import ModelSnapshot
from civtools.core.results import OperationResult


def sample():
    return ModelSnapshot('example.std', 'Metric',
        {1: (0, 0, 0), 2: (0, 6, 0), 3: (10, 6, 0), 4: (10, 0, 0)},
        {1: (1, 2), 2: (2, 3), 3: (3, 4)}, [1, 4], [1, 2], primary_cases=[1])


class ProductivityUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = patch('civtools.qt_pages.config_root', return_value=Path(self.temp.name))
        self.config.start()
        self.window = CivToolsApp()
        self.window.navigate('productivity')
        self.palette = self.window.pages['productivity']

    def wait(self):
        deadline = time.monotonic() + 10
        self.app.processEvents()
        while (self.palette.busy or self.window.pool.activeThreadCount() or self.window.cad_pool.activeThreadCount()) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertFalse(self.palette.busy)

    def tearDown(self):
        self.wait()
        self.window.close()
        self.app.processEvents()
        self.config.stop()
        self.temp.cleanup()

    def page(self, key):
        return self.palette.open_feature(key)

    def test_all_tools_enabled_and_existing_tools_owned_only_by_suite(self):
        self.assertNotIn('dj', [tool[0] for tool in TOOLS])
        self.assertNotIn('rack', [tool[0] for tool in TOOLS])
        self.assertEqual(len(self.palette.buttons), 10)
        for key, action in self.palette.buttons.items():
            self.assertTrue(action.isEnabled(), key)
            self.assertIsNotNone(self.page(key))
        self.window.navigate('dj')
        self.assertIsInstance(self.palette.children_windows['parameters'].page, DJPage)
        self.window.navigate('rack')
        self.assertIsInstance(self.palette.children_windows['rack'].page, RackPage)
        self.assertNotIn('dj', self.window.pages)
        self.assertNotIn('rack', self.window.utility_windows)

    def test_all_peb_variants_generate_complete_staad_files(self):
        for variant in 'ABCD':
            page = self.page('peb' + variant)
            path = Path(self.temp.name) / f'peb-{variant}.std'
            with patch('civtools.qt_productivity_tools.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                page.generate_structure()
            text = path.read_text()
            self.assertIn('STAAD SPACE', text)
            self.assertIn('MEMBER INCIDENCES', text)
            self.assertIn('SUPPORTS', text)
            self.assertTrue(text.rstrip().endswith('FINISH'))

    def test_peb_family_has_one_entry_and_keeps_each_variants_inputs(self):
        picker = self.palette.tool_picker
        self.assertEqual([picker.itemText(index) for index in range(picker.count())
                          if picker.itemText(index).startswith('PEB')], ['PEB frames'])
        self.palette.pick_tool(picker.findText('PEB frames'))
        self.app.processEvents()
        self.assertTrue(self.palette.peb_family.isVisible())
        for variant, width in (('A', 24), ('B', 28), ('C', 32), ('D', 36)):
            self.palette.peb_variant_buttons[variant].click()
            self.assertEqual(self.palette.active_feature, 'peb' + variant)
            self.assertEqual(picker.currentText(), 'PEB frames')
            self.assertTrue(self.palette.peb_variant_buttons[variant].isChecked())
            self.palette.children_windows['peb' + variant].page.geometry_fields['width'].setValue(width)
        self.page('groups')
        self.assertTrue(self.palette.peb_family.isHidden())
        self.palette.pick_tool(picker.findText('PEB frames'))
        self.assertEqual(self.palette.active_feature, 'pebD')
        for variant, width in (('A', 24), ('B', 28), ('C', 32), ('D', 36)):
            self.palette.peb_variant_buttons[variant].click()
            self.assertEqual(self.palette.children_windows['peb' + variant].page.geometry_fields['width'].value(), width)

    def test_peb_favourite_and_restart_restore_last_variant(self):
        self.page('pebC')
        self.palette.toggle_favourite()
        self.page('groups')
        self.palette.buttons['pebA'].click()
        self.assertEqual(self.palette.active_feature, 'pebC')
        self.window.settings.sync()
        reopened = CivToolsApp()
        try:
            reopened.navigate('productivity')
            suite = reopened.pages['productivity']
            suite.pick_tool(suite.tool_picker.findText('PEB frames'))
            self.assertEqual(suite.active_feature, 'pebC')
            self.assertTrue(suite.peb_variant_buttons['C'].isChecked())
        finally:
            reopened.close()

    def test_workbench_search_detach_and_dock_preserve_tool_inputs(self):
        page = self.page('pebC')
        page.geometry_fields['width'].setValue(28)
        self.assertEqual(self.palette.peb_variant.currentText(), 'PEB C')
        child = self.palette.children_windows['pebC']
        self.assertIs(self.palette.tool_stack.currentWidget(), child)
        self.palette.detach_active()
        self.assertTrue(child.isWindow())
        self.assertIs(self.palette.tool_stack.currentWidget(), self.palette.detached_hint)
        self.palette.dock_active()
        self.assertFalse(child.isWindow())
        self.assertIs(child.page, page)
        self.assertEqual(page.geometry_fields['width'].value(), 28)
        self.palette.tool_search.setText('release')
        self.palette.open_search_result()
        self.assertEqual(self.palette.active_feature, 'releases')
        self.palette.tool_search.setText('no such tool')
        self.assertFalse(self.palette.no_tools.isHidden())
        self.palette.tool_search.clear()
        self.palette.show_compact()
        self.assertTrue(self.palette.compact_window.isVisible())
        self.palette.close_children()
        self.assertFalse(self.palette.compact_window.isVisible())

    def test_release_setting_change_invalidates_review(self):
        from civtools.core.productivity_model_tools import selected_release_plan, release_plan_commands
        from civtools.qt_productivity_tools import PreparedAction
        page = self.page('releases')
        model = sample()
        page.set_snapshot(model)
        plan = selected_release_plan(model, [1, 2], 'BOTH', ('MZ',))
        prepared = PreparedAction(model, 'releases', {'plan': plan, 'end': 'BOTH', 'dofs': ('MZ',)},
                                  release_plan_commands(plan), plan.summary)
        page.on_success(prepared)
        self.assertTrue(page.apply_release_button.isEnabled())
        self.assertEqual(page.release_table.rowCount(), 2)
        page.release_dofs['MY'].click()
        self.assertIsNone(page.prepared_release)
        self.assertFalse(page.apply_release_button.isEnabled())
        self.assertEqual(page.release_table.rowCount(), 0)

    def test_floating_panel_switch_fold_and_expand_keep_inputs(self):
        host = self.window.utility_windows['productivity']
        self.app.processEvents()
        self.assertEqual((host.width(), host.height()), (420, 480))
        page = self.page('pebC')
        page.geometry_fields['width'].setValue(28)
        self.palette.tool_picker.setEditText('release')
        self.palette.tool_picker.lineEdit().returnPressed.emit()
        self.assertEqual(self.palette.active_feature, 'releases')
        self.assertFalse(self.palette.children_windows['releases'].isWindow())
        self.palette.toggle_collapsed()
        self.app.processEvents()
        self.assertTrue(self.palette.task_area.isHidden())
        self.assertLess(host.height(), 100)
        self.palette.toggle_collapsed()
        self.palette.toggle_expanded()
        self.app.processEvents()
        self.assertGreaterEqual(host.width(), 900)
        self.palette.show_compact()
        self.app.processEvents()
        self.assertEqual(host.width(), 420)
        self.assertEqual(self.page('pebC').geometry_fields['width'].value(), 28)

    def test_compact_release_controls_and_review_stay_reachable(self):
        page = self.page('releases')
        self.app.processEvents()
        self.assertTrue(page.release_table.isHidden() or not page.release_table.isVisible())
        self.assertFalse(page.apply_release_button.isEnabled())
        self.assertFalse(page.define_releases_button.isEnabled())
        for action in (page.define_releases_button, page.apply_release_button):
            self.assertTrue(page.rect().contains(action.mapTo(page, action.rect().bottomRight())))

    def test_parameter_table_fills_editor_at_normal_and_small_window_sizes(self):
        page = self.page('parameters')
        page.tabs.setCurrentIndex(1)
        utility = self.window.utility_windows['productivity']
        table = page.parameter_tables['steel']
        for width, height in ((1140, 760), (920, 640)):
            utility.resize(width, height)
            self.app.processEvents()
            self.assertTrue(page.heading_title.isHidden())
            self.assertTrue(page.header_art.isHidden())
            self.assertGreater(table.viewport().height(), utility.height() * .55)
            self.assertGreaterEqual(table.viewport().height() // table.rowHeight(0), 8)  # Long scopes/descriptions wrap.
            self.assertLess(table.mapTo(utility, table.rect().topLeft()).y(), utility.height() * .25)
            self.assertTrue(page.generate_button.isVisible())
        self.palette.detach_active()
        self.app.processEvents()
        self.assertFalse(page.heading_title.isHidden())
        self.palette.dock_active()
        self.assertTrue(page.heading_title.isHidden())

    def test_combination_template_and_word_report_end_to_end(self):
        page = self.page('combinations')
        source = Path(self.temp.name) / 'matrix.xlsx'
        destination = source.with_suffix('.docx')
        with patch('civtools.qt_productivity_tools.QFileDialog.getSaveFileName', return_value=(str(source), '')):
            page.save_template()
        page.combination_file.setText(str(source))
        with patch('civtools.qt_productivity_tools.QFileDialog.getSaveFileName', return_value=(str(destination), '')):
            page.generate_combinations()
            self.wait()
        with ZipFile(destination) as document:
            xml = document.read('word/document.xml').decode()
            self.assertIn('LOAD COMB', xml)
            self.assertIn('LOAD', xml)
            self.assertIn('<w:tbl>', xml)

    def test_catalogue_exports_saved_custom_section(self):
        page = self.page('girders')
        custom = {'name': 'MY_SECTION', 'depth_mm': 700, 'flange_width_mm': 300,
                  'flange_thickness_mm': 25, 'web_thickness_mm': 16}
        page.custom_sections.setText(json.dumps([custom]))
        page.save_state()
        path = Path(self.temp.name) / 'girders.txt'
        with patch('civtools.qt_productivity_tools.QFileDialog.getSaveFileName', return_value=(str(path), '')):
            page.generate_girders()
        self.assertIn('MY_SECTION', path.read_text())
        self.assertIn('WIDE FLANGE', path.read_text())

    def test_groups_prepare_confirm_apply_and_invalidate_cache(self):
        page = self.page('groups')
        model = sample()
        with patch('civtools.qt_productivity_tools.live.scan', return_value=model), patch.object(
                page, 'confirm', return_value=True) as confirm, patch(
                'civtools.core.productivity_model_tools.apply_predefined_groups', return_value=OperationResult('Created')) as apply:
            page.prepare_groups()
            self.wait()
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.kwargs['target'], model.path)
        self.assertIn('_RB_PRI_BM', confirm.call_args.args[1])
        self.assertIs(apply.call_args.args[0], model)
        self.assertIsNone(self.palette.shared_snapshot)
        self.assertFalse(page.log.isVisible())

    def test_renumber_declining_confirmation_never_changes_model(self):
        page = self.page('renumber')
        with patch('civtools.qt_productivity_tools.live.scan', return_value=sample()), patch.object(
                page, 'confirm', return_value=False), patch('civtools.qt_productivity_tools.live.apply_renumber') as apply:
            page.prepare_renumber()
            self.wait()
        apply.assert_not_called()
        self.assertIn('1001', page.output.toPlainText())

    def test_releases_use_current_staad_selection_and_exact_reviewed_plan(self):
        page = self.page('releases')
        model = sample()
        page.set_snapshot(model)
        with patch('civtools.qt_productivity_tools.live.connect', return_value=MagicMock()), patch(
                'civtools.qt_productivity_tools.live.require_snapshot', return_value=model), patch(
                'civtools.qt_productivity_tools.live._selected_ids', return_value={2}), patch.object(
                page, 'confirm', return_value=True), patch(
                'civtools.core.productivity_model_tools.apply_selected_releases', return_value=OperationResult('Applied')) as apply:
            page.prepare_releases('BOTH', ('MY', 'MZ'))
            self.wait()
            apply.assert_not_called()
            self.assertEqual(page.release_table.rowCount(), 1)
            self.assertTrue(page.apply_release_button.isEnabled())
            page.apply_release_button.click()
            self.wait()
        self.assertEqual(apply.call_args.kwargs['plan'].selected, (2,))
        self.assertEqual(apply.call_args.kwargs['dofs'], ('MY', 'MZ'))
        self.assertTrue(apply.call_args.kwargs['proceed_skipped'])
        self.assertFalse(page.define_releases_button.isEnabled())

    def test_tables_select_load_cases_and_export_only_chosen_cases(self):
        page = self.page('tables')
        model = sample()
        with patch('civtools.qt_productivity_tools.live.scan', return_value=model), patch(
                'civtools.core.productivity_design_results.load_case_inventory', return_value=[(1, 'Primary', 'DL'), (2, 'Combination', 'ULS')]):
            page.load_cases()
            self.wait()
        self.assertEqual(page.available_cases.count(), 2)
        page.available_cases.item(1).setSelected(True)
        page.move_cases(page.available_cases, page.selected_cases)
        self.assertEqual(page.selected_cases.item(0).data(Qt.ItemDataRole.UserRole), 2)
        path = Path(self.temp.name) / 'reactions.xlsx'
        with patch('civtools.qt_productivity_tools.QFileDialog.getSaveFileName', return_value=(str(path), '')), patch(
                'civtools.core.productivity_design_results.export_results', return_value=OperationResult('Exported')) as export:
            page.export_table('Reactions')
            self.wait()
        self.assertEqual(export.call_args.args[1:4], ('Reactions', [1, 4], [2]))

    def test_parameter_generator_omits_automatic_lengths_and_joints_section(self):
        page = self.page('parameters')
        self.app.processEvents()
        self.assertEqual([page.tabs.tabText(index) for index in range(page.tabs.count())],
                         ['Concrete', 'Steel', 'Preview'])
        self.assertFalse(hasattr(page, 'automatic'))
        self.assertFalse(hasattr(page, 'design_code'))

    def test_compact_parameter_editor_fits_text_without_horizontal_scrolling(self):
        page = self.page('parameters')
        host = self.window.utility_windows['productivity']
        for width in (360, 420):
            host.resize(width, 480)
            page.tabs.setCurrentIndex(1)
            self.app.processEvents()
            table = page.parameter_tables['steel']
            self.assertTrue(table.isColumnHidden(3))
            self.assertTrue(table.isColumnHidden(4))
            self.assertEqual(table.horizontalScrollBar().maximum(), 0)
            self.assertGreaterEqual(table.rowHeight(0), table.fontMetrics().height() + 6)
            self.assertGreater(table.columnWidth(1), 140)
            for index in range(page.tabs.count()):
                tab = page.tabs.tabBar()
                self.assertGreater(tab.tabRect(index).width(), tab.fontMetrics().horizontalAdvance(tab.tabText(index)))
            table.selectRow(0)
            self.app.processEvents()
            self.assertIn(page.steel[0].scope, page.parameter_context.text())

    def test_native_dark_palette_does_not_leak_into_parameter_form(self):
        from PySide6.QtGui import QPalette, QColor
        original = self.app.palette()
        dark = QPalette(original)
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            dark.setColor(role, QColor('#202020'))
        try:
            self.app.setPalette(dark)
            page = self.page('parameters')
            self.app.processEvents()
            self.assertEqual(page.form.palette().color(QPalette.ColorRole.Window).name(), '#f5f8fa')
            self.assertEqual(page.form.grab().toImage().pixelColor(0, 0).name(), '#f5f8fa')
            self.assertEqual(page.parameter_tables['concrete'].palette().color(QPalette.ColorRole.Base).name(), '#ffffff')
        finally:
            self.app.setPalette(original)

    def test_parameter_editor_preserves_small_values(self):
        from PySide6.QtWidgets import QStyleOptionViewItem
        page = self.page('parameters')
        table = page.parameter_tables['concrete']
        row = next(index for index, parameter in enumerate(page.concrete) if parameter.value == .002)
        index = page.models['concrete'].index(row, 2)
        delegate = table.itemDelegateForColumn(2)
        editor = delegate.createEditor(table, QStyleOptionViewItem(), index)
        delegate.setEditorData(editor, index)
        self.assertEqual(editor.text(), '0.002')
        delegate.setModelData(editor, page.models['concrete'], index)
        self.assertEqual(page.concrete[row].value, .002)
        editor.deleteLater()

    def test_rack_numeric_editors_display_their_values(self):
        from PySide6.QtWidgets import QLineEdit
        page = self.page('rack')
        self.app.processEvents()
        for field in (page.base, page.depth):
            editor = field.findChild(QLineEdit)
            self.assertTrue(editor.isVisible())
            self.assertGreater(editor.width(), editor.fontMetrics().horizontalAdvance(editor.text()))

    def test_compact_member_table_headers_fit_their_columns(self):
        for key in ('select', 'releases'):
            page = self.page(key)
            toggle = page.member_details_toggle if key == 'select' else page.release_details_toggle
            toggle.setChecked(True)
            self.app.processEvents()
            table = page.members if key == 'select' else page.release_table
            header = table.horizontalHeader()
            for column in range(table.columnCount()):
                if table.isColumnHidden(column):
                    continue
                title = table.horizontalHeaderItem(column).text()
                self.assertGreaterEqual(header.sectionSize(column), header.fontMetrics().horizontalAdvance(title) + 12)

    def test_release_dialog_remains_readable_with_native_dark_palette(self):
        from PySide6.QtGui import QPalette, QColor
        from PySide6.QtWidgets import QDialog, QCheckBox, QPushButton
        page = self.page('releases')
        page.set_snapshot(sample())
        original = self.app.palette()
        dark = QPalette(original)
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            dark.setColor(role, QColor('#202020'))
        self.app.setPalette(dark)
        def inspect(dialog):
            dialog.show()
            dialog.ensurePolished()
            self.app.processEvents()
            self.assertEqual(dialog.palette().color(QPalette.ColorRole.Window).name(), '#f5f8fa')
            for field in dialog.findChildren(QCheckBox):
                self.assertEqual(field.palette().color(QPalette.ColorRole.WindowText).name(), '#233b4a')
            for action in dialog.findChildren(QPushButton):
                self.assertEqual(action.palette().color(QPalette.ColorRole.ButtonText).name(), '#ffffff')
            dialog.close()
            return QDialog.DialogCode.Rejected
        try:
            with patch('civtools.qt_productivity_tools.QDialog.exec', new=inspect):
                page.release_dialog()
        finally:
            self.app.setPalette(original)


if __name__ == '__main__':
    unittest.main()
