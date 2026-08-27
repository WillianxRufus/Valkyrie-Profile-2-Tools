#!/usr/bin/env python3
"""Inspect VP2's MCPS2/DCMS dialogue resources in a tri-Ace PS2 ISO."""
import argparse
import csv
import os
import struct

from .paths import TOOLS_DIR

HERE = os.fspath(TOOLS_DIR)

from . import triace_ps2_unpack as triace
from .slz import decompress


CODEPAGE_LOW = "0123456789-+% !\"#$&'()*,./:;<=>"
assert len(CODEPAGE_LOW) == 0x1F

ENGLISH_CONTROLS = {token + 1: character
                    for token, character in enumerate(CODEPAGE_LOW)}
ENGLISH_CONTROLS[0x8080] = "\n"

CODEPAGE_UNUSED = (0x11, 0x12, 0x13, 0x17, 0x1D, 0x1E, 0x1F,
                   0x3C, 0x3D, 0x3E, 0x40, 0x41, 0x5C, 0x5D, 0x5E, 0x5F)


def decode_english_tokens(tokens):
    """Decode the ordinary VP2 USA (mcps2lib 1.50) glyph code page."""
    result = []
    for token in tokens:
        if token in ENGLISH_CONTROLS:
            result.append(ENGLISH_CONTROLS[token])
        elif 0x20 <= token <= 0x5F:
            result.append(chr(token + 0x1F))
        else:
            result.append("<%04X>" % token)
    return "".join(result)


def is_compression_trailer(tag_bytes, offset, number, count):
    """Is this table row the archive's compression trailer rather than data?"""
    return (tag_bytes[:3] in (b"SLZ", b"SLE")
            and offset == 0 and number == count - 1)


def parse_pk1(data):
    """Return (tag, offset, length) entries from a validated PK1 archive."""
    if len(data) < 0x20 or struct.unpack_from("<I", data, 0)[0] != 0:
        return []
    count = struct.unpack_from("<I", data, 4)[0] + 1
    table_bytes = count * 16
    if count < 1 or 0x10 + table_bytes > len(data):
        return []
    if struct.unpack_from("<I", data, 8)[0] != table_bytes:
        return []
    result = []
    for number in range(count):
        pos = 0x10 + number * 16
        raw_tag = data[pos:pos + 4]
        tag = raw_tag.split(b"\0", 1)[0].decode("ascii", "replace")
        _, length, offset = struct.unpack_from("<III", data, pos + 4)
        if is_compression_trailer(raw_tag, offset, number, count):
            continue
        if offset + length > len(data):
            return []
        result.append((tag, offset, length))
    return result


def read_entry(handle, table, total, index):
    sectors = table[total + index]
    if not sectors:
        return b""
    handle.seek(table[index] * triace.SECTOR)
    return handle.read(sectors * triace.SECTOR)


def dcms_section(raw):
    for sub_index, (tag, offset, length) in enumerate(parse_pk1(raw)):
        if tag == "DCMS":
            payload = raw[offset:offset + length]
            if payload[:3] != b"SLZ":
                raise ValueError("DCMS is not an SLZ stream")
            return sub_index, payload
    return None


