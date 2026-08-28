# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Minimal reader for Valkyrie Profile 2's encrypted tri-Ace ISO index."""

from dataclasses import dataclass
import struct


SECTOR_SIZE = 0x800
TABLE_OFFSET = 0x00200000
TOTAL_ENTRIES = 0x0C00
SEED = 0x49287491
SIGNATURE = 0x516F6699
MASK = 0xFFFFFFFF


@dataclass(frozen=True)
class Index:
    offsets: tuple
    sector_counts: tuple
    metadata: tuple

    def extent(self, resource):
        if not 0 <= resource < len(self.offsets):
            raise ValueError("resource %d is outside the index" % resource)
        sector = self.offsets[resource]
        count = self.sector_counts[resource]
        if not sector or not count:
            raise ValueError("resource %d is absent from this image" % resource)
        return sector * SECTOR_SIZE, count * SECTOR_SIZE


def _read_exact(handle, size):
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("truncated ISO while reading the tri-Ace index")
    return data


def read_index(handle):
    """Read and decrypt the fixed VP2 resource index."""
    handle.seek(TABLE_OFFSET)
    raw = _read_exact(handle, TOTAL_ENTRIES * 3 * 4)
    if struct.unpack_from("<I", raw)[0] != SIGNATURE:
        raise ValueError(
            "not a supported VP2 image: index signature at 0x%X is not 0x%08X"
            % (TABLE_OFFSET, SIGNATURE)
        )
    values = list(struct.unpack("<%dI" % (TOTAL_ENTRIES * 3), raw))
    key = SEED
    for index in range(TOTAL_ENTRIES):
        values[index] ^= key
        key = (key ^ ((key << 1) & MASK)) & MASK
        values[TOTAL_ENTRIES + index] ^= key
        key = (key ^ (~SEED & MASK)) & MASK
        values[2 * TOTAL_ENTRIES + index] ^= key
        key = (key ^ ((key << 2) & MASK) ^ SEED) & MASK
    values[0] = TABLE_OFFSET // SECTOR_SIZE
    return Index(
        tuple(values[:TOTAL_ENTRIES]),
        tuple(values[TOTAL_ENTRIES:2 * TOTAL_ENTRIES]),
        tuple(values[2 * TOTAL_ENTRIES:]),
    )


def read_resource(handle, index, resource):
    offset, size = index.extent(resource)
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        raise ValueError(
            "resource %d extends past the end of the ISO: need 0x%X bytes"
            % (resource, size)
        )
    return data
