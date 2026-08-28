# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Disable VP2's main, save, and battle checksum systems on disc."""

from dataclasses import dataclass
import struct
from typing import Optional

from . import battle_overlay, elf, sle, slz12


MAIN_RESOURCE = 22
SAVE_RESOURCE = 652
BATTLE_RESOURCE = 1781
MEMORY_CARD_RESOURCE = 3
EXECUTABLE_PATH = "/SLUS_214.52"
EXECUTABLE_ADDRESS = 0x0010D1B8
EXECUTABLE_ORIGINAL = 0x24020009
EXECUTABLE_PATCHED = 0x24020000
CRC_COMPENSATION_OFFSET = 0x0C


@dataclass(frozen=True)
class InstructionPatch:
    address: int
    original: int
    patched: int


MAIN_PATCHES = (
    InstructionPatch(0x00423464, 0x06E1FFF4, 0x00000000),
    InstructionPatch(0x004234A0, 0x2C420001, 0x34020001),
    InstructionPatch(0x0042361C, 0x06E1FFF4, 0x00000000),
    InstructionPatch(0x00423658, 0x2C420001, 0x34020001),
    InstructionPatch(0x004237E4, 0x06E1FFF4, 0x00000000),
    InstructionPatch(0x00423828, 0x14400005, 0x10000005),
)

MEMORY_CARD_PATCHES = (
    InstructionPatch(0x00360948, 0x306B00FF, 0x340B0000),
    InstructionPatch(0x00360AC8, 0x306B00FF, 0x340B0000),
)

SAVE_PATCHES = (
    InstructionPatch(0x0049A2CC, 0x0C126F2C, 0x00000000),
    InstructionPatch(0x0049BF2C, 0x0661FFF4, 0x00000000),
    InstructionPatch(0x0049BF60, 0x2C420001, 0x34020001),
    InstructionPatch(0x0049C094, 0x0641FFF4, 0x00000000),
    InstructionPatch(0x0049C0C8, 0x2C630001, 0x34030001),
)

BATTLE_GUARD_ADDRESS = 0x00397CAC
BATTLE_GUARD_INSTRUCTION = 0x0262102A
BATTLE_PATCHES = (
    InstructionPatch(0x00397BF8, 0x14400007, 0x00000000),
    InstructionPatch(0x00397C0C, 0x1040002E, 0x1000002E),
    InstructionPatch(0x00397C74, 0x14200010, 0x10000010),
    InstructionPatch(0x003ABF44, 0x1060001E, 0x1000001E),
    InstructionPatch(0x003AD168, 0x106200C3, 0x100000C3),
    InstructionPatch(0x003AD61C, 0x1062000A, 0x1000000A),
    InstructionPatch(0x003AF1B0, 0x18E000BB, 0x100000BB),
    InstructionPatch(0x003AF1EC, 0x14E3000A, 0x1000000A),
    InstructionPatch(0x003AF388, 0x14A00009, 0x10000009),
    InstructionPatch(0x003AF448, 0x15460009, 0x10000009),
    InstructionPatch(0x003C59F8, 0x14200009, 0x10000009),
    InstructionPatch(0x003CFFF0, 0x10C30009, 0x10000009),
    InstructionPatch(0x003D2650, 0x1040008B, 0x1000008B),
    InstructionPatch(0x003D27FC, 0x14200020, 0x10000020),
    InstructionPatch(0x003D2824, 0x10200016, 0x10000016),
    InstructionPatch(0x003D4930, 0x1040006F, 0x1000006F),
    InstructionPatch(0x00430B74, 0x1262000A, 0x10000024),
    InstructionPatch(0x00431A64, 0x12820022, 0x10000022),
    InstructionPatch(0x00431C1C, 0x12820010, 0x10000010),
)

CORRUPTED_SAVE_PATCHES = (
    InstructionPatch(0x003C01A4, 0x00031FFE, 0x34030000),
    InstructionPatch(0x005053BC, 0x1020001A, 0x00000000),
    InstructionPatch(0x005053C0, 0x3C010036, 0x00000000),
    InstructionPatch(0x00505418, 0x2C415260, 0x34010000),
)

