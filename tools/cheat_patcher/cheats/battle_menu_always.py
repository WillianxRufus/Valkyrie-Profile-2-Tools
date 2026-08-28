# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Remove the cooldown that hides the battle menu."""

from dataclasses import dataclass
import struct

from .. import battle_overlay


RESOURCE = 1781
LABEL = "Battle Menu Always Available"
OVERLAY_LOAD_ADDRESS = 0x0036D900
GUARD_ADDRESS = 0x00371CA0
GUARD_INSTRUCTION = 0x8CE4011C
PATCHES = (
    (0x00371CB4, 0x10C30004, 0x14000004),
    (0x0046E5A0, 0x10C30003, 0x14000003),
)
TARGET_OFFSETS = tuple(address - OVERLAY_LOAD_ADDRESS
                       for address, _, _ in PATCHES)


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    allocation_size: int
    label: str
    change_count: int
    stream_offset: int
    overlay_offsets: tuple
    old_stored_size: int
    new_stored_size: int
    item_span: int


def _word(output, address):
    offset = address - OVERLAY_LOAD_ADDRESS
    if not 0 <= offset <= len(output) - 4:
        raise ValueError(
            "battle overlay does not cover EE address 0x%08X" % address
        )
    return struct.unpack_from("<I", output, offset)[0]


def patch_resource(resource):
    """Patch the two guarded cooldown branches in resource 1781."""
    resource = bytes(resource)
    overlay = battle_overlay.read(resource)
    if len(overlay.output) < 12:
        raise ValueError("battle overlay is too small for its load address")
    observed_base = struct.unpack_from("<I", overlay.output, 8)[0]
    if observed_base != OVERLAY_LOAD_ADDRESS:
        raise ValueError(
            "battle overlay load-base validation failed; expected 0x%08X, "
            "found 0x%08X" % (OVERLAY_LOAD_ADDRESS, observed_base)
        )
    guard = _word(overlay.output, GUARD_ADDRESS)
    if guard != GUARD_INSTRUCTION:
        raise ValueError(
            "battle-menu condition validation failed at EE 0x%08X; expected "
            "0x%08X, found 0x%08X"
            % (GUARD_ADDRESS, GUARD_INSTRUCTION, guard)
        )
    observed = tuple(_word(overlay.output, address)
                     for address, _, _ in PATCHES)
    originals = tuple(original for _, original, _ in PATCHES)
    replacements = tuple(replacement for _, _, replacement in PATCHES)
    if observed == replacements:
        raise ValueError("Battle Menu Always Available is already patched")
    if observed != originals:
        raise ValueError(
            "battle-menu instruction validation failed; expected %s, found %s"
            % ("/".join("0x%08X" % word for word in originals),
               "/".join("0x%08X" % word for word in observed))
        )

    patched_output = bytearray(overlay.output)
    for offset, replacement in zip(TARGET_OFFSETS, replacements):
        struct.pack_into("<I", patched_output, offset, replacement)
    rebuilt, new_stored_size = battle_overlay.replace(resource, patched_output)
    read_back = battle_overlay.read(rebuilt)
    expected = bytearray(overlay.output)
    for offset, replacement in zip(TARGET_OFFSETS, replacements):
        struct.pack_into("<I", expected, offset, replacement)
    if read_back.output != bytes(expected):
        raise ValueError("battle overlay changed outside the two cooldown words")
    return ResourcePatch(
        rebuilt, len(resource), "battle menu cooldown", len(PATCHES),
        overlay.stream_offset, TARGET_OFFSETS, overlay.stored_size,
        new_stored_size, overlay.item_span,
    )
