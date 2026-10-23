import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CIVTOOLS_REDUCED_MOTION", "1")
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, QMimeData, QPoint, QPointF, QUrl, Qt
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
from civtools.qt_pages import parse_series
from civtools.jobs import scan_pdfs, render_pdf
from PySide6.QtGui import QImage, QDragEnterEvent, QDropEvent
import pymupdf


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config_patch = patch("civtools.qt_pages.config_root", return_value=Path(self.temp.name))
        self.config_patch.start()
        self.window = CivToolsApp()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.wait_for(lambda: self.window.pool.activeThreadCount() == 0 and self.window.cad_pool.activeThreadCount() == 0 and not any(getattr(p, "busy", False) for p in self.window.pages.values()))
        self.window.close()
        self.app.processEvents()
        self.config_patch.stop()
        self.temp.cleanup()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 20
        self.app.processEvents()
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(predicate(), "Background task did not finish")

    def suite_page(self, key):
        self.window.navigate("productivity")
        return self.window.pages["productivity"].open_feature("parameters" if key == "dj" else key)

    def suite_window(self, key):
        self.suite_page(key)
        return self.window.pages["productivity"].children_windows["parameters" if key == "dj" else key]

    def test_all_pages_construct_and_keep_state(self):
        for key in ("quantities", "mapper", "rack", "dj", "library", "productivity"):
            self.window.navigate(key)
            self.app.processEvents()
            utility = self.suite_window(key) if key in ('dj', 'rack') else self.window.utility_windows[key]
            page = self.suite_page(key) if key in ('dj', 'rack') else self.window.pages[key]
            self.assertIs(utility.page, page)
            self.assertTrue(utility.isVisible())
        self.assertIs(self.window.stack.currentWidget(), self.window.dashboard)
        rack = self.suite_page("rack")
        rack.trans.setText("0, 5, 10")
        self.window.navigate("home")
        self.window.navigate("rack")
        self.assertEqual(rack.configuration()["num_transverse_grids"], 3)
        if os.environ.get("CIVTOOLS_CAPTURE") == "1":
            self.wait_for(lambda: not any(getattr(p, "busy", False) for p in self.window.pages.values()))
            self.wait_for(lambda: not rack.preview_timer.isActive())
            output = Path(__file__).resolve().parents[1] / "artifacts"
            output.mkdir(exist_ok=True)
            self.window.navigate("home")
            self.app.processEvents()
            self.window.grab().save(str(output / "workspace.png"))
            self.window.navigate("rack")
            self.app.processEvents()
            self.suite_window("rack").grab().save(str(output / "modeler.png"))
            for key in ("quantities", "mapper", "dj", "library"):
                utility = self.suite_window(key) if key == 'dj' else self.window.utility_windows[key]
                utility.grab().save(str(output / f"{key}.png"))

    def test_staad_generator_parameters_preview_and_saved_settings(self):
        self.window.navigate("dj")
        page = self.suite_page("dj")
        model = page.models["concrete"]
        self.assertGreaterEqual(page.parameter_tables["concrete"].columnWidth(2), 120)
        fc = model.index(0, 2)
        self.assertEqual(model.data(fc), 30.0)
        self.assertTrue(model.setData(fc, "32.5", Qt.ItemDataRole.EditRole))
        self.assertEqual(page.concrete[0].value, 32.5)

        page.parameter_search.setText("compressive strength")
        self.app.processEvents()
        self.assertFalse(page.parameter_tables["concrete"].isRowHidden(0))
        self.assertTrue(page.parameter_tables["concrete"].isRowHidden(1))
        page.parameter_search.clear()

        page.output.setPlainText("FC 30000 MEMB 1 TO 5 to 6")
        self.app.processEvents()
        ranges = page.output.document().firstBlock().layout().formats()
        self.assertEqual(
            [(item.start, item.length) for item in ranges],
            [(0, 2), (9, 4)],
        )
        self.assertTrue(page.validate_preview(show_feedback=False))
        page.output.setPlainText("FC " + ("1" * 80))
        self.assertFalse(page.validate_preview(show_feedback=False))

        page.save_state()
        restored = type(page)(self.window)
        restored.restore_state("dj")
        self.assertEqual(restored.concrete[0].value, 32.5)

    def test_productivity_local_workflows_and_saved_inputs(self):
        from civtools.core.staad_productivity import ModelSnapshot
        self.window.navigate('productivity')
        palette = self.window.pages['productivity']
        self.assertEqual(len(palette.buttons), 10)
        for key in palette.buttons:
            self.assertTrue(palette.buttons[key].isEnabled())
            palette.open_feature(key)
        snapshot = ModelSnapshot('sample.std', 'Metric',
            {1: (0, 0, 0), 2: (0, 6, 0), 3: (10, 6, 0), 4: (10, 0, 0)},
            {1: (1, 2), 2: (2, 3), 3: (3, 4)}, [1, 4], [1, 2])
        selector = palette.children_windows['select'].page
        selector.set_snapshot(snapshot)
        self.assertIs(palette.shared_snapshot, snapshot)
        self.assertIs(palette.children_windows['groups'].page.snapshot, snapshot)
        self.assertIsNone(palette.children_windows['parameters'].page.snapshot)
        peb = palette.children_windows['pebA'].page
        peb.geometry_fields['width'].setValue(24)
        child = palette.children_windows['pebA']
        child.close()
        self.assertFalse(child.isVisible())
        self.assertIs(palette.open_feature('pebA'), peb)
        peb.save_state()
        palette.children_windows['renumber'].page.on_event('renumbered', True)
        self.assertIsNone(palette.shared_snapshot)
        self.assertTrue(all(child.page.snapshot is None for child in palette.children_windows.values()))
        palette.save_state()
        restored = type(palette)(self.window)
        restored.restore_state('productivity')
        self.assertEqual(restored.open_feature('pebA').geometry_fields['width'].value(), 24)
        restored.close_children()
        for child in restored.children_windows.values():
            child.deleteLater()

    def test_selection_buttons_directly_toggle_combined_staad_groups(self):
        from civtools.core.staad_productivity import ModelSnapshot, classify_members
        from civtools.core.results import OperationResult
        from PySide6.QtWidgets import QComboBox, QTableWidget, QToolButton
        self.window.navigate('productivity')
        page = self.window.pages['productivity'].open_feature('select')
        snapshot = ModelSnapshot('sample.std', 'Metric',
            {1: (0, 0, 0), 2: (0, 6, 0), 3: (10, 6, 0), 4: (10, 0, 0)},
            {1: (1, 2), 2: (2, 3), 3: (3, 4)}, [1, 4], [1])
        self.assertEqual(page.members.rowCount(), 0)
        self.assertIsNotNone(page.search)
        self.assertEqual(page.findChildren(QToolButton), [page.member_details_toggle])
        self.assertFalse(page.member_details_toggle.isChecked())
        self.assertNotEqual(page.process_members_button.objectName(), 'secondary')
        steps = [('Columns', [1, 3], []), ('Pri.Beams', [1, 2, 3], []),
                 ('Pri.X', [1, 2, 3], []), ('Pri.Beams', [1, 2, 3], []),
                 ('Columns', [2], []), ('Sup.Nodes', [2], [1, 4]),
                 ('Pri.X', [], [1, 4]), ('Sup.Nodes', [], [])]
        with patch('civtools.qt_productivity.live.scan', return_value=snapshot) as scan, patch(
                'civtools.qt_productivity.live.set_selection', return_value=OperationResult('Selected')) as apply, patch(
                'civtools.qt_productivity.classify_members', wraps=classify_members) as classify, patch.object(
                page.palette, 'share_snapshot', wraps=page.palette.share_snapshot) as publish:
            for index, (key, members, nodes) in enumerate(steps):
                page.category_buttons[key].click()
                self.wait_for(lambda: not page.busy)
                self.assertIs(apply.call_args.args[0], snapshot)
                self.assertEqual(sorted(apply.call_args.args[1]), members)
                self.assertEqual(sorted(apply.call_args.args[2]), nodes)
                self.assertEqual({k for k, b in page.category_buttons.items() if b.isChecked()}, page.selected_groups)
                if index == 0:
                    self.assertEqual(page.members.rowCount(), 3)
                    self.assertIn('2 members', page.scope_summary.text())
                    initial_classifications = classify.call_count
                else:
                    self.assertEqual(classify.call_count, initial_classifications)
                self.assertEqual(publish.call_count, 1)
                self.assertFalse(page.log.isVisible())
            scan.assert_called_once()
        self.assertEqual(page.selected_groups, set())
        with patch('civtools.qt_productivity.live.set_selection', side_effect=RuntimeError('STAAD rejected selection')):
            page.category_buttons['Columns'].click()
            self.wait_for(lambda: not page.busy)
        self.assertFalse(page.category_buttons['Columns'].isChecked())
        self.assertIn('STAAD rejected', page.feedback.text())
        self.assertFalse(page.log.isVisible())
        with patch('civtools.qt_productivity.live.set_selection', return_value=OperationResult('Selected')):
            page.category_buttons['Columns'].click()
            self.wait_for(lambda: not page.busy)
        with patch('civtools.qt_productivity.live.set_selection', side_effect=RuntimeError('STAAD rejected selection')):
            page.category_buttons['Pri.Beams'].click()
            self.wait_for(lambda: not page.busy)
        self.assertTrue(page.category_buttons['Columns'].isChecked())
        self.assertFalse(page.category_buttons['Pri.Beams'].isChecked())

    def test_productivity_apply_refreshes_preview_and_invalidates_shared_model(self):
        from civtools.core.staad_productivity import ModelSnapshot
        from civtools.core.results import OperationResult
        from civtools.core.productivity_model_tools import predefined_group_plan, group_plan_commands
        from civtools.qt_productivity_tools import PreparedAction
        self.window.navigate('productivity')
        palette = self.window.pages['productivity']
        model = ModelSnapshot('sample.std', 'Metric',
            {1: (0, 0, 0), 2: (0, 6, 0), 3: (10, 6, 0), 4: (10, 0, 0)},
            {1: (1, 2), 2: (2, 3), 3: (3, 4)}, [1, 4], [1])
        groups = palette.open_feature('groups')
        groups.set_snapshot(model)
        plan = predefined_group_plan(model)
        prepared = PreparedAction(model, 'groups', plan, group_plan_commands(plan), 'Create groups?')
        with patch.object(groups, 'confirm', return_value=True) as confirm, patch.object(groups, 'run') as schedule, patch(
                'civtools.core.productivity_model_tools.apply_predefined_groups', return_value=OperationResult('Applied')) as apply:
            groups.review_action(prepared)
            self.assertEqual(confirm.call_args.kwargs['target'], model.path)
            self.assertIn('_RB_PRI_BM', confirm.call_args.args[1])
            self.assertTrue(schedule.call_args.kwargs['cad'])
            events = []
            schedule.call_args.args[0](lambda *event: events.append(event))
        self.assertIs(apply.call_args.args[0], model)
        self.assertIn(('model_changed', True), events)
        groups.on_event('model_changed', True)
        self.assertIsNone(palette.shared_snapshot)
        self.assertIsNone(groups.snapshot)
        releases = palette.open_feature('releases')
        releases.set_snapshot(model)
        releases.mutating = True
        releases.on_failure('Simulated uncertain failure')
        self.assertIsNone(palette.shared_snapshot)
        self.assertFalse(releases.define_releases_button.isEnabled())
        self.assertFalse(releases.log.isVisible())

    def test_search_categories_and_empty_state(self):
        dashboard = self.window.dashboard
        self.assertFalse(dashboard.logo.pixmap().isNull())
        self.assertEqual(dashboard.logo.accessibleName(), "L&T Energy Hydrocarbon logo")
        self.assertGreaterEqual(dashboard.logo.pixmap().height(), 54)
        self.assertTrue(dashboard.category_buttons["All tools"].isChecked())
        self.assertEqual(len(dashboard.category_buttons), 5)
        dashboard.category_buttons["Modeling"].click()
        self.assertEqual(dashboard.category, "Modeling")
        self.assertEqual(sum(not c.isHidden() for c in dashboard.cards), 1)
        dashboard.search.setText("STAAD")
        self.assertEqual(sum(not c.isHidden() for c in dashboard.cards), 1)
        dashboard.set_category("Documents")
        self.assertFalse(dashboard.empty.isHidden())
        dashboard.search.clear()
        self.assertEqual(sum(not c.isHidden() for c in dashboard.cards), 1)
        self.assertTrue(dashboard.category_buttons["Documents"].isChecked())

    def test_open_buttons_launch_every_tool_and_resume_the_same_window(self):
        errors = []
        with patch("sys.excepthook", side_effect=lambda kind, value, tb: errors.append(str(value))):
            for card in self.window.dashboard.cards:
                key = card.tool[0]
                card.open_button.click()
                self.app.processEvents()
                self.assertIn(key, self.window.utility_windows)
                utility = self.window.utility_windows[key]
                self.assertTrue(utility.isVisible())
                utility.close()
                card.open_button.click()
                self.app.processEvents()
                self.assertIs(self.window.utility_windows[key], utility)
                self.assertTrue(utility.isVisible())
        self.assertEqual(errors, [])

    def test_card_grid_reflows_on_resize_and_filter(self):
        dashboard = self.window.dashboard
        self.assertEqual(dashboard.grid.getItemPosition(dashboard.grid.indexOf(dashboard.cards[2]))[:2], (0, 2))
        self.window.resize(540, 700)
        self.app.processEvents()
        self.assertEqual(dashboard.grid.getItemPosition(dashboard.grid.indexOf(dashboard.cards[2]))[:2], (1, 0))
        dashboard.search.setText("STAAD")
        self.app.processEvents()
        for index, card in enumerate(card for card in dashboard.cards if not card.isHidden()):
            self.assertEqual(dashboard.grid.getItemPosition(dashboard.grid.indexOf(card))[:2], (0, index))
        self.assertEqual(dashboard.surface.minimumSizeHint().width() <= dashboard.width(), True)

    def test_tool_windows_are_compact_independent_and_resume_inputs(self):
        self.assertLessEqual(self.window.width(), 800)
        self.assertLessEqual(self.window.height(), 720)
        self.window.navigate("mapper")
        self.window.navigate("rack")
        mapper_window = self.window.utility_windows["mapper"]
        rack_window = self.suite_window("rack")
        self.assertIsNone(mapper_window.parentWidget())
        self.assertTrue(mapper_window.isVisible())
        self.assertTrue(rack_window.isVisible())
        self.window.pages["mapper"].height.setValue(375)
        mapper_window.close()
        self.assertFalse(mapper_window.isVisible())
        self.window.navigate("mapper")
        self.assertIs(self.window.utility_windows["mapper"], mapper_window)
        self.assertEqual(mapper_window.page.height.value(), 375)
        self.assertFalse(rack_window.page.preview_panel.isVisible())
        rack_window.page.preview_toggle.setChecked(True)
        self.assertTrue(rack_window.page.preview_panel.isVisible())

    def test_quantity_actions_follow_input_readiness_and_remove_selection(self):
        self.window.navigate("quantities")
        page = self.window.pages["quantities"]
        self.assertFalse(page.extract_button.isEnabled())
        self.assertFalse(page.consolidate_button.isEnabled())
        path = Path(self.temp.name) / "mapping.xlsx"
        path.touch()
        page.workbook.edit.setText(str(path))
        self.assertTrue(page.consolidate_button.isEnabled())
        self.assertFalse(page.extract_button.isEnabled())
        page.add_files(["first.dxf", "second.dxf", "first.dxf"])
        self.assertTrue(page.extract_button.isEnabled())
        self.assertEqual(page.list.count(), 2)
        page.list.item(0).setSelected(True)
        page.remove_selected()
        self.assertEqual(page.files, ["second.dxf"])
        page.clear()
        self.assertFalse(page.extract_button.isEnabled())

    def test_dropping_a_workbook_sets_a_local_path(self):
        self.window.navigate("mapper")
        field = self.window.pages["mapper"].workbook
        path = Path(self.temp.name) / "drawing data.xlsx"
        path.touch()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(field, enter)
        self.assertTrue(enter.isAccepted())
        drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(field, drop)
        self.assertEqual(Path(field.edit.text()), path)

    def test_worker_reports_on_ui_thread_and_recovers_after_failure(self):
        self.window.navigate("quantities")
        page = self.window.pages["quantities"]
        threads = []
        original = page.on_event
        def on_event(kind, value):
            threads.append(QThread.currentThread())
            original(kind, value)
        page.on_event = on_event
        def operation(report):
            report("log", "Running on worker")
            raise RuntimeError("Expected failure")
        page.run(operation)
        self.assertFalse(page.form.isEnabled())
        self.window.navigate("rack")
        self.wait_for(lambda: not page.busy)
        self.assertTrue(page.form.isEnabled())
        self.assertIn("Expected failure", page.feedback.text())
        self.assertEqual(threads, [self.app.thread()])

    def test_grid_validation_rejects_duplicate_nonfinite_and_low_tiers(self):
        for text in ("0, 0", "0, nan", "0, inf", "two, 4"):
            with self.assertRaises(ValueError):
                parse_series(text, "Grids", 2)
        self.window.navigate("rack")
        rack = self.suite_page("rack")
        rack.trans_levels.setText("-1, 2")
        with self.assertRaises(ValueError):
            rack.configuration()

    def test_latest_document_selection_wins_during_slow_preview(self):
        root = Path(self.temp.name)
        for name, text in (("a.pdf", "Document A"), ("b.pdf", "Document B")):
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                page.insert_text((30, 30), text)
                pdf.save(root / name)
        self.window.navigate("library")
        library = self.window.pages["library"]
        self.wait_for(lambda: not library.busy)
        library.model.set_documents(scan_pdfs(root, lambda *args: None))
        library.preview_toggle.setChecked(True)
        original = self.window.pdf.call
        def slow_render(operation, report, *args):
            time.sleep(.04)
            return original(operation, report, *args)
        with patch.object(self.window.pdf, "call", side_effect=slow_render):
            row_a = library.proxy.mapFromSource(library.model.index(0, 0)).row()
            row_b = library.proxy.mapFromSource(library.model.index(1, 0)).row()
            library.table.selectRow(row_a)
            self.app.processEvents()
            library.table.selectRow(row_b)
            self.wait_for(lambda: library.preview_job is None and library.pending_preview is None)
        self.assertEqual(library.selected[0], "b.pdf")
        self.assertIsNotNone(library.rendered_pixmap, library.preview_label.text())
        image = QImage.fromData(render_pdf(str(root / "b.pdf"), lambda *args: None))
        self.assertEqual(library.rendered_pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888),
                         image.convertToFormat(QImage.Format.Format_RGBA8888))
        self.assertEqual(len(library.cache), 2)

    def test_hidden_pdf_preview_does_not_render(self):
        self.window.navigate("library")
        page = self.window.pages["library"]
        self.wait_for(lambda: not page.busy)
        page.model.set_documents([("a.pdf", str(Path(self.temp.name) / "a.pdf"), 1, 1, 1)])
        with patch.object(self.window.pdf, "call", side_effect=AssertionError("Hidden preview must not render")):
            page.table.selectRow(0)
            self.app.processEvents()
            self.assertIsNone(page.preview_job)
            self.assertIsNone(page.pending_preview)

    def test_invalid_rack_inputs_are_visible_without_preview(self):
        self.window.navigate("rack")
        page = self.suite_page("rack")
        page.trans_levels.setText("-1, 6")
        self.wait_for(lambda: not page.preview_timer.isActive())
        self.assertFalse(page.preview_toggle.isChecked())
        self.assertTrue(page.geometry_status.isVisible())
        self.assertIn("above the base", page.geometry_status.text())
        self.assertFalse(page.generate_button.isEnabled())
        self.assertIsNone(page.preview.plan)
        page.trans_levels.setText("3, 6")
        self.wait_for(lambda: not page.preview_timer.isActive())
        self.assertTrue(page.generate_button.isEnabled())

    def test_preferences_restore_on_a_new_workspace(self):
        self.window.navigate("mapper")
        page = self.window.pages["mapper"]
        page.height.setValue(425)
        self.window.utility_windows["mapper"].resize(640, 680)
        self.window.utility_windows["mapper"].close()
        self.window.close()
        self.window = CivToolsApp()
        self.window.show()
        self.window.navigate("mapper")
        self.assertEqual(self.window.pages["mapper"].height.value(), 425)
        self.assertEqual(self.window.utility_windows["mapper"].width(), 640)

    def test_mapper_worksheet_selection_matches_validated_sample(self):
        import openpyxl
        path = Path(self.temp.name) / "coordinates.xlsx"
        workbook = openpyxl.Workbook()
        workbook.active.title = "First"
        workbook.active.append(["X", "Y", "Width", "Height", "Label"])
        workbook.active.append([1, 2, 3, 4, "First box"])
        second = workbook.create_sheet("Second")
        second.append(["X", "Y", "Width", "Height", "Label"])
        second.append([2, 4, -1, 6, "Bad box"])
        workbook.active = 1
        workbook.save(path)
        workbook.close()
        self.window.navigate("mapper")
        page = self.window.pages["mapper"]
        page.workbook.edit.setText(str(path))
        self.wait_for(lambda: page.mapping is not None)
        self.assertEqual(page.sheet.currentText(), "First")
        self.assertTrue(page.plot_button.isEnabled())
        self.assertEqual(page.sample.item(0, 5).text(), "First box")
        page.sheet.setCurrentText("Second")
        self.wait_for(lambda: page.mapping is not None)
        self.assertFalse(page.plot_button.isEnabled())
        self.assertIn("1 invalid", page.validation.text())

    def test_cad_queue_does_not_block_general_jobs(self):
        import threading
        from civtools.jobs import Job
        gate = threading.Event()
        blockers = [Job(lambda report: gate.wait(5)) for _ in range(3)]
        general_done = []
        job = Job(lambda report: "available")
        job.signals.succeeded.connect(general_done.append)
        try:
            for blocker in blockers:
                self.window.cad_pool.start(blocker)
            self.window.pool.start(job)
            self.wait_for(lambda: bool(general_done))
            self.assertEqual(general_done, ["available"])
        finally:
            gate.set()
            self.wait_for(lambda: self.window.cad_pool.activeThreadCount() == 0)

    def test_large_text_cards_fit_wrapped_content(self):
        self.window.set_text_size("130%")
        for _ in range(4):
            self.app.processEvents()
        dashboard = self.window.dashboard
        self.assertEqual(dashboard.text_size.currentText(), "130%")
        self.assertEqual(dashboard.grid.getItemPosition(dashboard.grid.indexOf(dashboard.cards[2]))[:2], (1, 0))
        for card in dashboard.cards:
            self.assertGreaterEqual(card.height(), card.layout().totalHeightForWidth(card.width()))


if __name__ == "__main__":
    unittest.main()
