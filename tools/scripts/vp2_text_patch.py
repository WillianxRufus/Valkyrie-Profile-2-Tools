#!/usr/bin/env python3
"""Build a safe, same-size VP2 USA text-patch ISO from a translation CSV."""
import argparse
import collections
import csv
import os
import struct
import sys

from .paths import TOOLS_DIR

HERE = os.fspath(TOOLS_DIR)

from . import slz
from . import slz_compress
from . import triace_ps2_unpack as triace
from . import vp2_dcms as dcms
from . import vp2_shared_font as shared_font
from .vp2_shared_font import (
    SHARED_FONT_ENTRY,
    SHARED_ACCENT_DONORS,
    SHARED_EXTENSION_TOKENS,
    _round_up,
    shared_font_stream,
    patch_shared_font,
    install_glyphs,
    verify_shared_font_output,
    describe_install,
)


SUPPORTED_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    " ?-',.\n"
)
SUPPORTED_CHARS |= set(dcms.ENGLISH_CONTROLS.values())
CONTROL_TO_TOKEN = {value: token for token, value in dcms.ENGLISH_CONTROLS.items()}


def parse_resources(value):
    if value is None:
        return None
    try:
        result = {int(part.strip()) for part in value.split(",") if part.strip()}
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--resources uses comma-separated integers") from exc
    if not result:
        raise argparse.ArgumentTypeError("--resources must name at least one resource")
    return result


def encode_english_text(text, accent_tokens=None):
    """Encode a confirmed ASCII subset of the USA mcps2lib 1.50 code page."""
    accent_tokens = accent_tokens or {}
    unsupported = sorted(set(text) - SUPPORTED_CHARS - set(accent_tokens))
    if unsupported:
        details = ", ".join("U+%04X %r" % (ord(char), char) for char in unsupported)
        raise ValueError("unsupported glyph(s): %s" % details)
    output = bytearray()
    for char in text:
        if char in accent_tokens:
            output.append(accent_tokens[char])
        elif char in CONTROL_TO_TOKEN:
            token = CONTROL_TO_TOKEN[char]
            if token < 0x80:
                output.append(token)
            else:
                output.extend(struct.pack("<H", token))
        else:
            output.append(ord(char) - 0x1F)
    output.append(0)
    return bytes(output)


