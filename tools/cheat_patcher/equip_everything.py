# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Patch CampEquip.ovl so every character can equip every item."""

from dataclasses import dataclass
import struct

from . import sle, slz3


RESOURCE = 645
OVERLAY_LOAD_ADDRESS = 0x00495500
TARGET_ADDRESS = 0x0049D768
TARGET_OFFSET = TARGET_ADDRESS - OVERLAY_LOAD_ADDRESS
ORIGINAL_INSTRUCTION = 0x10A00129
PATCHED_INSTRUCTION = 0x00000000
ZLS_HEADER_SIZE = 0x10


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    stream_offset: int
    overlay_offset: int
    old_stored_size: int
    new_stored_size: int
    wrapper_span: int
    allocation_size: int


def _read_wrapper(resource):
    if len(resource) < ZLS_HEADER_SIZE or resource[:4] != b"ZLS\0":
        raise ValueError("resource 645 does not begin with a ZLS wrapper")
    inner_size, previous_span, span = struct.unpack_from("<III", resource, 4)
    if previous_span != 0:
        raise ValueError("CampEquip ZLS wrapper has an unexpected previous span")
    if not ZLS_HEADER_SIZE + inner_size <= span <= len(resource):
        raise ValueError("CampEquip ZLS wrapper has an invalid span")
    streams = list(sle.iter_streams(resource[:span]))
    if len(streams) != 1:
        raise ValueError("CampEquip wrapper does not contain exactly one SLE stream")
    stream = streams[0]
    if stream.offset != ZLS_HEADER_SIZE or len(stream.encoded) != inner_size:
        raise ValueError("CampEquip inner-stream size disagrees with its wrapper")
    if stream.next_offset:
        raise ValueError("CampEquip inner SLE unexpectedly has a chain link")
    if stream.mode != 3:
        raise ValueError(
            "CampEquip uses unsupported SLZ mode %d; expected mode 3"
            % stream.mode
        )
    if any(resource[ZLS_HEADER_SIZE + inner_size:span]):
        raise ValueError("CampEquip wrapper padding contains unknown non-zero data")
    return stream, inner_size, span


def _instruction(stream):
    if TARGET_OFFSET + 4 > len(stream.output):
        raise ValueError(
            "CampEquip overlay is too small for EE address 0x%08X"
            % TARGET_ADDRESS
        )
    return struct.unpack_from("<I", stream.output, TARGET_OFFSET)[0]


def patch_resource(resource):
    """NOP the guarded CampEquip instruction inside its fixed ZLS span."""
    resource = bytes(resource)
    stream, inner_size, span = _read_wrapper(resource)
    observed = _instruction(stream)
    if observed == PATCHED_INSTRUCTION:
        raise ValueError("Let Everyone Equip Everything is already patched")
    if observed != ORIGINAL_INSTRUCTION:
        raise ValueError(
            "CampEquip instruction validation failed at EE 0x%08X; expected "
            "0x%08X, found 0x%08X"
            % (TARGET_ADDRESS, ORIGINAL_INSTRUCTION, observed)
        )

    patched_output = bytearray(stream.output)
    struct.pack_into("<I", patched_output, TARGET_OFFSET, PATCHED_INSTRUCTION)
    new_sle = sle.conceal(slz3.compress(bytes(patched_output)))
    capacity = span - ZLS_HEADER_SIZE
    if len(new_sle) > capacity:
        raise ValueError(
            "recompressed CampEquip stream needs 0x%X bytes but its fixed "
            "ZLS span holds only 0x%X" % (len(new_sle), capacity)
        )

    rebuilt = bytearray(resource)
    rebuilt[ZLS_HEADER_SIZE:span] = b"\0" * capacity
    rebuilt[ZLS_HEADER_SIZE:ZLS_HEADER_SIZE + len(new_sle)] = new_sle
    struct.pack_into("<I", rebuilt, 4, len(new_sle))
    rebuilt = bytes(rebuilt)
    verify_patched_resource(resource, rebuilt)
    return ResourcePatch(
        data=rebuilt,
        stream_offset=stream.offset,
        overlay_offset=TARGET_OFFSET,
        old_stored_size=inner_size,
        new_stored_size=len(new_sle),
        wrapper_span=span,
        allocation_size=len(resource),
    )


def verify_patched_resource(original, candidate):
    """Verify one expanded instruction changed and every following span stayed."""
    if len(original) != len(candidate):
        raise ValueError("resource 645 allocation size changed")
    old_stream, _, old_span = _read_wrapper(original)
    new_stream, _, new_span = _read_wrapper(candidate)
    if new_span != old_span:
        raise ValueError("CampEquip ZLS span changed")
    if original[old_span:] != candidate[new_span:]:
        raise ValueError("streams following CampEquip changed or moved")
    if _instruction(old_stream) != ORIGINAL_INSTRUCTION:
        raise ValueError("original CampEquip instruction no longer matches")
    if _instruction(new_stream) != PATCHED_INSTRUCTION:
        raise ValueError("patched CampEquip instruction did not read back")
    expected = bytearray(old_stream.output)
    struct.pack_into("<I", expected, TARGET_OFFSET, PATCHED_INSTRUCTION)
    if bytes(expected) != new_stream.output:
        raise ValueError("CampEquip expanded bytes changed outside the instruction")
