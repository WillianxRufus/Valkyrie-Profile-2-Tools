# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
import tempfile
import unittest

from tools.cheat_patcher import battle_overlay, elf, sle, slz3, slz12, triace
from tools.cheat_patcher.angel_slayer import (
    ORIGINAL_WORD as ANGEL_ORIGINAL,
    PATCHED_WORD as ANGEL_PATCHED,
    TARGET_ADDRESS as ANGEL_ADDRESS,
)
from tools.cheat_patcher.battle_anti_freeze import (
    ORIGINAL_INSTRUCTION as ANTI_FREEZE_ORIGINAL,
    PATCHED_INSTRUCTION as ANTI_FREEZE_PATCHED,
    TARGET_ADDRESS as ANTI_FREEZE_ADDRESS,
)
from tools.cheat_patcher.build import build_iso
from tools.cheat_patcher.disable_anti_cheat import (
    ALL_BATTLE_PATCHES,
    CRC_COMPENSATION_OFFSET,
    EXECUTABLE_ADDRESS,
    EXECUTABLE_ORIGINAL,
    EXECUTABLE_PATCHED,
    MAIN_PATCHES,
    MEMORY_CARD_PATCHES,
    SAVE_PATCHES,
    patch_battle_resource,
    patch_executable,
    patch_main_resource,
    patch_memory_card_resource,
    patch_save_resource,
)
from tests.test_cheat_angel_slayer import write_synthetic_iso
from tests.test_cheat_equip_everything import make_equip_resource


def _plant(output, base, patches):
    for patch in patches:
        struct.pack_into("<I", output, patch.address - base, patch.original)


def make_resource_3():
    first_output = bytearray(0x19A00)
    struct.pack_into("<I", first_output, 8, 0x0035EC80)
    _plant(first_output, 0x0035EC80, MEMORY_CARD_PATCHES)
    first_unlinked = sle.conceal(slz12.compress(first_output, 1))
    first = sle.conceal(
        slz12.compress(first_output, 1, next_offset=len(first_unlinked))
    )

    base = ANGEL_ADDRESS - 0x40
    second_output = bytearray(0x200)
    struct.pack_into("<I", second_output, 8, base)
    struct.pack_into("<I", second_output, 0x40, ANGEL_ORIGINAL)
    second = sle.conceal(slz3.compress(bytes(second_output)))
    return first + second + b"\0" * 0x800


def make_main_resource():
    output = bytearray(0xC4D00)
    struct.pack_into("<I", output, 8, 0x0035EC80)
    _plant(output, 0x0035EC80, MAIN_PATCHES)
    return sle.conceal(slz12.compress(output, 2)) + b"\0" * 0x800


def make_save_resource():
    output = bytearray(0x6D00)
    struct.pack_into("<I", output, 8, 0x00495500)
    _plant(output, 0x00495500, SAVE_PATCHES)
    encoded = sle.conceal(slz12.compress(output, 1))
    inner_size = (len(encoded) + 3) & ~3
    span = (0x10 + inner_size + 0x7F) & ~0x7F
    suffix = b"SAVE-SUFFIX" + b"\xA5" * 32
    resource = bytearray(span + len(suffix) + 0x100)
    struct.pack_into("<4sIII", resource, 0, b"ZLS\0", inner_size, 0, span)
    resource[0x10:0x10 + len(encoded)] = encoded
    resource[span:span + len(suffix)] = suffix
    return bytes(resource), suffix, span


