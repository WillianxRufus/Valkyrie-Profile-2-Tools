"""A weapon location's reference sheet lists only the lines that can appear there."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.scripts import einherjar_roster, translation_layout  # noqa: E402


NAMES = ("Lwyn", "Jessica", "Arcana", "Sophalla")
FIELDS = ("kind", "scene", "scene_line", "resource", "message_id",
          "message_index", "script_offset", "voice_scene", "voice_slot",
          "audio_id", "speaker", "original_en", "original_jp", "translated",
          "details", "notes")


def _records():
    rows = []

    def add(message_id, english, speaker=""):
        row = {field: "" for field in FIELDS}
        row.update(kind="scene", resource="7", message_id=str(message_id),
                   speaker=speaker, original_en=english)
        rows.append(row)

    for offset, name in enumerate(NAMES):
        add(96 + offset, "I will fight.", speaker=name)
    for number, english in enumerate((
            "A light warrior's soul emanates from the sword.",
            "A heavy warrior's soul emanates from the sword.",
            "An archer's soul emanates from the bow.",
            "A sorcerer's soul emanates from the staff.",
            "Perform materialization?", "Yes", "No",
            "Materialization is impossible without Silmeria...",
            "An Area Name"), start=100):
        add(number, english)
    for offset, name in enumerate(NAMES):
        add(200 + offset, f"{name} <PART> has joined the party.")
        add(300 + offset, name)
    return rows


class ReferenceSheetTests(unittest.TestCase):

    def test_lines_that_cannot_appear_at_a_weapon_location_are_left_out(self):
        table = {"weapon": {"7": {"Arcana", "Sophalla"}},
                 "weapon_type": {"7": "Archer"},
                 "fallback": {"Jessica"},
                 "release": {"8": {"Lwyn"}}}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "resource-0007-scenes.csv"
            target = Path(directory) / "scene-0007.csv"
            with open(source, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(_records())
            count = translation_layout._copy_reference_rows(
                source, target, translation_layout.SCENE_REFERENCE_FIELDS,
                lambda rows: einherjar_roster.hidden_message_ids(rows, table))
            with open(target, encoding="utf-8", newline="") as handle:
                listed = [row["message_id"] for row in csv.DictReader(handle)]
        self.assertEqual(count, len(listed))
        self.assertEqual(sorted(listed, key=int), [
            "97", "98", "99",                  # Jessica, Arcana, Sophalla
            "102",                             # the bow
            "104", "105", "106", "107",        # prompt, Yes, No, refusal
            "108",                             # the area name
            "201", "202", "203",               # joined the party
            "301", "302", "303",               # Jessica, Arcana, Sophalla
        ])


if __name__ == "__main__":
    unittest.main()
