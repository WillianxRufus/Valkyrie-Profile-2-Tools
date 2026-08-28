# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Read and rebuild fixed-span ZLS menu overlays."""

from dataclasses import dataclass
import struct

from . import sle, slz3, slz12


HEADER_SIZE = 0x10


@dataclass(frozen=True)
class Overlay:
    output: bytes
    stream_offset: int
    stored_size: int
    wrapper_span: int


def read(resource, resource_number, label, mode):
    """Expand one menu overlay and validate its fixed ZLS envelope."""
    resource = bytes(resource)
    if len(resource) < HEADER_SIZE or resource[:4] != b"ZLS\0":
        raise ValueError("resource %d does not begin with a ZLS wrapper"
                         % resource_number)
    inner_size, previous_span, span = struct.unpack_from("<III", resource, 4)
    if previous_span:
        raise ValueError("%s ZLS wrapper has an unexpected previous span" % label)
    if not HEADER_SIZE + inner_size <= span <= len(resource):
        raise ValueError("%s ZLS wrapper has an invalid span" % label)
    streams = list(sle.iter_streams(resource[:span]))
    if len(streams) != 1:
        raise ValueError("%s wrapper does not contain exactly one SLE stream"
                         % label)
    stream = streams[0]
    aligned_size = (len(stream.encoded) + 3) & ~3
    if (stream.offset != HEADER_SIZE or
            inner_size not in (len(stream.encoded), aligned_size)):
        raise ValueError("%s inner-stream size disagrees with its wrapper" % label)
    if stream.next_offset:
        raise ValueError("%s inner SLE unexpectedly has a chain link" % label)
    if stream.mode != mode:
        raise ValueError(
            "%s uses unsupported SLZ mode %d; expected mode %d"
            % (label, stream.mode, mode)
        )
    if any(resource[HEADER_SIZE + len(stream.encoded):span]):
        raise ValueError("%s wrapper padding contains unknown non-zero data" % label)
    return Overlay(stream.output, stream.offset, inner_size, span)


def replace(resource, output, resource_number, label, mode):
    """Recompress a menu overlay without moving the following wrapper."""
    resource = bytes(resource)
    old = read(resource, resource_number, label, mode)
    output = bytes(output)
    if len(output) != len(old.output):
        raise ValueError("%s expanded size changed" % label)
    compressed = (slz3.compress(output) if mode == 3
                  else slz12.compress(output, mode))
    encoded = sle.conceal(compressed)
    capacity = old.wrapper_span - HEADER_SIZE
    if len(encoded) > capacity:
        raise ValueError(
            "recompressed %s stream needs 0x%X bytes but its fixed ZLS "
            "span holds only 0x%X" % (label, len(encoded), capacity)
        )
    rebuilt = bytearray(resource)
    rebuilt[HEADER_SIZE:old.wrapper_span] = b"\0" * capacity
    rebuilt[HEADER_SIZE:HEADER_SIZE + len(encoded)] = encoded
    struct.pack_into("<I", rebuilt, 4, len(encoded))
    rebuilt = bytes(rebuilt)
    new = read(rebuilt, resource_number, label, mode)
    if new.output != output or new.wrapper_span != old.wrapper_span:
        raise ValueError("rebuilt %s overlay did not read back" % label)
    if rebuilt[old.wrapper_span:] != resource[old.wrapper_span:]:
        raise ValueError("streams following %s changed or moved" % label)
    return rebuilt, len(encoded)