def parse_messages(expanded):
    """Parse MCPS2's message index and preserve each string as glyph tokens."""
    if len(expanded) < 0x80 or not expanded.startswith(b"mcps2lib "):
        raise ValueError("not an mcps2lib container")
    version = expanded[9:13].decode("ascii", "replace")
    stored_size, table_start, text_start, text_end = struct.unpack_from("<IIII", expanded, 0x20)
    if text_end == 0 and version == "1.50":
        text_end = min(stored_size, len(expanded))
    if not (0x40 <= table_start <= text_start <= text_end <= len(expanded)):
        raise ValueError("invalid message table/text bounds")
    pointers = []
    for pos in range(table_start, text_start, 8):
        if pos + 8 > text_start:
            raise ValueError("message index is not an eight-byte table")
        message_id, relative_offset = struct.unpack_from("<II", expanded, pos)
        if message_id == 0 and relative_offset == 0:
            break
        if relative_offset >= text_end - text_start:
            raise ValueError("message %d points outside text data" % message_id)
        pointers.append((message_id, relative_offset))

    next_offset = {}
    offsets = sorted(set(relative for _, relative in pointers))
    for position, relative in enumerate(offsets):
        next_offset[relative] = offsets[position + 1] if position + 1 < len(offsets) else text_end - text_start

    messages = []
    for message_index, (message_id, relative_offset) in enumerate(pointers):
        start = text_start + relative_offset
        limit = text_start + next_offset[relative_offset]
        position = start
        tokens = []
        terminated = False
        while position < limit:
            first = expanded[position]
            position += 1
            if first == 0:
                terminated = True
                break
            if first >= 0x80:
                if position >= limit:
                    raise ValueError("message %d ends inside a two-byte token" % message_id)
                token = first | (expanded[position] << 8)
                position += 1
            else:
                token = first
            tokens.append(token)
        raw = expanded[start:position]
        text = ""
        text_status = "not_applicable"
        if version == "1.50":
            text = decode_english_tokens(tokens)
            unknown_count = text.count("<")
            if unknown_count == 0:
                text_status = "decoded"
            elif len(tokens) >= unknown_count * 5:
                text_status = "readable_with_controls"
            else:
                text_status = "structured_or_binary"
        messages.append({
            "message_index": message_index,
            "message_id": message_id,
            "text_byte_offset": relative_offset,
            "byte_length": len(raw),
            "terminated": int(terminated),
            "raw_hex": raw.hex(" ").upper(),
            "tokens": " ".join("%04X" % token for token in tokens),
            "text": text,
            "text_status": text_status,
        })
    return messages


def messages_from_iso(iso_path):
    """Return {outer-index: [message rows]} for every DCMS resource."""
    result = {}
    with open(iso_path, "rb") as handle:
        _, total, table = triace.load_table(handle)
        for index in range(total):
            raw = read_entry(handle, table, total, index)
            if not raw or triace.classify(raw, len(raw)) != "pk1":
                continue
            found = dcms_section(raw)
            if found:
                result[index] = parse_messages(decompress(found[1]))
    return result


def describe(iso_path):
    rows = []
    with open(iso_path, "rb") as handle:
        game, total, table = triace.load_table(handle)
        for index in range(total):
            raw = read_entry(handle, table, total, index)
            if not raw or triace.classify(raw, len(raw)) != "pk1":
                continue
            found = dcms_section(raw)
            if not found:
                continue
            sub_index, compressed = found
            try:
                expanded = decompress(compressed)
            except (IndexError, ValueError, struct.error) as exc:
                raise RuntimeError("#%04d has unreadable DCMS: %s" % (index, exc))
            rows.append({
                "index": index,
                "pk1_bytes": len(raw),
                "dcms_sub_index": sub_index,
                "slz_mode": compressed[3],
                "compressed_bytes": len(compressed),
                "decompressed_bytes": len(expanded),
                "format": expanded[:16].rstrip(b"\0").decode("ascii", "replace"),
            })
    return game, rows


def cmd_report(args):
    game, rows = describe(args.iso)
    formats = sorted(set(row["format"] for row in rows))
    print("game=%s  DCMS resources=%d" % (game, len(rows)))
    print("format: %s" % ", ".join(formats))
    print("compressed: %.1f MiB  decompressed: %.1f MiB" % (
        sum(row["compressed_bytes"] for row in rows) / 1048576,
        sum(row["decompressed_bytes"] for row in rows) / 1048576,
    ))


