#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Classify every entry in a VP2 USA ISO by writer coverage."""
import argparse
import csv
import struct
import sys

from . import triace_ps2_unpack as triace
from . import vp2_dcms as dcms
from .slz import decompress


CLASSIFICATION_ORDER = [
    "local_font_dcms",
    "fontless_dcms_compatible",
    "fontless_dcms_with_payload",
    "dcms_other_version",
    "container_slz",
    "container_zls",
    "container_sle",
    "non_text",
    "empty",
    "unreadable",
]


def parse_dcms_header(expanded):
    """Read the 15-word mcps2lib header words, or return ``None``."""
    if len(expanded) < 0x5C or not expanded.startswith(b"mcps2lib "):
        return None
    (stored_size, table_start, text_start, text_end, font_start,
     glyph_count, texture_width, texture_height, glyph_width,
     glyph_height, glyph_pitch, pixel_format, glyph_base,
     metric_count, flags) = struct.unpack_from("<15I", expanded, 0x20)
    version = expanded[9:13].decode("ascii", "replace")
    return {
        "mcps2_version": version,
        "stored_size": stored_size,
        "table_start": table_start,
        "text_start": text_start,
        "text_end": text_end,
        "font_start": font_start,
        "glyph_count": glyph_count,
        "texture_width": texture_width,
        "texture_height": texture_height,
        "glyph_width": glyph_width,
        "glyph_height": glyph_height,
        "glyph_pitch": glyph_pitch,
        "pixel_format": pixel_format,
        "glyph_base": glyph_base,
        "metric_count": metric_count,
        "flags": flags,
    }


def has_local_font(info):
    """Mirror vp2_scene_inventory.parse_local_font's success conditions."""
    if info is None:
        return False
    return bool(info["glyph_count"] and info["font_start"]
                and info["glyph_height"] and info["glyph_pitch"])


def classify_dcms(info):
    if info is None:
        return "non_text"
    if info["mcps2_version"] != "1.50":
        return "dcms_other_version"
    if has_local_font(info):
        return "local_font_dcms"
    if info["text_end"] == 0:
        return "fontless_dcms_compatible"
    return "fontless_dcms_with_payload"


def peek_zls_walker(buf, length):
    """Return inner content kind of a ZLS wrapper, or None if not ZLS."""
    if length < 0x20 or buf[:4] != b"ZLS\0":
        return None
    outer_size, span = struct.unpack_from("<I4xI", buf, 4)
    if span < 0x10 or span > length:
        return None
    inner = buf[0x10:span]
    if inner[:3] == b"SLZ":
        return "slz"
    return "zls"


def classify_entry(raw_bytes):
    """Return (classification, info_dict-or-None)."""
    if not raw_bytes:
        return "empty", None
    cls = triace.classify(raw_bytes, len(raw_bytes))
    if cls == "pk1":
        for tag, offset, length in dcms.parse_pk1(raw_bytes):
            if tag != "DCMS":
                continue
            packed = raw_bytes[offset:offset + length]
            try:
                expanded = decompress(packed)
            except (IndexError, ValueError, struct.error):
                return "unreadable", None
            info = parse_dcms_header(expanded)
            classification = classify_dcms(info)
            messages = dcms.parse_messages(expanded)
            info_out = dict(info or {})
            info_out["decompressed_bytes"] = len(expanded)
            info_out["message_count"] = len(messages)
            return classification, info_out
        return "non_text", None
    if cls == "slz":
        return "container_slz", None
    if cls == "zls":
        inner_kind = peek_zls_walker(raw_bytes, len(raw_bytes))
        if inner_kind == "slz":
            return "container_slz", None
        return "container_zls", None
    if cls == "sle":
        return "container_sle", None
    if cls == "sys":
        return "non_text", None
    return "non_text", None


HEADERS = [
    "resource", "classification", "mcps2_version", "text_start", "text_end",
    "font_start", "glyph_count", "message_count", "decompressed_bytes",
    "error",
]


def audit_iso(iso_path, output):
    writer = csv.DictWriter(output, fieldnames=HEADERS)
    writer.writeheader()
    with open(iso_path, "rb") as source:
        _, total, table = triace.load_table(source)
        for index in range(total):
            raw = dcms.read_entry(source, table, total, index)
            try:
                classification, info = classify_entry(raw)
            except (OSError, ValueError, IndexError, struct.error) as exc:
                writer.writerow({
                    "resource": index, "classification": "unreadable",
                    "error": str(exc),
                })
                continue
            row = {"resource": index, "classification": classification}
            if info:
                row.update({
                    "mcps2_version": info.get("mcps2_version", ""),
                    "text_start": "0x%X" % info.get("text_start", 0),
                    "text_end": "0x%X" % info.get("text_end", 0),
                    "font_start": "0x%X" % info.get("font_start", 0),
                    "glyph_count": info.get("glyph_count", 0),
                    "message_count": info.get("message_count", 0),
                    "decompressed_bytes": info.get("decompressed_bytes", 0),
                })
            else:
                row.update({
                    "mcps2_version": "", "text_start": "", "text_end": "",
                    "font_start": "", "glyph_count": "", "message_count": "",
                    "decompressed_bytes": "",
                })
            row["error"] = ""
            writer.writerow(row)


def summarise(iso_path):
    counts = {k: 0 for k in CLASSIFICATION_ORDER}
    counts["non_text_padded"] = 0
    with open(iso_path, "rb") as source:
        _, total, table = triace.load_table(source)
        for index in range(total):
            raw = dcms.read_entry(source, table, total, index)
            try:
                classification, _ = classify_entry(raw)
            except (OSError, ValueError, IndexError, struct.error):
                classification = "unreadable"
            counts[classification] = counts.get(classification, 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("iso", help="USA ISO to classify")
    parser.add_argument("output", nargs="?",
                        help="CSV path; omit for stdout")
    parser.add_argument("--summary", action="store_true",
                        help="print category counts and exit")
    args = parser.parse_args()

    if args.summary:
        counts = summarise(args.iso)
        for key in CLASSIFICATION_ORDER:
            print(f"{key:35s} {counts.get(key, 0)}")
        others = {k: v for k, v in counts.items()
                  if k not in CLASSIFICATION_ORDER and v}
        for key, value in sorted(others.items()):
            print(f"{key:35s} {value}")
        return

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as handle:
            audit_iso(args.iso, handle)
        print("wrote %s" % args.output)
    else:
        audit_iso(args.iso, sys.stdout)


if __name__ == "__main__":
    main()
