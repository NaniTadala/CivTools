"""Package the verified Windows distribution and check every archive entry."""
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / "dist" / "CivTools"
    executable = folder / "CivTools.exe"
    verification = json.loads((root / "artifacts" / "release-verification.json").read_text(encoding="utf-8"))
    if not verification["packaged"]["passed"] or verification["executable_sha256"] != hashlib.sha256(executable.read_bytes()).hexdigest():
        raise SystemExit("Run scripts/verify_release.py against the current build before packaging.")
    (folder / "README.txt").write_text(
        "CivTools - Windows engineering toolkit\n\n"
        "Extract the entire archive, then run CivTools.exe. Keep the _internal folder\n"
        "beside the executable. Python does not need to be installed.\n\n"
        "Open the intended AutoCAD drawing or STAAD model before using a CAD tool.\n"
        "Pipe rack generation requires an open, saved, blank STAAD model.\n"
        "Tier elevations are absolute, in meters. The geometry preview is not a design check.\n"
        "Installed AutoCAD and STAAD.Pro are required for their corresponding operations.\n\n"
        "Each tool opens independently. Closing a tool preserves its inputs.\n"
        "Use the launcher to exit after jobs complete. Settings and window positions\n"
        "are saved in %APPDATA%/CivTools. Text size is adjustable in the launcher.\n\n"
        "The mapper lets you select a worksheet and inspect sample rows. Columns A-E\n"
        "are center X, center Y, width, height and label; data starts at row 2.\n"
        "Completed quantity jobs offer Open workbook and Show in folder.\n"
        "Select a local PDF folder in the library and enable Preview to render a page.\n\n"
        "This build passed automated regression tests and source/packaged startup checks,\n"
        "including isolated PDF rendering. Live CAD integration needs validation with\n"
        "your installed CAD versions and real models.\n", encoding="utf-8")
    archive = root / "dist" / "CivTools-Windows.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(folder.parent))
    with zipfile.ZipFile(archive) as output:
        damaged = output.testzip()
        if damaged:
            raise SystemExit(f"Archive validation failed: {damaged}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Verified archive: {archive}\nSize: {archive.stat().st_size / 1048576:.1f} MiB\nSHA256: {digest}")


if __name__ == "__main__":
    main()
