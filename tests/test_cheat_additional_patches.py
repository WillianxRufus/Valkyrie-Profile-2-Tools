# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Regression coverage for the six small PNACH-to-ISO ports."""

import struct
import unittest

from tools.cheat_patcher import (
    battle_overlay, main_overlay, menu_overlay, resource3_overlay
)
from tools.cheat_patcher.cheats import (
    character_limit_36,
    drop_rate_100,
    dupe_attacks,
    ether_set_effects,
    infinite_ap_attacks,
    negate_encounters,
)
from tests.test_cheat_disable_anti_cheat import (
    make_attack_resource,
    make_battle_resource,
    make_main_resource,
    make_resource_3,
)


def assert_word_changes(test, before, after, base, patches):
    expected = bytearray(before)
    for address, _original, replacement in patches:
        struct.pack_into("<I", expected, address - base, replacement)
    test.assertEqual(bytes(expected), after)


class AdditionalPatchTests(unittest.TestCase):
    def test_main_overlay_cheats_change_only_their_declared_words(self):
        for module in (character_limit_36, negate_encounters):
            with self.subTest(cheat=module.LABEL):
                resource = make_main_resource()
                old = main_overlay.read(resource).output
                result = module.patch_resource(resource)
                new = main_overlay.read(result.data).output
                assert_word_changes(
                    self, old, new, main_overlay.LOAD_ADDRESS, module.PATCHES
                )

    def test_battle_cheats_change_only_their_declared_words(self):
        for module in (infinite_ap_attacks, drop_rate_100):
            with self.subTest(cheat=module.LABEL):
                resource, marker, marker_at = make_battle_resource()
                old = battle_overlay.read(resource).output
                result = module.patch_resource(resource)
                new = battle_overlay.read(result.data).output
                assert_word_changes(
                    self, old, new, 0x0036D900, module.PATCHES
                )
                self.assertEqual(
                    marker, result.data[marker_at:marker_at + len(marker)]
                )

    def test_dupe_attacks_changes_only_camp_attack(self):
        resource = make_attack_resource()
        old = menu_overlay.read(
            resource, dupe_attacks.RESOURCE, dupe_attacks.OWNER,
            dupe_attacks.MODE
        )
        result = dupe_attacks.patch_resource(resource)
        new = menu_overlay.read(
            result.data, dupe_attacks.RESOURCE, dupe_attacks.OWNER,
            dupe_attacks.MODE
        )
        assert_word_changes(
            self, old.output, new.output, 0x00495500, dupe_attacks.PATCHES
        )
        self.assertEqual(
            resource[old.wrapper_span:], result.data[new.wrapper_span:]
        )

    def test_ether_set_changes_four_bytes_and_preserves_neighbor_flags(self):
        resource = make_resource_3()
        old = resource3_overlay.read(resource).output
        result = ether_set_effects.patch_resource(resource)
        new = resource3_overlay.read(result.data).output
        expected = bytearray(old)
        for address, _original, replacement in ether_set_effects.BYTE_PATCHES:
            expected[address - resource3_overlay.LOAD_ADDRESS] = replacement
        self.assertEqual(bytes(expected), new)
        self.assertEqual(
            0x0000140A,
            struct.unpack_from(
                "<I", new, 0x003170F4 - resource3_overlay.LOAD_ADDRESS
            )[0],
        )

    def test_infinite_ap_rejects_a_condition_with_only_matching_low_half(self):
        resource, _, _ = make_battle_resource()
        overlay = battle_overlay.read(resource)
        output = bytearray(overlay.output)
        address, _expected = infinite_ap_attacks.GUARDS[0]
        struct.pack_into("<I", output, address - 0x0036D900, 0xDEAD102A)
        changed, _ = battle_overlay.replace(resource, output)
        with self.assertRaisesRegex(ValueError, "expected 0x0262102A"):
            infinite_ap_attacks.patch_resource(changed)

    def test_dupe_attacks_rejects_the_wrong_camp_attack_condition(self):
        resource = make_attack_resource()
        overlay = menu_overlay.read(
            resource, dupe_attacks.RESOURCE, dupe_attacks.OWNER,
            dupe_attacks.MODE
        )
        output = bytearray(overlay.output)
        struct.pack_into("<I", output, 0x00499AF4 - 0x00495500, 0xDEADFFD8)
        changed, _ = menu_overlay.replace(
            resource, output, dupe_attacks.RESOURCE, dupe_attacks.OWNER,
            dupe_attacks.MODE
        )
        with self.assertRaisesRegex(ValueError, "expected 0x1460FFD8"):
            dupe_attacks.patch_resource(changed)


if __name__ == "__main__":
    unittest.main()
