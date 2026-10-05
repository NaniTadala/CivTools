# CivTools

CivTools is a Windows desktop launcher for the DXF quantity extractor, AutoCAD
plotter, STAAD DJ parameter tool, pipe rack modeler, and EIL standards library.

## Project layout

- `CivTools.py` is the source-run entry point.
- `src/civtools/` contains the launcher and tool modules.
- `assets/` contains UI images and icons.
- `data/` is provisioned separately and is not included in this repository.
- STAAD DJ settings are stored locally and are not included in this repository.

The repository contains application source and UI assets only; it excludes
engineering datasets, standards documents, local settings, and generated build
outputs. The app does not log startup usage. To use the Video Tutorials button,
set `CIVTOOLS_TUTORIALS_PATH` to the tutorials folder on your system.

Install the application and build dependencies into a virtual environment:

```powershell
python -m pip install -r requirements.txt
python CivTools.py
```

Build a single-file Windows executable with PyInstaller:

```powershell
pyinstaller CivTools.spec
```

The build creates `dist/CivTools.exe`. Provision the required `data/` directory
beside the executable separately so the standards library, drawing database,
and SOP document remain available. A one-file executable has some unavoidable
startup extraction time; UPX is disabled to avoid decompression overhead and
reduce false-positive antivirus scanning.
