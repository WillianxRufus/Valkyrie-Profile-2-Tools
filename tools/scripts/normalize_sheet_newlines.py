#!/usr/bin/env python3
"""Report or fix CRLF line breaks *inside* a sheet's quoted fields."""
import argparse
import csv
import glob
import io
import os
import sys


def field_internal_crlf(data):
    """Byte offsets of every ``\\r`` of a CRLF that sits inside quotes."""
    found = []
    in_quotes = False
    position = 0
    while position < len(data):
        byte = data[position]
        if byte == 0x22:                       # '"'
            if in_quotes and position + 1 < len(data) and data[position + 1] == 0x22:
                position += 2                  # an escaped quote, still inside
                continue
            in_quotes = not in_quotes
        elif (in_quotes and byte == 0x0D
              and position + 1 < len(data) and data[position + 1] == 0x0A):
            found.append(position)
        position += 1
    return found


def normalized(data):
    offsets = set(field_internal_crlf(data))
    if not offsets:
        return data, 0
    out = bytearray()
    for position, byte in enumerate(data):
        if position not in offsets:
            out.append(byte)
    return bytes(out), len(offsets)


def bare_record_terminators(data):
    """Byte offsets of every record-terminating ``"""
    found = []
    in_quotes = False
    position = 0
    while position < len(data):
        byte = data[position]
        if byte == 0x22:                       # '"'
            if in_quotes and position + 1 < len(data) and data[position + 1] == 0x22:
                position += 2
                continue
            in_quotes = not in_quotes
        elif not in_quotes and byte == 0x0A:
            if position == 0 or data[position - 1] != 0x0D:
                found.append(position)
        position += 1
    return found


def with_record_terminators(data):
    """Put the ``"""
    offsets = set(bare_record_terminators(data))
    if not offsets:
        return data, 0
    out = bytearray()
    for position, byte in enumerate(data):
        if position in offsets:
            out.append(0x0D)
        out.append(byte)
    return bytes(out), len(offsets)


def canonical(data):
    """Both halves of the convention at once."""
    data, fields = normalized(data)
    data, records = with_record_terminators(data)
    return data, fields, records


def read_rows(path):
    """Parse a sheet, tolerating whatever endings an editor left behind."""
    with open(path, "rb") as handle:
        data = handle.read()
    data, fields, records = canonical(data)
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows = list(reader)
    return rows, reader.fieldnames, (fields, records)


def repair_in_place(path):
    """Rewrite *path* in the canonical form.  Returns ``(fields, records)``."""
    with open(path, "rb") as handle:
        data = handle.read()
    fixed, fields, records = canonical(data)
    if fixed != data:
        with open(path, "wb") as handle:
            handle.write(fixed)
    return fields, records


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--write", action="store_true",
                        help="rewrite the files; default is to report only")
    args = parser.parse_args()

    paths = []
    for pattern in args.paths:
        paths.extend(sorted(glob.glob(pattern)) or [pattern])

    offenders = 0
    for path in paths:
        if not os.path.exists(path):
            print("missing: %s" % path, file=sys.stderr)
            offenders += 1
            continue
        with open(path, "rb") as handle:
            data = handle.read()
        fixed, count = normalized(data)
        fixed, restored = with_record_terminators(fixed)
        if not count and not restored:
            continue
        offenders += 1
        print("%s: %s%s%s"
              % (path,
                 "%d field-internal CRLF" % count if count else "",
                 "; " if count and restored else "",
                 "%d bare record terminator(s)" % restored if restored else ""))
        if args.write:
            with open(path, "wb") as handle:
                handle.write(fixed)
            print("  rewritten (%d -> %d bytes)" % (len(data), len(fixed)))

    if not offenders:
        print("checked %d file(s); record terminators are CRLF and every line "
              "break inside a quoted field is LF" % len(paths))
    return 1 if offenders and not args.write else 0


if __name__ == "__main__":
    sys.exit(main())
