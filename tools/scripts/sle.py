#!/usr/bin/env python3
"""tri-Ace SLE deobfuscator and decompressor."""
import struct
import sys

from . import slz


KEY = bytes.fromhex("66 66 54 42 B3 79 F0 C7 E7 D5 1E 4B 7B A4 1C 7D")
HEADER_SIZE = 0x10


def reveal(data):
    """Return one SLE stream as an ordinary SLZ stream."""
    if len(data) < HEADER_SIZE or data[:3] != b"SLE":
        raise ValueError("not an SLE stream")
    stored_size = struct.unpack_from("<I", data, 4)[0]
    end = HEADER_SIZE + stored_size
    if end > len(data):
        raise ValueError("truncated SLE body: need %d bytes, have %d" %
                         (stored_size, len(data) - HEADER_SIZE))

    revealed = bytearray(data[:end])
    for position in range(stored_size):
        addend = (3 + 3 * position) & 0xFF
        revealed[HEADER_SIZE + position] = (
            (revealed[HEADER_SIZE + position] - addend) & 0xFF
        ) ^ KEY[position & 0x0F]
    revealed[2] = ord("Z")
    return bytes(revealed)


def decompress(data):
    """Reveal and decompress one SLE stream."""
    return slz.decompress(reveal(data))


def streams(data):
    """Yield ``(number, offset, output)`` from a bare or ZLS-wrapped entry."""
    if data[:4] == b"ZLS\0":
        data = data[HEADER_SIZE:]
    offset = 0
    number = 0
    while offset + HEADER_SIZE <= len(data) and data[offset:offset + 3] == b"SLE":
        stored_size, _, next_offset = struct.unpack_from("<III", data, offset + 4)
        end = offset + HEADER_SIZE + stored_size
        if end > len(data):
            raise ValueError("truncated SLE stream %d" % number)
        yield number, offset, decompress(data[offset:end])
        if not next_offset:
            return
        if next_offset < HEADER_SIZE or offset + next_offset <= offset:
            raise ValueError("invalid SLE next-stream offset %d" % next_offset)
        offset += next_offset
        number += 1


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], "rb") as source:
        data = source.read()
    decoded = list(streams(data))
    if not decoded:
        raise ValueError("input contains no SLE stream")
    multiple = len(decoded) > 1
    for number, _, output in decoded:
        path = "%s.%d" % (sys.argv[2], number) if multiple else sys.argv[2]
        with open(path, "wb") as target:
            target.write(output)
        print("stream %d: %d bytes -> %s" % (number, len(output), path))


if __name__ == "__main__":
    main()
