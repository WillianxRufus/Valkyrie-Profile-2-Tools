# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Patch the battle overlay to initialize late-game characters safely."""

from dataclasses import dataclass
import struct

from .. import battle_overlay


RESOURCE = 1781
TARGET_ADDRESS = 0x00398E10
OVERLAY_LOAD_ADDRESS = 0x0036D900
TARGET_OFFSET = TARGET_ADDRESS - OVERLAY_LOAD_ADDRESS
ORIGINAL_INSTRUCTION = 0x00031FFE
PATCHED_INSTRUCTION = 0x20030001
PACKAGE_HEADER_XOR = battle_overlay.HEADER_XOR
PackageLayout = battle_overlay.PackageLayout


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    stream_offset: int
    module_base: int
    module_offset: int
    old_stored_size: int
    new_stored_size: int
    item_span: int
    allocation_size: int


def _package_layout(resource):
    return battle_overlay.package_layout(resource)


def _first_stream(resource):
    overlay = battle_overlay.read(resource)
    return (overlay.layout, overlay.stream_offset, overlay.item_end,
            overlay.stored_size, overlay.output)


def _instruction(output):
    if len(output) < 12:
        raise ValueError("battle overlay is too small to contain its load address")
    module_base = struct.unpack_from("<I", output, 8)[0]
    if module_base != OVERLAY_LOAD_ADDRESS:
        raise ValueError(
            "battle overlay load-base validation failed; expected 0x%08X, "
            "found 0x%08X" % (OVERLAY_LOAD_ADDRESS, module_base)
        )
    module_offset = TARGET_ADDRESS - module_base
    if not 0 <= module_offset <= len(output) - 4:
        raise ValueError(
            "battle overlay does not cover EE address 0x%08X" % TARGET_ADDRESS
        )
    return module_base, module_offset, struct.unpack_from(
        "<I", output, module_offset
    )[0]


def patch_resource(resource):
    """Patch one instruction while preserving resource 1781's item geometry."""
    resource = bytes(resource)
    _, start, item_end, old_stored_size, output = _first_stream(resource)
    module_base, module_offset, observed = _instruction(output)
    if observed == PATCHED_INSTRUCTION:
        raise ValueError("Anti Freeze In Battles is already patched")
    if observed != ORIGINAL_INSTRUCTION:
        raise ValueError(
            "battle instruction validation failed at EE 0x%08X; expected "
            "0x%08X, found 0x%08X"
            % (TARGET_ADDRESS, ORIGINAL_INSTRUCTION, observed)
        )

    patched_output = bytearray(output)
    struct.pack_into("<I", patched_output, module_offset, PATCHED_INSTRUCTION)
    capacity = item_end - start
    rebuilt, new_stored_size = battle_overlay.replace(resource, patched_output)
    verify_patched_resource(resource, rebuilt)
    return ResourcePatch(
        data=rebuilt,
        stream_offset=start,
        module_base=module_base,
        module_offset=module_offset,
        old_stored_size=old_stored_size,
        new_stored_size=new_stored_size,
        item_span=capacity,
        allocation_size=len(resource),
    )


def verify_patched_resource(original, candidate):
    """Prove only the expanded battle instruction changed semantically."""
    original = bytes(original)
    candidate = bytes(candidate)
    if len(original) != len(candidate):
        raise ValueError("resource 1781 allocation size changed")
    old_layout, old_start, old_end, _, old_output = _first_stream(original)
    new_layout, new_start, new_end, _, new_output = _first_stream(candidate)
    if old_layout != new_layout or (old_start, old_end) != (new_start, new_end):
        raise ValueError("resource 1781 p@Ck item geometry changed")
    if original[:old_start] != candidate[:new_start]:
        raise ValueError("resource 1781 p@Ck header changed")
    if original[old_end:] != candidate[new_end:]:
        raise ValueError("resource 1781 items after the battle overlay changed")

    _, old_offset, old_word = _instruction(old_output)
    _, new_offset, new_word = _instruction(new_output)
    if old_offset != new_offset or old_word != ORIGINAL_INSTRUCTION:
        raise ValueError("original battle instruction no longer matches")
    if new_word != PATCHED_INSTRUCTION:
        raise ValueError("patched battle instruction did not read back")
    expected = bytearray(old_output)
    struct.pack_into("<I", expected, old_offset, PATCHED_INSTRUCTION)
    if bytes(expected) != new_output:
        raise ValueError("battle overlay changed outside the target instruction")
