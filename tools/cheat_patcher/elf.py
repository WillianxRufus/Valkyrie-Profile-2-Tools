# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Minimal ELF32 mapping and injection for the VP2 main executable."""

from dataclasses import dataclass
import struct


PT_LOAD = 1
CRC_COMPENSATION_OFFSET = 0x0C
CODE_ARENA_ADDRESS = 0x01FEA000
CODE_ARENA_SIZE = 0x3E00


@dataclass(frozen=True)
class LoadSegmentInjection:
    data: bytes
    header_index: int
    header_offset: int
    file_offset: int
    address: int
    size: int


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


def preserve_pcsx2_crc(original, candidate,
                       compensation_offset=CRC_COMPENSATION_OFFSET):
    """Balance a changed ELF in unused identification padding."""
    original = bytes(original)
    candidate = bytearray(candidate)
    if original[9:12] != b"\0" * 3 or candidate[9:12] != b"\0" * 3:
        raise ValueError("executable ELF identification padding is invalid")
    if compensation_offset != CRC_COMPENSATION_OFFSET:
        raise ValueError("unsupported executable CRC compensation offset")
    if (file_range_is_loaded(original, compensation_offset, 4) or
            file_range_is_loaded(candidate, compensation_offset, 4)):
        raise ValueError("executable CRC compensation word is file-backed")
    original_crc = pcsx2_crc(original)
    correction = pcsx2_crc(candidate) ^ original_crc
    current = struct.unpack_from("<I", candidate, compensation_offset)[0]
    value = current ^ correction
    struct.pack_into("<I", candidate, compensation_offset, value)
    patched_crc = pcsx2_crc(candidate)
    if patched_crc != original_crc:
        raise ValueError(
            "executable PCSX2 CRC changed from %08X to %08X"
            % (original_crc, patched_crc)
        )
    return bytes(candidate), value, patched_crc


def _code_arena(data):
    """The terminal header and file offset for the injected-code arena.

    The optional section-header table is not loaded at runtime, so its
    file bytes back the arena and the executable keeps its LBA.
    """
    data = bytes(data)
    program_offset = struct.unpack_from("<I", data, 28)[0]
    entry_size, count = struct.unpack_from("<HH", data, 42)
    headers = _program_headers(data)
    terminal = headers[-1]
    header_offset = program_offset + (count - 1) * entry_size

    if (terminal[0] == PT_LOAD and
            terminal[2] == CODE_ARENA_ADDRESS and
            terminal[4] == CODE_ARENA_SIZE and
            terminal[5] == CODE_ARENA_SIZE and
            terminal[6] == 5 and terminal[7] >= 4):
        file_offset = terminal[1]
        if (terminal[7] & (terminal[7] - 1) or
                struct.unpack_from("<I", data, 32)[0] != 0 or
                struct.unpack_from("<HHH", data, 46) != (0, 0, 0) or
                file_offset + CODE_ARENA_SIZE > len(data) or
                file_offset % terminal[7] !=
                CODE_ARENA_ADDRESS % terminal[7]):
            raise ValueError("injected ELF32 code arena has invalid geometry")
        for index, header in enumerate(headers[:-1]):
            kind, other_offset, virtual_address, _, file_size, memory_size = header[:6]
            if (kind == PT_LOAD and memory_size and
                    CODE_ARENA_ADDRESS < virtual_address + memory_size and
                    virtual_address < CODE_ARENA_ADDRESS + CODE_ARENA_SIZE):
                raise ValueError("injected ELF32 code arena overlaps another segment")
            if (kind == PT_LOAD and file_size and
                    file_offset < other_offset + file_size and
                    other_offset < file_offset + CODE_ARENA_SIZE):
                raise ValueError("injected ELF32 code arena storage is file-backed twice")
        return data, count - 1, header_offset, file_offset

    candidates = [
        (index, header) for index, header in enumerate(headers)
        if header[0] == PT_LOAD and header[4] == 0 and header[5] == 0
    ]
    if len(candidates) != 1 or candidates[0][0] != count - 1:
        raise ValueError(
            "ELF32 has %d usable empty terminal load segments"
            % len(candidates)
        )
    index, old_header = candidates[0]
    alignment = old_header[7]
    if alignment < 4 or alignment & (alignment - 1):
        raise ValueError("empty ELF32 load segment has invalid alignment")
    if (CODE_ARENA_ADDRESS % alignment or CODE_ARENA_SIZE % alignment):
        raise ValueError("injected ELF32 code arena violates segment alignment")

    section_offset = struct.unpack_from("<I", data, 32)[0]
    section_entry_size, section_count, string_index = struct.unpack_from(
        "<HHH", data, 46
    )
    section_end = section_offset + section_entry_size * section_count
    if (not section_offset or section_entry_size < 40 or not section_count or
            string_index >= section_count or section_end != len(data)):
        raise ValueError(
            "ELF32 section-header table is not the executable's final region"
        )
    if section_offset % alignment != CODE_ARENA_ADDRESS % alignment:
        raise ValueError("ELF32 section-header storage violates segment alignment")

    arena_end = CODE_ARENA_ADDRESS + CODE_ARENA_SIZE
    storage_end = section_offset + CODE_ARENA_SIZE
    for header in headers[:-1]:
        kind, file_offset, virtual_address, _, file_size, memory_size = header[:6]
        if (kind == PT_LOAD and memory_size and
                CODE_ARENA_ADDRESS < virtual_address + memory_size and
                virtual_address < arena_end):
            raise ValueError("injected ELF32 code arena overlaps another segment")
        if (kind == PT_LOAD and file_size and
                section_offset < file_offset + file_size and
                file_offset < storage_end):
            raise ValueError("ELF32 section-header storage is file-backed")

    rebuilt = bytearray(data)
    if len(rebuilt) < storage_end:
        rebuilt.extend(b"\0" * (storage_end - len(rebuilt)))
    rebuilt[section_offset:storage_end] = b"\0" * CODE_ARENA_SIZE
    struct.pack_into("<I", rebuilt, 32, 0)
    struct.pack_into("<HHH", rebuilt, 46, 0, 0, 0)
    struct.pack_into(
        "<8I", rebuilt, header_offset,
        PT_LOAD, section_offset, CODE_ARENA_ADDRESS, CODE_ARENA_ADDRESS,
        CODE_ARENA_SIZE, CODE_ARENA_SIZE, 5, alignment
    )
    return bytes(rebuilt), index, header_offset, section_offset


