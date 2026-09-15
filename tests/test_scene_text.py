# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

import unittest

from tools.scripts import vp2_cutscene_subtitles as subtitles


class CleanTextTests(unittest.TestCase):
    def test_literal_angle_bracket_text_survives(self):
        self.assertEqual(
            subtitles.clean_text("<Making Valued Customer Items>"),
            "<Making Valued Customer Items>",
        )

    def test_structural_tags_are_still_removed(self):
        self.assertEqual(
            subtitles.clean_text("<8082>hello<0011><?><END>"),
            "hello",
        )


class SharedHeadingTests(unittest.TestCase):
    """A heading keeps its < > frame, so a translation spells it."""

    META = {"glyph_base": 0x0100, "glyph_count": 4}
    ALPHABET = {0: "<", 1: ">", 2: "a", 3: " "}
    SOURCE = [0x280, 0x282, 0x281]

    def test_a_framed_translation_is_encoded(self):
        from tools.scripts import scene_text
        self.assertTrue(scene_text.encode_shared_header(
            "<ab>", self.SOURCE, self.META, self.ALPHABET))

    def test_a_translation_without_the_frame_is_refused(self):
        from tools.scripts import scene_text
        with self.assertRaisesRegex(ValueError, "<ab>"):
            scene_text.encode_shared_header(
                "ab", self.SOURCE, self.META, self.ALPHABET)


class PageBreakCountTests(unittest.TestCase):
    """Read-back counts page breaks run by run, as the writer lays them out."""

    def test_a_break_opening_a_run(self):
        from tools.scripts import scene_verify
        self.assertEqual(scene_verify.page_breaks("magos! <PART> ---"), 1)

    def test_a_break_on_its_own_line(self):
        from tools.scripts import scene_verify
        self.assertEqual(scene_verify.page_breaks("magos!\n---\nfim"), 1)

    def test_dashes_inside_a_line_are_text(self):
        from tools.scripts import scene_verify
        self.assertEqual(scene_verify.page_breaks("a --- b"), 0)


if __name__ == "__main__":
    unittest.main()
