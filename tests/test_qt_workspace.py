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

    def test_all_pages_construct_and_keep_state(self):
        for key in ("quantities", "mapper", "rack", "dj", "library"):
            self.window.navigate(key)
            self.app.processEvents()
            self.assertIs(self.window.utility_windows[key].page, self.window.pages[key])
            self.assertTrue(self.window.utility_windows[key].isVisible())
        self.assertIs(self.window.stack.currentWidget(), self.window.dashboard)
        rack = self.window.pages["rack"]
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
            self.window.utility_windows["rack"].grab().save(str(output / "modeler.png"))
            for key in ("quantities", "mapper", "dj", "library"):
                self.window.utility_windows[key].grab().save(str(output / f"{key}.png"))

    def test_search_categories_and_empty_state(self):
        dashboard = self.window.dashboard
        dashboard.search.setText("STAAD")
        self.assertEqual(sum(not c.isHidden() for c in dashboard.cards), 2)
        dashboard.set_category("Documents")
        self.assertFalse(dashboard.empty.isHidden())
        dashboard.search.clear()
        self.assertEqual(sum(not c.isHidden() for c in dashboard.cards), 1)

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
        for index, card in enumerate((dashboard.cards[1], dashboard.cards[2])):
            self.assertEqual(dashboard.grid.getItemPosition(dashboard.grid.indexOf(card))[:2], (0, index))
        self.assertEqual(dashboard.surface.minimumSizeHint().width() <= dashboard.width(), True)

    def test_tool_windows_are_compact_independent_and_resume_inputs(self):
        self.assertLessEqual(self.window.width(), 800)
        self.assertLessEqual(self.window.height(), 720)
        self.window.navigate("mapper")
        self.window.navigate("rack")
        mapper_window = self.window.utility_windows["mapper"]
        rack_window = self.window.utility_windows["rack"]
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
        rack = self.window.pages["rack"]
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
        page = self.window.pages["rack"]
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