def _normalize_breaks(value):
    """Normalize CRLF/CR editor line endings to the game's LF line break."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _source_text_matches(actual, sheet):
    """Compare source text while ignoring spreadsheet-trimmed line endings."""
    clean = lambda value: "\n".join(
        line.rstrip(" \t") for line in _normalize_breaks(value).split("\n"))
    return clean(actual) == clean(sheet)


def _structured_codepage_runs(message):
    """Return the full source extent and its visible shared-font runs."""
    from . import vp2_cutscene_subtitles as subtitles

    source = bytes.fromhex(message.get("record_raw_hex", message["raw_hex"]))
    metadata = {"glyph_base": 0x65, "glyph_count": 0}
    runs = []
    for start, end, tokens in subtitles.parse_record(source, metadata):
        rendered, _, _ = subtitles.render_tokens(tokens, metadata, {})
        visible = subtitles.clean_text(rendered)
        if visible:
            leading = rendered[:len(rendered) - len(rendered.lstrip(" \t"))]
            trailing = rendered[len(rendered.rstrip(" \t")):]
            leading_newlines = len(rendered) - len(rendered.lstrip("\n"))
            runs.append((start, end, visible, leading, trailing,
                         leading_newlines))
    return source, runs


def _structured_codepage_targets(text):
    from . import vp2_cutscene_subtitles as subtitles

    return [subtitles.fragment_target(part) for part in
            _normalize_breaks(text).split("<PART>")]


def _structured_codepage_matches(message, text):
    """Whether a full structured record renders the requested visible text."""
    _source, runs = _structured_codepage_runs(message)
    targets = _structured_codepage_targets(text)
    return len(runs) == len(targets) and all(
        _source_text_matches(run[2], target)
        for run, target in zip(runs, targets))


def _structured_codepage_replacement(message, row):
    """Rewrite visible runs in a shared-font record, preserving its controls."""
    from . import vp2_cutscene_subtitles as subtitles

    source, runs = _structured_codepage_runs(message)

    source_parts = [visible for _, _, visible, _, _, _ in runs]
    expected_parts = _structured_codepage_targets(row["en_text"])
    targets = _structured_codepage_targets(row["translated"])

    def matches(parts):
        return len(source_parts) == len(parts) and all(
            _source_text_matches(actual, expected)
            for actual, expected in zip(source_parts, parts))

    source_is_original = matches(expected_parts)
    source_is_translation = matches(targets)
    if not source_is_original and not source_is_translation:
        raise ValueError("structured source no longer matches the CSV source text")

    if len(targets) != len(runs):
        raise ValueError(
            "structured record has %d visible run(s) but its translation has "
            "%d; separate visible runs with <PART>" %
            (len(runs), len(targets)))

    if not any(leading or trailing
               for _, _, _, leading, trailing, _ in runs):
        repaired = []
        for index, (start, end, visible, leading, trailing,
                    leading_newlines) in enumerate(runs):
            if index:
                gap = subtitles.byte_tokens(source[runs[index - 1][1]:start])
                if (any(token >= 0x8000 for token in gap)
                        and not targets[index].startswith("\n")):
                    leading = " "
            repaired.append((start, end, visible, leading, trailing,
                             leading_newlines))
        runs = repaired

    rebuilt = bytearray(source)
    for index, ((start, end, _visible, leading, trailing,
                 leading_newlines), target) in reversed(
            list(enumerate(zip(runs, targets)))):
        if (source_is_translation and index and leading_newlines == 1
                and target.startswith("\n")
                and not target.lstrip().startswith("---")):
            gap = subtitles.byte_tokens(source[runs[index - 1][1]:start])
            if 0x8082 in gap:
                leading_newlines = 6
        if leading_newlines:
            target = "\n" * leading_newlines + target.lstrip("\n")
        target = leading + target + trailing
        leading_gap = (source[runs[index - 1][1]:start]
                       if index else b"")
        trailing_gap = (source[end:runs[index + 1][0]]
                        if index + 1 < len(runs) else b"")
        target = subtitles.preserve_input_icon_spacing(
            target, leading_gap=leading_gap, trailing_gap=trailing_gap)
        replacement = subtitles.encode_visible_text(
            target, {}, 0x65, codepage=True)
        rebuilt[start:end] = replacement[:-1]
    return bytes(rebuilt)


def read_translations(path, resources, text_encoder=None):
    """Read a tracked scene sheet or the legacy message-index sheet."""
    text_encoder = text_encoder or encode_english_text
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            fields = set(reader.fieldnames or ())
            legacy = {
                "resource_index", "message_index", "en_text",
                "en_text_status", "translated",
            }.issubset(fields)
            scene_sheet = {
                "resource", "message_id", "original_en",
            }.issubset(fields)
            if not legacy and not scene_sheet:
                raise ValueError(
                    "translation CSV is neither a VP2 scene sheet nor a "
                    "legacy text sheet")
            result = collections.defaultdict(dict)
            for row_number, row in enumerate(reader, start=2):
                if scene_sheet:
                    row = dict(row)
                    row.update({
                        "resource_index": row["resource"],
                        "en_text": row["original_en"],
                        "en_text_status": "decoded",
                        "translated": row.get("translated") or "",
                    })
                row["en_text"] = _normalize_breaks(row["en_text"])
                row["translated"] = _normalize_breaks(row["translated"])
                text = row["translated"]
                if not text.strip():
                    continue
                resource_index = int(row["resource_index"])
                if scene_sheet:
                    message_key = ("message_id", int(row["message_id"]))
                    label = "id %d" % message_key[1]
                else:
                    message_key = int(row["message_index"])
                    label = "index %d" % message_key
                if resources is not None and resource_index not in resources:
                    continue
                if row["en_text_status"] != "decoded":
                    raise ValueError("CSV row %d (#%d %s) is %s; control/structured strings are not safe to patch yet" %
                                     (row_number, resource_index, label, row["en_text_status"]))
                if message_key in result[resource_index]:
                    raise ValueError("CSV repeats translation key #%d %s" %
                                     (resource_index, label))
                text_encoder(text)  # fail before an ISO copy is made
                result[resource_index][message_key] = row
    except (OSError, csv.Error, ValueError) as exc:
        raise ValueError("cannot read translations: %s" % exc) from exc
    return dict(result)


def dcms_layout(data):
    """Read the indexed string-table bounds needed for a zero-tail rebuild."""
    if not data.startswith(b"mcps2lib 1.50"):
        raise ValueError("expected a USA mcps2lib 1.50 container")
    stored_size, table_start, text_start, text_end = struct.unpack_from("<IIII", data, 0x20)
    if text_end != 0:
        raise ValueError("resource has a trailing payload (text_end=0x%X); this first patcher refuses to move it" % text_end)
    if stored_size != len(data) or not (0x40 <= table_start <= text_start <= len(data)):
        raise ValueError("invalid zero-tail mcps2lib layout")

    pointers = []
    for table_pos in range(table_start, text_start, 8):
        message_id, relative_offset = struct.unpack_from("<II", data, table_pos)
        if message_id == 0 and relative_offset == 0:
            break
        if relative_offset >= len(data) - text_start:
            raise ValueError("message %d points outside text data" % message_id)
        pointers.append((table_pos, message_id, relative_offset))
    if not pointers:
        raise ValueError("message table is empty")
    return table_start, text_start, pointers


def _parse_messages_with_extents(data):
    """Parse indexed strings and attach each full pointer-table record span."""
    _, text_start, pointers = dcms_layout(data)
    messages = dcms.parse_messages(data)
    if len(messages) != len(pointers):
        raise ValueError("message table/parser disagree on entry count")
    offsets = sorted({relative for _, _, relative in pointers})
    next_offset = {
        relative: (offsets[index + 1]
                   if index + 1 < len(offsets)
                   else len(data) - text_start)
        for index, relative in enumerate(offsets)
    }
    result = []
    for message in messages:
        enriched = dict(message)
        relative = message["text_byte_offset"]
        record = data[text_start + relative:
                      text_start + next_offset[relative]]
        enriched["record_byte_length"] = len(record)
        enriched["record_raw_hex"] = record.hex(" ").upper()
        result.append(enriched)
    return result


def rebuild_dcms(data, edits, encoder=None, verify_text=True):
    """Apply message-index keyed edits and rebuild the zero-tail text stream."""
    if encoder is None:
        encoder = lambda row: encode_english_text(row["translated"])
    _, text_start, pointers = dcms_layout(data)
    messages = _parse_messages_with_extents(data)

    replacements = {}
    offsets_seen = collections.defaultdict(list)
    structured_edits = set()
    for message_index, row in edits.items():
        if message_index < 0 or message_index >= len(messages):
            raise ValueError("message index %d is outside this resource" % message_index)
        message = messages[message_index]
        if message["text_status"] in (
                "readable_with_controls", "structured_or_binary"):
            encoded = _structured_codepage_replacement(message, row)
            old_length = message["record_byte_length"]
            structured_edits.add(message_index)
        elif message["text_status"] != "decoded":
            raise ValueError("message %d is %s, not a safe decoded string" %
                             (message_index, message["text_status"]))
        else:
            encoded = encoder(row)
            old_length = message["byte_length"]
            if (not _source_text_matches(message["text"], row["en_text"])
                    and not _source_text_matches(
                        message["text"], row["translated"])
                    and bytes.fromhex(message["raw_hex"]) != encoded):
                raise ValueError("message %d no longer matches the CSV source text" % message_index)
        offsets_seen[message["text_byte_offset"]].append(message_index)
        replacements[message["text_byte_offset"]] = (
            encoded, old_length)

    shared = [indexes for indexes in offsets_seen.values() if len(indexes) > 1]
    if shared:
        raise ValueError("shared message offsets are not supported yet: %s" % shared)

    old_text = data[text_start:]
    offsets = sorted({relative_offset for _, _, relative_offset in pointers})
    new_text = bytearray()
    new_offsets = {}
    cursor = 0
    for position, start in enumerate(offsets):
        end = offsets[position + 1] if position + 1 < len(offsets) else len(old_text)
        if start < cursor or end < start:
            raise ValueError("invalid/non-monotonic message offsets")
        new_text.extend(old_text[cursor:start])
        new_offsets[start] = len(new_text)
        segment = old_text[start:end]
        if start in replacements:
            encoded, old_string_length = replacements[start]
            if old_string_length > len(segment):
                raise ValueError("message string extends beyond its indexed segment")
            new_text.extend(encoded)
            new_text.extend(segment[old_string_length:])
        else:
            new_text.extend(segment)
        cursor = end
    new_text.extend(old_text[cursor:])

    rebuilt = bytearray(data[:text_start] + new_text)
    struct.pack_into("<I", rebuilt, 0x20, len(rebuilt))
    for table_pos, _, old_relative in pointers:
        struct.pack_into("<I", rebuilt, table_pos + 4, new_offsets[old_relative])

    # Parse again so corrupt offsets or token encoding fail before compression.
    reparsed = _parse_messages_with_extents(bytes(rebuilt))
    if verify_text:
        for message_index, row in edits.items():
            if message_index in structured_edits:
                verified = _structured_codepage_matches(
                    reparsed[message_index], row["translated"])
            else:
                verified = reparsed[message_index]["text"] == row["translated"]
            if not verified:
                raise ValueError("rebuilt message %d did not verify" % message_index)
    return bytes(rebuilt), reparsed


def patch_resource_bytes(raw, resource_index, edits, encoder=None, verify_text=True):
    """Build a same-size patch from a resource's raw bytes."""
    if not raw or triace.classify(raw, len(raw)) != "pk1":
        raise ValueError("resource #%d is not a PK1 archive" % resource_index)
    entries = dcms.parse_pk1(raw)
    for tag, offset, length in entries:
        if tag == "DCMS":
            original_slz = raw[offset:offset + length]
            break
    else:
        raise ValueError("resource #%d has no DCMS section" % resource_index)
    if original_slz[:4] != b"SLZ\x02":
        raise ValueError("resource #%d DCMS is not mode-2 SLZ" % resource_index)

    expanded = slz.decompress(original_slz)
    messages = _parse_messages_with_extents(expanded)
    indexes_by_id = collections.defaultdict(list)
    for message_index, message in enumerate(messages):
        indexes_by_id[message["message_id"]].append(message_index)
    resolved_edits = {}
    for message_key, row in edits.items():
        if isinstance(message_key, tuple) and message_key[0] == "message_id":
            matches = indexes_by_id.get(message_key[1], [])
            if len(matches) != 1:
                raise ValueError("resource #%d message id %d resolves to %d records" %
                                 (resource_index, message_key[1], len(matches)))
            message_index = matches[0]
        else:
            message_index = message_key
        if message_index in resolved_edits:
            raise ValueError("resource #%d repeats resolved message index %d" %
                             (resource_index, message_index))
        resolved_edits[message_index] = row

    if encoder is None:
        encoder = lambda row: encode_english_text(row["translated"])
    ignored_control_only = []
    writable_edits = {}
    expected_encoded = {}
    for message_index, row in resolved_edits.items():
        message = messages[message_index]
        if (message["text_status"] == "structured_or_binary"
                and not _structured_codepage_runs(message)[1]):
            ignored_control_only.append(message["message_id"])
            continue
        writable_edits[message_index] = row
        expected_encoded[message_index] = (
            _structured_codepage_replacement(message, row)
            if message["text_status"] in (
                "readable_with_controls", "structured_or_binary")
            else encoder(row))
    rebuilt, reparsed = rebuild_dcms(expanded, writable_edits,
                                     encoder=encoder, verify_text=verify_text)
    recompressed = slz_compress.compress(rebuilt, mode=2)
    if slz.decompress(recompressed) != rebuilt:
        raise ValueError("resource #%d mode-2 compressor round-trip failed" % resource_index)
    if len(recompressed) <= length:
        patched = bytearray(raw)
        patched[offset:offset + length] = recompressed.ljust(length, b"\0")
    else:
        from .pk1_archive import repack_pk1_subresource
        patched = repack_pk1_subresource(raw, "DCMS", recompressed)
    return bytes(patched), {
        "resource_index": resource_index,
        "source_slz_bytes": len(original_slz),
        "rebuilt_dcms_bytes": len(rebuilt),
        "new_slz_bytes": len(recompressed),
        "changed_messages": len(writable_edits),
        "ignored_control_only": ignored_control_only,
        "edits": writable_edits,
        "encoded": expected_encoded,
        "verify_text": verify_text,
        "parsed": reparsed,
    }


