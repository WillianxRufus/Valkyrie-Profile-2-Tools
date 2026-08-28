# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Keep protected party members when VP2 rebuilds the active roster."""

from dataclasses import dataclass
import struct
from typing import Optional

from .. import elf, main_overlay


RESOURCE = 22
EXECUTABLE_PATH = "/SLUS_214.52"
HOOK_ADDRESS = 0x003BB5C4
HOOK_ORIGINALS = (0x0002382B, 0x0100282D)
INJECT_ADDRESS = 0x01FEAFE8
ENTRY_ADDRESS = INJECT_ADDRESS + 0x18
HOOK_PATCHED = (
    0x08000000 | ((ENTRY_ADDRESS >> 2) & 0x03FFFFFF),
    0x0002382B,
)
INJECT_WORDS = (
    0x00004021, 0x0100282D, 0x24010001, 0x0000302D,
    0x080EED75, 0x00000000, 0x24010009, 0x1101FFF8,
    0x00000000, 0x24010008, 0x1101FFF5, 0x00000000,
    0x2401000A, 0x1101FFF2, 0x00000000, 0x24010001,
    0x1101FFEF, 0x00000000, 0x24010002, 0x1101FFEC,
    0x00000000, 0x24010005, 0x1101FFE9, 0x00000000,
    0x24010007, 0x1101FFE6, 0x00000000, 0x24010004,
    0x1101FFE3, 0x00000000, 0x24010006, 0x1101FFE0,
    0x00000000, 0x24010001, 0x0100282D, 0x080EED73,
    0x00000000,
)
INJECTED_CODE = struct.pack("<%dI" % len(INJECT_WORDS), *INJECT_WORDS)


@dataclass(frozen=True)
class ComponentPatch:
    data: bytes
    allocation_size: int
    label: str
    change_count: int
    old_stored_size: Optional[int] = None
    new_stored_size: Optional[int] = None
    file_offset: Optional[int] = None
    original_size: Optional[int] = None
    new_size: Optional[int] = None
    original_crc: Optional[int] = None
    patched_crc: Optional[int] = None
    crc_compensation_offset: Optional[int] = None
    crc_compensation_value: Optional[int] = None
    program_header_index: Optional[int] = None


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def _word(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def patch_main_resource(resource):
    """Replace two roster instructions with a jump into injected code."""
    resource = bytes(resource)
    overlay = main_overlay.read(resource)
    offset = HOOK_ADDRESS - main_overlay.LOAD_ADDRESS
    if not 0 <= offset <= len(overlay.output) - 8:
        raise ValueError("main overlay does not cover the roster hook")
    observed = tuple(_word(overlay.output, offset + index * 4)
                     for index in range(2))
    if observed == HOOK_PATCHED:
        raise ValueError(
            "Stop The Game From Removing Characters is already patched "
            "in the main overlay"
        )
    if observed != HOOK_ORIGINALS:
        raise ValueError(
            "roster hook validation failed at EE 0x%08X; expected %s, found %s"
            % (HOOK_ADDRESS,
               "/".join("0x%08X" % word for word in HOOK_ORIGINALS),
               "/".join("0x%08X" % word for word in observed))
        )
    patched_output = bytearray(overlay.output)
    struct.pack_into("<2I", patched_output, offset, *HOOK_PATCHED)
    rebuilt, new_stored_size = main_overlay.replace(
        resource, bytes(patched_output)
    )
    read_back = main_overlay.read(rebuilt)
    expected = bytearray(overlay.output)
    struct.pack_into("<2I", expected, offset, *HOOK_PATCHED)
    if read_back.output != bytes(expected):
        raise ValueError("main overlay changed outside the roster hook")
    return ComponentPatch(
        rebuilt, len(resource), "main overlay roster hook", 2,
        overlay.stored_size, new_stored_size
    )


def patch_executable(data):
    """Install the 37-word routine in a validated ELF load segment."""
    data = bytes(data)
    original_crc = elf.pcsx2_crc(data)
    injection = elf.inject_load_segment(data, INJECT_ADDRESS, INJECTED_CODE)
    rebuilt, compensation_value, patched_crc = elf.preserve_pcsx2_crc(
        data, injection.data
    )
    mapped = elf.file_offset_for_address(rebuilt, INJECT_ADDRESS,
                                         len(INJECTED_CODE))
    if mapped != injection.file_offset:
        raise ValueError("injected roster routine maps to the wrong file offset")
    if rebuilt[mapped:mapped + len(INJECTED_CODE)] != INJECTED_CODE:
        raise ValueError("injected roster routine did not read back byte-for-byte")
    return ComponentPatch(
        rebuilt, len(rebuilt), "main executable roster routine",
        len(INJECT_WORDS), file_offset=injection.file_offset,
        original_size=len(data), new_size=len(rebuilt),
        original_crc=original_crc, patched_crc=patched_crc,
        crc_compensation_offset=elf.CRC_COMPENSATION_OFFSET,
        crc_compensation_value=compensation_value,
        program_header_index=injection.header_index,
    )


RESOURCE_PATCHERS = ((RESOURCE, patch_main_resource),)
ISO_FILE_PATCHERS = ((EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
