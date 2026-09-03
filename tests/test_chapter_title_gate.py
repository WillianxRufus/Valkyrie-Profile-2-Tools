"""The build hands a row's chapter title to the read-back gate."""
import argparse
import csv
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.scripts import build_patchers
from tools.scripts import scene_verify
from tools.scripts import vp2_title_face as tf


class GateTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".iso", delete=False)
        handle.write(b"\0" * 16)
        handle.close()
        self.iso = handle.name
        self.addCleanup(os.unlink, self.iso)

    def args(self, title, reference=None):
        return argparse.Namespace(
            iso=self.iso, reference_iso=reference,
            chapter_title=title, chapter_title_message=1349)

    def run_gate(self, title, decoded, reference=None):
        with mock.patch.object(scene_verify.triace, "load_table",
                               return_value=(None, 0, {})), \
             mock.patch("tools.scripts.vp2_title_face.decode_title",
                        return_value=decoded) as decode:
            checked = scene_verify.verify_chapter_title(
                self.args(title, reference), 1313)
        return checked, decode

    def test_a_row_without_a_title_is_not_checked(self):
        self.assertFalse(scene_verify.verify_chapter_title(
            self.args(None), 1313))
        self.assertFalse(scene_verify.verify_chapter_title(
            self.args("   "), 1313))

    def test_a_matching_title_passes(self):
        checked, _ = self.run_gate("A Arvore do Mundo Retorcida",
                                   "A Arvore do Mundo Retorcida")
        self.assertTrue(checked)

    def test_case_differences_pass_because_the_face_is_unicase(self):
        checked, _ = self.run_gate("A Arvore do Mundo Retorcida",
                                   "a arvore do MUndo retorcida")
        self.assertTrue(checked)

    def test_a_different_title_fails(self):
        with self.assertRaises(ValueError) as caught:
            self.run_gate("Motivos Ocultos", "Motivos Ocultas")
        self.assertIn("Motivos Ocultas", str(caught.exception))

    def test_a_glyph_the_decoder_cannot_name_fails(self):
        with self.assertRaises(ValueError):
            self.run_gate("Motivos Ocultos", "Motivos O?ultos")

    def test_a_reference_image_names_the_face_when_there_is_one(self):
        _, decode = self.run_gate("Ira dos Deuses", "ira dos Deuses",
                                  reference=self.iso)
        self.assertIsNotNone(decode.call_args.kwargs["donor_iso"])

    def test_without_a_reference_the_decoder_falls_back(self):
        _, decode = self.run_gate("Ira dos Deuses", "ira dos Deuses")
        self.assertIsNone(decode.call_args.kwargs["donor_iso"])


class InMemoryBuildTests(unittest.TestCase):
    ROW = {"kind": "scene", "verify": "yes", "resource": "1313",
           "sheet": "scenes/resource-1313-scenes.csv"}

    def captured(self, row):
        with mock.patch("tools.scripts.vp2_cutscene_subtitles."
                        "verify_scene_sheet") as gate:
            build_patchers.verify_scene_in_memory("out.iso", row, "ref.iso")
        return gate.call_args.args[0] if gate.call_args else None

    def test_a_chapter_row_carries_its_title_into_the_gate(self):
        row = dict(self.ROW, chapter_title="A Arvore do Mundo Retorcida",
                   chapter_title_message="1349")
        args = self.captured(row)
        self.assertEqual(args.chapter_title, "A Arvore do Mundo Retorcida")
        self.assertEqual(args.chapter_title_message, "1349")

    def test_an_ordinary_scene_row_passes_no_title(self):
        args = self.captured(dict(self.ROW))
        self.assertIsNone(args.chapter_title)
        self.assertIsNone(args.chapter_title_message)

    def test_a_blank_title_column_is_not_a_title(self):
        args = self.captured(dict(self.ROW, chapter_title="",
                                  chapter_title_message=""))
        self.assertIsNone(args.chapter_title)


