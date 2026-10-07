# -*- mode: python ; coding: utf-8 -*-
# A directory build avoids extracting the Qt runtime on every launch.
a = Analysis(
    ["CivTools.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("assets/icons/logo.ico", "assets/icons"),
        ("fonts/Poppins/Poppins-Regular.ttf", "fonts/Poppins"),
        ("fonts/Poppins/Poppins-SemiBold.ttf", "fonts/Poppins"),
        ("fonts/Poppins/Poppins-Bold.ttf", "fonts/Poppins"),
        ("fonts/Poppins/OFL.txt", "fonts/Poppins"),
    ],
    hiddenimports=["civtools.core.mapper", "civtools.core.dj", "civtools.core.quantities", "civtools.core.piperack"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "customtkinter", "PyQt5", "PyQt6"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="CivTools", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    disable_windowed_traceback=False,
    icon=["assets/icons/logo.ico"],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CivTools")
