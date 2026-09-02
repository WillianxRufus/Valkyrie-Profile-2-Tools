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


if __name__ == "__main__":
    unittest.main()
