# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

import csv
import tempfile
import unittest
from pathlib import Path

from tools.scripts.translation_layout import (
    MENU_LAYOUT_FIELDS,
    write_reference_tree,
)


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class TranslationLayoutTests(unittest.TestCase):
    def test_reference_mirrors_dialogue_chapter_and_five_menus(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            reference = root / "reference"
            layout = root / "menu-layout.csv"
            fields = [
                "kind", "resource", "message_id", "message_index",
                "original_en", "original_jp", "translated", "notes",
            ]
            write_csv(original / "scenes" / "resource-1197-scenes.csv", [
                *fields, "speaker", "scene", "scene_line", "details",
            ], [{
                "kind": "scene", "resource": "1197", "message_id": "1",
                "message_index": "", "original_en": "English dialogue",
                "original_jp": "Japanese dialogue", "translated": "",
                "notes": "", "speaker": "Alicia", "scene": "1",
                "scene_line": "1", "details": "",
            }])
            write_csv(original / "containers" / "container-0010.csv", fields, [{
                "kind": "container", "resource": "10", "message_id": "100",
                "message_index": "", "original_en": "Skip?",
                "original_jp": "", "translated": "", "notes": "",
            }])
            write_csv(original / "containers" / "container-0641.csv", fields, [{
                "kind": "container", "resource": "641", "message_id": "8",
                "message_index": "", "original_en": "Long menu\nlabel",
                "original_jp": "", "translated": "", "notes": "",
            }])
            write_csv(original / "containers" / "container-0642.csv", fields, [{
                "kind": "container", "resource": "642", "message_id": "9",
                "message_index": "", "original_en": "Long menu label",
                "original_jp": "", "translated": "", "notes": "",
            }])
            write_csv(original / "chapters.csv", [
                *fields, "chapter",
            ], [{
                "kind": "chapter", "resource": "1197", "message_id": "2739",
                "message_index": "", "original_en": "Chapter title",
                "original_jp": "", "translated": "", "notes": "",
                "chapter": "1",
            }])
            write_csv(layout, MENU_LAYOUT_FIELDS, [
                {"menu": "1", "unit": "1", "resource": "641",
                 "message_id": "8", "message_index": ""},
                {"menu": "1", "unit": "1", "resource": "642",
                 "message_id": "9", "message_index": ""},
            ])
            details = write_reference_tree(original, layout, reference)
            self.assertEqual(1, details["menu_rows"])
            self.assertTrue((reference / "chapter.csv").is_file())
            self.assertTrue(
                (reference / "dialogue" / "scene-1197.csv").is_file())
            self.assertTrue(
                (reference / "dialogue" / "container-0010.csv").is_file())
            for menu in range(1, 6):
                self.assertTrue(
                    (reference / "menu" / f"menu-{menu}.csv").is_file())
            for path in (
                reference / "chapter.csv",
                reference / "dialogue" / "scene-1197.csv",
                reference / "dialogue" / "container-0010.csv",
                reference / "menu" / "menu-1.csv",
            ):
                with path.open("r", encoding="utf-8", newline="") as source:
                    header = next(csv.reader(source))
                self.assertEqual(
                    ["resource", "message_id", "original_en", "original_jp"],
                    header[:4],
                )


if __name__ == "__main__":
    unittest.main()
