# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for a single-file Windows executable.

Built windowed, so double-clicking opens the interface with no console behind
it; the command line still works because the program attaches to the calling
console when it is given a subcommand.
"""

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "tabletmidi.cli",
        "tabletmidi.gui",
        "tabletmidi.engine",
        "tabletmidi.hid_win",
        "tabletmidi.midi_win",
        "tabletmidi.hidhide",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Nothing here needs the scientific stack; excluding it keeps the
    # executable small and the build fast.
    excludes=[
        "numpy", "scipy", "pandas", "matplotlib", "PIL", "PyQt5", "PySide2",
        "pytest", "setuptools", "pip", "unittest", "email", "http", "xml",
        "pydoc_data",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="TabletMidi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Elevation is only needed to change the HidHide configuration, and the
    # program offers to restart itself for that. Demanding it up front would
    # put a UAC prompt in front of every launch.
    uac_admin=False,
)