def make_battle_resource():
    base = 0x0036D900
    highest = max(patch.address for patch in ALL_BATTLE_PATCHES)
    output = bytearray((highest - base + 0x104) & ~1)
    struct.pack_into("<I", output, 8, base)
    struct.pack_into(
        "<I", output, ANTI_FREEZE_ADDRESS - base, ANTI_FREEZE_ORIGINAL
    )
    struct.pack_into("<I", output, 0x00397CAC - base, 0x0262102A)
    _plant(output, base, ALL_BATTLE_PATCHES)
    stream = slz3.compress(bytes(output))

    count = 2
    first = 8 + (count + 1) * 8
    second = (first + len(stream) + 0x3F) & ~0x3F
    marker = b"NEXT-PACKAGE-ITEM" + b"\xA5" * 32
    end = (second + len(marker) + 0x3F) & ~0x3F
    resource = bytearray(end + 0x200)
    struct.pack_into("<4sHH", resource, 0, b"p@Ck", 1, count)
    struct.pack_into("<II", resource, 8, first, 0x6800)
    struct.pack_into("<II", resource, 16, second, 0x6A00)
    struct.pack_into("<II", resource, 24, end, 0)
    resource[first:first + len(stream)] = stream
    resource[second:second + len(marker)] = marker
    for index, value in enumerate(battle_overlay.HEADER_XOR):
        resource[index] ^= value
    return bytes(resource), marker, second


