# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Patch CampEquip.ovl so every character can equip every item."""

from dataclasses import dataclass
import struct

from .. import menu_overlay


RESOURCE = 645
OVERLAY_LOAD_ADDRESS = 0x00495500
TARGET_ADDRESS = 0x0049D768
TARGET_OFFSET = TARGET_ADDRESS - OVERLAY_LOAD_ADDRESS
ORIGINAL_INSTRUCTION = 0x10A00129
PATCHED_INSTRUCTION = 0x00000000
LABEL = "CampEquip"
MODE = 3


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    stream_offset: int
    overlay_offset: int
    old_stored_size: int
    new_stored_size: int
    wrapper_span: int
    allocation_size: int


def _instruction(output):
    if TARGET_OFFSET + 4 > len(output):
        raise ValueError(
            "CampEquip overlay is too small for EE address 0x%08X"
            % TARGET_ADDRESS
        )
    return struct.unpack_from("<I", output, TARGET_OFFSET)[0]


def patch_resource(resource):
    """NOP the guarded CampEquip instruction inside its fixed ZLS span."""
    resource = bytes(resource)
    overlay = menu_overlay.read(resource, RESOURCE, LABEL, MODE)
    observed = _instruction(overlay.output)
    if observed == PATCHED_INSTRUCTION:
        raise ValueError("Let Everyone Equip Everything is already patched")
    if observed != ORIGINAL_INSTRUCTION:
        raise ValueError(
            "CampEquip instruction validation failed at EE 0x%08X; expected "
            "0x%08X, found 0x%08X"
            % (TARGET_ADDRESS, ORIGINAL_INSTRUCTION, observed)
        )

    patched_output = bytearray(overlay.output)
    struct.pack_into("<I", patched_output, TARGET_OFFSET, PATCHED_INSTRUCTION)
    rebuilt, new_stored_size = menu_overlay.replace(
        resource, patched_output, RESOURCE, LABEL, MODE
    )
    verify_patched_resource(resource, rebuilt)
    return ResourcePatch(
        data=rebuilt,
        stream_offset=overlay.stream_offset,
        overlay_offset=TARGET_OFFSET,
        old_stored_size=overlay.stored_size,
        new_stored_size=new_stored_size,
        wrapper_span=overlay.wrapper_span,
        allocation_size=len(resource),
    )


def verify_patched_resource(original, candidate):
    """Verify one expanded instruction changed and every following span stayed."""
    if len(original) != len(candidate):
        raise ValueError("resource 645 allocation size changed")
    old = menu_overlay.read(original, RESOURCE, LABEL, MODE)
    new = menu_overlay.read(candidate, RESOURCE, LABEL, MODE)
    if new.wrapper_span != old.wrapper_span:
        raise ValueError("CampEquip ZLS span changed")
    if original[old.wrapper_span:] != candidate[new.wrapper_span:]:
        raise ValueError("streams following CampEquip changed or moved")
    if _instruction(old.output) != ORIGINAL_INSTRUCTION:
        raise ValueError("original CampEquip instruction no longer matches")
    if _instruction(new.output) != PATCHED_INSTRUCTION:
        raise ValueError("patched CampEquip instruction did not read back")
    expected = bytearray(old.output)
    struct.pack_into("<I", expected, TARGET_OFFSET, PATCHED_INSTRUCTION)
    if bytes(expected) != new.output:
        raise ValueError("CampEquip expanded bytes changed outside the instruction")
