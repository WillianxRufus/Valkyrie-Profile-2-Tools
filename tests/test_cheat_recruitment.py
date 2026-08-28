# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
import struct
import unittest

from tools.cheat_patcher import elf, main_overlay, resource3_overlay
from tools.cheat_patcher.cheats import (
    join_all_unlocked, join_level_1, mithra_swap,
    stop_removing_characters,
)
from tests.test_cheat_disable_anti_cheat import (
    make_executable, make_main_resource, make_resource_3,
)


def _words(data, address, count):
    offset = elf.file_offset_for_address(data, address, count * 4)
    return struct.unpack_from("<%dI" % count, data, offset)


class RecruitmentPatchTests(unittest.TestCase):
    def test_all_unlocked_changes_only_three_hooks_and_installs_exact_code(self):
        resource = make_resource_3()
        before = resource3_overlay.read(resource).output
        details = join_all_unlocked.patch_resource(resource)
        after = resource3_overlay.read(details.data).output
        expected = bytearray(before)
        for address, _, replacement in join_all_unlocked.PATCHES:
            struct.pack_into(
                "<I", expected,
                address - resource3_overlay.LOAD_ADDRESS, replacement
            )
        self.assertEqual(bytes(expected), after)

        executable, _ = make_executable()
        patched = join_all_unlocked.patch_executable(executable).data
        self.assertEqual(
            join_all_unlocked.INJECT_WORDS,
            _words(patched, join_all_unlocked.INJECT_ADDRESS,
                   len(join_all_unlocked.INJECT_WORDS))
        )
        self.assertEqual(elf.pcsx2_crc(executable), elf.pcsx2_crc(patched))

    def test_mithra_guard_uses_complete_original_words_and_exact_routine(self):
        resource = make_main_resource()
        before = main_overlay.read(resource).output
        details = mithra_swap.patch_main_resource(resource)
        after = main_overlay.read(details.data).output
        expected = bytearray(before)
        for address, _, replacement in mithra_swap.PATCHES:
            struct.pack_into(
                "<I", expected,
                address - main_overlay.LOAD_ADDRESS, replacement
            )
        self.assertEqual(bytes(expected), after)
        self.assertEqual(0x2685001E, mithra_swap.PATCHES[1][1])

        malformed = bytearray(before)
        struct.pack_into(
            "<I", malformed,
            0x003C20C0 - main_overlay.LOAD_ADDRESS, 0xDEAD001E
        )
        malformed_resource, _ = main_overlay.replace(resource, malformed)
        with self.assertRaisesRegex(ValueError, "expected .*0x2685001E"):
            mithra_swap.patch_main_resource(malformed_resource)

        executable, _ = make_executable()
        patched = mithra_swap.patch_executable(executable).data
        self.assertEqual(
            mithra_swap.INJECT_WORDS,
            _words(patched, mithra_swap.INJECT_ADDRESS,
                   len(mithra_swap.INJECT_WORDS))
        )

    def test_each_hook_jump_resolves_to_the_literal_pnach_entry(self):
        self.assertEqual(
            join_all_unlocked.INJECT_ADDRESS + 0x18,
            (join_all_unlocked.PATCHES[1][2] & 0x03FFFFFF) << 2
        )
        self.assertEqual(
            mithra_swap.INJECT_ADDRESS,
            (mithra_swap.PATCHES[1][2] & 0x03FFFFFF) << 2
        )
        self.assertEqual(
            join_level_1.INJECT_ADDRESS,
            (join_level_1.PATCHES[0][2] & 0x03FFFFFF) << 2
        )

    def test_level_one_is_independent_and_writes_its_mithra_overrides(self):
        resource = make_resource_3()
        before = resource3_overlay.read(resource).output
        details = join_level_1.patch_resource(resource)
        after = resource3_overlay.read(details.data).output
        expected = bytearray(before)
        address, _, replacement = join_level_1.PATCHES[0]
        struct.pack_into(
            "<I", expected,
            address - resource3_overlay.LOAD_ADDRESS, replacement
        )
        self.assertEqual(bytes(expected), after)

        executable, _ = make_executable()
        patched = join_level_1.patch_executable(executable).data
        self.assertEqual(
            join_level_1.INJECT_WORDS,
            _words(patched, join_level_1.INJECT_ADDRESS,
                   len(join_level_1.INJECT_WORDS))
        )
        for address, _, replacement in join_level_1.MITHRA_LEVEL_OVERRIDES:
            self.assertEqual((replacement,), _words(patched, address, 1))

    def test_level_one_and_mithra_compose_in_either_order(self):
        executable, _ = make_executable()
        level_then_mithra = mithra_swap.patch_executable(
            join_level_1.patch_executable(executable).data
        ).data
        mithra_then_level = join_level_1.patch_executable(
            mithra_swap.patch_executable(executable).data
        ).data
        self.assertEqual(level_then_mithra, mithra_then_level)
        self.assertEqual(
            mithra_swap.INJECT_WORDS_WITH_LEVEL1,
            _words(level_then_mithra, mithra_swap.INJECT_ADDRESS,
                   len(mithra_swap.INJECT_WORDS_WITH_LEVEL1))
        )

    def test_all_injected_routines_share_one_exact_address_arena(self):
        executable, _ = make_executable()
        modules = (
            stop_removing_characters,
            join_all_unlocked,
            mithra_swap,
            join_level_1,
        )
        forward = executable
        for module in modules:
            forward = module.patch_executable(forward).data
        reverse = executable
        for module in reversed(modules):
            reverse = module.patch_executable(reverse).data
        self.assertEqual(forward, reverse)
        self.assertEqual(len(executable) + 0x3E0, len(forward))
        self.assertEqual(elf.pcsx2_crc(executable), elf.pcsx2_crc(forward))
        self.assertEqual(
            join_all_unlocked.INJECT_WORDS,
            _words(forward, join_all_unlocked.INJECT_ADDRESS,
                   len(join_all_unlocked.INJECT_WORDS))
        )
        self.assertEqual(
            stop_removing_characters.INJECT_WORDS,
            _words(forward, stop_removing_characters.INJECT_ADDRESS,
                   len(stop_removing_characters.INJECT_WORDS))
        )
        self.assertEqual(
            join_level_1.INJECT_WORDS,
            _words(forward, join_level_1.INJECT_ADDRESS,
                   len(join_level_1.INJECT_WORDS))
        )


if __name__ == "__main__":
    unittest.main()
