# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Regression coverage for the runtime-conditional pointer-write hook."""

import struct
import unittest

from tools.cheat_patcher import elf, main_overlay
from tools.cheat_patcher.cheats import hold_circle_float
from tests.test_cheat_disable_anti_cheat import (
    make_executable,
    make_main_resource,
)


def words_at(data, address, count):
    offset = elf.file_offset_for_address(data, address, count * 4)
    return struct.unpack_from("<%dI" % count, data, offset)


class HoldCircleFloatTests(unittest.TestCase):
    def test_changes_only_the_two_displaced_main_overlay_words(self):
        resource = make_main_resource()
        before = main_overlay.read(resource).output
        details = hold_circle_float.patch_resource(resource)
        after = main_overlay.read(details.data).output
        expected = bytearray(before)
        for address, _original, replacement in hold_circle_float.HOOK_PATCHES:
            struct.pack_into(
                "<I", expected,
                address - main_overlay.LOAD_ADDRESS, replacement,
            )
        self.assertEqual(bytes(expected), after)

    def test_installs_the_exact_conditional_pointer_write(self):
        executable, _ = make_executable()
        details = hold_circle_float.patch_executable(executable)
        self.assertEqual(
            hold_circle_float.INJECT_WORDS,
            words_at(
                details.data, hold_circle_float.INJECT_ADDRESS,
                len(hold_circle_float.INJECT_WORDS),
            ),
        )
        self.assertEqual(
            (0xE60202C4, 0x46001036),
            hold_circle_float.INJECT_WORDS[:2],
        )
        self.assertEqual(elf.pcsx2_crc(executable), details.patched_crc)

    def test_control_flow_lands_on_the_routine_and_returns_after_the_hook(self):
        hook_jump = hold_circle_float.HOOK_PATCHES[0][2]
        return_jump = hold_circle_float.INJECT_WORDS[-2]
        self.assertEqual(
            hold_circle_float.INJECT_ADDRESS,
            (hook_jump & 0x03FFFFFF) << 2,
        )
        self.assertEqual(
            hold_circle_float.RETURN_ADDRESS,
            (return_jump & 0x03FFFFFF) << 2,
        )
        branch_address = hold_circle_float.INJECT_ADDRESS + 5 * 4
        branch_immediate = hold_circle_float.INJECT_WORDS[5] & 0xFFFF
        self.assertEqual(
            hold_circle_float.INJECT_ADDRESS + 12 * 4,
            branch_address + 4 + branch_immediate * 4,
        )

    def test_rejects_the_wrong_neighboring_airborne_store(self):
        resource = make_main_resource()
        overlay = main_overlay.read(resource)
        output = bytearray(overlay.output)
        address, expected = hold_circle_float.GUARDS[0]
        struct.pack_into(
            "<I", output, address - main_overlay.LOAD_ADDRESS,
            expected ^ 1,
        )
        changed, _ = main_overlay.replace(resource, output)
        with self.assertRaisesRegex(ValueError, "condition validation failed"):
            hold_circle_float.patch_resource(changed)


if __name__ == "__main__":
    unittest.main()
