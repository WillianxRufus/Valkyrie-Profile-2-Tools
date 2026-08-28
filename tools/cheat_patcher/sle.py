# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""tri-Ace SLE reveal/conceal and chained-stream support."""

from dataclasses import dataclass
import struct

from . import slz


KEY = bytes.fromhex("66 66 54 42 B3 79 F0 C7 E7 D5 1E 4B 7B A4 1C 7D")
HEADER_SIZE = 0x10


@dataclass(frozen=True)
class Stream:
    number: int
    offset: int
    stored_size: int
    expanded_size: int
    next_offset: int
    mode: int
    encoded: bytes
    revealed: bytes
    output: bytes


def reveal(data):
    """Return one SLE stream as an ordinary SLZ stream."""
    if len(data) < HEADER_SIZE or data[:3] != b"SLE":
        raise ValueError("not an SLE stream")
    stored_size = struct.unpack_from("<I", data, 4)[0]
    end = HEADER_SIZE + stored_size
    if end > len(data):
        raise ValueError("truncated SLE body")
    revealed = bytearray(data[:end])
    for position in range(stored_size):
        addend = (3 + 3 * position) & 0xFF
        revealed[HEADER_SIZE + position] = (
            (revealed[HEADER_SIZE + position] - addend) & 0xFF
        ) ^ KEY[position & 0x0F]
    revealed[2] = ord("Z")
    return bytes(revealed)


def conceal(data):
    """Return one ordinary SLZ stream encoded as SLE."""
    if len(data) < HEADER_SIZE or data[:3] != b"SLZ":
        raise ValueError("not an SLZ stream")
    stored_size = struct.unpack_from("<I", data, 4)[0]
    end = HEADER_SIZE + stored_size
    if end != len(data):
        raise ValueError(
            "SLZ stream length %d does not match header length %d"
            % (len(data), end)
        )
    concealed = bytearray(data)
    for position in range(stored_size):
        plain = concealed[HEADER_SIZE + position]
        concealed[HEADER_SIZE + position] = (
            (plain ^ KEY[position & 0x0F]) + 3 + 3 * position
        ) & 0xFF
    concealed[2] = ord("E")
    return bytes(concealed)


def iter_streams(data):
    """Yield structurally decoded SLE streams from a resource."""
    offset = HEADER_SIZE if data[:4] == b"ZLS\0" else 0
    number = 0
    while offset + HEADER_SIZE <= len(data):
        if data[offset:offset + 3] != b"SLE":
            if number == 0:
                raise ValueError("resource contains no SLE stream")
            raise ValueError("expected chained SLE stream at 0x%X" % offset)
        stored_size, expanded_size, next_offset = struct.unpack_from(
            "<III", data, offset + 4
        )
        end = offset + HEADER_SIZE + stored_size
        if end > len(data):
            raise ValueError("truncated SLE stream %d" % number)
        encoded = bytes(data[offset:end])
        revealed = reveal(encoded)
        output = slz.decompress(revealed)
        if len(output) != expanded_size:
            raise ValueError("SLE stream %d expanded-size mismatch" % number)
        yield Stream(
            number, offset, stored_size, expanded_size, next_offset,
            encoded[3], encoded, revealed, output
        )
        if not next_offset:
            return
        if next_offset < HEADER_SIZE + stored_size:
            raise ValueError("invalid SLE next-stream offset %d" % next_offset)
        offset += next_offset
        number += 1
