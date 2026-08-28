# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
# -*- mode: python ; coding: utf-8 -*-

"""One-file GUI build of the cheat patcher, for people who do not have Python.

Sibling of `vp2_release.spec`, and deliberately much smaller. The translator
carries a payload -- structural tables and every language pack -- because it
has to know things about the game's text that it cannot recover from a disc
cheaply. This one carries no payload at all: every address, original word and
replacement it needs is source code, so the window and its artwork are the
whole bundle.

Nothing here is game-derived either. What the patches embed is the same
(address, original, replacement) triples a PNACH publishes, which is why this
can ship at all.

    pyinstaller data/vp2_cheats.spec \
        --workpath workspace/internal/build \
        --clean --noconfirm
    ./dist/ValkyrieProfile2-CheatPatcher --self-check
"""
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, os.fspath(ROOT))

APP_NAME = "ValkyrieProfile2-CheatPatcher"
ICON = ROOT / "images" / "vp2_release.ico"
ARTWORK = (
    "images/vp2_release.ico",
    "images/vp2_release.png",
    "images/vp2_release_bg.png",
)
UNUSED_TCL_TREES = ("_tcl_data/tzdata", "_tcl_data/msgs", "_tk_data/msgs")

datas = [(os.fspath(ROOT / name), os.path.dirname(name)) for name in ARTWORK
         if (ROOT / name).is_file()]
print("artwork: %d file(s)" % len(datas))

a = Analysis(
    [os.fspath(ROOT / "vp2_cheats.py")],
    pathex=[os.fspath(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "turtle",
        "numpy", "scipy", "pandas", "matplotlib", "PIL",
        "pytest", "setuptools", "pip", "distutils",
        "test", "unittest.test",
        "curses", "readline",
        "email", "http.server", "xmlrpc", "pydoc_data",
    ],
    noarchive=False,
    optimize=0,
)

_before = len(a.datas)
a.datas = [entry for entry in a.datas
           if not entry[0].replace("\\", "/").startswith(UNUSED_TCL_TREES)]
print("dropped %d unused Tcl/Tk data file(s)" % (_before - len(a.datas)))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    icon=os.fspath(ICON) if ICON.is_file() else None,
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
)
