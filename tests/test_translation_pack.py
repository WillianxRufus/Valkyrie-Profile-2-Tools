# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

import csv
import tempfile
import unittest
from pathlib import Path

from tools.scripts.translation_pack import (
    LEGACY_PACK_FIELDS,
    PACK_FIELDS,
    PackError,
    load_pack,
    source_hash,
)
from tools.scripts.translation_layout import MENU_LAYOUT_FIELDS


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        return list(reader.fieldnames or ()), list(reader)


def write_manifest(path, format_number=2):
    path.mkdir(parents=True, exist_ok=True)
    (path / "pack.toml").write_text(
        f'format = {format_number}\nlocale = "x-test"\nname = "Test"\n',
        encoding="utf-8")


class TranslationPackTests(unittest.TestCase):
    def test_structured_pack_is_minimal_and_blank_rows_are_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            write_manifest(pack)
            write_csv(pack / "dialogue" / "scene-0089.csv", PACK_FIELDS, [
                {"resource": "89", "message_id": "12",
                 "translated": "Target", "notes": "Authored note"},
                {"resource": "89", "message_id": "14",
                 "translated": "", "notes": ""},
            ])
            rows = load_pack(pack)
            self.assertEqual({("scene", "89", "12", "")}, set(rows))

    def test_pack_rejects_source_columns(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            write_manifest(pack)
            write_csv(pack / "chapter.csv", [*PACK_FIELDS, "original_en"], [{
                "resource": "1", "message_id": "2", "translated": "Target",
                "notes": "", "original_en": "Source",
            }])
            with self.assertRaisesRegex(PackError, "forbidden source"):
                load_pack(pack)

    def test_dialogue_filename_must_match_resource(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            write_manifest(pack)
            write_csv(pack / "dialogue" / "scene-0089.csv", PACK_FIELDS, [{
                "resource": "90", "message_id": "12",
                "translated": "Target", "notes": "",
            }])
            with self.assertRaisesRegex(PackError, "does not match"):
                load_pack(pack)

if __name__ == "__main__":
    unittest.main()
