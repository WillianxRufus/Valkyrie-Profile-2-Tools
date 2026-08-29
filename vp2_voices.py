#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""GUI and command-line launcher for the VP2 voice tool."""

from __future__ import annotations

import argparse
import sys

from tools.voice_patcher import audio
from tools.voice_patcher.build import (
    default_patch_output, default_voice_root, extract_voices, patch_iso,
)
from tools.voice_patcher.layout import load_bank_map


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check", action="store_true",
        help="verify this build carries everything it needs, then exit",
    )
    commands = parser.add_subparsers(dest="command")
    extract = commands.add_parser(
        "extract", help="extract every voice line from a USA or Japan ISO"
    )
    extract.add_argument("source", help="USA or Japan Valkyrie Profile 2 ISO")
    extract.add_argument(
        "-o", "--output", help="voice root (default: voices; en/jp is added)"
    )
    patch = commands.add_parser(
        "patch", help="patch a folder of identified WAV files into a new ISO"
    )
    patch.add_argument("source", help="USA or Japan Valkyrie Profile 2 ISO")
    patch.add_argument("voices", help="folder containing replacement WAV files")
    patch.add_argument("-o", "--output", help="new ISO path")
    patch.add_argument(
        "--allow-overlong", action="store_true",
        help="deliberately trim WAVs that exceed their fixed game slots",
    )
    return parser


def self_check(stream=None):
    output = stream or sys.stdout
    notes, problems = [], []
    frozen = bool(getattr(sys, "frozen", False))
    notes.append("frozen            : %s" % frozen)
    try:
        owners = load_bank_map()
        notes.append("known bank map    : %d cutscene bank(s)" % len(owners))
    except Exception as exc:
        problems.append("voice-bank map does not load: %r" % exc)
    try:
        encoded = audio.encode_adpcm(b"\0\0" * 28)
        if len(encoded) != audio.FRAME:
            raise ValueError("unexpected encoded frame length")
        notes.append("audio codec       : %d Hz PCM/PS-ADPCM" % audio.SAMPLE_RATE)
    except Exception as exc:
        problems.append("audio codec self-test failed: %r" % exc)
    try:
        from tools.voice_patcher import gui
        artwork = [name for name in (
            gui.ICON_ICO, gui.ICON_PNG, gui.BACKDROP_PNG
        ) if gui.asset_path(name)]
        notes.append("window artwork    : " + (", ".join(artwork) or "none"))
        for name in (gui.ICON_ICO, gui.ICON_PNG, gui.BACKDROP_PNG):
            if name not in artwork:
                problems.append("missing window artwork: %s" % name)
        import tkinter
        notes.append("window runtime    : Tcl %s"
                     % tkinter.Tcl().eval("info patchlevel"))
        if frozen:
            for relative in ("_tcl_data/init.tcl", "_tk_data/tk.tcl"):
                if not (gui.PROJECT_ROOT / relative).is_file():
                    problems.append("missing window runtime file: %s" % relative)
    except Exception as exc:  # pragma: no cover - packaging environment
        problems.append("the Tk window runtime does not initialize: %r" % exc)
    for note in notes:
        print(note, file=output)
    for problem in problems:
        print("FAIL  %s" % problem, file=output)
    if problems:
        print("\n%d problem(s); this build should not ship" % len(problems),
              file=output)
        return 1
    print("\nself-check ok", file=output)
    return 0


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.self_check:
        return self_check()
    if args.command is None:
        from tools.voice_patcher.gui import run_gui
        return run_gui()
    try:
        if args.command == "extract":
            result = extract_voices(
                args.source, args.output or default_voice_root(), progress=print
            )
            print(
                "Extracted %d clips from %d banks to %s"
                % (result.clips, result.banks, result.output)
            )
        else:
            result = patch_iso(
                args.source, args.voices,
                args.output or default_patch_output(args.source),
                progress=print,
                allow_overlong=args.allow_overlong,
            )
            print(
                "Patched %d voice clips; verified output: %s"
                % (len(result.replacements), result.output)
            )
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
