# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
import tempfile
import unittest

from tools.cheat_patcher import sle, slz3, triace
from tools.cheat_patcher.angel_slayer import (
    ORIGINAL_WORD,
    PATCHED_WORD,
    TARGET_ADDRESS,
    build_iso,
    patch_resource,
)


MASK = 0xFFFFFFFF


def make_resource(word=ORIGINAL_WORD):
    first_plain = bytearray((b"FIRST-MODULE-123" * 16)[:0x100])
    struct.pack_into("<I", first_plain, 8, 0x00100000)
    first_unlinked = sle.conceal(slz3.compress(bytes(first_plain)))
    first = sle.conceal(
        slz3.compress(bytes(first_plain), next_offset=len(first_unlinked))
    )

    base = TARGET_ADDRESS - 0x40
    second_plain = bytearray((b"ANGEL-SLAYER-DATA" * 32)[:0x200])
    struct.pack_into("<I", second_plain, 8, base)
    struct.pack_into("<I", second_plain, 0x40, word)
    second = sle.conceal(slz3.compress(bytes(second_plain)))
    return first + second + b"\0" * 0x800


def encode_index(entries):
    total = triace.TOTAL_ENTRIES
    decoded = [0] * (3 * total)
    for resource, (sector, sector_count) in entries.items():
        decoded[resource] = sector
        decoded[total + resource] = sector_count
    key_at = [0] * (3 * total)
    key = triace.SEED
    for index in range(total):
        key_at[index] = key
        key = (key ^ ((key << 1) & MASK)) & MASK
        key_at[total + index] = key
        key = (key ^ (~triace.SEED & MASK)) & MASK
        key_at[2 * total + index] = key
        key = (key ^ ((key << 2) & MASK) ^ triace.SEED) & MASK
    raw = [decoded[index] ^ key_at[index] for index in range(3 * total)]
    raw[0] = triace.SIGNATURE
    return struct.pack("<%dI" % (3 * total), *raw)


def write_synthetic_iso(path, resources):
    if isinstance(resources, bytes):
        resources = {3: resources}
    layouts = {}
    payloads = {}
    sector = 0x500
    for resource, payload in sorted(resources.items()):
        sectors = (len(payload) + triace.SECTOR_SIZE - 1) // triace.SECTOR_SIZE
        allocation = sectors * triace.SECTOR_SIZE
        layouts[resource] = (sector * triace.SECTOR_SIZE, allocation)
        payloads[resource] = payload + b"\0" * (allocation - len(payload))
        sector += sectors
    table = encode_index({
        resource: (offset // triace.SECTOR_SIZE,
                   allocation // triace.SECTOR_SIZE)
        for resource, (offset, allocation) in layouts.items()
    })
    size = max(
        [triace.TABLE_OFFSET + len(table)] +
        [offset + allocation for offset, allocation in layouts.values()]
    )
    image = bytearray(size)
    image[triace.TABLE_OFFSET:triace.TABLE_OFFSET + len(table)] = table
    for resource, payload in payloads.items():
        offset, allocation = layouts[resource]
        image[offset:offset + allocation] = payload
    path.write_bytes(image)
    return layouts


class ResourcePatchTests(unittest.TestCase):
    def test_only_target_word_changes_after_expansion(self):
        original = make_resource()
        patch = patch_resource(original)
        old_streams = list(sle.iter_streams(original))
        new_streams = list(sle.iter_streams(patch.data))
        self.assertEqual(old_streams[0].encoded, new_streams[0].encoded)
        expected = bytearray(old_streams[1].output)
        struct.pack_into("<I", expected, 0x40, PATCHED_WORD)
        self.assertEqual(bytes(expected), new_streams[1].output)
        self.assertEqual(len(original), len(patch.data))

    def test_rejects_an_already_patched_resource(self):
        with self.assertRaisesRegex(ValueError, "already patched"):
            patch_resource(make_resource(PATCHED_WORD))

    def test_rejects_unknown_trailing_data(self):
        resource = bytearray(make_resource())
        resource[-1] = 1
        with self.assertRaisesRegex(ValueError, "non-zero data"):
            patch_resource(resource)


class IsoBuildTests(unittest.TestCase):
    def test_copies_patches_and_reads_back_a_synthetic_iso(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clean.iso"
            output = root / "patched.iso"
            layouts = write_synthetic_iso(source, make_resource())
            iso_offset, allocation = layouts[3]
            source_before = source.read_bytes()

            result = build_iso(source, output)

            self.assertEqual(output.resolve(), result.output)
            self.assertEqual(iso_offset, result.iso_offset)
            self.assertEqual(allocation, result.patch.allocation_size)
            self.assertEqual(source_before, source.read_bytes())
            with output.open("rb") as handle:
                index = triace.read_index(handle)
                patched_resource = triace.read_resource(handle, index, 3)
            target_stream = list(sle.iter_streams(patched_resource))[1]
            self.assertEqual(PATCHED_WORD, struct.unpack_from(
                "<I", target_stream.output, 0x40
            )[0])

    def test_refuses_to_overwrite_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clean.iso"
            output = root / "exists.iso"
            write_synthetic_iso(source, make_resource())
            output.write_bytes(b"keep me")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                build_iso(source, output)
            self.assertEqual(b"keep me", output.read_bytes())


if __name__ == "__main__":
    unittest.main()
