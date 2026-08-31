#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Command-line interface for the VP2 voice tool."""

from __future__ import annotations

import argparse
import sys

from tools.voice_patcher import audio
from tools.voice_patcher.build import (
    default_japanese_audio_output, default_patch_output, default_voice_root,
    extract_voices, import_japanese_audio, patch_iso,
)
from tools.voice_patcher.layout import load_bank_map, load_unmapped_map


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
    import_jp = commands.add_parser(
        "import-japanese",
        help="create a Japanese-audio edition of a supported USA or PAL ISO",
    )
    import_jp.add_argument(
        "base", help="USA or PAL Valkyrie Profile 2 target ISO"
    )
    import_jp.add_argument("japan", help="Japanese Valkyrie Profile 2 ISO")
    import_jp.add_argument("-o", "--output", help="new ISO path")
    return parser


def self_check(stream=None):
    output = stream or sys.stdout
    notes, problems = [], []
    notes.append("frozen            : %s" % bool(getattr(sys, "frozen", False)))
    try:
        owners = load_bank_map()
        alternates = sum(owner.category == "alternate"
                         for owner in owners.values())
        notes.append(
            "known bank map    : %d bank(s), %d alternate/unmapped"
            % (len(owners), alternates)
        )
    except Exception as exc:
        problems.append("voice-bank map does not load: %r" % exc)
    try:
        voices = load_unmapped_map()
        notes.append("unmapped voice map: %d sample(s)" % len(voices))
    except Exception as exc:
        problems.append("unmapped-voice map does not load: %r" % exc)
    try:
        encoded = audio.encode_adpcm(b"\0\0" * 28)
        if len(encoded) != audio.FRAME:
            raise ValueError("unexpected encoded frame length")
        notes.append("audio codec       : %d Hz PCM/PS-ADPCM" % audio.SAMPLE_RATE)
    except Exception as exc:
        problems.append("audio codec self-test failed: %r" % exc)
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
        _parser().print_help(sys.stderr)
        return 2
    try:
        if args.command == "extract":
            result = extract_voices(
                args.source, args.output or default_voice_root(), progress=print
            )
            print(
                "Extracted %d cutscene clips from %d banks and %d unmapped "
                "samples to %s"
                % (result.clips - result.unmapped_clips, result.banks,
                   result.unmapped_clips, result.output)
            )
        elif args.command == "patch":
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
        else:
            result = import_japanese_audio(
                args.base, args.japan,
                args.output or default_japanese_audio_output(args.base),
                progress=print,
            )
            print(
                "Imported %d complete Japanese audio resources; verified "
                "output: %s"
                % (len(result.resources), result.output)
            )
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