def cmd_compare(args):
    game_a, rows_a = describe(args.iso_a)
    game_b, rows_b = describe(args.iso_b)
    if game_a != game_b:
        raise RuntimeError("different game indexes: %s vs %s" % (game_a, game_b))
    by_a = {row["index"]: row for row in rows_a}
    by_b = {row["index"]: row for row in rows_b}
    indexes = sorted(set(by_a) | set(by_b))
    output = []
    with open(args.iso_a, "rb") as a, open(args.iso_b, "rb") as b:
        _, total_a, table_a = triace.load_table(a)
        _, total_b, table_b = triace.load_table(b)
        for index in indexes:
            left, right = by_a.get(index), by_b.get(index)
            status = "only-in-a" if not right else "only-in-b" if not left else "same"
            if left and right:
                left_raw = read_entry(a, table_a, total_a, index)
                right_raw = read_entry(b, table_b, total_b, index)
                left_dcms = dcms_section(left_raw)[1]
                right_dcms = dcms_section(right_raw)[1]
                if left_dcms != right_dcms:
                    status = "changed"
            row = {"index": index, "status": status}
            for prefix, value in (("a", left), ("b", right)):
                for key in ("dcms_sub_index", "slz_mode", "compressed_bytes",
                            "decompressed_bytes", "format"):
                    row[prefix + "_" + key] = "" if value is None else value[key]
            output.append(row)
    changed = sum(row["status"] == "changed" for row in output)
    print("DCMS resources: %d shared; %d changed" % (
        sum(row["status"] not in ("only-in-a", "only-in-b") for row in output), changed))
    if args.csv:
        parent = os.path.dirname(os.path.abspath(args.csv))
        if parent:
            os.makedirs(parent, exist_ok=True)
        fields = ["index", "status", "a_dcms_sub_index", "a_slz_mode",
                  "a_compressed_bytes", "a_decompressed_bytes", "a_format",
                  "b_dcms_sub_index", "b_slz_mode", "b_compressed_bytes",
                  "b_decompressed_bytes", "b_format"]
        with open(args.csv, "w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            writer.writerows(output)
        print("wrote %s" % args.csv)


def cmd_extract(args):
    changed = None
    if args.changed_against:
        _, other_rows = describe(args.changed_against)
        other_indexes = {row["index"] for row in other_rows}
        changed = set()
        with open(args.iso, "rb") as source, open(args.changed_against, "rb") as other:
            _, total, table = triace.load_table(source)
            _, other_total, other_table = triace.load_table(other)
            for index in other_indexes:
                if index >= total or index >= other_total:
                    continue
                raw = read_entry(source, table, total, index)
                other_raw = read_entry(other, other_table, other_total, index)
                if dcms_section(raw)[1] != dcms_section(other_raw)[1]:
                    changed.add(index)
    os.makedirs(args.out_dir, exist_ok=True)
    written = 0
    with open(args.iso, "rb") as handle:
        _, total, table = triace.load_table(handle)
        for index in range(total):
            if changed is not None and index not in changed:
                continue
            raw = read_entry(handle, table, total, index)
            if not raw or triace.classify(raw, len(raw)) != "pk1":
                continue
            found = dcms_section(raw)
            if not found:
                continue
            _, payload = found
            suffix = ".dcms" if args.decompress else ".slz"
            target = os.path.join(args.out_dir, "%04d%s" % (index, suffix))
            with open(target, "wb") as out:
                out.write(decompress(payload) if args.decompress else payload)
            written += 1
    print("extracted %d DCMS resources -> %s" % (written, args.out_dir))


def cmd_messages(args):
    primary = messages_from_iso(args.iso)
    paired = messages_from_iso(args.paired) if args.paired else None
    if paired is not None:
        missing = sorted(set(primary) - set(paired))
        if missing:
            raise RuntimeError("paired ISO lacks DCMS resources: %s" % ", ".join(map(str, missing)))
        extra = len(set(paired) - set(primary))
        if extra:
            print("note: paired ISO has %d extra DCMS resource(s), not exported" % extra)

    source_label = clean_label(args.source_label)
    paired_label = clean_label(args.paired_label)
    fields = ["resource_index", "message_index", "message_id", "text_byte_offset",
              "byte_length", "terminated", source_label + "_raw_hex",
              source_label + "_tokens", source_label + "_text",
              source_label + "_text_status"]
    if paired is not None:
        fields += [paired_label + "_text_byte_offset", paired_label + "_byte_length",
                   paired_label + "_terminated", paired_label + "_raw_hex",
                   paired_label + "_tokens", paired_label + "_text",
                   paired_label + "_text_status",
                   paired_label + "_message_id", paired_label + "_message_count",
                   "pairing_status", "message_id_matches", args.translation_column]
    parent = os.path.dirname(os.path.abspath(args.csv))
    if parent:
        os.makedirs(parent, exist_ok=True)
    count = 0
    with open(args.csv, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for resource_index in sorted(primary):
            rows = primary[resource_index]
            companion = paired[resource_index] if paired is not None else None
            same_count = companion is not None and len(rows) == len(companion)
            for row_number, row in enumerate(rows):
                output = {"resource_index": resource_index}
                output.update(row)
                output[source_label + "_raw_hex"] = output.pop("raw_hex")
                output[source_label + "_tokens"] = output.pop("tokens")
                output[source_label + "_text"] = output.pop("text")
                output[source_label + "_text_status"] = output.pop("text_status")
                if companion is not None and same_count:
                    other = companion[row_number]
                    output.update({
                        paired_label + "_text_byte_offset": other["text_byte_offset"],
                        paired_label + "_byte_length": other["byte_length"],
                        paired_label + "_terminated": other["terminated"],
                        paired_label + "_raw_hex": other["raw_hex"],
                        paired_label + "_tokens": other["tokens"],
                        paired_label + "_text": other["text"],
                        paired_label + "_text_status": other["text_status"],
                        paired_label + "_message_id": other["message_id"],
                        paired_label + "_message_count": len(companion),
                        "pairing_status": "position",
                        "message_id_matches": int(row["message_id"] == other["message_id"]),
                        args.translation_column: "",
                    })
                elif companion is not None:
                    output.update({
                        paired_label + "_message_count": len(companion),
                        "pairing_status": "message_count_mismatch",
                        "message_id_matches": "",
                        args.translation_column: "",
                    })
                writer.writerow(output)
                count += 1
    print("wrote %d message rows -> %s" % (count, args.csv))


def clean_label(value):
    """Make a user-supplied language label safe and consistent for CSV fields."""
    label = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
    if not label:
        raise ValueError("language labels need at least one letter or digit")
    return label


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="count and describe DCMS resources")
    report.add_argument("iso")
    report.set_defaults(func=cmd_report)
    compare = commands.add_parser("compare", help="compare DCMS streams in two ISOs")
    compare.add_argument("iso_a")
    compare.add_argument("iso_b")
    compare.add_argument("--csv", help="write the paired-resource report as CSV")
    compare.set_defaults(func=cmd_compare)
    extract = commands.add_parser("extract", help="export raw SLZ or decompressed MCPS2 resources")
    extract.add_argument("iso")
    extract.add_argument("out_dir")
    extract.add_argument("--changed-against", metavar="ISO",
                         help="only export DCMS streams different from this ISO")
    extract.add_argument("--decompress", action="store_true",
                         help="write decompressed *.dcms MCPS2 containers")
    extract.set_defaults(func=cmd_extract)
    messages = commands.add_parser("messages", help="export indexed glyph/control tokens as CSV")
    messages.add_argument("iso", help="source ISO; normally the original Japanese image")
    messages.add_argument("csv", help="output CSV; existing file is replaced")
    messages.add_argument("--paired", metavar="ISO",
                          help="include equal-keyed tokens from a translated comparison ISO")
    messages.add_argument("--source-label", default="jp", metavar="NAME",
                          help="column prefix for the source ISO (default: jp)")
    messages.add_argument("--paired-label", default="paired", metavar="NAME",
                          help="column prefix for --paired (default: paired)")
    messages.add_argument("--translation-column", default="translation", metavar="NAME",
                          help="empty editable translation column (default: translation)")
    messages.set_defaults(func=cmd_messages)
    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, "error: %s\n" % exc)


if __name__ == "__main__":
    main()
