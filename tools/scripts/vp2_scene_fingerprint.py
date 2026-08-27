#!/usr/bin/env python3
"""Decode VP2 local-font scene text by matching glyph bitmap fingerprints."""
import argparse
import csv
import hashlib
import json
import os
import re


from .paths import TOOLS_DIR

HERE = os.fspath(TOOLS_DIR)

from .scene_codec import REFERENCE_BY_CODEPOINT, REFERENCE_FONT_RESOURCE
from .vp2_dcms import ENGLISH_CONTROLS


_CODEPAGE_ACCENTS = None


def codepage_accents():
    global _CODEPAGE_ACCENTS
    if _CODEPAGE_ACCENTS is None:
        from .vp2_shared_font import SHARED_EXTENSION_TOKENS
        _CODEPAGE_ACCENTS = {token: character for character, token
                             in SHARED_EXTENSION_TOKENS.items()}
    return _CODEPAGE_ACCENTS


OUTPUT_FIELDS = [
    "resource_index", "message_index", "message_id", "text_byte_offset",
    "byte_length", "matched_glyphs", "unknown_glyphs", "glyph_coverage",
    "decoded_text", "search_text", "source_tokens", "source_raw_hex",
]
TOKEN_TAG = re.compile(r"<[^>]+>")


def load_metadata(resource_dir):
    json_paths = [name for name in os.listdir(resource_dir) if name.endswith(".json")]
    if len(json_paths) != 1:
        raise ValueError("expected one metadata JSON in %s" % resource_dir)
    path = os.path.join(resource_dir, json_paths[0])
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def inventory_resources(inventory_dir):
    for name in sorted(os.listdir(inventory_dir)):
        resource_dir = os.path.join(inventory_dir, name)
        if not name.startswith("resource-") or not os.path.isdir(resource_dir):
            continue
        yield resource_dir, load_metadata(resource_dir)


def glyph_blocks(resource_dir, metadata):
    font_name = metadata["files"]["font"]
    path = os.path.join(resource_dir, font_name)
    with open(path, "rb") as source:
        font = source.read()
    glyph_bytes = metadata["glyph_pitch"] * metadata["glyph_height"] // 2
    expected = metadata["glyph_count"] * glyph_bytes
    if len(font) < expected:
        raise ValueError("short font payload: %s" % path)
    return [font[offset:offset + glyph_bytes]
            for offset in range(0, expected, glyph_bytes)]


def token_slot(token, glyph_base, glyph_count):
    """Return a local-font slot for a glyph token."""
    if token < 0x100:
        code = token
    elif (token & 0xFF) >= 0x80:
        code = (token & 0xFF) - 0x80 + (token >> 8) * 0x80
    else:
        return None
    slot = code - glyph_base
    return slot if 0 <= slot < glyph_count else None


def reference_fingerprints(inventory_dir, reference_resource):
    resource_dir = os.path.join(inventory_dir, "resource-%04d" % reference_resource)
    metadata = load_metadata(resource_dir)
    blocks = glyph_blocks(resource_dir, metadata)
    characters = {}
    conflicts = {}
    for token, character in REFERENCE_BY_CODEPOINT.items():
        slot = token_slot(token, metadata["glyph_base"], metadata["glyph_count"])
        if slot is None:
            continue
        digest = hashlib.sha1(blocks[slot]).hexdigest()
        if digest in characters and characters[digest] != character:
            conflicts.setdefault(digest, {characters[digest]}).add(character)
        else:
            characters[digest] = character
    for digest in conflicts:
        characters.pop(digest, None)
    return characters, metadata


def local_alphabet(resource_dir, metadata, fingerprints):
    result = {}
    for slot, block in enumerate(glyph_blocks(resource_dir, metadata)):
        character = fingerprints.get(hashlib.sha1(block).hexdigest())
        if character is not None:
            result[slot] = character
    return result


def parse_tokens(value):
    return [int(token, 16) for token in value.split()] if value else []


PAGE_BREAK = 0x8081
PAGE_BREAK_TEXT = "\n---\n"


def render_tokens(tokens, metadata, alphabet):
    parts = []
    matched = 0
    unknown = 0
    for token in tokens:
        slot = token_slot(token, metadata["glyph_base"], metadata["glyph_count"])
        if slot is not None:
            if slot in alphabet:
                parts.append(alphabet[slot])
                matched += 1
            else:
                parts.append("<?>")
                unknown += 1
        elif token == 0x8080:
            parts.append("\n")
        elif token == PAGE_BREAK:
            parts.append(PAGE_BREAK_TEXT)
        elif token == 0x8082:
            parts.append("<END>")
        elif token in codepage_accents():
            parts.append(codepage_accents()[token])
        elif token in ENGLISH_CONTROLS:
            parts.append(ENGLISH_CONTROLS[token])
        elif 0x20 <= token <= 0x5F:
            parts.append(chr(token + 0x1F))
        else:
            parts.append("<%04X>" % token)
    return "".join(parts), matched, unknown


def searchable_text(decoded):
    text = TOKEN_TAG.sub(" ", decoded)
    return " ".join(text.replace("---", " ").split())


def decode_inventory(inventory_dir, fingerprints):
    for resource_dir, metadata in inventory_resources(inventory_dir):
        alphabet = local_alphabet(resource_dir, metadata, fingerprints)
        messages_path = os.path.join(resource_dir, metadata["files"]["messages"])
        with open(messages_path, newline="", encoding="utf-8") as source:
            for row in csv.DictReader(source):
                decoded, matched, unknown = render_tokens(
                    parse_tokens(row["tokens"]), metadata, alphabet)
                glyph_total = matched + unknown
                coverage = (100.0 * matched / glyph_total) if glyph_total else 0.0
                yield {
                    "resource_index": metadata["resource_index"],
                    "message_index": row["message_index"],
                    "message_id": row["message_id"],
                    "text_byte_offset": row["text_byte_offset"],
                    "byte_length": row["byte_length"],
                    "matched_glyphs": matched,
                    "unknown_glyphs": unknown,
                    "glyph_coverage": "%.1f" % coverage,
                    "decoded_text": decoded,
                    "search_text": searchable_text(decoded),
                    "source_tokens": row["tokens"],
                    "source_raw_hex": row["raw_hex"],
                }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inventory_dir", help="scene inventory directory")
    parser.add_argument("csv", help="searchable CSV to create")
    parser.add_argument("--reference-resource", type=int,
                        default=REFERENCE_FONT_RESOURCE,
                        help="decoded reference font resource (default: 33)")
    parser.add_argument("--contains", action="append", default=[],
                        help="print rows containing this text (repeatable)")
    args = parser.parse_args()
    try:
        fingerprints, reference = reference_fingerprints(
            args.inventory_dir, args.reference_resource)
        rows = list(decode_inventory(args.inventory_dir, fingerprints))
        parent = os.path.dirname(os.path.abspath(args.csv))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        print("reference #%d: %d unambiguous glyph fingerprints" %
              (args.reference_resource, len(fingerprints)))
        print("decoded %d messages -> %s" % (len(rows), args.csv))
        needles = [needle.casefold() for needle in args.contains]
        hits = [row for row in rows
                if needles and any(needle in row["search_text"].casefold()
                                   for needle in needles)]
        for row in hits:
            print("#%04d message %s (%.1f%%): %s" %
                  (row["resource_index"], row["message_id"],
                   float(row["glyph_coverage"]), row["search_text"]))
        if needles:
            print("matches: %d" % len(hits))
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        parser.exit(1, "error: %s\n" % exc)


if __name__ == "__main__":
    main()
