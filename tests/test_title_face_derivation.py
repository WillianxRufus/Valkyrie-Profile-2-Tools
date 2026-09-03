# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Letters the chapter-title face has to derive, because no disc cut them."""
import unittest

from tools.scripts import vp2_glyph_compose as gc
from tools.scripts import vp2_title_face as tf

WIDTH, HEIGHT = gc.WIDTH, gc.HEIGHT


def block(rows):
    """Pack a {row: "hex digits"} sketch into a glyph block."""
    grid = [[0] * WIDTH for _ in range(HEIGHT)]
    for y, line in rows.items():
        for x, digit in enumerate(line):
            if digit != ".":
                grid[y][x] = int(digit, 16)
    return gc.pack(grid)


def wedge():
    """A V: two arms converging on the baseline, with a foot."""
    rows = {}
    for step, y in enumerate(range(5, 22)):
        left = step // 2
        right = 15 - step // 2
        rows[y] = "".join("F" if x in (left, right) else "."
                          for x in range(WIDTH))
    rows[22] = "." * 7 + "FF" + "." * (WIDTH - 9)
    rows[23] = "." * 7 + "FF" + "." * (WIDTH - 9)
    return block(rows)


def column():
    """An I: a stem down to the baseline, with a foot."""
    rows = {y: "." * 3 + "FF" + "." * (WIDTH - 5) for y in range(5, 22)}
    rows[22] = "." * 2 + "FFFF" + "." * (WIDTH - 6)
    rows[23] = "." * 2 + "FFFF" + "." * (WIDTH - 6)
    return block(rows)


class DerivedYTests(unittest.TestCase):
    """`y` is in no chapter title on any disc, so the face has to build one."""

    def setUp(self):
        self.art = {"v": (wedge(), bytes([16, 10])),
                    "i": (column(), bytes([8, 10]))}

    def derived(self):
        got = tf.compose_procedural("y", self.art)
        self.assertIsNotNone(got, "the face could not derive a y")
        return gc.unpack(bytes(got[0])), got[1], got[2]

    def test_it_is_derived_from_the_faces_own_v_and_i(self):
        _grid, _metric, source = self.derived()
        self.assertEqual("procedural v over i", source)

    def test_the_arms_stop_at_the_junction_and_a_stem_carries_on(self):
        grid, _metric, _source = self.derived()
        above = [y for y in range(tf.Y_JUNCTION_ROW) if any(grid[y])]
        self.assertTrue(above, "the arms are missing")
        widths = {}
        for y in range(tf.Y_JUNCTION_ROW, HEIGHT):
            inked = [x for x in range(WIDTH) if grid[y][x]]
            if inked:
                widths[y] = max(inked) - min(inked) + 1
        self.assertTrue(widths, "the stem is missing")
        # Below the junction the glyph is a stem, never the open arms again.
        self.assertLessEqual(max(widths.values()), 6)
        self.assertIn(HEIGHT - 5, widths, "the stem does not reach the foot")

    def test_the_arms_are_wider_than_the_stem(self):
        grid, _metric, _source = self.derived()
        top = next(y for y in range(HEIGHT) if any(grid[y]))
        spread = [x for x in range(WIDTH) if grid[top][x]]
        self.assertGreater(max(spread) - min(spread) + 1, 6)

    def test_it_takes_the_vs_width_because_that_is_what_it_occupies(self):
        _grid, metric, _source = self.derived()
        self.assertEqual(self.art["v"][1], metric)

    def test_a_face_without_a_v_or_an_i_derives_nothing(self):
        for drop in ("v", "i"):
            with self.subTest(missing=drop):
                art = {k: v for k, v in self.art.items() if k != drop}
                self.assertIsNone(tf.compose_procedural("y", art))

    def test_the_junction_has_to_sit_inside_the_arms(self):
        """A letterform shorter than the junction cannot be split at it."""
        short = {y: "." * 5 + "FF" + "." * (WIDTH - 7) for y in range(2, 6)}
        art = dict(self.art, v=(block(short), bytes([16, 10])))
        self.assertIsNone(tf.compose_procedural("y", art))


if __name__ == "__main__":
    unittest.main()
