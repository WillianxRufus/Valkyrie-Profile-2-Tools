# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Read and rebuild a bare SLZ overlay inside a fixed resource span."""

from dataclasses import dataclass
import struct

from . import slz, slz3


HEADER_SIZE = 0x10


@dataclass(frozen=True)
class Overlay:
    output: bytes
    stored_size: int
    fixed_span: int


def read(resource, resource_number, label, mode, fixed_span):
    resource = bytes(resource)
    if not HEADER_SIZE <= fixed_span <= len(resource):
        raise ValueError("%s has an invalid fixed SLZ span" % label)
    if resource[:3] != b"SLZ" or resource[3] != mode:
        raise ValueError(
            "resource %d is not the expected mode-%d %s overlay"
            % (resource_number, mode, label)
        )
    stored_size, expanded_size = struct.unpack_from("<II", resource, 4)
    stream_end = HEADER_SIZE + stored_size
    if stream_end > fixed_span:
        raise ValueError("%s SLZ stream exceeds its fixed span" % label)
    if any(resource[stream_end:fixed_span]):
        raise ValueError("%s fixed-span padding is not zero" % label)
    output = slz.decompress(resource[:stream_end])
    if len(output) != expanded_size:
        raise ValueError("%s expanded-size validation failed" % label)
    return Overlay(output, stored_size, fixed_span)


def replace(resource, output, resource_number, label, mode, fixed_span):
    resource = bytes(resource)
    old = read(resource, resource_number, label, mode, fixed_span)
    output = bytes(output)
    if len(output) != len(old.output):
        raise ValueError("%s expanded size changed" % label)
    if mode != 3:
        raise ValueError("%s uses unsupported rewrite mode %d" % (label, mode))
    next_offset = struct.unpack_from("<I", resource, 0x0C)[0]
    encoded = slz3.compress(output, next_offset=next_offset)
    if len(encoded) > fixed_span:
        raise ValueError(
            "recompressed %s needs 0x%X bytes but its fixed span holds 0x%X"
            % (label, len(encoded), fixed_span)
        )
    rebuilt = bytearray(resource)
    rebuilt[:fixed_span] = b"\0" * fixed_span
    rebuilt[:len(encoded)] = encoded
    rebuilt = bytes(rebuilt)
    new = read(rebuilt, resource_number, label, mode, fixed_span)
    if new.output != output:
        raise ValueError("rebuilt %s overlay did not read back" % label)
    if struct.unpack_from("<I", rebuilt, 0x0C)[0] != next_offset:
        raise ValueError("rebuilt %s overlay changed its stream chain" % label)
    if rebuilt[fixed_span:] != resource[fixed_span:]:
        raise ValueError("data following %s changed or moved" % label)
    return rebuilt, new.stored_size
