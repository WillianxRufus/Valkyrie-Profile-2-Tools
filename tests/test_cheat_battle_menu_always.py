# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
import struct
import unittest

from tools.cheat_patcher import battle_overlay
from tools.cheat_patcher.cheats.battle_menu_always import (
    GUARD_ADDRESS,
    OVERLAY_LOAD_ADDRESS,
    PATCHES,
    patch_resource,
)
from tests.test_cheat_disable_anti_cheat import make_battle_resource


class BattleMenuAlwaysTests(unittest.TestCase):
    def test_changes_only_the_two_guarded_battle_instructions(self):
        resource, marker, marker_offset = make_battle_resource()
        before = battle_overlay.read(resource).output
        details = patch_resource(resource)
        after = battle_overlay.read(details.data).output
        expected = bytearray(before)
        for address, _, replacement in PATCHES:
            struct.pack_into(
                "<I", expected, address - OVERLAY_LOAD_ADDRESS, replacement
            )
        self.assertEqual(bytes(expected), after)
        self.assertEqual(2, details.change_count)
        self.assertEqual(
            marker,
            details.data[marker_offset:marker_offset + len(marker)],
        )

    def test_rejects_a_guard_with_only_the_matching_low_half(self):
        resource, _, _ = make_battle_resource()
        output = bytearray(battle_overlay.read(resource).output)
        struct.pack_into(
            "<I", output, GUARD_ADDRESS - OVERLAY_LOAD_ADDRESS, 0xDEAD011C
        )
        malformed, _ = battle_overlay.replace(resource, output)
        with self.assertRaisesRegex(ValueError, "expected 0x8CE4011C"):
            patch_resource(malformed)


if __name__ == "__main__":
    unittest.main()
