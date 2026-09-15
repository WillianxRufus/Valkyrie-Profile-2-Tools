# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.cheat_patcher import battle_overlay, slz3
from tools.scripts import overlay_edits
from tools.scripts.overlay_edits import Edit, word


def make_output(size=0x200, **words):
    output = bytearray(size)
    struct.pack_into("<I", output, 8, overlay_edits.LOAD_ADDRESS)
    for offset, value in words.items():
        struct.pack_into("<I", output, int(offset, 16), value)
    return bytes(output)


def make_resource(output):
    stream = slz3.compress(bytes(output))
    start = 8 + 2 * 8
    item_end = (start + len(stream) + 0x3F) & ~0x3F
    resource = bytearray(item_end + 0x200)
    struct.pack_into("<4sHH", resource, 0, b"p@Ck", 1, 1)
    struct.pack_into("<II", resource, 8, start, 0x6800)
    struct.pack_into("<II", resource, 16, item_end, 0)
    resource[start:start + len(stream)] = stream
    for index, value in enumerate(battle_overlay.HEADER_XOR):
        resource[index] ^= value
    return bytes(resource)


class EditOutputTests(unittest.TestCase):
    def setUp(self):
        self.output = make_output(**{"0x40": 0x11111111, "0x80": 0x22222222})
        self.edits = [
            Edit(0x40, word(0x11111111), word(0x33333333), "first"),
            Edit(0x80, word(0x22222222), word(0x22222222), "guard"),
        ]

    def test_an_edit_replaces_only_its_own_bytes(self):
        patched, changed = overlay_edits.edit_output(self.output, self.edits)
        expected = bytearray(self.output)
        struct.pack_into("<I", expected, 0x40, 0x33333333)
        self.assertEqual(bytes(expected), patched)
        self.assertEqual(4, changed)

    def test_applying_the_same_edits_twice_changes_nothing(self):
        patched, _ = overlay_edits.edit_output(self.output, self.edits)
        again, changed = overlay_edits.edit_output(patched, self.edits)
        self.assertEqual(patched, again)
        self.assertEqual(0, changed)

    def test_bytes_that_are_neither_original_nor_replacement_are_refused(self):
        other = make_output(**{"0x40": 0x44444444, "0x80": 0x22222222})
        with self.assertRaisesRegex(ValueError, "first: expected"):
            overlay_edits.edit_output(other, self.edits)

    def test_two_edits_that_disagree_about_a_byte_are_refused(self):
        clash = Edit(0x42, word(0x00001111)[:2], b"\x99\x99", "second")
        with self.assertRaisesRegex(ValueError, "first and second"):
            overlay_edits.edit_output(self.output, self.edits + [clash])

    def test_an_edit_outside_the_overlay_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            overlay_edits.edit_output(self.output, [
                Edit(0x1FE, word(0), word(1), "late")])

    def test_a_different_load_address_is_refused(self):
        output = bytearray(self.output)
        struct.pack_into("<I", output, 8, 0x00100000)
        with self.assertRaisesRegex(ValueError, "loads at"):
            overlay_edits.edit_output(bytes(output), self.edits)


class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = make_output(**{"0x40": 0x11111111, "0x80": 0x22222222})
        cls.resource = make_resource(cls.output)

    def test_every_edit_lands_in_one_recompression(self):
        edits = [Edit(0x40, word(0x11111111), word(0x33333333), "first"),
                 Edit(0x80, word(0x22222222), word(0x44444444), "second")]
        with mock.patch.object(battle_overlay, "replace",
                               wraps=battle_overlay.replace) as replace:
            result = overlay_edits.apply(self.resource, edits)
        self.assertEqual(1, replace.call_count)
        read = battle_overlay.read(result.data).output
        self.assertEqual(0x33333333, struct.unpack_from("<I", read, 0x40)[0])
        self.assertEqual(0x44444444, struct.unpack_from("<I", read, 0x80)[0])
        self.assertEqual(len(self.resource), len(result.data))
        self.assertEqual(8, result.changed)
        overlay = battle_overlay.read(result.data)
        self.assertEqual(
            overlay.item_span - battle_overlay.SLZ_HEADER_SIZE
            - overlay.stored_size, result.room)

    def test_edits_that_change_nothing_do_not_recompress(self):
        edits = [Edit(0x80, word(0x22222222), word(0x22222222), "guard")]
        with mock.patch.object(battle_overlay, "replace") as replace:
            result = overlay_edits.apply(self.resource, edits)
        replace.assert_not_called()
        self.assertEqual(self.resource, result.data)
        self.assertEqual(0, result.changed)


if __name__ == "__main__":
    unittest.main()
