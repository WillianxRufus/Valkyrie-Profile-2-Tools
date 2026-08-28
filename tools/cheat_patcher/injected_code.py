# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Apply and verify exact-address code writes in SLUS_214.52."""

from dataclasses import dataclass
import struct
from typing import Optional

from . import elf


EXECUTABLE_PATH = "/SLUS_214.52"


@dataclass(frozen=True)
class Write:
    address: int
    words: tuple
    expected: tuple = ()


@dataclass(frozen=True)
class ComponentPatch:
    data: bytes
    allocation_size: int
    label: str
    change_count: int
    file_offset: Optional[int] = None
    original_size: Optional[int] = None
    new_size: Optional[int] = None
    original_crc: Optional[int] = None
    patched_crc: Optional[int] = None
    crc_compensation_offset: Optional[int] = None
    crc_compensation_value: Optional[int] = None
    program_header_index: Optional[int] = None


def words_bytes(words):
    return struct.pack("<%dI" % len(words), *words)


def patch_executable(data, label, writes):
    """Apply exact PNACH writes and preserve the current PCSX2 ELF CRC."""
    data = bytes(data)
    candidate = data
    first_offset = None
    header_index = None
    change_count = 0
    for write in writes:
        payload = words_bytes(write.words)
        expected = (tuple(words_bytes(words) for words in write.expected)
                    if write.expected else None)
        injection = elf.inject_load_segment(
            candidate, write.address, payload, expected
        )
        candidate = injection.data
        if first_offset is None:
            first_offset = injection.file_offset
            header_index = injection.header_index
        change_count += len(write.words)

    original_crc = elf.pcsx2_crc(data)
    rebuilt, compensation_value, patched_crc = elf.preserve_pcsx2_crc(
        data, candidate
    )
    for write in writes:
        payload = words_bytes(write.words)
        mapped = elf.file_offset_for_address(
            rebuilt, write.address, len(payload)
        )
        if rebuilt[mapped:mapped + len(payload)] != payload:
            raise ValueError(
                "%s did not read back at EE 0x%08X" % (label, write.address)
            )
    return ComponentPatch(
        rebuilt, len(rebuilt), label, change_count,
        file_offset=first_offset, original_size=len(data), new_size=len(rebuilt),
        original_crc=original_crc, patched_crc=patched_crc,
        crc_compensation_offset=elf.CRC_COMPENSATION_OFFSET,
        crc_compensation_value=compensation_value,
        program_header_index=header_index,
    )
