# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Minimal ELF32 virtual-address mapping for the VP2 main executable."""

import struct


PT_LOAD = 1


def pcsx2_crc(data):
    """Return PCSX2's XOR of the complete aligned ELF words."""
    data = bytes(data)
    result = 0
    aligned_size = len(data) & ~3
    for (word,) in struct.iter_unpack("<I", data[:aligned_size]):
        result ^= word
    return result


def _program_headers(data):
    data = bytes(data)
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        raise ValueError("not a little-endian ELF32 executable")
    program_offset = struct.unpack_from("<I", data, 28)[0]
    entry_size, count = struct.unpack_from("<HH", data, 42)
    if entry_size < 32 or program_offset + entry_size * count > len(data):
        raise ValueError("ELF32 program-header table exceeds the file")
    return tuple(
        struct.unpack_from("<8I", data, program_offset + number * entry_size)
        for number in range(count)
    )


def file_range_is_loaded(data, file_offset, size):
    """Return whether any file-backed PT_LOAD overlaps a file range."""
    if file_offset < 0 or size < 0 or file_offset + size > len(data):
        raise ValueError("ELF32 file range exceeds the file")
    for header in _program_headers(data):
        kind, segment_offset, _, _, file_size = header[:5]
        if (kind == PT_LOAD and file_size and
                file_offset < segment_offset + file_size and
                segment_offset < file_offset + size):
            return True
    return False


def file_offset_for_address(data, address, size=1):
    """Map one file-backed virtual-address range through ELF program headers."""
    matches = []
    for header in _program_headers(data):
        kind, file_offset, virtual_address, _, file_size = header[:5]
        relative = address - virtual_address
        if kind == PT_LOAD and 0 <= relative <= file_size - size:
            mapped = file_offset + relative
            if mapped + size > len(data):
                raise ValueError("ELF32 load segment exceeds the file")
            matches.append(mapped)
    if len(matches) != 1:
        raise ValueError(
            "ELF32 address 0x%08X has %d file-backed mappings"
            % (address, len(matches))
        )
    return matches[0]
