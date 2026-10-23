import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('CIVTOOLS_REDUCED_MOTION', '1')

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QPushButton
from civtools.qt_pages import DJPage, RackPage
from civtools.qt_productivity_migrated import ProductivityParametersPage, ProductivityRackPage
from civtools.core.staad_productivity import ModelSnapshot
from civtools.core.geometry import build_rack_plan
from civtools.core.peb import geometry_commands


class ProductivityMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.settings = QSettings(str(self.directory / 'settings.ini'), QSettings.Format.IniFormat)
        self.window = SimpleNamespace(settings=self.settings, update_status=Mock())
        self.root_patch = patch('civtools.qt_pages.config_root', return_value=self.directory)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.pages = []

    def tearDown(self):
        for page in self.pages:
            if hasattr(page, 'save_timer'):
                page.save_timer.stop()
            if hasattr(page, 'preview_timer'):
                page.preview_timer.stop()
            page.close()
            page.deleteLater()
        self.app.processEvents()

    def page(self, kind):
        page = kind(self.window)
        self.pages.append(page)
        return page

    def test_parameter_page_keeps_complete_manual_generator_without_automatic_tab(self):
        page = self.page(ProductivityParametersPage)
        self.assertIsInstance(page, DJPage)
        self.assertEqual([page.tabs.tabText(i) for i in range(page.tabs.count())],
                         ['Concrete parameters', 'Steel parameters', 'Command preview'])
        for kind in ('concrete', 'steel'):
            self.assertGreater(page.models[kind].rowCount(), 5)
            self.assertIs(page.parameter_tables[kind].model(), page.models[kind])
        titles = {button.text() for button in page.findChildren(QPushButton)}
        self.assertTrue({'Enable all', 'Disable all', 'Save preset', 'Load preset', 'Validate', 'Copy', 'Export'} <= titles)
        self.assertFalse(hasattr(page, 'automatic'))
        self.assertFalse(hasattr(page, 'design_actions'))

    def test_parameter_settings_preserve_existing_namespace(self):
        self.settings.setValue('forms/dj_parameters', json.dumps({'concrete': {'FC': {'enabled': True, 'value': 41.25}}}))
        page = self.page(ProductivityParametersPage)
        fc = next(item for item in page.concrete if item.name == 'FC')
        self.assertEqual(fc.value, 41.25)
        fc.value = 38.5
        timer = page.save_timer
        page.restore_state('dj')
        self.assertIs(page.save_timer, timer)
        self.assertEqual(fc.value, 38.5)
        page.save_state()
        page.save_state()
        restored = self.page(ProductivityParametersPage)
        self.assertEqual(next(item.value for item in restored.concrete if item.name == 'FC'), 38.5)

    def test_parameter_presets_and_command_preview_remain_available(self):
        page = self.page(ProductivityParametersPage)
        destination = self.directory / 'concrete.json'
        page.models['concrete'].setData(page.models['concrete'].index(0, 2), '42.5', Qt.ItemDataRole.EditRole)
        with patch('civtools.qt_pages.QFileDialog.getSaveFileName', return_value=(str(destination), '')):
            page.save_preset('concrete')
        self.assertTrue(destination.is_file())
        page.models['concrete'].setData(page.models['concrete'].index(0, 2), '30', Qt.ItemDataRole.EditRole)
        with patch('civtools.qt_pages.QFileDialog.getOpenFileName', return_value=(str(destination), '')):
            page.load_preset('concrete')
        self.assertEqual(page.concrete[0].value, 42.5)
        page.output.setPlainText('FC 42500 MEMB 1 TO 5')
        self.assertTrue(page.validate_preview(show_feedback=False))
        page.copy_preview()
        self.assertEqual(self.app.clipboard().text(), 'FC 42500 MEMB 1 TO 5')

    def test_parameter_live_generation_uses_original_runner(self):
        page = self.page(ProductivityParametersPage)
        page.tabs.setCurrentIndex(1)
        with patch.object(page, 'run') as run, patch('civtools.qt_pages.run_staad_parameter_generation') as operation:
            page.start()
            self.assertTrue(run.call_args.kwargs['cad'])
            run.call_args.args[0](Mock())
            self.assertEqual(operation.call_args.args[0], 'steel')
            self.assertEqual(len(operation.call_args.args[1]), len(page.steel))

    def test_parameter_busy_and_manual_error_activity(self):
        page = self.page(ProductivityParametersPage)
        self.assertFalse(page.busy)
        page.busy = True
        self.assertTrue(page.busy)
        page.busy = False
        page.on_failure('Example runner failure')
        self.assertFalse(page.log.isHidden())
        self.assertIn('Example runner failure', page.log.toPlainText())

    def test_parameter_snapshot_sharing_and_invalidation_delegate(self):
        page = self.page(ProductivityParametersPage)
        model = ModelSnapshot('sample.std', 'Metric',
                              {1: (0, 0, 0), 2: (0, 3, 0), 3: (5, 3, 0), 4: (5, 0, 0)},
                              {1: (1, 2), 2: (2, 3), 3: (3, 4)}, [1, 4], [])
        page.set_snapshot(model, publish=False)
        self.assertIs(page.snapshot, model)
        page.snapshot, page.categories = None, {}
        page.invalidate_mapping()
        self.assertIsNone(page.snapshot)

    def test_rack_preserves_saved_form_full_config_and_preview(self):
        state = {'trans': '0, 4, 9', 'long': '0, 5, 10', 'trans_levels': '4, 7',
                 'long_levels': '3, 6', 'base': 1, 'depth': 2,
                 'support': 'Pinned', 'bracing': False, 'preview_toggle': True, 'saved_toggle': True}
        self.settings.setValue('forms/rack', json.dumps(state))
        page = self.page(ProductivityRackPage)
        self.assertIsInstance(page, RackPage)
        config = page.configuration()
        self.assertEqual(config['transverse_spacing'], [0, 4, 9])
        self.assertEqual(config['trans_beam_elevations'], [4, 7])
        self.assertEqual(config['long_beam_elevations'], [3, 6])
        self.assertEqual(config['foundation_depth'], 2)
        self.assertEqual(config['support_type'], 'Pinned')
        self.assertFalse(config['bracing_enabled'])
        self.assertFalse(page.preview_panel.isHidden())
        self.assertIn('nodes', page.geometry_status.text())
        timer = page.save_timer
        page.trans.setText('0, 6, 12')
        page.restore_state('rack')
        self.assertIs(page.save_timer, timer)
        self.assertEqual(page.trans.text(), '0, 6, 12')
        page.save_state()
        restored = self.page(ProductivityRackPage)
        self.assertEqual(restored.trans.text(), '0, 6, 12')

    def test_rack_saved_configuration_actions_remain_usable(self):
        page = self.page(ProductivityRackPage)
        page.trans.setText('0, 3, 6')
        with patch('civtools.qt_pages.QInputDialog.getText', return_value=('Three lines', True)):
            page.save_config()
        self.assertTrue((self.directory / 'pipe_rack_configs.json').is_file())
        page.trans.setText('0, 8')
        page.saved.setCurrentIndex(1)
        page.load_config()
        self.assertEqual(page.configuration()['transverse_spacing'], [0, 3, 6])

    def test_rack_export_uses_every_current_geometry_input_without_com(self):
        page = self.page(ProductivityRackPage)
        destination = self.directory / 'rack.std'
        expected = geometry_commands(build_rack_plan(page.configuration()), 'METER')
        with patch('civtools.qt_productivity_migrated.QFileDialog.getSaveFileName', return_value=(str(destination), '')):
            page.export_staad()
        self.assertEqual(destination.read_text(encoding='utf-8'), expected)
        self.assertIn('UNIT METER KN', expected)
        self.assertIn('_CIV_BRACE', expected)
        self.assertIn('SUPPORTS', expected)
        self.assertFalse(page.busy)

    def test_rack_live_generate_uses_original_runner_and_invalid_export_is_disabled(self):
        page = self.page(ProductivityRackPage)
        with patch.object(page, 'run') as run, patch('civtools.qt_pages.run_piperack') as operation:
            page.start()
            self.assertTrue(run.call_args.kwargs['cad'])
            run.call_args.args[0](Mock())
            self.assertEqual(operation.call_args.args[0], page.configuration())
        page.trans.setText('invalid')
        page.update_preview()
        self.assertFalse(page.export_button.isEnabled())
        with patch('civtools.qt_productivity_migrated.QFileDialog.getSaveFileName') as choose:
            page.export_staad()
            choose.assert_not_called()


if __name__ == '__main__':
    unittest.main()
