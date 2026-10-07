"""Map validated worksheet rows into the active AutoCAD drawing."""
from array import array
import time
from pyautocad import Autocad, APoint
from .callbacks import ServiceCallbacks
from .spreadsheet import read_mapping
from .results import OperationResult


class MapperService(ServiceCallbacks):
    def create_layer(self, document, name, color):
        try:
            return document.Layers.Item(name)
        except Exception:
            layer = document.Layers.Add(name)
            layer.Color = color
            return layer

    def _plot_boxes_job(self, path, height, offset, sheet_name=None):
        self.report("stage", "Validating worksheet rows…")
        mapping = read_mapping(path, sheet_name)
        if not mapping["valid"]:
            raise ValueError("No valid rows to plot. Check columns A–D and the selected sheet.")
        self.report("stage", "Connecting to AutoCAD…")
        acad = Autocad(create_if_not_exists=False)
        document = acad.doc
        if document is None:
            raise RuntimeError("Open the intended AutoCAD drawing first.")
        self.report("target", str(document.FullName or document.Name))
        space = document.ModelSpace
        self.create_layer(document, "AutomatedBOXES", 1)
        self.create_layer(document, "AutomatedBOXESTEXT", 2)
        successful, failed, label_failures = 0, 0, 0
        start = time.monotonic()
        rows = mapping["rows"]
        for index, (number, data, status) in enumerate(rows, 1):
            if data is None:
                if status != "Blank row":
                    self.report("log", f"Row {number}: {status}")
            else:
                x, y, width, depth, text = data
                rectangle = None
                try:
                    x1, y1, x2, y2 = x - width / 2, y - depth / 2, x + width / 2, y + depth / 2
                    rectangle = space.AddPolyline(array('d', [x1, y1, 0, x2, y1, 0, x2, y2, 0, x1, y2, 0]))
                    rectangle.Closed = True
                    rectangle.Layer = "AutomatedBOXES"
                    successful += 1
                except Exception as error:
                    failed += 1
                    self.report("log", f"Row {number}: rectangle failed ({error}); inspect the drawing for partial geometry.")
                else:
                    if text.strip():
                        try:
                            point = APoint(x, y1 - offset)
                            entity = space.AddText(text, point, height)
                            entity.Layer = "AutomatedBOXESTEXT"
                            entity.Alignment = 7
                            entity.TextAlignmentPoint = point
                        except Exception as error:
                            label_failures += 1
                            self.report("log", f"Row {number}: label failed ({error}).")
            if index % 25 == 0 or index == len(rows):
                self.report("stage", f"Plotting rows: {index:,} / {len(rows):,}")
                self.update_progress(index / len(rows))
        if successful == 0:
            raise RuntimeError("No boxes were completed. Review Activity and the drawing for partial changes.")
        skipped = mapping["skipped"] + mapping["invalid"]
        summary = f"{successful:,} boxes plotted · {skipped:,} rows skipped · {failed:,} boxes failed · {label_failures:,} labels failed."
        summary += f"\nSheet: {mapping['sheet']} · {time.monotonic() - start:.1f}s"
        self.result = OperationResult(summary, successful=successful, skipped=skipped, failed=failed + label_failures)