def inject_load_segment(data, address, payload, expected=None):
    """Write payload at its exact EE address in the shared code arena.

    *expected* may be one byte string or several acceptable byte strings.
    It defaults to zeroes, which is the PNACH safe-region contract.
    """
    data = bytes(data)
    payload = bytes(payload)
    if not payload or len(payload) % 4 or address % 4:
        raise ValueError("injected ELF code must be non-empty and word-aligned")
    arena_end = CODE_ARENA_ADDRESS + CODE_ARENA_SIZE
    if not (CODE_ARENA_ADDRESS <= address and
            address + len(payload) <= arena_end):
        raise ValueError(
            "injected ELF code at 0x%08X falls outside 0x%08X-0x%08X"
            % (address, CODE_ARENA_ADDRESS, arena_end)
        )
    rebuilt, index, header_offset, segment_file_offset = _code_arena(data)
    file_offset = segment_file_offset + address - CODE_ARENA_ADDRESS
    current = rebuilt[file_offset:file_offset + len(payload)]
    if current == payload:
        raise ValueError(
            "injected ELF code at 0x%08X is already present" % address
        )
    if expected is None:
        alternatives = (b"\0" * len(payload),)
    elif isinstance(expected, (bytes, bytearray)):
        alternatives = (bytes(expected),)
    else:
        alternatives = tuple(bytes(item) for item in expected)
    if any(len(item) != len(payload) for item in alternatives):
        raise ValueError("injected ELF expected bytes have the wrong size")
    if current not in alternatives:
        raise ValueError(
            "injected ELF code validation failed at 0x%08X" % address
        )
    rebuilt = bytearray(rebuilt)
    rebuilt[file_offset:file_offset + len(payload)] = payload
    rebuilt = bytes(rebuilt)
    if file_offset_for_address(rebuilt, address, len(payload)) != file_offset:
        raise ValueError("injected ELF32 load segment did not map back")
    return LoadSegmentInjection(
        rebuilt, index, header_offset, file_offset, address, len(payload)
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
