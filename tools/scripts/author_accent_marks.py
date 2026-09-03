#!/usr/bin/env python3
"""Draw the project's own accent marks in the game's subtitle face."""
import argparse
import base64
import csv
import hashlib
import io
import math
import os

from . import vp2_glyph_compose as gc
from .vp2_cutscene_subtitles import _resolve_authored_marks_path

SUPERSAMPLE = 8

PROFILE = ((0.00, 15.0), (0.60, 15.0), (1.60, 7.0),
           (2.60, 7.0), (3.40, 0.0))

DEFAULT_CAP = 1.0

BASELINE = 23

TILDE_SCALE = 0.9

RING_RADIUS_X, RING_RADIUS_Y = 2.5, 1.9

RING_PROFILE = ((0.00, 15.0), (0.80, 15.0), (1.40, 7.0), (1.80, 0.0))


def _nearest_position(px, py, ax, ay, bx, by):
    """Where on a segment the nearest point falls, clamped to ``0..1``."""
    dx, dy = bx - ax, by - ay
    squared = dx * dx + dy * dy
    if squared == 0:
        return 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / squared
    return max(0.0, min(1.0, t))


def _interpolate(distance, weight=1.0, profile=None):
    """The face's ink at *distance* pixels from a stroke's centreline."""
    profile = profile or PROFILE
    distance = distance / weight if weight else distance
    if distance >= profile[-1][0]:
        return 0.0
    for (d0, v0), (d1, v1) in zip(profile, profile[1:]):
        if distance <= d1:
            if d1 == d0:
                return v0
            return v0 + (v1 - v0) * (distance - d0) / (d1 - d0)
    return 0.0


HALO = 7.0




def _taper_at(taper, position):
    """How much core a stroke has *position* of the way along it."""
    if not taper:
        return 1.0
    if position <= taper[0][0]:
        return taper[0][1]
    for (t0, m0), (t1, m1) in zip(taper, taper[1:]):
        if position <= t1:
            if t1 == t0:
                return m0
            return m0 + (m1 - m0) * (position - t0) / (t1 - t0)
    return taper[-1][1]


def _polyline_metrics(polyline):
    """``[(ax, ay, bx, by, start, length)]`` with *start* the run so far."""
    out, run = [], 0.0
    for (ax, ay), (bx, by) in zip(polyline, polyline[1:]):
        length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        out.append((ax, ay, bx, by, run, length))
        run += length
    return out, run


def _segment_distance(px, py, ax, ay, bx, by, cap=1.0):
    """Distance to a segment, with *cap* controlling how the ends close."""
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / length_squared
    length = length_squared ** 0.5
    clamped = max(0.0, min(1.0, t))
    nearest_x, nearest_y = ax + clamped * dx, ay + clamped * dy
    perpendicular = ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5
    overshoot = max(0.0, -t, t - 1.0) * length
    if overshoot == 0.0 or cap == 1.0:
        return perpendicular
    return max(perpendicular, overshoot * cap)


def render(path, rows, cap=DEFAULT_CAP, weight=1.0, taper=None,
           profile=None, widths=None):
    """Rasterise one mark's centreline into a packed glyph block."""
    measured = [_polyline_metrics(polyline) for polyline in path]
    grid = [[0] * gc.WIDTH for _ in range(gc.HEIGHT)]
    step = 1.0 / SUPERSAMPLE
    offset = step / 2.0 - 0.5
    for y in rows:
        for x in range(gc.WIDTH):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                py = y + offset + sy * step
                for sx in range(SUPERSAMPLE):
                    px = x + offset + sx * step
                    best, along = None, 0.0
                    needs_position = bool(taper or widths)
                    for segments, whole in measured:
                        for ax, ay, bx, by, start, length in segments:
                            d = _segment_distance(px, py, ax, ay, bx, by, cap)
                            if best is None or d < best:
                                best = d
                                if whole and needs_position:
                                    near = _nearest_position(
                                        px, py, ax, ay, bx, by)
                                    along = (start + near * length) / whole
                    scale = weight * _taper_at(widths, along)
                    value = _interpolate(best, scale, profile)
                    if taper and value > HALO:
                        value = HALO + (value - HALO) * _taper_at(taper, along)
                    total += value
            value = int(round(total / (SUPERSAMPLE * SUPERSAMPLE)))
            grid[y][x] = max(0, min(15, value))
    return grid


