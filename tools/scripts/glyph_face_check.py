#!/usr/bin/env python3
"""Measure whether a glyph or mark belongs to the game's face."""
import argparse
import base64
import csv
import os
import statistics

from . import vp2_glyph_compose as gc
from .vp2_cutscene_subtitles import _DEFAULT_POOL_PATH


def default_pool():
    """The glyph pool this tree builds from."""
    return os.environ.get("VP2_GLYPH_POOL") or _DEFAULT_POOL_PATH

#: Letters, not punctuation: a period is a handful of pixels and its level
#: histogram says nothing about how the face renders a stroke.
REFERENCE_CHARACTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def read_table(path):
    """``[(character, pixels)]`` from any table carrying base64 bitmaps."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            character = row.get("character")
            pixels = row.get("pixels")
            if character and pixels:
                rows.append((character, base64.b64decode(pixels)))
    return rows


def profile(pixels):
    """``(levels, max_share)`` over a bitmap's inked pixels only."""
    grid = gc.unpack(pixels)
    ink = [value for row in grid for value in row if value]
    if not ink:
        return 0, 0.0
    return len(set(ink)), sum(1 for v in ink if v == 15) / len(ink)


def reference_profile(path=None):
    """What the face itself does, as ``(median levels, median max share)``."""
    path = path or default_pool()
    levels, shares = [], []
    for character, pixels in read_table(path):
        if character not in REFERENCE_CHARACTERS:
            continue
        count, share = profile(pixels)
        if count:
            levels.append(count)
            shares.append(share)
    if not levels:
        raise SystemExit("no reference letters in %s" % path)
    return statistics.median(levels), statistics.median(shares)


def cmd_reference(args):
    pool = args.pool or default_pool()
    levels, share = reference_profile(pool)
    print("face reference from %d letter(s) in %s"
          % (len(REFERENCE_CHARACTERS), os.path.basename(pool)))
    print("  median distinct ink levels : %.0f" % levels)
    print("  median share at full ink   : %.0f%%" % (share * 100))


def cmd_check(args):
    want_levels, want_share = reference_profile(args.pool)
    # Half the face's level count is the line between "antialiased like the
    # game" and "quantised": the Arial renders sit at three against twelve.
    floor = max(2, round(want_levels / 2))
    rows = read_table(args.table)
    print("%-4s %-8s %-10s %s" % ("char", "levels", "full ink", "verdict"))
    suspect = 0
    for character, pixels in rows:
        levels, share = profile(pixels)
        bad = levels < floor or share > want_share * 3
        suspect += bad
        print("%-4s %-8d %-10s %s"
              % (character, levels, "%.0f%%" % (share * 100),
                 "off-face" if bad else "ok"))
    print("\nface median %.0f level(s), %.0f%% full ink; flagging under %d "
          "level(s) or over %.0f%% full ink"
          % (want_levels, want_share * 100, floor, want_share * 300))
    print("%d of %d entr(ies) look off-face" % (suspect, len(rows)))
    return 1 if suspect else 0


def cmd_show(args):
    for character, pixels in read_table(args.table):
        if character != args.character:
            continue
        grid = gc.unpack(pixels)
        levels, share = profile(pixels)
        print("%s -- %d ink level(s), %.0f%% at full"
              % (character, levels, share * 100))
        for y, row in enumerate(grid):
            print("  %2d |%s|"
                  % (y, "".join("%X" % v if v else "." for v in row)))
        return 0
    raise SystemExit("%r is not in %s" % (args.character, args.table))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", default=None,
                        help="glyph table defining the face (default: the "
                             "tracked subtitle pool)")
    commands = parser.add_subparsers(dest="command", required=True)

    reference = commands.add_parser(
        "reference", help="print what the face itself measures")
    reference.set_defaults(func=cmd_reference)

    check = commands.add_parser(
        "check", help="score every glyph in a table against the face")
    check.add_argument("table")
    check.set_defaults(func=cmd_check)

    show = commands.add_parser(
        "show", help="print one glyph as an intensity map")
    show.add_argument("table")
    show.add_argument("character")
    show.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