class ChapterRecordTests(unittest.TestCase):
    """A chapter title is not subtitle text, on any path that reads a sheet."""

    def sheet(self, resource, message_id):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix="-scenes.csv", delete=False, newline="",
            encoding="utf-8")
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(["resource", "message_id", "audio_id",
                         "original_en", "translated"])
        writer.writerow([resource, message_id,
                         "r%04d-m%04d" % (resource, message_id),
                         "Darkness in Dipan", "Escuridao"])
        writer.writerow([resource, 99, "r%04d-m0099" % resource,
                         "Dipan", "Dipan"])
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_a_title_record_is_not_returned_as_a_scene_row(self):
        from tools.scripts.scene_text import read_scene_rows
        from tools.scripts.vp2_title_face import CHAPTER_RECORDS
        resource, message_id = sorted(CHAPTER_RECORDS)[0]
        rows = read_scene_rows(self.sheet(resource, message_id), resource)
        self.assertEqual([row["message_id"] for row in rows], ["99"])

    def test_an_ordinary_record_still_is(self):
        from tools.scripts.scene_text import read_scene_rows
        from tools.scripts.vp2_title_face import CHAPTER_RECORDS
        resource, message_id = sorted(CHAPTER_RECORDS)[0]
        taken = {mid for res, mid in CHAPTER_RECORDS if res == resource}
        spare = next(n for n in range(1, 500) if n not in taken and n != 99)
        rows = read_scene_rows(self.sheet(resource, spare), resource)
        self.assertEqual(sorted(row["message_id"] for row in rows),
                         sorted([str(spare), "99"]))


class PlaceTitleTests(unittest.TestCase):
    """Where a deferred title glyph lands, and whether the font grows."""

    GLYPH_BYTES = 448

    def font(self, glyph_count=8):
        import struct
        text_end = 384
        font_start = text_end + 64 * 2
        font_end = font_start + glyph_count * self.GLYPH_BYTES
        expanded = bytearray(font_end)
        for slot in range(glyph_count):
            start = font_start + slot * self.GLYPH_BYTES
            expanded[start:start + self.GLYPH_BYTES] = (
                bytes([slot + 1]) * self.GLYPH_BYTES)
        struct.pack_into("<I", expanded, 0x20, len(expanded))
        struct.pack_into("<I", expanded, 0x2C, text_end)
        struct.pack_into("<I", expanded, 0x30, font_start)
        struct.pack_into("<I", expanded, 0x34, glyph_count)
        return expanded, {"text_end": text_end, "font_start": font_start,
                          "font_end": font_end, "glyph_count": glyph_count,
                          "glyph_bytes": self.GLYPH_BYTES}

    def pending(self, *characters):
        return [(character, bytes([0xA0 + n]) * self.GLYPH_BYTES,
                 bytes([n, n]), "harvested", character)
                for n, character in enumerate(characters)]

    def test_a_freed_slot_is_taken_before_the_font_grows(self):
        expanded, layout = self.font()
        size = len(expanded)
        assignment, installed, appended = tf.place_title(
            expanded, layout, self.pending("á"), [5])
        self.assertEqual(assignment, {"á": 5})
        self.assertEqual(appended, [])
        self.assertEqual(len(expanded), size, "the font must not grow")
        start = layout["font_start"] + 5 * self.GLYPH_BYTES
        self.assertEqual(bytes(expanded[start:start + self.GLYPH_BYTES]),
                         installed[0] and self.pending("á")[0][1])

    def test_the_cheapest_slot_wins_when_one_can_be_measured(self):
        expanded, layout = self.font()

        def measure(data):
            start = layout["font_start"] + 6 * self.GLYPH_BYTES
            return 10 if data[start] == 0xA0 else 99

        assignment, _installed, appended = tf.place_title(
            expanded, layout, self.pending("á"), [2, 6, 7], measure=measure)
        self.assertEqual(assignment, {"á": 6})
        self.assertEqual(appended, [])

    def test_the_first_free_slot_is_taken_when_nothing_measures(self):
        expanded, layout = self.font()
        assignment, _installed, _appended = tf.place_title(
            expanded, layout, self.pending("á"), [3, 6])
        self.assertEqual(assignment, {"á": 3})

    def test_with_no_free_slot_the_font_grows(self):
        expanded, layout = self.font()
        size = len(expanded)
        assignment, _installed, appended = tf.place_title(
            expanded, layout, self.pending("á"), [])
        self.assertEqual(appended, [8])
        self.assertEqual(assignment, {"á": 8})
        self.assertEqual(len(expanded), size + self.GLYPH_BYTES)

    def test_free_slots_are_spent_before_anything_is_appended(self):
        expanded, layout = self.font()
        assignment, _installed, appended = tf.place_title(
            expanded, layout, self.pending("á", "ç", "ê"), [4])
        self.assertEqual(assignment, {"á": 4, "ç": 8, "ê": 9})
        self.assertEqual(appended, [8, 9])

    def test_a_case_pair_is_keyed_by_one_slot(self):
        expanded, layout = self.font()
        assignment, _installed, _appended = tf.place_title(
            expanded, layout, self.pending("Á"), [5])
        self.assertEqual(assignment, {"á": 5},
                         "the face is unicase, so the slot is keyed folded")

    def test_the_record_names_the_slots_the_letters_landed_in(self):
        tokens = tf.title_tokens("Áá", {"á": 5}, 0x65)
        self.assertEqual(tokens, tf.title_tokens("áÁ", {"á": 5}, 0x65))


