# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
import struct
import unittest

from tools.cheat_patcher import slz, slz3
from tools.cheat_patcher.cheats.battle_anti_freeze import (
    ORIGINAL_INSTRUCTION,
    OVERLAY_LOAD_ADDRESS,
    PACKAGE_HEADER_XOR,
    PATCHED_INSTRUCTION,
    TARGET_OFFSET,
    patch_resource,
)


def make_resource(instruction=ORIGINAL_INSTRUCTION):
    overlay = bytearray(TARGET_OFFSET + 0x100)
    struct.pack_into("<I", overlay, 8, OVERLAY_LOAD_ADDRESS)
    struct.pack_into("<I", overlay, TARGET_OFFSET, instruction)
    stream = slz3.compress(bytes(overlay))

    count = 2
    first = 8 + (count + 1) * 8
    second = (first + len(stream) + 0x3F) & ~0x3F
    marker = b"NEXT-PACKAGE-ITEM" + b"\xA5" * 64
    end = (second + len(marker) + 0x3F) & ~0x3F
    resource = bytearray(end + 0x200)
    struct.pack_into("<4sHH", resource, 0, b"p@Ck", 1, count)
    struct.pack_into("<II", resource, 8, first, 0x6800)
    struct.pack_into("<II", resource, 16, second, 0x6A00)
    struct.pack_into("<II", resource, 24, end, 0)
    resource[first:first + len(stream)] = stream
    resource[second:second + len(marker)] = marker
    for index, value in enumerate(PACKAGE_HEADER_XOR):
        resource[index] ^= value
    return bytes(resource), marker, second


def expanded_first_item(resource):
    header = bytearray(resource)
    for index, value in enumerate(PACKAGE_HEADER_XOR):
        header[index] ^= value
    start = struct.unpack_from("<I", header, 8)[0]
    end = struct.unpack_from("<I", header, 16)[0]
    return slz.decompress(resource[start:end])


class BattleAntiFreezeResourceTests(unittest.TestCase):
    def test_changes_only_the_battle_instruction(self):
        original, marker, second = make_resource()
        patch = patch_resource(original)
        old_output = expanded_first_item(original)
        new_output = expanded_first_item(patch.data)
        expected = bytearray(old_output)
        struct.pack_into("<I", expected, TARGET_OFFSET, PATCHED_INSTRUCTION)
        self.assertEqual(bytes(expected), new_output)
        self.assertEqual(marker, patch.data[second:second + len(marker)])
        self.assertEqual(len(original), len(patch.data))

    def test_rejects_an_already_patched_overlay(self):
        resource, _, _ = make_resource(PATCHED_INSTRUCTION)
        with self.assertRaisesRegex(ValueError, "already patched"):
            patch_resource(resource)

    def test_rejects_a_different_instruction_with_the_same_low_half(self):
        resource, _, _ = make_resource(0xDEAD1FFE)
        with self.assertRaisesRegex(ValueError, "expected 0x00031FFE"):
            patch_resource(resource)


if __name__ == "__main__":
    unittest.main()


class ProtectedPackageTests(unittest.TestCase):
    def _clear_entry(self):
        """A minimal clear p@Ck holding one mode-3 SLZ item."""
        from tools.cheat_patcher import battle_overlay, slz3
        payload = slz3.compress(b"\x00" * 0x40)
        table_end = 8 + 2 * 8
        start = table_end
        item_end = start + len(payload) + 0x10
        header = bytearray(b"p@Ck\x00\x00")
        header += struct.pack("<H", 1)
        header += struct.pack("<II", start, 0x6800)
        header += struct.pack("<II", item_end, 0)
        entry = bytearray(header)
        entry += b"\x00" * (item_end - len(entry))
        entry[start:start + len(payload)] = payload
        for index, value in enumerate(battle_overlay.HEADER_XOR):
            entry[index] ^= value
        return bytes(entry)

    def test_a_clear_package_is_still_read_directly(self):
        from tools.cheat_patcher import battle_overlay
        layout = battle_overlay.package_layout(self._clear_entry())
        self.assertEqual(2, len(layout.offsets))

    def test_a_protected_package_uses_the_decoded_table(self):
        """The header stays obscured, so the offsets come from the layout."""
        from tools.cheat_patcher import battle_overlay
        from tools.scripts import protected_package

        class Parsed:
            offsets = (0x40, 0x80)
            flags = (26624, 0)

        layout = battle_overlay._layout_for(b"", Parsed())
        self.assertEqual((0x40, 0x80), layout.offsets)
        self.assertEqual((26624, 0), layout.flags)
        self.assertIs(battle_overlay.HEADER_XOR, protected_package.HEADER_XOR)

    def test_an_unreadable_entry_is_treated_as_clear(self):
        """So the error a caller sees is still about the p@Ck, not the wrapper."""
        from tools.cheat_patcher import battle_overlay
        clear, parsed = battle_overlay._clear_package(b"\x00" * 0x40)
        self.assertIsNone(parsed)
        with self.assertRaises(ValueError) as raised:
            battle_overlay.package_layout(b"\x00" * 0x40)
        self.assertIn("p@Ck header", str(raised.exception))