ALL_BATTLE_PATCHES = BATTLE_PATCHES + CORRUPTED_SAVE_PATCHES

@dataclass(frozen=True)
class ComponentPatch:
    data: bytes
    allocation_size: int
    label: str
    change_count: int
    old_stored_size: Optional[int] = None
    new_stored_size: Optional[int] = None
    file_offset: Optional[int] = None
    original_crc: Optional[int] = None
    patched_crc: Optional[int] = None
    crc_compensation_offset: Optional[int] = None
    crc_compensation_value: Optional[int] = None


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def _word(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _validate_base(output, base, label):
    observed = _word(output, 8) if len(output) >= 12 else None
    if observed != base:
        found = "missing" if observed is None else "0x%08X" % observed
        raise ValueError(
            "%s load-base validation failed; expected 0x%08X, found %s"
            % (label, base, found)
        )


def _patch_words(output, base, patches, label):
    output = bytes(output)
    observed = []
    for patch in patches:
        offset = patch.address - base
        if not 0 <= offset <= len(output) - 4:
            raise ValueError(
                "%s does not cover EE address 0x%08X" % (label, patch.address)
            )
        observed.append(_word(output, offset))
    if all(value == patch.patched for value, patch in zip(observed, patches)):
        raise ValueError("Disable Anti-Cheat Systems is already patched in %s" % label)
    for value, patch in zip(observed, patches):
        if value != patch.original:
            raise ValueError(
                "%s validation failed at EE 0x%08X; expected 0x%08X, "
                "found 0x%08X"
                % (label, patch.address, patch.original, value)
            )
    rebuilt = bytearray(output)
    for patch in patches:
        struct.pack_into("<I", rebuilt, patch.address - base, patch.patched)
    return bytes(rebuilt)


def _verify_output(original, candidate, base, patches, label):
    expected = bytearray(original)
    for patch in patches:
        if _word(original, patch.address - base) != patch.original:
            raise ValueError("original %s instruction no longer matches" % label)
        struct.pack_into("<I", expected, patch.address - base, patch.patched)
    if bytes(expected) != candidate:
        raise ValueError("%s changed outside its anti-cheat instructions" % label)


def _single_sle(resource, mode, label):
    streams = list(sle.iter_streams(resource))
    if len(streams) != 1 or streams[0].offset != 0 or streams[0].next_offset:
        raise ValueError("%s does not contain one final SLE stream" % label)
    stream = streams[0]
    if stream.mode != mode:
        raise ValueError(
            "%s uses unsupported SLZ mode %d; expected mode %d"
            % (label, stream.mode, mode)
        )
    if any(resource[len(stream.encoded):]):
        raise ValueError("%s has unknown data after its SLE stream" % label)
    return stream


def patch_main_resource(resource):
    """Patch the six main checksum instructions in resource 22."""
    resource = bytes(resource)
    stream = _single_sle(resource, 2, "main overlay")
    _validate_base(stream.output, 0x0035EC80, "main overlay")
    patched_output = _patch_words(
        stream.output, 0x0035EC80, MAIN_PATCHES, "main overlay"
    )
    encoded = sle.conceal(slz12.compress(patched_output, 2))
    if len(encoded) > len(resource):
        raise ValueError("recompressed main overlay exceeds resource 22")
    rebuilt = encoded.ljust(len(resource), b"\0")
    new_stream = _single_sle(rebuilt, 2, "main overlay")
    _verify_output(
        stream.output, new_stream.output, 0x0035EC80,
        MAIN_PATCHES, "main overlay"
    )
    return ComponentPatch(
        rebuilt, len(resource), "main overlay", len(MAIN_PATCHES),
        stream.stored_size, new_stream.stored_size
    )


def patch_memory_card_resource(resource):
    """Patch the first resource-3 overlay used by memory-card recovery."""
    resource = bytes(resource)
    streams = list(sle.iter_streams(resource))
    if len(streams) < 2 or streams[0].offset != 0 or not streams[0].next_offset:
        raise ValueError("memory-card resource has no chained first overlay")
    stream = streams[0]
    if stream.mode != 1 or stream.next_offset != len(stream.encoded):
        raise ValueError("memory-card overlay has unsupported SLE geometry")
    _validate_base(stream.output, 0x0035EC80, "memory-card overlay")
    patched_output = _patch_words(
        stream.output, 0x0035EC80, MEMORY_CARD_PATCHES,
        "memory-card overlay"
    )
    encoded = sle.conceal(
        slz12.compress(patched_output, 1, next_offset=stream.next_offset)
    )
    if len(encoded) > stream.next_offset:
        raise ValueError("recompressed memory-card overlay exceeds its chain span")
    rebuilt = bytearray(resource)
    rebuilt[:stream.next_offset] = b"\0" * stream.next_offset
    rebuilt[:len(encoded)] = encoded
    rebuilt = bytes(rebuilt)
    new_stream = next(sle.iter_streams(rebuilt))
    if resource[stream.next_offset:] != rebuilt[stream.next_offset:]:
        raise ValueError("streams after the memory-card overlay changed")
    _verify_output(
        stream.output, new_stream.output, 0x0035EC80,
        MEMORY_CARD_PATCHES, "memory-card overlay"
    )
    return ComponentPatch(
        rebuilt, len(resource), "memory-card overlay",
        len(MEMORY_CARD_PATCHES), stream.stored_size,
        new_stream.stored_size
    )


def _save_wrapper(resource):
    if len(resource) < 0x10 or resource[:4] != b"ZLS\0":
        raise ValueError("save overlay does not begin with a ZLS wrapper")
    inner_size, previous_span, span = struct.unpack_from("<III", resource, 4)
    if previous_span or not 0x10 + inner_size <= span <= len(resource):
        raise ValueError("save overlay ZLS wrapper has invalid geometry")
    streams = list(sle.iter_streams(resource[:span]))
    if len(streams) != 1:
        raise ValueError("save overlay wrapper does not contain one SLE stream")
    stream = streams[0]
    aligned_size = (len(stream.encoded) + 3) & ~3
    if stream.offset != 0x10 or aligned_size != inner_size:
        raise ValueError("save overlay SLE size disagrees with its wrapper")
    if stream.mode != 1 or stream.next_offset:
        raise ValueError("save overlay is not one final mode-1 stream")
    if any(resource[0x10 + len(stream.encoded):span]):
        raise ValueError("save overlay wrapper has unknown trailing data")
    return stream, span


def patch_save_resource(resource):
    """Patch the five save checksum instructions in resource 652."""
    resource = bytes(resource)
    stream, span = _save_wrapper(resource)
    _validate_base(stream.output, 0x00495500, "save overlay")
    patched_output = _patch_words(
        stream.output, 0x00495500, SAVE_PATCHES, "save overlay"
    )
    encoded = sle.conceal(slz12.compress(patched_output, 1))
    capacity = span - 0x10
    aligned_size = (len(encoded) + 3) & ~3
    if aligned_size > capacity:
        raise ValueError("recompressed save overlay exceeds its fixed ZLS span")
    rebuilt = bytearray(resource)
    rebuilt[0x10:span] = b"\0" * capacity
    rebuilt[0x10:0x10 + len(encoded)] = encoded
    struct.pack_into("<I", rebuilt, 4, aligned_size)
    rebuilt = bytes(rebuilt)
    new_stream, new_span = _save_wrapper(rebuilt)
    if new_span != span or resource[span:] != rebuilt[span:]:
        raise ValueError("save overlay suffix changed")
    _verify_output(
        stream.output, new_stream.output, 0x00495500,
        SAVE_PATCHES, "save overlay"
    )
    return ComponentPatch(
        rebuilt, len(resource), "save overlay", len(SAVE_PATCHES),
        stream.stored_size, new_stream.stored_size
    )


def patch_battle_resource(resource):
    """Patch the nineteen checksum branches in resource 1781."""
    resource = bytes(resource)
    overlay = battle_overlay.read(resource)
    _validate_base(overlay.output, 0x0036D900, "battle overlay")
    guard_offset = BATTLE_GUARD_ADDRESS - 0x0036D900
    guard = _word(overlay.output, guard_offset)
    if guard != BATTLE_GUARD_INSTRUCTION:
        raise ValueError(
            "battle condition validation failed at EE 0x%08X; expected "
            "0x%08X, found 0x%08X"
            % (BATTLE_GUARD_ADDRESS, BATTLE_GUARD_INSTRUCTION, guard)
        )
    patched_output = _patch_words(
        overlay.output, 0x0036D900, ALL_BATTLE_PATCHES, "battle overlay"
    )
    rebuilt, new_stored_size = battle_overlay.replace(resource, patched_output)
    new_overlay = battle_overlay.read(rebuilt)
    _verify_output(
        overlay.output, new_overlay.output, 0x0036D900,
        ALL_BATTLE_PATCHES, "battle overlay"
    )
    return ComponentPatch(
        rebuilt, len(resource), "battle overlay", len(ALL_BATTLE_PATCHES),
        overlay.stored_size, new_stored_size
    )


def patch_executable(data):
    """Patch SLUS_214.52 while preserving its PCSX2 executable CRC."""
    data = bytes(data)
    offset = elf.file_offset_for_address(data, EXECUTABLE_ADDRESS, 4)
    observed = _word(data, offset)
    if observed == EXECUTABLE_PATCHED:
        raise ValueError("Disable Anti-Cheat Systems is already patched in the executable")
    if observed != EXECUTABLE_ORIGINAL:
        raise ValueError(
            "executable validation failed at EE 0x%08X; expected 0x%08X, "
            "found 0x%08X"
            % (EXECUTABLE_ADDRESS, EXECUTABLE_ORIGINAL, observed)
        )
    rebuilt = bytearray(data)
    struct.pack_into("<I", rebuilt, offset, EXECUTABLE_PATCHED)
    if data[9:16] != b"\0" * 7:
        raise ValueError("executable ELF identification padding is not pristine")
    if elf.file_range_is_loaded(data, CRC_COMPENSATION_OFFSET, 4):
        raise ValueError("executable CRC compensation word is file-backed")
    original_crc = elf.pcsx2_crc(data)
    functional_crc = elf.pcsx2_crc(rebuilt)
    compensation = functional_crc ^ original_crc
    compensation_value = (
        _word(data, CRC_COMPENSATION_OFFSET) ^ compensation
    )
    struct.pack_into(
        "<I", rebuilt, CRC_COMPENSATION_OFFSET, compensation_value
    )
    expected = bytearray(data)
    struct.pack_into("<I", expected, offset, EXECUTABLE_PATCHED)
    struct.pack_into(
        "<I", expected, CRC_COMPENSATION_OFFSET, compensation_value
    )
    if rebuilt != expected or len(rebuilt) != len(data):
        raise ValueError("executable changed outside its two validated words")
    patched_crc = elf.pcsx2_crc(rebuilt)
    if patched_crc != original_crc:
        raise ValueError(
            "executable PCSX2 CRC changed from %08X to %08X"
            % (original_crc, patched_crc)
        )
    return ComponentPatch(
        bytes(rebuilt), len(data), "main executable", 1,
        file_offset=offset, original_crc=original_crc,
        patched_crc=patched_crc,
        crc_compensation_offset=CRC_COMPENSATION_OFFSET,
        crc_compensation_value=compensation_value
    )


RESOURCE_PATCHERS = (
    (MEMORY_CARD_RESOURCE, patch_memory_card_resource),
    (MAIN_RESOURCE, patch_main_resource),
    (SAVE_RESOURCE, patch_save_resource),
    (BATTLE_RESOURCE, patch_battle_resource),
)
ISO_FILE_PATCHERS = ((EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
