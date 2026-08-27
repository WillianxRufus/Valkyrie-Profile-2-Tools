#!/usr/bin/env python3
"""Relocate a tri-Ace resource into fresh space at the end of an ISO."""
import math
import os
import struct

from .paths import TOOLS_DIR

HERE = os.fspath(TOOLS_DIR)

from . import triace_ps2_unpack as triace
from . import slz
from . import slz_compress

MASK = triace.MASK
SECTOR = triace.SECTOR
PVD_SECTOR = 16


def _locate(handle):
    for name, (seed, signature, offset, total) in triace.GAMES.items():
        handle.seek(offset)
        head = handle.read(4)
        if len(head) == 4 and struct.unpack("<I", head)[0] == signature:
            return name, seed, offset, total
    raise ValueError("no tri-Ace index table found (unsupported ISO)")


def _crypt(values, seed, total):
    """XOR the index with its evolving keystream (its own inverse)."""
    out = list(values)
    key = seed
    for index in range(total):
        out[0 * total + index] ^= key
        key = (key ^ ((key << 1) & MASK)) & MASK
        out[1 * total + index] ^= key
        key = (key ^ (~seed & MASK)) & MASK
        out[2 * total + index] ^= key
        key = (key ^ ((key << 2) & MASK) ^ seed) & MASK
    return out


def read_index(handle):
    """Return (seed, table_offset, total, decrypted values)."""
    _, seed, offset, total = _locate(handle)
    handle.seek(offset)
    raw = handle.read(total * 3 * 4)
    values = list(struct.unpack("<%dI" % (total * 3), raw))
    return seed, offset, total, _crypt(values, seed, total)


def write_index(handle, seed, offset, total, values):
    encrypted = _crypt(values, seed, total)
    handle.seek(offset)
    handle.write(struct.pack("<%dI" % (total * 3), *encrypted))


def read_volume_sectors(handle):
    handle.seek(PVD_SECTOR * SECTOR)
    block = handle.read(SECTOR)
    if block[1:6] != b"CD001" or block[0] != 1:
        return None
    return struct.unpack_from("<I", block, 80)[0]


def write_volume_sectors(handle, sectors):
    """Update the primary volume descriptor's both-endian volume space size."""
    handle.seek(PVD_SECTOR * SECTOR)
    block = bytearray(handle.read(SECTOR))
    if block[1:6] != b"CD001" or block[0] != 1:
        raise ValueError("no ISO9660 primary volume descriptor at sector %d"
                         % PVD_SECTOR)
    struct.pack_into("<I", block, 80, sectors)
    struct.pack_into(">I", block, 84, sectors)
    handle.seek(PVD_SECTOR * SECTOR)
    handle.write(bytes(block))


def _root_directory(handle):
    handle.seek(PVD_SECTOR * SECTOR)
    pvd = handle.read(SECTOR)
    if pvd[1:6] != b"CD001" or pvd[0] != 1:
        return None
    record = pvd[156:190]
    return (struct.unpack_from("<I", record, 2)[0],
            struct.unpack_from("<I", record, 10)[0])


