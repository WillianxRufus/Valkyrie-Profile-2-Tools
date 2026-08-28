# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
import tempfile
import unittest

from tools.cheat_patcher import sle, slz3, triace
from tools.cheat_patcher.build import build_iso
from tools.cheat_patcher.cheats.equip_everything import (
    ORIGINAL_INSTRUCTION,
    PATCHED_INSTRUCTION,
    TARGET_OFFSET,
    patch_resource,
)
from tests.test_cheat_battle_anti_freeze import (
    expanded_first_item,
    make_resource as make_battle_resource,
)
from tests.test_cheat_angel_slayer import make_resource as make_angel_resource
from tests.test_cheat_angel_slayer import write_synthetic_iso


def make_equip_resource(instruction=ORIGINAL_INSTRUCTION):
    overlay = bytearray((b"CAMP-EQUIP-OVERLAY" * 0x800)[:0x8300])
    struct.pack_into("<I", overlay, TARGET_OFFSET, instruction)
    inner = sle.conceal(slz3.compress(bytes(overlay)))
    span = (0x10 + len(inner) + 0x7F) & ~0x7F
    suffix = b"NEXT-ZLS-STREAM" + b"\xA5" * 64
    resource = bytearray(span + len(suffix) + 0x200)
    struct.pack_into("<4sIII", resource, 0, b"ZLS\0", len(inner), 0, span)
    resource[0x10:0x10 + len(inner)] = inner
    resource[span:span + len(suffix)] = suffix
    return bytes(resource), suffix, span


class EquipEverythingResourceTests(unittest.TestCase):
    def test_nops_only_the_guarded_overlay_instruction(self):
        original, suffix, span = make_equip_resource()
        patch = patch_resource(original)
        old_stream = next(sle.iter_streams(original[:span]))
        new_stream = next(sle.iter_streams(patch.data[:span]))
        expected = bytearray(old_stream.output)
        struct.pack_into("<I", expected, TARGET_OFFSET, PATCHED_INSTRUCTION)
        self.assertEqual(bytes(expected), new_stream.output)
        self.assertEqual(suffix, patch.data[span:span + len(suffix)])
        self.assertEqual(span, patch.wrapper_span)
        self.assertEqual(len(original), len(patch.data))

    def test_rejects_an_already_patched_overlay(self):
        resource, _, _ = make_equip_resource(PATCHED_INSTRUCTION)
        with self.assertRaisesRegex(ValueError, "already patched"):
            patch_resource(resource)

    def test_rejects_a_different_instruction_with_same_low_half(self):
        resource, _, _ = make_equip_resource(0xDEAD0129)
        with self.assertRaisesRegex(ValueError, "expected 0x10A00129"):
            patch_resource(resource)


class MultiPatchBuildTests(unittest.TestCase):
    def test_applies_all_patches_in_one_verified_iso_copy(self):
        equip_resource, _, equip_span = make_equip_resource()
        battle_resource, _, _ = make_battle_resource()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clean.iso"
            output = root / "patched.iso"
            write_synthetic_iso(source, {
                3: make_angel_resource(),
                645: equip_resource,
                1781: battle_resource,
            })
            source_before = source.read_bytes()

            selected = (
                "angel-slayer", "equip-everything", "battle-anti-freeze"
            )
            result = build_iso(source, output, selected=selected)

            self.assertEqual(("angel-slayer", "equip-everything",
                              "battle-anti-freeze"),
                             tuple(item.name for item in result.patches))
            self.assertEqual(source_before, source.read_bytes())
            with output.open("rb") as handle:
                index = triace.read_index(handle)
                angel = triace.read_resource(handle, index, 3)
                equip = triace.read_resource(handle, index, 645)
                battle = triace.read_resource(handle, index, 1781)
            angel_stream = list(sle.iter_streams(angel))[1]
            equip_stream = next(sle.iter_streams(equip[:equip_span]))
            self.assertEqual(0xC0000000,
                             struct.unpack_from("<I", angel_stream.output, 0x40)[0])
            self.assertEqual(PATCHED_INSTRUCTION, struct.unpack_from(
                "<I", equip_stream.output, TARGET_OFFSET
            )[0])
            battle_output = expanded_first_item(battle)
            self.assertEqual(0x20030001, struct.unpack_from(
                "<I", battle_output, 0x2B510
            )[0])


if __name__ == "__main__":
    unittest.main()