class TitleOnlyResourceTests(unittest.TestCase):
    """A resource may carry a chapter title and no translated dialogue."""

    def row(self, sheet, title="Mörker i Dipan"):
        return {"kind": "scene", "resource": "61", "sheet": sheet,
                "flags": "", "verify": "yes", "chapter_title": title,
                "chapter_title_message": "26"}

    def empty_sheet(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix="-scenes.csv", newline="", encoding="utf-8",
            delete=False)
        writer = csv.writer(handle)
        writer.writerow(["resource", "message_id", "key", "original_en",
                         "translated"])
        writer.writerow(["61", "99", "r0061-m0099", "Dipan", ""])
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_the_patcher_does_not_skip_a_resource_that_has_only_a_title(self):
        sheet = self.empty_sheet()
        with mock.patch.object(build_patchers, "_scene_args_from_row") as args,              mock.patch("tools.scripts.vp2_cutscene_subtitles."
                        "patch_resource_in_memory",
                        return_value={"patched": b"", "written": 1}) as patch:
            details = build_patchers.patch_scene_resource_in_memory(
                mock.Mock(), self.row(sheet))
        self.assertTrue(patch.called, "the chapter title was never patched")
        self.assertIn("patched", details)
        self.assertTrue(args.called)

    def test_a_sheet_with_neither_rows_nor_a_title_is_still_skipped(self):
        sheet = self.empty_sheet()
        with mock.patch("tools.scripts.vp2_cutscene_subtitles."
                        "patch_resource_in_memory") as patch:
            details = build_patchers.patch_scene_resource_in_memory(
                mock.Mock(), self.row(sheet, title=""))
        self.assertFalse(patch.called)
        self.assertEqual(0, details["written"])

    def test_verify_runs_the_title_gate_when_there_are_no_rows(self):
        args = argparse.Namespace(
            csv=self.empty_sheet(), resource=61, iso="disc.iso",
            reference_iso=None, en_names=None, primary_lookup=None,
            chapter_title="Mörker i Dipan", chapter_title_message="26")
        with mock.patch.object(scene_verify, "verify_chapter_title",
                               return_value=True) as gate:
            scene_verify.verify_scene_sheet(args)
        gate.assert_called_once_with(args, 61)

    def test_verify_still_refuses_a_sheet_with_nothing_in_it(self):
        args = argparse.Namespace(
            csv=self.empty_sheet(), resource=61, iso="disc.iso",
            reference_iso=None, en_names=None, primary_lookup=None,
            chapter_title=None, chapter_title_message=None)
        with self.assertRaises(ValueError):
            scene_verify.verify_scene_sheet(args)



if __name__ == "__main__":
    unittest.main()
