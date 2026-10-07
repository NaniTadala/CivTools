import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import openpyxl
from civtools.core.spreadsheet import read_mapping
from civtools.jobs import run_mapper


class MapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "data.xlsx"
        workbook = openpyxl.Workbook()
        workbook.active.title = "Coordinates"
        workbook.active.append(["X", "Y", "Width", "Height", "Label"])
        workbook.active.append([10, 20, 4, 6, "Box 1"])
        workbook.active.append([10, 20, -4, 6, "Invalid"])
        workbook.active.append([None, None, None, None, None])
        workbook.active.append([30, 40, 8, 10, "Box 2"])
        workbook.create_sheet("Empty")
        workbook.active = 1
        workbook.save(self.path)
        workbook.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_first_sheet_and_row_validation(self):
        result = read_mapping(self.path)
        self.assertEqual(result["sheet"], "Coordinates")
        self.assertEqual((result["valid"], result["invalid"], result["skipped"]), (2, 1, 1))
        self.assertIsNone(result["rows"][1][1])
        self.assertEqual(read_mapping(self.path, "Empty")["valid"], 0)

    def test_invalid_workbook_does_not_connect_to_cad(self):
        with patch("civtools.core.mapper.Autocad") as acad:
            with self.assertRaisesRegex(ValueError, "No valid rows"):
                run_mapper(self.path, 250, 125, lambda *args: None, "Empty")
            acad.assert_not_called()

    def test_plot_uses_selected_sheet_and_preserves_active_layer(self):
        document = MagicMock()
        document.Name = "target.dwg"
        document.FullName = "C:/Drawings/target.dwg"
        document.ActiveLayer = "User layer"
        events = []
        with patch("civtools.core.mapper.Autocad") as acad:
            acad.return_value.doc = document
            result = run_mapper(self.path, 250, 125, lambda *event: events.append(event), "Coordinates")
        self.assertEqual((result.successful, result.skipped, result.failed), (2, 2, 0))
        self.assertEqual(document.ActiveLayer, "User layer")
        self.assertEqual(document.ModelSpace.AddPolyline.call_count, 2)
        self.assertEqual(document.Layers.Item.call_count, 2)
        self.assertEqual(document.ModelSpace.AddText.return_value.Layer, "AutomatedBOXESTEXT")
        self.assertIn(("progress", 100), events)
        self.assertIn(("target", "C:/Drawings/target.dwg"), events)

    def test_label_failures_are_reported(self):
        with patch("civtools.core.mapper.Autocad") as acad:
            acad.return_value.doc.ModelSpace.AddText.side_effect = RuntimeError("label rejected")
            result = run_mapper(self.path, 250, 125, lambda *args: None)
        self.assertEqual(result.successful, 2)
        self.assertEqual(result.failed, 2)
        self.assertIn("2 labels failed", result.summary)


if __name__ == "__main__":
    unittest.main()
