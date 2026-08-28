#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""GUI and command-line launcher for the VP2 cheat patcher."""

import argparse
import sys

from tools.cheat_patcher import (
    angel_slayer,
    battle_anti_freeze,
    disable_anti_cheat,
    equip_everything,
)
from tools.cheat_patcher.build import PATCHERS, build_iso, default_output_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?",
                        help="path to a clean Valkyrie Profile 2 ISO; "
                             "omit it to open the window")
    parser.add_argument(
        "-o", "--output",
        help="output path (default: beside the tool, named after the source)",
    )
    parser.add_argument(
        "--self-check", action="store_true",
        help="verify this build carries everything it needs, then exit")
    parser.add_argument(
        "--patch",
        action="append",
        choices=tuple(PATCHERS),
        help="patch to apply; repeat to select multiple (default: all)",
    )
    return parser.parse_args(argv)


def self_check(stream=None):
    """Load what a patch run loads and report it.  Non-zero means do not ship."""
    out = stream or sys.stdout
    notes, problems = [], []
    frozen = getattr(sys, "frozen", False)
    notes.append("frozen            : %s" % bool(frozen))

    from tools.cheat_patcher import gui
    notes.append("payload root      : %s" % gui.PROJECT_ROOT)
    notes.append("iso written to    : %s" % default_output_path("Example.iso").parent)

    artwork = [name for name in (gui.ICON_ICO, gui.ICON_PNG, gui.BACKDROP_PNG)
               if gui.asset_path(name)]
    notes.append("window artwork    : " + (", ".join(artwork) or "none"))
    for name in (gui.ICON_ICO, gui.ICON_PNG, gui.BACKDROP_PNG):
        if name not in artwork:
            problems.append("missing window artwork: %s" % name)

    try:
        import tkinter
        notes.append("window runtime    : Tcl %s"
                     % tkinter.Tcl().eval("info patchlevel"))
        if frozen:
            for relative in ("_tcl_data/init.tcl", "_tk_data/tk.tcl"):
                if not (gui.PROJECT_ROOT / relative).is_file():
                    problems.append("missing window runtime file: %s" % relative)
    except Exception as exc:                     # pragma: no cover - packaging
        problems.append("the Tk window runtime does not initialize: %r" % exc)

    try:
        from tools.cheat_patcher import catalog
        notes.append("patches           : %d (%s)"
                     % (len(catalog.CHEATS),
                        ", ".join(sorted(catalog.BY_NAME))))
        missing = sorted(set(PATCHERS) - set(catalog.BY_NAME))
        if missing:
            problems.append("patches with no description: %s" % missing)
    except Exception as exc:                     # pragma: no cover - packaging
        problems.append("the catalog does not import: %r" % exc)

    for line in notes:
        print(line, file=out)
    for line in problems:
        print("FAIL  %s" % line, file=out)
    if problems:
        print("\n%d problem(s); this build should not ship" % len(problems),
              file=out)
        return 1
    print("\nself-check ok", file=out)
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.self_check:
        return self_check()
    if args.source is None:
        from tools.cheat_patcher.gui import run_gui
        return run_gui()
    output = args.output or default_output_path(args.source)
    selected = args.patch or tuple(PATCHERS)
    print("Validating and recompressing: %s..." % ", ".join(selected))
    try:
        result = build_iso(args.source, output, selected=selected,
                           progress=print)
    except (OSError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    for applied in result.patches:
        patch = applied.details
        if applied.name == "angel-slayer":
            print(
                "Angel Slayer: EE 0x%08X 0x%08X -> 0x%08X "
                "(resource %d, stream %d, module +0x%X)"
                % (angel_slayer.TARGET_ADDRESS, angel_slayer.ORIGINAL_WORD,
                   angel_slayer.PATCHED_WORD, applied.resource,
                   patch.stream_number, patch.module_offset)
            )
        elif applied.name == "equip-everything":
            print(
                "Equip Everything: EE 0x%08X 0x%08X -> NOP "
                "(resource %d, CampEquip.ovl +0x%X)"
                % (equip_everything.TARGET_ADDRESS,
                   equip_everything.ORIGINAL_INSTRUCTION,
                   applied.resource, patch.overlay_offset)
            )
        elif applied.name == "battle-anti-freeze":
            print(
                "Battle Anti-Freeze: EE 0x%08X 0x%08X -> 0x%08X "
                "(resource %d, battle overlay +0x%X)"
                % (battle_anti_freeze.TARGET_ADDRESS,
                   battle_anti_freeze.ORIGINAL_INSTRUCTION,
                   battle_anti_freeze.PATCHED_INSTRUCTION,
                   applied.resource, patch.module_offset)
            )
        elif applied.name == "disable-anti-cheat":
            resources = ", ".join(
                "%s: %d" % (item.label, item.change_count)
                for item in patch.resources
            )
            file_changes = sum(item.change_count for item in patch.files)
            total = (sum(item.change_count for item in patch.resources) +
                     file_changes)
            print(
                "Disable Anti-Cheat: %d instructions (%s; executable: %d; "
                "PCSX2 CRC preserved: %08X)"
                % (total, resources, file_changes,
                   patch.files[0].patched_crc)
            )
    print("Verified output: %s" % result.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
