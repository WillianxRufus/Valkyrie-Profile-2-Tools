# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Read and rebuild the first battle-overlay item in a tri-Ace p@Ck package."""

from dataclasses import dataclass
import struct

from . import slz, slz3
from ..scripts import protected_package


PACKAGE_MAGIC = b"p@Ck"
# The same key the translation runtime opens a package header with.
HEADER_XOR = protected_package.HEADER_XOR
SLZ_HEADER_SIZE = 0x10


def _clear_package(resource):
    """The package bytes to work on, and how to put them back.

    The entry may be protected or clear; either way the work is done on
    the clear bytes and any wrapper goes back on at the end.
    """
    try:
        clear, parsed = protected_package.decode_entry(resource)
    except (protected_package.ProtectedPackageError, ValueError,
            struct.error, IndexError):
        return bytes(resource), None
    return clear, parsed


@dataclass(frozen=True)
class PackageLayout:
    offsets: tuple
    flags: tuple


@dataclass(frozen=True)
class Overlay:
    layout: PackageLayout
    stream_offset: int
    item_end: int
    stored_size: int
    output: bytes

    @property
    def item_span(self):
        return self.item_end - self.stream_offset


def package_layout(resource):
    """Read the p@Ck item table, protected or clear."""
    clear, parsed = _clear_package(resource)
    return _layout_for(clear, parsed)


def _layout_for(resource, parsed):
    """A protected entry keeps its header obscured; its table is decoded."""
    if parsed is None:
        return _clear_layout(resource)
    return PackageLayout(tuple(parsed.offsets), tuple(parsed.flags))


def _clear_layout(resource):
    if len(resource) < 0x18:
        raise ValueError("battle resource is too small for a p@Ck header")
    header = bytearray(resource)
    for index, value in enumerate(HEADER_XOR):
        header[index] ^= value
    if header[:4] != PACKAGE_MAGIC:
        raise ValueError("battle resource does not contain the expected p@Ck header")
    count = struct.unpack_from("<H", header, 6)[0]
    table_end = 8 + (count + 1) * 8
    if not count or table_end > len(resource):
        raise ValueError("battle p@Ck item table exceeds its allocation")
    rows = [
        struct.unpack_from("<II", header, 8 + number * 8)
        for number in range(count + 1)
    ]
    offsets = tuple(row[0] for row in rows)
    flags = tuple(row[1] for row in rows)
    if offsets[0] != table_end:
        raise ValueError("battle p@Ck payload does not follow its table")
    if offsets[-1] > len(resource):
        raise ValueError("battle p@Ck payload exceeds its allocation")
    if any(left > right for left, right in zip(offsets, offsets[1:])):
        raise ValueError("battle p@Ck item offsets are not sorted")
    if flags[-1] != 0:
        raise ValueError("battle p@Ck terminal row has flags")
    if any(resource[offsets[-1]:]):
        raise ValueError("battle resource has unknown data after the p@Ck package")
    return PackageLayout(offsets, flags)


def read(resource):
    """Expand the first, fixed-span mode-3 SLZ item."""
    clear, parsed = _clear_package(resource)
    return _read_clear(clear, parsed)


def _read_clear(resource, parsed=None):
    layout = _layout_for(resource, parsed)
    start, item_end = layout.offsets[:2]
    if resource[start:start + 3] != b"SLZ":
        raise ValueError("battle p@Ck first item is not an SLZ stream")
    mode = resource[start + 3]
    if mode != 3:
        raise ValueError(
            "battle overlay uses unsupported SLZ mode %d; expected mode 3" % mode
        )
    stored_size, expanded_size = struct.unpack_from("<II", resource, start + 4)
    stream_end = start + SLZ_HEADER_SIZE + stored_size
    if stream_end > item_end:
        raise ValueError("battle overlay SLZ stream exceeds its p@Ck item")
    if any(resource[stream_end:item_end]):
        raise ValueError("battle overlay p@Ck item has unknown trailing data")
    output = slz.decompress(resource[start:stream_end])
    if len(output) != expanded_size:
        raise ValueError("battle overlay expanded-size validation failed")
    return Overlay(layout, start, item_end, stored_size, output)


def replace(resource, output):
    """Recompress a requested expanded overlay inside the same first item."""
    original = bytes(resource)
    resource, parsed = _clear_package(original)
    old = _read_clear(resource, parsed)
    new_stream = slz3.compress(bytes(output))
    if len(new_stream) > old.item_span:
        raise ValueError(
            "recompressed battle overlay needs 0x%X bytes but its fixed "
            "p@Ck item holds only 0x%X" % (len(new_stream), old.item_span)
        )
    rebuilt = bytearray(resource)
    rebuilt[old.stream_offset:old.item_end] = b"\0" * old.item_span
    rebuilt[old.stream_offset:old.stream_offset + len(new_stream)] = new_stream
    rebuilt = bytes(rebuilt)
    new = _read_clear(rebuilt, parsed)
    if new.layout != old.layout:
        raise ValueError("battle p@Ck item geometry changed")
    if resource[:old.stream_offset] != rebuilt[:new.stream_offset]:
        raise ValueError("battle p@Ck header changed")
    if resource[old.item_end:] != rebuilt[new.item_end:]:
        raise ValueError("items after the battle overlay changed")
    if new.output != bytes(output):
        raise ValueError("rebuilt battle overlay did not expand as requested")
    if parsed is not None:
        rebuilt = protected_package.encode_entry(original, rebuilt, parsed)
    return rebuilt, new.stored_size
