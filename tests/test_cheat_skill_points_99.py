# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
import tempfile
import unittest

from tools.cheat_patcher import menu_overlay, sle, slz12, triace
from tools.cheat_patcher.build import build_iso
from tools.cheat_patcher.cheats.skill_points_99 import (
    LABEL,
    MODE,
    PATCHES,
    RESOURCE,
    TARGET_OFFSETS,
    patch_resource,
)
from tests.test_cheat_angel_slayer import write_synthetic_iso


def make_skill_resource(words=None):
    words = words or tuple(original for _, original, _ in PATCHES)
    overlay = bytearray((b"CAMP-SKILL-OVERLAY" * 0x800)[:0x7E00])
    struct.pack_into("<I", overlay, 8, 0x00495500)
    for offset, word in zip(TARGET_OFFSETS, words):
        struct.pack_into("<I", overlay, offset, word)
    encoded = sle.conceal(slz12.compress(bytes(overlay), MODE))
    inner_size = (len(encoded) + 3) & ~3
    span = (0x10 + inner_size + 0x7F) & ~0x7F
    suffix = b"NEXT-SKILL-ZLS" + b"\xA5" * 64
    resource = bytearray(span + len(suffix) + 0x200)
    struct.pack_into("<4sIII", resource, 0, b"ZLS\0", inner_size, 0, span)
    resource[0x10:0x10 + len(encoded)] = encoded
    resource[span:span + len(suffix)] = suffix
    return bytes(resource), suffix, span


class SkillPointsResourceTests(unittest.TestCase):
    def test_changes_only_the_two_guarded_camp_skill_words(self):
        original, suffix, span = make_skill_resource()
        before = menu_overlay.read(original, RESOURCE, LABEL, MODE).output
        details = patch_resource(original)
        after = menu_overlay.read(details.data, RESOURCE, LABEL, MODE).output
        expected = bytearray(before)
        for offset, (_, _, replacement) in zip(TARGET_OFFSETS, PATCHES):
            struct.pack_into("<I", expected, offset, replacement)
        self.assertEqual(bytes(expected), after)
        self.assertEqual(suffix, details.data[span:span + len(suffix)])
        self.assertEqual(span, details.wrapper_span)
        self.assertEqual(len(original), len(details.data))

    def test_rejects_an_already_patched_overlay(self):
        patched = tuple(replacement for _, _, replacement in PATCHES)
        resource, _, _ = make_skill_resource(patched)
        with self.assertRaisesRegex(ValueError, "already patched"):
            patch_resource(resource)

    def test_rejects_a_different_instruction_with_the_same_guard_half(self):
        resource, _, _ = make_skill_resource((0xDEAD0003, PATCHES[1][1]))
        with self.assertRaisesRegex(ValueError, "expected 0x14200003"):
            patch_resource(resource)

    def test_builds_and_reads_back_a_selected_skill_patch(self):
        resource, _, _ = make_skill_resource()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clean.iso"
            output = root / "patched.iso"
            write_synthetic_iso(source, {RESOURCE: resource})
            result = build_iso(
                source, output, selected=("99-skill-points",)
            )
            self.assertEqual(("99-skill-points",),
                             tuple(item.name for item in result.patches))
            with output.open("rb") as handle:
                index = triace.read_index(handle)
                rebuilt = triace.read_resource(handle, index, RESOURCE)
            expanded = menu_overlay.read(
                rebuilt, RESOURCE, LABEL, MODE
            ).output
            self.assertEqual(
                tuple(replacement for _, _, replacement in PATCHES),
                tuple(struct.unpack_from("<I", expanded, offset)[0]
                      for offset in TARGET_OFFSETS)
            )


if __name__ == "__main__":
    unittest.main()