SHAPES = {
    "acute": {
        "rows": range(4, 10),
        "path": [[(8.4, 6.6), (6.8, 8.6)]],
        "weight": 0.85,
    },
    "grave": {
        "rows": range(4, 10),
        "path": [[(4.8, 6.6), (6.4, 8.6)]],
        "weight": 0.85,
    },
    "circumflex": {
        "rows": range(4, 11),
        "path": [[(4.7, 9.1), (6.4, 6.9), (8.1, 9.1)]],
        "weight": 0.75,
    },
    "tilde": {
        "rows": range(4, 10),
        # A sampled curve keeps the turns round instead of concentrating ink
        # at the corners of a four-segment zigzag.
        "path": [[
            (6.7 + TILDE_SCALE * (-2.9 + 5.8 * step / 32),
             7.8 + TILDE_SCALE * 0.9 *
             math.cos(3.0 * math.pi * step / 32))
            for step in range(33)
        ]],
        "weight": 0.72 * TILDE_SCALE,
    },
    # Left at full weight: no report against it, and no language whose text
    # has been read in game draws it.
    "diaeresis": {
        "rows": range(5, 10),
        "path": [[(4.9, 7.1), (4.9, 7.9)], [(9.1, 7.1), (9.1, 7.9)]],
    },
    "ring": {
        "rows": range(4, 12),
        "path": [[(7.0 + RING_RADIUS_X * math.cos(2.0 * math.pi * step / 48),
                   7.5 + RING_RADIUS_Y * math.sin(2.0 * math.pi * step / 48))
                  for step in range(49)]],
        "weight": 0.75,
        "profile": RING_PROFILE,
    },
    "cedilla": {
        "rows": range(22, 28),
        "path": [[(7.2, 22.5), (7.9, 23.6), (6.2, 24.8), (5.4, 25.0)]],
        "weight": 0.85,
    },
}

DONOR_SHAPES = {
    "à": "grave", "á": "acute", "â": "circumflex", "ã": "tilde",
    "é": "acute", "ê": "circumflex",
    "ó": "acute", "ô": "circumflex", "õ": "tilde",
    "ú": "acute", "ü": "diaeresis",
    "ç": "cedilla", "å": "ring",
}

FIELDS = ["character", "base", "position", "rows", "donor_bottom",
          "digest", "pixels"]


def mark_rows(grid, allowed):
    """The rows a rendered mark actually inks, on the harvester's floor."""
    return [y for y in allowed
            if sum(1 for value in grid[y] if value) >= gc.MARK_INK_FLOOR]


def trim(grid, rows):
    """Blank every row the mark does not declare."""
    return [list(row) if y in rows else [0] * gc.WIDTH
            for y, row in enumerate(grid)]


def build_rows():
    """Every donor row the composer expects, as CSV-ready dicts."""
    rendered = {name: render(shape["path"], shape["rows"],
                             shape.get("cap", DEFAULT_CAP),
                             shape.get("weight", 1.0),
                             profile=shape.get("profile"))
                for name, shape in SHAPES.items()}
    out = []
    for donor in sorted(DONOR_SHAPES, key=ord):
        name = DONOR_SHAPES[donor]
        grid = rendered[name]
        rows = mark_rows(grid, SHAPES[name]["rows"])
        block = gc.pack(trim(grid, rows))
        out.append({
            "character": donor,
            "base": gc.DONOR_BASE[donor],
            "position": "below" if name == "cedilla" else "above",
            "rows": " ".join(str(y) for y in rows),
            "donor_bottom": str(BASELINE),
            "digest": hashlib.sha1(block).hexdigest(),
            "pixels": base64.b64encode(block).decode("ascii"),
        })
    return out


def _profile(block):
    """``(ink pixels, total ink, distinct levels)`` for one packed mark."""
    values = [v for row in gc.unpack(block) for v in row if v]
    return len(values), sum(values), len(set(values))


def cmd_check(harvested):
    """Print each shape, with the harvested set's numbers beside it."""
    reference = {}
    if harvested and os.path.exists(harvested):
        with io.open(harvested, newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                reference[row["character"]] = base64.b64decode(row["pixels"])
    for row in build_rows():
        block = base64.b64decode(row["pixels"])
        ink, mass, levels = _profile(block)
        line = ("%s  %-11s rows %-14s ink %3d  mass %4d  levels %2d"
                % (row["character"], DONOR_SHAPES[row["character"]],
                   row["rows"], ink, mass, levels))
        if row["character"] in reference:
            other = reference[row["character"]]
            ink2, mass2, levels2 = _profile(other)
            line += ("   | harvested ink %3d  mass %4d  levels %2d%s"
                     % (ink2, mass2, levels2,
                        "  IDENTICAL" if other == block else ""))
        print(line)
    print()
    for name, shape in sorted(SHAPES.items()):
        grid = render(shape["path"], shape["rows"],
                      shape.get("cap", DEFAULT_CAP),
                      shape.get("weight", 1.0),
                      profile=shape.get("profile"))
        grid = trim(grid, mark_rows(grid, shape["rows"]))
        print("--- %s" % name)
        for y in shape["rows"]:
            print("   %2d |%s|"
                  % (y, "".join("%X" % v if v else "." for v in grid[y][:16])))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", action="append", default=[],
                        help="write the table here as well (repeatable)")
    parser.add_argument("--write", action="store_true",
                        help="write the table this build reads")
    parser.add_argument("--check", action="store_true",
                        help="print the shapes and their metrics")
    parser.add_argument(
        "--compare",
        help="another marks table to print alongside in --check")
    args = parser.parse_args(argv)

    targets = list(args.out)
    if args.write:
        targets.insert(0, _resolve_authored_marks_path())
    if args.check or not targets:
        return cmd_check(args.compare)

    rows = build_rows()
    for target in targets:
        with io.open(target, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS,
                                    lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)
        print("wrote %d mark(s) -> %s" % (len(rows), target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
