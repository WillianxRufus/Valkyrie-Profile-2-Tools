"""Generic PK1 subresource rebuilding."""

import struct

from . import vp2_dcms as dcms


def repack_pk1_subresource(raw, target_tag, replacement, alignment=16,
                           target_offset=None):
    """Grow one PK1 subresource inside its existing outer ISO allocation."""
    entry_count = struct.unpack_from("<I", raw, 4)[0]
    table_end = struct.unpack_from("<I", raw, 8)[0]
    if table_end != 0x10 + entry_count * 16:
        raise ValueError("unsupported PK1 table layout")
    entries = []
    for number in range(entry_count):
        position = 0x10 + number * 16
        raw_tag = raw[position:position + 4]
        tag = raw_tag.split(b"\0", 1)[0].decode("ascii", "replace")
        flags, length, offset = struct.unpack_from("<III", raw, position + 4)
        if dcms.is_compression_trailer(raw_tag, offset, number, entry_count):
            continue
        if offset < table_end or offset + length > len(raw):
            raise ValueError("invalid PK1 subresource bounds")
        entries.append((position, tag, flags, length, offset))
    matches = [entry for entry in entries
               if entry[1] == target_tag and
               (target_offset is None or entry[4] == target_offset)]
    if len(matches) != 1:
        qualifier = (" at 0x%X" % target_offset
                     if target_offset is not None else "")
        raise ValueError("expected exactly one %s subresource%s" %
                         (target_tag, qualifier))
    target_position, _, _, target_length, _ = matches[0]
    if alignment > 1:
        remainder = (len(replacement) - target_length) % alignment
        if remainder:
            replacement = bytes(replacement) + b"\0" * (alignment - remainder)
    content_end = max(offset + length for _, _, _, length, offset in entries)
    trailing = bytes(raw[content_end:])
    if any(trailing):
        raise ValueError(
            "PK1 has %d bytes of non-zero trailing data; "
            "repack_pk1_subresource would shift it.  Use "
            "iso_space.repack_content_region." % len(trailing))
    rebuilt = bytearray(raw[:table_end])
    for position, tag, flags, length, offset in entries:
        payload = (replacement if position == target_position
                   else raw[offset:offset + length])
        new_offset = len(rebuilt)
        struct.pack_into("<III", rebuilt, position + 4, flags, len(payload), new_offset)
        rebuilt.extend(payload)
    rebuilt.extend(trailing)
    if len(rebuilt) > len(raw):
        def _declared_end(position):
            _flags, length, offset = struct.unpack_from("<III", rebuilt,
                                                        position + 4)
            return offset + length

        rebuilt_end = max(_declared_end(position)
                          for position, _, _, _, _ in entries)
        if rebuilt_end > len(raw):
            raise ValueError(
                "repacked PK1 is %d bytes and its last subresource ends at "
                "%d, past the %d-byte allocation; use "
                "iso_space.repack_content_region"
                % (len(rebuilt), rebuilt_end, len(raw)))
        overflow = rebuilt[len(raw):]
        if any(overflow):
            raise ValueError(
                "rebuilt PK1 needs %d bytes but the outer resource has %d, and "
                "the %d overflowing bytes are not zero padding" %
                (len(rebuilt), len(raw), len(overflow)))
        del rebuilt[len(raw):]
    else:
        rebuilt.extend(b"\0" * (len(raw) - len(rebuilt)))
    return bytes(rebuilt)