def build_resource_patch(handle, table, total, resource_index, edits,
                         encoder=None, verify_text=True):
    raw = dcms.read_entry(handle, table, total, resource_index)
    return patch_resource_bytes(raw, resource_index, edits,
                                encoder=encoder, verify_text=verify_text)


def patch_resource_in_memory(iso, resource_index, edits, *,
                             shared_font_glyphs=False, verify_text=True):
    """Patch a fontless/shared-font DCMS resource in *iso* (IsoBuffer)."""
    if not edits:
        raise ValueError("resource #%d has no translated rows" % resource_index)
    accent_tokens = SHARED_EXTENSION_TOKENS
    requested_accents = set("".join(
        row["translated"] for row in edits.values())) & set(accent_tokens)
    if requested_accents:
        verify_text = False

    def encoder(row):
        return encode_english_text(row["translated"], accent_tokens)

    raw = iso.read_entry(resource_index)
    patched, info = patch_resource_bytes(raw, resource_index, edits,
                                         encoder=encoder,
                                         verify_text=verify_text)
    iso.write_entry(resource_index, patched)

    written_edits = info["edits"]
    accents = set("".join(row["translated"]
                           for row in written_edits.values())) & set(accent_tokens)
    font_patch = None
    if accents:
        original_font = iso.read_entry(SHARED_FONT_ENTRY)
        patched_font, font_info = install_glyphs(
            original_font, accents, accent_tokens)
        if not font_info.get("no_op"):
            iso.write_entry(SHARED_FONT_ENTRY, patched_font)
        font_patch = (patched_font, font_info)
    return {"written": info["changed_messages"], "details": info,
            "font_patch": font_patch}


