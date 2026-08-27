#!/usr/bin/env python3
"""tri-Ace SLZ decompressor (STORE / LZSS / LZSS+RLE / LZSS16)."""
import struct, sys


def decompress(data, mode=None, out_size=None):
    """Decompress an SLZ blob. If `data` starts with a 'SLZ' header, mode and"""
    sp = 0
    if len(data) >= 0x10 and data[0:3] == b"SLZ":
        mode = data[3]
        out_size = struct.unpack_from("<I", data, 8)[0]
        sp = 0x10
    if mode is None or out_size is None:
        raise ValueError("mode/out_size required when there is no SLZ header")

    out = bytearray(out_size)
    op = 0

    if mode == 0:  # STORE
        out[:out_size] = data[sp:sp + out_size]
        return bytes(out)

    flags = 0
    while op < out_size:
        flags >>= 1
        if flags <= 0xFFFF:               # reload control bits
            flags = 0x00FF0000 | data[sp]; sp += 1
            if mode == 3:
                flags |= 0xFF000000 | (data[sp] << 8); sp += 1

        if flags & 1:                     # literal
            out[op] = data[sp]; op += 1; sp += 1
            if mode == 3:
                out[op] = data[sp]; op += 1; sp += 1
        else:                             # match / run
            b0 = data[sp]; sp += 1
            b1 = data[sp]; sp += 1
            if mode == 2 and b1 >= 0xF0:   # RLE run
                if b1 > 0xF0:
                    length = (b1 & 0x0F) + 3
                    fill = b0
                else:                      # b1 == 0xF0 : long run
                    length = b0 + 0x13
                    fill = data[sp]; sp += 1
                for _ in range(length):
                    out[op] = fill; op += 1
            else:                          # LZSS back-reference
                pos = b0 | ((b1 & 0x0F) << 8)
                length = (b1 >> 4) + 3
                if mode == 3:
                    length = (length - 1) << 1
                    pos <<= 1
                src = op - pos
                for _ in range(length):
                    out[op] = out[src]; op += 1; src += 1

    return bytes(out)


def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    out = decompress(data)
    with open(sys.argv[2], "wb") as f:
        f.write(out)
    print("%d -> %d bytes" % (len(data), len(out)))


if __name__ == "__main__":
    main()
