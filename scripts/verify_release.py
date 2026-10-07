"""Verify both source and packaged startup without opening CAD or user documents."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    root = Path(__file__).resolve().parents[1]
    executable = root / "dist" / "CivTools" / "CivTools.exe"
    if not executable.is_file():
        raise SystemExit("Build dist/CivTools/CivTools.exe first.")
    reports = {}
    with tempfile.TemporaryDirectory(prefix="civtools-release-") as temporary:
        for name, command in (("source", [sys.executable, str(root / "CivTools.py"), "--smoke-test"]),
                              ("packaged", [str(executable), "--smoke-test"])):
            report_path = Path(temporary) / f"{name}.json"
            environment = os.environ.copy()
            environment["CIVTOOLS_CONFIG_DIR"] = str(Path(temporary) / name)
            environment["CIVTOOLS_SMOKE_REPORT"] = str(report_path)
            environment["QT_QPA_PLATFORM"] = "offscreen"
            started = time.perf_counter()
            result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True,
                                    timeout=60, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"passed": False, "failures": [result.stderr]}
            report.update(exit_code=result.returncode, seconds=round(time.perf_counter() - started, 2))
            reports[name] = report
            print(f"{name}: {'PASS' if report['passed'] and result.returncode == 0 else 'FAIL'} ({report['seconds']}s)", flush=True)
    reports["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    reports["distribution_bytes"] = sum(path.stat().st_size for path in executable.parent.rglob("*") if path.is_file())
    output = root / "artifacts" / "release-verification.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(output)
    if not all(reports[name]["passed"] and reports[name]["exit_code"] == 0 for name in ("source", "packaged")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
