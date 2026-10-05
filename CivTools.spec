# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["CivTools.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("assets/icons/logo.ico", "assets/icons"),
        ("assets/icons/dxf_extractor.png", "assets/icons"),
        ("assets/icons/dj_parameter.png", "assets/icons"),
        ("assets/icons/pipe_rack.png", "assets/icons"),
        ("assets/icons/autocad_mapper.png", "assets/icons"),
        ("assets/icons/standards_library.png", "assets/icons"),
        ("assets/icons/video-tutorial.png", "assets/icons"),
        ("assets/icons/file_icon.png", "assets/icons"),
        ("assets/icons/excel_icon.png", "assets/icons"),
        ("assets/images/background4.png", "assets/images"),
        ("assets/images/snap.png", "assets/images"),
        ("assets/images/snap2.png", "assets/images"),
    ],
    # Keep the optional tools available while their heavy modules load on demand.
    hiddenimports=[
        "civtools.autocad_plotter",
        "civtools.dj_parameter_assigner",
        "civtools.drawing_manager",
        "civtools.dxf_extractor_app",
        "civtools.piperack_generator",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CivTools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets/icons/logo.ico"],
)