def verify_output(iso, patches):
    with open(iso, "rb") as handle:
        _, total, table = triace.load_table(handle)
        for resource_index, expected_raw, info in patches:
            actual = dcms.read_entry(handle, table, total, resource_index)
            if actual != expected_raw:
                raise ValueError("verification failed: ISO bytes differ for resource #%d" % resource_index)
            found = dcms.dcms_section(actual)
            if not found:
                raise ValueError("verification failed: resource #%d lost DCMS" % resource_index)
            parsed = dcms.parse_messages(slz.decompress(found[1]))
            for message_index, row in info["edits"].items():
                if info.get("verify_text", True):
                    matched = parsed[message_index]["text"] == row["translated"]
                else:
                    actual = bytes.fromhex(parsed[message_index]["raw_hex"])
                    matched = actual == info["encoded"][message_index]
                if not matched:
                    raise ValueError("verification failed: message #%d/%d" %
                                     (resource_index, message_index))


def verify_in_memory(iso, resource_index, expected_raw, info, font_patch):
    """Same coverage as ``verify_output`` but reads through the IsoBuffer."""
    actual = iso.read_entry(resource_index)
    if actual != expected_raw:
        raise ValueError("verification failed: ISO bytes differ for resource #%d" % resource_index)
    found = dcms.dcms_section(actual)
    if not found:
        raise ValueError("verification failed: resource #%d lost DCMS" % resource_index)
    parsed = dcms.parse_messages(slz.decompress(found[1]))
    for message_index, row in info["edits"].items():
        if info.get("verify_text", True):
            matched = parsed[message_index]["text"] == row["translated"]
        else:
            actual_bytes = bytes.fromhex(parsed[message_index]["raw_hex"])
            matched = actual_bytes == info["encoded"][message_index]
        if not matched:
            raise ValueError("verification failed: message #%d/%d" %
                             (resource_index, message_index))
    if font_patch and not font_patch[1].get("no_op"):
        actual_font = iso.read_entry(SHARED_FONT_ENTRY)
        if actual_font != font_patch[0]:
            raise ValueError("verification failed: shared-font entry bytes differ")
        _, _, _, _, expanded, _ = shared_font_stream(actual_font)
        if expanded != font_patch[1]["font"]:
            raise ValueError("verification failed: shared font did not read back")


