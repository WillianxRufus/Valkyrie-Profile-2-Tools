# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Read and rebuild resource 3's final resident mode-3 overlay."""

from dataclasses import dataclass
import struct

from . import sle, slz3


RESOURCE = 3
LOAD_ADDRESS = 0x001E7E00


@dataclass(frozen=True)
class Overlay:
    output: bytes
    stream_number: int
    stream_offset: int
    stored_size: int


@dataclass(frozen=True)
class PatchedOverlay:
    data: bytes
    offsets: tuple
    old_stored_size: int
    new_stored_size: int


def read(resource):
    resource = bytes(resource)
    streams = list(sle.iter_streams(resource))
    candidates = []
    for stream in streams:
        if len(stream.output) >= 12:
            base = struct.unpack_from("<I", stream.output, 8)[0]
            if base == LOAD_ADDRESS:
                candidates.append(stream)
    if len(candidates) != 1:
        raise ValueError(
            "resource 3 contains %d resident-overlay candidates"
            % len(candidates)
        )
    stream = candidates[0]
    if stream.number != len(streams) - 1 or stream.next_offset:
        raise ValueError("resource 3 resident overlay is not the final SLE stream")
    if stream.mode != 3:
        raise ValueError(
            "resource 3 resident overlay uses SLZ mode %d; expected mode 3"
            % stream.mode
        )
    if any(resource[stream.offset + len(stream.encoded):]):
        raise ValueError("resource 3 has unknown data after its resident overlay")
    return Overlay(
        stream.output, stream.number, stream.offset, stream.stored_size
    )


def replace(resource, output):
    resource = bytes(resource)
    old = read(resource)
    output = bytes(output)
    if len(output) != len(old.output):
        raise ValueError("resource 3 resident-overlay expanded size changed")
    encoded = sle.conceal(slz3.compress(output))
    capacity = len(resource) - old.stream_offset
    if len(encoded) > capacity:
        raise ValueError("recompressed resource 3 resident overlay exceeds its allocation")
    rebuilt = bytearray(resource)
    rebuilt[old.stream_offset:] = b"\0" * capacity
    rebuilt[old.stream_offset:old.stream_offset + len(encoded)] = encoded
    rebuilt = bytes(rebuilt)
    new = read(rebuilt)
    if new.output != output or new.stream_offset != old.stream_offset:
        raise ValueError("rebuilt resource 3 resident overlay did not read back")
    return rebuilt, new.stored_size


def patch_words(resource, label, patches):
    """Patch validated address/original/replacement triples in the overlay."""
    resource = bytes(resource)
    overlay = read(resource)
    offsets = tuple(address - LOAD_ADDRESS for address, _, _ in patches)
    if any(offset < 0 or offset + 4 > len(overlay.output)
           for offset in offsets):
        raise ValueError("%s target falls outside the resource 3 overlay" % label)
    observed = tuple(
        struct.unpack_from("<I", overlay.output, offset)[0]
        for offset in offsets
    )
    originals = tuple(original for _, original, _ in patches)
    replacements = tuple(replacement for _, _, replacement in patches)
    if observed == replacements:
        raise ValueError("%s is already patched in resource 3" % label)
    if observed != originals:
        raise ValueError(
            "%s validation failed; expected %s, found %s"
            % (label,
               "/".join("0x%08X" % word for word in originals),
               "/".join("0x%08X" % word for word in observed))
        )
    patched_output = bytearray(overlay.output)
    for offset, replacement in zip(offsets, replacements):
        struct.pack_into("<I", patched_output, offset, replacement)
    rebuilt, new_stored_size = replace(resource, patched_output)
    expected = bytearray(overlay.output)
    for offset, replacement in zip(offsets, replacements):
        struct.pack_into("<I", expected, offset, replacement)
    if read(rebuilt).output != bytes(expected):
        raise ValueError("%s changed outside its declared words" % label)
    return PatchedOverlay(
        rebuilt, offsets, overlay.stored_size, new_stored_size
    )