def make_executable():
    data = bytearray(0x11000)
    data[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<I", data, 28, 52)
    struct.pack_into("<HH", data, 42, 32, 1)
    file_offset = 0x1000
    virtual_address = 0x00100000
    file_size = len(data) - file_offset
    struct.pack_into(
        "<8I", data, 52, 1, file_offset, virtual_address, 0,
        file_size, file_size, 5, 0x1000
    )
    target = file_offset + EXECUTABLE_ADDRESS - virtual_address
    struct.pack_into("<I", data, target, EXECUTABLE_ORIGINAL)
    return bytes(data), target


def install_iso_file(path, name, data):
    image = bytearray(path.read_bytes())
    root_sector = 0x100
    file_sector = 0x120
    root_size = 0x800
    end = file_sector * 0x800 + len(data)
    if len(image) < end:
        image.extend(b"\0" * (end - len(image)))

    descriptor = bytearray(0x800)
    descriptor[0:7] = b"\x01CD001\x01"
    root = bytearray(34)
    root[0] = 34
    struct.pack_into("<I", root, 2, root_sector)
    struct.pack_into("<I", root, 10, root_size)
    root[25] = 2
    root[32:34] = b"\x01\0"
    descriptor[156:190] = root
    image[16 * 0x800:17 * 0x800] = descriptor

    encoded_name = name.encode("ascii") + b";1"
    record_length = 33 + len(encoded_name) + (len(encoded_name) % 2 == 0)
    record = bytearray(record_length)
    record[0] = record_length
    struct.pack_into("<I", record, 2, file_sector)
    struct.pack_into("<I", record, 10, len(data))
    record[32] = len(encoded_name)
    record[33:33 + len(encoded_name)] = encoded_name
    root_at = root_sector * 0x800
    image[root_at:root_at + len(record)] = record
    file_at = file_sector * 0x800
    image[file_at:file_at + len(data)] = data
    path.write_bytes(image)


def _assert_patches(test, before, after, base, patches):
    expected = bytearray(before)
    for patch in patches:
        struct.pack_into("<I", expected, patch.address - base, patch.patched)
    test.assertEqual(bytes(expected), after)


class DisableAntiCheatTests(unittest.TestCase):
    def test_each_owner_changes_only_declared_instructions(self):
        resource = make_resource_3()
        old = list(sle.iter_streams(resource))[0].output
        new = list(sle.iter_streams(
            patch_memory_card_resource(resource).data
        ))[0].output
        _assert_patches(self, old, new, 0x0035EC80, MEMORY_CARD_PATCHES)

        resource = make_main_resource()
        old = next(sle.iter_streams(resource)).output
        new = next(sle.iter_streams(patch_main_resource(resource).data)).output
        _assert_patches(self, old, new, 0x0035EC80, MAIN_PATCHES)

        resource, suffix, span = make_save_resource()
        old = next(sle.iter_streams(resource[:span])).output
        patched = patch_save_resource(resource).data
        new = next(sle.iter_streams(patched[:span])).output
        _assert_patches(self, old, new, 0x00495500, SAVE_PATCHES)
        self.assertEqual(suffix, patched[span:span + len(suffix)])

        resource, marker, second = make_battle_resource()
        old = battle_overlay.read(resource).output
        patched = patch_battle_resource(resource).data
        new = battle_overlay.read(patched).output
        _assert_patches(self, old, new, 0x0036D900, ALL_BATTLE_PATCHES)
        self.assertEqual(marker, patched[second:second + len(marker)])

        executable, target = make_executable()
        details = patch_executable(executable)
        patched = details.data
        expected = bytearray(executable)
        struct.pack_into("<I", expected, target, EXECUTABLE_PATCHED)
        compensation = elf.pcsx2_crc(expected) ^ elf.pcsx2_crc(executable)
        struct.pack_into(
            "<I", expected, CRC_COMPENSATION_OFFSET, compensation
        )
        self.assertEqual(bytes(expected), patched)
        self.assertEqual(elf.pcsx2_crc(executable), elf.pcsx2_crc(patched))
        self.assertEqual(CRC_COMPENSATION_OFFSET,
                         details.crc_compensation_offset)
        self.assertEqual(compensation, details.crc_compensation_value)

    def test_rejects_a_memory_card_instruction_with_only_matching_low_half(self):
        original = make_resource_3()
        stream = list(sle.iter_streams(original))[0]
        output = bytearray(stream.output)
        offset = MEMORY_CARD_PATCHES[0].address - 0x0035EC80
        struct.pack_into("<I", output, offset, 0xDEAD00FF)
        unlinked = sle.conceal(slz12.compress(output, 1))
        encoded = sle.conceal(
            slz12.compress(output, 1, next_offset=len(unlinked))
        )
        resource = encoded + original[stream.next_offset:]
        with self.assertRaisesRegex(ValueError, "expected 0x306B00FF"):
            patch_memory_card_resource(resource)


class VersionOneBuildTests(unittest.TestCase):
    def test_all_four_patches_compose_in_one_iso(self):
        save_resource, _, _ = make_save_resource()
        battle_resource, _, _ = make_battle_resource()
        executable, executable_target = make_executable()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clean.iso"
            output = root / "patched.iso"
            equip_resource, _, _ = make_equip_resource()
            write_synthetic_iso(source, {
                3: make_resource_3(),
                22: make_main_resource(),
                645: equip_resource,
                652: save_resource,
                1781: battle_resource,
            })
            install_iso_file(source, "SLUS_214.52", executable)
            source_before = source.read_bytes()

            result = build_iso(source, output)

            self.assertEqual(
                ("angel-slayer", "equip-everything", "battle-anti-freeze",
                 "disable-anti-cheat"),
                tuple(item.name for item in result.patches)
            )
            self.assertEqual(source_before, source.read_bytes())
            with output.open("rb") as handle:
                index = triace.read_index(handle)
                resource_3 = triace.read_resource(handle, index, 3)
                battle = triace.read_resource(handle, index, 1781)
                handle.seek(0x120 * 0x800)
                patched_executable = handle.read(len(executable))

            streams = list(sle.iter_streams(resource_3))
            for patch in MEMORY_CARD_PATCHES:
                self.assertEqual(patch.patched, struct.unpack_from(
                    "<I", streams[0].output,
                    patch.address - 0x0035EC80
                )[0])
            self.assertEqual(ANGEL_PATCHED, struct.unpack_from(
                "<I", streams[1].output, 0x40
            )[0])

            battle_output = battle_overlay.read(battle).output
            self.assertEqual(ANTI_FREEZE_PATCHED, struct.unpack_from(
                "<I", battle_output, ANTI_FREEZE_ADDRESS - 0x0036D900
            )[0])
            for patch in ALL_BATTLE_PATCHES:
                self.assertEqual(patch.patched, struct.unpack_from(
                    "<I", battle_output, patch.address - 0x0036D900
                )[0])
            self.assertEqual(EXECUTABLE_PATCHED, struct.unpack_from(
                "<I", patched_executable, executable_target
            )[0])
            self.assertEqual(
                elf.pcsx2_crc(executable),
                elf.pcsx2_crc(patched_executable)
            )


if __name__ == "__main__":
    unittest.main()
