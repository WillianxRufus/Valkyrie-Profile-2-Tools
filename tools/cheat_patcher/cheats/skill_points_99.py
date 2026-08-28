# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Patch CampSkill.ovl to award 99 skill points to every character."""

from dataclasses import dataclass
import struct

from .. import menu_overlay


RESOURCE = 646
LABEL = "CampSkill"
MODE = 1
OVERLAY_LOAD_ADDRESS = 0x00495500
PATCHES = (
    (0x00496318, 0x14200003, 0x00000000),
    (0x00496320, 0x2403000C, 0x24030024),
)
TARGET_OFFSETS = tuple(address - OVERLAY_LOAD_ADDRESS
                       for address, _, _ in PATCHES)


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    stream_offset: int
    overlay_offsets: tuple
    old_stored_size: int
    new_stored_size: int
    wrapper_span: int
    allocation_size: int


def _words(output):
    words = []
    for offset in TARGET_OFFSETS:
        if offset + 4 > len(output):
            raise ValueError("CampSkill overlay is too small for its target words")
        words.append(struct.unpack_from("<I", output, offset)[0])
    return tuple(words)


def patch_resource(resource):
    """Patch only the two guarded CampSkill instructions."""
    resource = bytes(resource)
    overlay = menu_overlay.read(resource, RESOURCE, LABEL, MODE)
    observed = _words(overlay.output)
    originals = tuple(original for _, original, _ in PATCHES)
    patched = tuple(replacement for _, _, replacement in PATCHES)
    if observed == patched:
        raise ValueError("99 Skill Points is already patched")
    if observed != originals:
        raise ValueError(
            "CampSkill instruction validation failed; expected %s, found %s"
            % ("/".join("0x%08X" % word for word in originals),
               "/".join("0x%08X" % word for word in observed))
        )

    patched_output = bytearray(overlay.output)
    for offset, replacement in zip(TARGET_OFFSETS, patched):
        struct.pack_into("<I", patched_output, offset, replacement)
    rebuilt, new_stored_size = menu_overlay.replace(
        resource, patched_output, RESOURCE, LABEL, MODE
    )
    read_back = menu_overlay.read(rebuilt, RESOURCE, LABEL, MODE)
    expected = bytearray(overlay.output)
    for offset, replacement in zip(TARGET_OFFSETS, patched):
        struct.pack_into("<I", expected, offset, replacement)
    if read_back.output != bytes(expected):
        raise ValueError("CampSkill changed outside its two skill-point words")
    return ResourcePatch(
        rebuilt, overlay.stream_offset, TARGET_OFFSETS,
        overlay.stored_size, new_stored_size, overlay.wrapper_span,
        len(resource)
    )
