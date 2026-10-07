"""Local CPU timings; deliberately excludes live CAD execution."""
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from civtools.core.geometry import build_rack_plan
from civtools.core.spreadsheet import inspect_mapping


def main():
    reports = {}
    for name, count, tiers in (("typical_rack", 4, 2), ("large_rack", 20, 20)):
        config = {"transverse_spacing": list(range(0, count * 6, 6)), "longitudinal_spacing": list(range(0, count * 8, 8)),
                  "trans_beam_elevations": list(range(3, tiers * 3 + 1, 3)), "long_beam_elevations": list(range(3, tiers * 3 + 1, 3)),
                  "base_elevation": 0, "foundation_depth": 1.5, "support_type": "Fixed", "bracing_enabled": True}
        samples = []
        for _ in range(5):
            started = time.perf_counter()
            plan = build_rack_plan(config)
            samples.append((time.perf_counter() - started) * 1000)
        reports[name] = {"nodes": len(plan.nodes), "beams": len(plan.beams), "median_ms": round(statistics.median(samples), 2)}
    import openpyxl
    with tempfile.TemporaryDirectory(prefix="civtools-benchmark-") as directory:
        path = Path(directory) / "coordinates.xlsx"
        workbook = openpyxl.Workbook(write_only=True)
        sheet = workbook.create_sheet("Coordinates")
        sheet.append(["X", "Y", "Width", "Height", "Label"])
        for index in range(10000):
            sheet.append([index, index * 2, 4, 6, f"Box {index}"])
        workbook.save(path)
        workbook.close()
        started = time.perf_counter()
        result = inspect_mapping(path, None, lambda *args: None)
        reports["workbook_validation"] = {"rows": result["valid"], "ms": round((time.perf_counter() - started) * 1000, 2)}
    output = ROOT / "artifacts" / "benchmarks.json"
    output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