def cmd_patch(args):
    """CLI entry point: read sheet, patch in-memory, commit, verify."""
    if not args.dry_run and os.path.exists(args.output_iso) \
            and os.path.abspath(args.source_iso) != os.path.abspath(args.output_iso):
        raise ValueError("output ISO already exists; choose a new name: %s" % args.output_iso)
    accent_tokens = SHARED_EXTENSION_TOKENS
    text_encoder = lambda text: encode_english_text(text, accent_tokens)
    translations = read_translations(
        args.translation_csv, args.resources, text_encoder=text_encoder)
    if not translations:
        print("no non-empty translations selected; no ISO created")
        return

    from . import vp2_iso_buffer as iso_buffer
    iso = iso_buffer.IsoBuffer.from_path(args.source_iso)
    patches = []
    font_patch = None
    for resource_index in sorted(translations):
        result = patch_resource_in_memory(
            iso, resource_index, translations[resource_index])
        info = result["details"]
        patches.append((resource_index, iso.read_entry(resource_index), info))
        print("#%04d: %d message(s), DCMS %d -> %d bytes (%+d)" %
              (resource_index, info["changed_messages"], info["source_slz_bytes"],
               info["new_slz_bytes"], info["new_slz_bytes"] - info["source_slz_bytes"]))
        if result["font_patch"]:
            font_patch = result["font_patch"]
            print(describe_install(font_patch[1]))

    if args.dry_run:
        print("dry run OK: %d resource(s); no ISO was created" % len(patches))
        return

    iso.commit(args.output_iso)
    verify_output(args.output_iso, patches)
    if font_patch and not font_patch[1].get("no_op"):
        verify_shared_font_output(args.output_iso, *font_patch)
    print("verified %d patched resource(s): %s" % (len(patches), args.output_iso))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source_iso")
    parser.add_argument("translation_csv")
    parser.add_argument("output_iso")
    parser.add_argument("--resources", type=parse_resources,
                        help="only patch comma-separated outer resource indexes")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate/rebuild/compress but do not copy or write an ISO")
    parser.add_argument("--shared-font-glyphs", action="store_true",
                        help="compatibility option; fontless accent encoding "
                             "and installation are now automatic")
    args = parser.parse_args()

    try:
        cmd_patch(args)
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(1, "error: %s\n" % exc)


if __name__ == "__main__":
    main()
