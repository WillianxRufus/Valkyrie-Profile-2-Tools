"""Tests for the per-resource check in ``test.py``."""

import importlib.util
import io
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "vp2_resource_check", ROOT / "test.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def _write(path, header, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(",".join(row) + "\n")


class RowLookupTests(unittest.TestCase):
    """A build patches the compiled manifest row, not the profile row."""

    def setUp(self):
        import tempfile
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(
            lambda: [os.remove(p) for p in self.directory.iterdir()]
            and os.rmdir(self.directory))
        self.profile = self.directory / "build-profile.csv"
        self.manifest = self.directory / "manifest.csv"
        _write(self.profile, ("kind", "resource", "sheet", "flags", "verify"),
               [("scene", "1000", "resource-1000-scenes.csv", "full-font",
                 "yes")])
        _write(self.manifest,
               ("kind", "resource", "sheet", "flags", "verify",
                "chapter_title", "chapter_title_message"),
               [("scene", "1000", "resource-1000-scenes.csv", "full-font",
                 "yes", "A Title", "9001")])

    def test_reads_a_row_by_resource(self):
        row = check._row_for(self.profile, 1000)
        self.assertEqual(row["kind"], "scene")

    def test_missing_resource_is_none(self):
        self.assertIsNone(check._row_for(self.profile, 999))

    def test_manifest_carries_fields_the_profile_does_not(self):
        # The reason a check has to patch the manifest row: patching the
        # profile row leaves out what compiling worked out, and measures
        # something no build ever builds.
        profile = check._row_for(self.profile, 1000)
        manifest = check._row_for(self.manifest, 1000)
        self.assertNotIn("chapter_title", profile)
        self.assertEqual(manifest["chapter_title"], "A Title")


class HeadroomTests(unittest.TestCase):
    """What is reported as room left, and when it is a floor."""

    def test_repacked_scene_reports_its_own_slack(self):
        room, exact = check._headroom(b"", {"spare": 48, "recompressed": b"x"})
        self.assertEqual((room, exact), (48, True))

    def test_text_inside_its_original_space_reports_a_floor(self):
        room, exact = check._headroom(
            b"", {"spare": None, "recompressed": b"x" * 100,
                  "dcms_length": 260})
        self.assertEqual((room, exact), (160, False))

    def test_nothing_to_measure_reports_nothing(self):
        self.assertEqual(check._headroom(b"", {}), (None, False))


class ProfileRowTests(unittest.TestCase):
    """What the disc holds has to match what the row claims."""

    def test_accepts_a_matching_row(self):
        row = {"kind": "container", "flags": "shared-font-glyphs"}
        self.assertEqual(
            check.check_profile_row(row, "container_slz", 10, say=lambda _: None),
            [])

    def test_reports_the_wrong_kind(self):
        row = {"kind": "scene", "flags": ""}
        problems = check.check_profile_row(
            row, "container_slz", 10, say=lambda _: None)
        self.assertTrue(any("container" in problem for problem in problems))

    def test_reports_a_flag_a_kind_does_not_take(self):
        row = {"kind": "container", "flags": ""}
        problems = check.check_profile_row(
            row, "container_slz", 10, say=lambda _: None)
        self.assertTrue(
            any("shared-font-glyphs" in problem for problem in problems))

    def test_a_resource_with_no_row_is_reported(self):
        problems = check.check_profile_row(
            None, "fontless_dcms_compatible", 29, say=lambda _: None)
        self.assertEqual(problems, ["absent from the build profile"])


class AccentTests(unittest.TestCase):
    """Choosing the letter whose cost is worth measuring."""

    def _rendered(self, *texts):
        return [("id", 1, text) for text in texts]

    def test_picks_the_least_used_accent(self):
        found = check._least_used_accent(
            self._rendered("areá época", "maãe caça"))
        self.assertIsNotNone(found)

    def test_prefers_the_rarer_letter(self):
        character, base, used = check._least_used_accent(
            self._rendered("é é é ú e u"))
        self.assertEqual((character, base, used), ("ú", "u", 1))

    def test_needs_the_plain_letter_to_already_be_there(self):
        # Writing it plainly has to take a glyph out, not swap one in.
        self.assertIsNone(check._least_used_accent(self._rendered("ç")))

    def test_text_with_no_accents_has_nothing_to_measure(self):
        self.assertIsNone(check._least_used_accent(self._rendered("plain")))

    def test_writes_a_sheet_with_the_letter_written_plainly(self):
        import csv
        import tempfile
        directory = Path(tempfile.mkdtemp())
        sheet = directory / "resource-1000-scenes.csv"
        _write(sheet, ("message_id", "original_en", "translated"),
               [("1", "hope", "esperança"), ("2", "none", "")])
        into = directory / "plain"
        into.mkdir()
        target = check._sheet_without("ç", "c", sheet, into)
        rows = list(csv.DictReader(io.open(target, encoding="utf-8-sig",
                                           newline="")))
        self.assertEqual(rows[0]["translated"], "esperanca")
        self.assertEqual(rows[1]["translated"], "")

    def test_the_copy_keeps_the_name(self):
        import tempfile
        directory = Path(tempfile.mkdtemp())
        sheet = directory / "resource-1000-scenes.csv"
        _write(sheet, ("message_id", "translated"), [("1", "aço")])
        into = directory / "plain"
        into.mkdir()
        # Which records a sheet holds is read from its name.
        self.assertEqual(
            check._sheet_without("ç", "c", sheet, into).name, sheet.name)


if __name__ == "__main__":
    unittest.main()