def extend_last_file(handle, end_lba):
    """Grow the file whose extent ends last so it covers ``end_lba``."""
    located = _root_directory(handle)
    if located is None:
        return None
    root_lba, root_length = located
    handle.seek(root_lba * SECTOR)
    data = bytearray(handle.read(max(root_length, SECTOR)))

    best = None
    position = 0
    while position < len(data):
        length = data[position]
        if length == 0:
            position = (position // SECTOR + 1) * SECTOR
            continue
        lba = struct.unpack_from("<I", data, position + 2)[0]
        size = struct.unpack_from("<I", data, position + 10)[0]
        flags = data[position + 25]
        end = lba + (size + SECTOR - 1) // SECTOR
        if not flags & 2 and (best is None or end > best[2]):
            name_length = data[position + 32]
            name = bytes(data[position + 33:position + 33 + name_length])
            best = (position, lba, end, size, name.decode("ascii", "replace"))
        position += length
    if best is None:
        return None
    position, lba, end, size, name = best
    if end_lba <= end:
        return None
    new_size = (end_lba - lba) * SECTOR
    struct.pack_into("<I", data, position + 10, new_size)
    struct.pack_into(">I", data, position + 14, new_size)
    handle.seek(root_lba * SECTOR)
    handle.write(bytes(data))
    return {"name": name, "lba": lba, "old_size": size, "new_size": new_size,
            "old_end": end, "new_end": end_lba}


def take_vacated(vacated, sectors):
    """Claim ``sectors`` from a freed extent, or return ``None``."""
    for index, (lba, free) in enumerate(vacated):
        if free >= sectors:
            vacated.pop(index)
            if free > sectors:
                vacated.append((lba + sectors, free - sectors))
            return lba
    return None


def relocate(path, resource, payload, dvd5_limit=4700372992, pad_sectors=64,
             vacated=None):
    """Give ``resource`` a new home in ``path``, reusing freed space first."""
    if len(payload) % SECTOR:
        payload = payload + b"\0" * (SECTOR - len(payload) % SECTOR)
    sectors = len(payload) // SECTOR
    size = os.path.getsize(path)
    if size % SECTOR:
        raise ValueError("image size is not a whole number of sectors")

    reused = take_vacated(vacated, sectors) if vacated is not None else None
    start = reused
    if reused is None:
        start = size // SECTOR
        grown = len(payload) + pad_sectors * SECTOR
        if size <= dvd5_limit and size + grown > dvd5_limit:
            raise ValueError(
                "relocation would grow the image to %d bytes, past the %d-byte "
                "DVD-5 limit" % (size + grown, dvd5_limit))
    else:
        grown = 0

    with open(path, "r+b") as handle:
        seed, offset, total, values = read_index(handle)
        if not 0 <= resource < total:
            raise ValueError("resource #%d is outside the index" % resource)
        old_lba, old_sectors = values[resource], values[total + resource]
        declared = read_volume_sectors(handle)

        handle.seek(start * SECTOR)
        handle.write(payload)
        if reused is None and pad_sectors:
            handle.write(b"\0" * (pad_sectors * SECTOR))

        values[resource] = start
        values[total + resource] = sectors
        write_index(handle, seed, offset, total, values)
        end_lba = ((size + grown) // SECTOR if reused is None
                   else size // SECTOR)
        if declared is not None and end_lba > (declared or 0):
            write_volume_sectors(handle, end_lba)
        extended = extend_last_file(handle, end_lba)

    if vacated is not None and old_sectors:
        vacated.append((old_lba, old_sectors))

    return {
        "old_lba": old_lba, "old_sectors": old_sectors,
        "new_lba": start, "new_sectors": sectors,
        "pad_sectors": 0 if reused is not None else pad_sectors,
        "reused_vacated": reused is not None,
        "image_sectors": end_lba,
        "image_bytes": size + grown,
        "declared_sectors": declared,
        "extended_file": extended,
    }


def _parse_archive(raw):
    """Return ``(table_end, entries, content_end, tail_start, tail)``."""
    entry_count = struct.unpack_from("<I", raw, 4)[0]
    table_end = struct.unpack_from("<I", raw, 8)[0]
    if table_end != 0x10 + entry_count * 16:
        raise ValueError("unsupported PK1 table layout")
    entries = []
    for number in range(entry_count):
        position = 0x10 + number * 16
        tag = raw[position:position + 4].split(b"\0", 1)[0].decode("ascii", "replace")
        flags, length, offset = struct.unpack_from("<III", raw, position + 4)
        entries.append((position, tag, flags, length, offset))
    content_end = max(offset + length for _, _, _, length, offset in entries)
    tail_start = ((content_end + SECTOR - 1) // SECTOR) * SECTOR
    return table_end, entries, content_end, tail_start, bytes(raw[tail_start:])


def has_streamed_tail(raw):
    """Whether a PK1 carries data after its indexed content region."""
    return bool(_parse_archive(raw)[4])


FAST_RECOMPRESSIBLE = frozenset({"MRTA", "FISP"})
EXPENSIVE_RECOMPRESSIBLE = frozenset({"PAM"})
RECOMPRESSIBLE = FAST_RECOMPRESSIBLE | EXPENSIVE_RECOMPRESSIBLE


def _payloads(raw, entries, target_tag, replacement, recompress_limit,
              report, alignment, announce, budget=None, recompressible=None):
    """Bodies for every subresource: the target replaced, and as many"""
    def padded(body):
        if alignment > 1 and len(body) % alignment:
            return body + b"\0" * (alignment - len(body) % alignment)
        return body

    allowed = RECOMPRESSIBLE if recompressible is None else recompressible
    bodies, order = {}, []
    for position, tag, flags, length, offset in entries:
        if tag == target_tag:
            bodies[position] = padded(bytes(replacement))
            continue
        body = bytes(raw[offset:offset + length])
        bodies[position] = padded(body)
        if (tag in allowed
                and body[:3] == b"SLZ" and body[3] in (1, 2, 3)
                and (not recompress_limit or len(body) <= recompress_limit)):
            order.append((len(body), position, tag, body))

    def total():
        return sum(len(body) for body in bodies.values())

    for _size, position, tag, body in sorted(order, key=lambda item: item[0]):
        if budget is not None and total() <= budget:
            break
        plain = slz.decompress(body)
        if announce and len(plain) > 0x40000:
            announce("  recompressing %s, %.1f MB -- this takes a while"
                     % (tag, len(plain) / 1048576.0))
        packed = slz_compress.compress(plain, mode=body[3])
        if slz.decompress(packed) != plain:
            raise ValueError("%s re-encode did not round trip" % tag)
        if len(padded(packed)) < len(body):
            if report is not None:
                report.append((tag, len(body), len(padded(packed))))
            bodies[position] = padded(packed)

    return [(position, tag, flags, bodies[position])
            for position, tag, flags, _length, _offset in entries]


def _assemble(raw, table_end, payloads, tail_start, tail):
    """Lay the payloads out after the table and put the tail on its sector."""
    rebuilt = bytearray(raw[:table_end])
    for position, tag, flags, body in payloads:
        struct.pack_into("<III", rebuilt, position + 4,
                         flags, len(body), len(rebuilt))
        rebuilt.extend(body)
    rebuilt.extend(b"\0" * (tail_start - len(rebuilt)))
    rebuilt.extend(tail)
    return bytes(rebuilt)


def repack_content_region(raw, target_tag, replacement, recompress_limit=0,
                          report=None, alignment=4, announce=None,
                          recompressible=None):
    """Fit a larger subresource by recompressing its neighbours in place."""
    table_end, entries, _content_end, tail_start, tail = _parse_archive(raw)
    payloads = _payloads(raw, entries, target_tag, replacement,
                         recompress_limit, report, alignment, announce,
                         budget=tail_start - table_end,
                         recompressible=recompressible)
    used = table_end + sum(len(body) for _, _, _, body in payloads)
    if used > tail_start:
        raise ValueError(
            "content region holds %d bytes but the repack needs %d; recompress "
            "more neighbours or shrink the replacement by %d bytes"
            % (tail_start - table_end, used - table_end, used - tail_start))
    rebuilt = _assemble(raw, table_end, payloads, tail_start, tail)
    if len(rebuilt) != len(raw):
        raise ValueError("repacked archive changed size")
    return rebuilt, tail_start - used


def repack_grown(raw, target_tag, replacement, recompress_limit=0,
                 report=None, alignment=4, announce=None):
    """Rebuild the archive a whole number of sectors larger."""
    table_end, entries, _content_end, tail_start, tail = _parse_archive(raw)
    payloads = _payloads(raw, entries, target_tag, replacement,
                         recompress_limit, report, alignment, announce,
                         budget=math.inf)
    used = table_end + sum(len(body) for _, _, _, body in payloads)
    grown_start = ((used + SECTOR - 1) // SECTOR) * SECTOR
    if grown_start <= tail_start:
        raise ValueError(
            "replacement fits the existing allocation (%d bytes spare); use "
            "repack_content_region rather than relocating"
            % (tail_start - used))
    rebuilt = _assemble(raw, table_end, payloads, grown_start, tail)
    grown = len(rebuilt) - len(raw)
    if grown <= 0 or grown % SECTOR:
        raise ValueError("grown archive is not a whole number of added sectors")
    return rebuilt, grown // SECTOR


def append_subresource(raw, target_tag, replacement):
    """Rebuild a PK1 with ``target_tag`` relocated past the streamed tail."""
    entry_count = struct.unpack_from("<I", raw, 4)[0]
    table_end = struct.unpack_from("<I", raw, 8)[0]
    if table_end != 0x10 + entry_count * 16:
        raise ValueError("unsupported PK1 table layout")
    position = None
    for number in range(entry_count):
        at = 0x10 + number * 16
        tag = raw[at:at + 4].split(b"\0", 1)[0].decode("ascii", "replace")
        if tag == target_tag:
            if position is not None:
                raise ValueError("expected exactly one %s subresource" % target_tag)
            position = at
    if position is None:
        raise ValueError("no %s subresource" % target_tag)
    rebuilt = bytearray(raw)
    new_offset = len(rebuilt)
    flags = struct.unpack_from("<I", rebuilt, position + 4)[0]
    struct.pack_into("<III", rebuilt, position + 4,
                     flags, len(replacement), new_offset)
    rebuilt.extend(replacement)
    return bytes(rebuilt), new_offset
