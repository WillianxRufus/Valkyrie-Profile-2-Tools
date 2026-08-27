# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
# -*- mode: python ; coding: utf-8 -*-

"""One-file build of the translator, for people who do not have Python.

What goes in is the runtime plus the source-free tables a build reads: the
build profile, the structural tables, and every language pack. What stays out
is anything cut from a game image -- there is no workspace here, no glyph
pool, no compression cache. The user's first run makes those from the disc
they already own, which is what keeps this file publishable.

The result is a few megabytes. If it ever is not, something game-derived has
been added to the payload and should be taken back out.

    pyinstaller vp2_release.spec --clean --noconfirm
    ./dist/ValkyrieProfile2-Translator --self-check
"""
import os
import sys

# As the package, not as a loose module: everything under tools/scripts
# imports its siblings relatively, so a bare import of one of them fails
# before it reaches the first line that matters.
sys.path.insert(0, SPECPATH)
from tools.scripts.public_release import payload_members          # noqa: E402

APP_NAME = "ValkyrieProfile2-Translator"

members = payload_members(SPECPATH)
datas = [(os.fspath(source), os.path.dirname(name) or ".")
         for source, name in members]
print("payload: %d file(s), %.1f MB"
      % (len(members), sum(s.stat().st_size for s, _ in members) / 1e6))

a = Analysis(
    [os.path.join(SPECPATH, "vp2_translate.py")],
    pathex=[SPECPATH],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # The runtime is standard library only and drives a command line. None
    # of this is reachable from it, and each one costs megabytes -- the
    # numerical stack most of all, which PyInstaller will happily pull in
    # through a single transitive import if one ever appears.
    excludes=[
        "tkinter", "_tkinter", "turtle",
        "numpy", "scipy", "pandas", "matplotlib", "PIL",
        "pytest", "setuptools", "pip", "distutils",
        "test", "unittest.test",
        "curses", "readline",
        "email", "http.server", "xmlrpc", "pydoc_data",
    ],
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
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX shrinks the file and gets it flagged: a compressed entry point is
    # what a good deal of malware looks like to a heuristic scanner, and an
    # unsigned binary from an unknown publisher has little goodwill to
    # spend. A few megabytes is the cheaper side of that trade.
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
