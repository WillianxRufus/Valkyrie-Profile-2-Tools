"""Scene event-record parsing, matching, and CSV export."""

import csv
import difflib
import glob
import hashlib
import json
import os
import re
import struct

from .vp2_scene_fingerprint import (
    glyph_blocks, local_alphabet, reference_fingerprints, render_tokens,
    token_slot,
)
from .scene_codec import REFERENCE_FONT_RESOURCE
from .vp2_cutscene_subtitles import (
    BASIC_DONORS, FIELDS, FRAGMENT_MARKER, RECORD_PARAMETERS,
    RESOURCE_EXTRA_SLOTS, TAG, TEXT_BREAKS,
)

def load_resource(inventory_dir, resource):
    resource_dir = os.path.join(inventory_dir, "resource-%04d" % resource)
    paths = glob.glob(os.path.join(resource_dir, "*.json"))
    if len(paths) != 1:
        raise ValueError("expected one metadata JSON for resource #%d" % resource)
    with open(paths[0], encoding="utf-8") as source:
        metadata = json.load(source)
    path = os.path.join(resource_dir, metadata["files"]["mcps2"])
    with open(path, "rb") as source:
        return resource_dir, metadata, source.read()

def byte_tokens(data):
    tokens = []
    position = 0
    while position < len(data):
        first = data[position]
        position += 1
        if first >= 0x80:
            if position >= len(data):
                raise ValueError("subtitle ends inside a two-byte token")
            first |= data[position] << 8
            position += 1
        tokens.append(first)
    return tokens

def text_region_end(data):
    """Where the indexed text region ends, for a resource of either shape."""
    text_end = struct.unpack_from("<I", data, 0x2C)[0]
    if text_end:
        return text_end
    stored = struct.unpack_from("<I", data, 0x20)[0]
    return min(stored, len(data)) if stored else len(data)


def message_pointers(data, metadata):
    pointers = []
    for position in range(metadata["table_start"], metadata["text_start"], 8):
        message_id, offset = struct.unpack_from("<II", data, position)
        if message_id == 0 and offset == 0:
            break
        pointers.append((len(pointers), message_id, offset))
    offsets = sorted({offset for _, _, offset in pointers})
    text_bytes = metadata["text_end"] - metadata["text_start"]
    next_offset = {
        offset: offsets[index + 1] if index + 1 < len(offsets) else text_bytes
        for index, offset in enumerate(offsets)
    }
    return pointers, next_offset

def parse_record(record, metadata):
    """Return ``[(start, end, [tokens])]`` for each run of text in a record."""
    base, count = metadata["glyph_base"], metadata["glyph_count"]
    runs, current, start, position = [], [], 0, 0
    def flush(end):
        if current:
            runs.append((start, end, list(current)))
            del current[:]
    while position < len(record):
        at = position
        byte = record[position]
        if byte >= 0x80 and position + 1 < len(record):
            token = byte | (record[position + 1] << 8)
            position += 2
        else:
            token = byte
            position += 1
        if token in RECORD_PARAMETERS:
            flush(at)
            position += RECORD_PARAMETERS[token]
            continue
        if token in TEXT_BREAKS:
            # A break can arrive just after a parameter has closed the run it
            # belongs to, so it opens one rather than being discarded.
            if not current:
                start = at
            current.append(token)
            continue
        if (token >> 8) == 0x80 or token == 0:
            flush(at)
            continue
        if (token_slot(token, base, count) is not None
                or 0 < token < 0x80):
            if not current:
                start = at
            current.append(token)
            continue
        flush(at)
    flush(len(record))
    return runs

def split_nonempty(data):
    """Return ``(part_index, relative_offset, bytes)`` for null-separated parts."""
    parts = []
    start = 0
    part_index = 0
    for position in range(len(data) + 1):
        if position == len(data) or data[position] == 0:
            if position > start:
                parts.append((part_index, start, data[start:position]))
            part_index += 1
            start = position + 1
    return parts

def clean_text(rendered):
    """Readable text for a run, keeping the breaks that bound it."""
    visible = TAG.sub("", rendered)
    lines = [line.strip() for line in visible.splitlines()]
    body = "\n".join(line for line in lines if line)
    if not body:
        return ""
    leading = "\n" if lines and not lines[0] else ""
    trailing = "\n" if visible.endswith("\n") else ""
    return leading + body + trailing

def normalized(text):
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()

def subtitle_fingerprints(inventory_dir):
    """Build the shared alphabet plus known uppercase/basic donor glyphs."""
    fingerprints, _ = reference_fingerprints(
        inventory_dir, REFERENCE_FONT_RESOURCE)
    for character, (resource, slot) in BASIC_DONORS.items():
        resource_dir, metadata, _ = load_resource(inventory_dir, resource)
        blocks = glyph_blocks(resource_dir, metadata)
        if slot >= len(blocks):
            raise ValueError("invalid fingerprint donor #%d slot %d" %
                             (resource, slot))
        fingerprints[hashlib.sha1(blocks[slot]).hexdigest()] = character
    return fingerprints

def subtitle_records(inventory_dir, resource, message_id_min=1,
                     message_id_max=37):
    resource_dir, metadata, data = load_resource(inventory_dir, resource)
    fingerprints = subtitle_fingerprints(inventory_dir)
    alphabet = local_alphabet(resource_dir, metadata, fingerprints)
    alphabet.update(RESOURCE_EXTRA_SLOTS.get(resource, {}))
    pointers, next_offset = message_pointers(data, metadata)
    text_start = metadata["text_start"]
    rows = []
    for message_index, message_id, record_offset in pointers:
        if not message_id_min <= message_id <= message_id_max:
            continue
        record = data[text_start + record_offset:
                      text_start + next_offset[record_offset]]
        candidates = []
        for part_index, part_offset, part in split_nonempty(record):
            tokens = byte_tokens(part)
            rendered, matched, unknown = render_tokens(tokens, metadata, alphabet)
            if matched:
                candidates.append((matched, len(part), part_index, part_offset,
                                   part, tokens, rendered, unknown))
        if not candidates:
            continue
        # Headers contain only controls; the subtitle always has by far the
        # greatest number of recognized local-font glyphs.
        (matched, _, part_index, part_offset, part, tokens,
         rendered, unknown) = max(candidates)
        visible_parts = sorted(
            (candidate for candidate in candidates if candidate[0] >= 3),
            key=lambda candidate: candidate[3])
        part_rows = [{
            "part_index": candidate[2],
            "relative_offset": candidate[3],
            "byte_length": len(candidate[4]),
            "source_text": clean_text(candidate[6]),
            "source_tokens": " ".join("%04X" % token
                                      for token in candidate[5]),
            "source_raw_hex": candidate[4].hex(" ").upper(),
        } for candidate in visible_parts]
        combined_text = " ".join(
            item["source_text"] for item in part_rows if item["source_text"])
        rows.append({
            "resource_index": resource,
            "message_index": message_index,
            "message_id": message_id,
            "record_byte_offset": record_offset,
            "record_byte_length": next_offset[record_offset] - record_offset,
            "text_relative_offset": record_offset + part_offset,
            "text_byte_length": len(part),
            "text_part_index": part_index,
            "visible_part_count": len(part_rows),
            "visible_parts_json": json.dumps(
                part_rows, ensure_ascii=False, separators=(",", ":")),
            "source_tokens": " ".join("%04X" % token for token in tokens),
            "source_raw_hex": part.hex(" ").upper(),
            "source_rendered": rendered,
            "source_text": combined_text or clean_text(rendered),
            "matched_glyphs": matched,
            "unknown_glyphs": unknown,
        })
    return rows

def pair_manifest(records, manifest, allow_weak=False):
    spoken = [(index, row) for index, row in enumerate(manifest)
              if row["en_text"].strip()]
    scores = []
    for record_index, record in enumerate(records):
        source = normalized(record["source_text"])
        for manifest_index, row in spoken:
            score = difflib.SequenceMatcher(
                None, source, normalized(row["en_text"])).ratio()
            scores.append((score, record_index, manifest_index))
    used_records = set()
    used_manifest = set()
    pairs = {}
    for score, record_index, manifest_index in sorted(scores, reverse=True):
        if record_index in used_records or manifest_index in used_manifest:
            continue
        used_records.add(record_index)
        used_manifest.add(manifest_index)
        pairs[manifest_index] = (score, records[record_index])
    if len(used_records) != len(records) or len(used_manifest) != len(spoken):
        raise ValueError("manifest and subtitle record counts do not match")
    weak = [(manifest[index]["id"], score)
            for index, (score, _) in pairs.items() if score < 0.70]
    if weak and not allow_weak:
        raise ValueError("weak subtitle match: %s (review the audio and rerun "
                         "with --allow-weak-matches)" % weak)
    return pairs

def cmd_export(args):
    with open(args.manifest, newline="", encoding="utf-8-sig") as source:
        manifest = list(csv.DictReader(source))
    required = {"id", "en_text", "translated", "speaker"}
    if not manifest or not required.issubset(manifest[0]):
        raise ValueError("manifest lacks: %s" %
                         ", ".join(sorted(required - set(manifest[0] if manifest else ()))))
    records = subtitle_records(
        args.inventory_dir, args.resource,
        args.message_id_min, args.message_id_max)
    pairs = pair_manifest(records, manifest, args.allow_weak_matches)
    output_rows = []
    for manifest_index, manifest_row in enumerate(manifest):
        base = {
            "audio_id": manifest_row["id"],
            "resource_index": args.resource,
            "speaker": manifest_row["speaker"],
            "manifest_text": manifest_row["en_text"],
            "translated": manifest_row["translated"],
            "translator_notes": "",
        }
        if not manifest_row["en_text"].strip():
            output_rows.append({**base, "match_score": "",
                                "source_text": "", "source_rendered": ""})
            continue
        score, record = pairs[manifest_index]
        notes = []
        if score < 0.70:
            notes.append("LOW audio/message match %.3f; verify manually" % score)
        if record["visible_part_count"] > 1:
            notes.append("translate %d fragments separated by %s" %
                         (record["visible_part_count"], FRAGMENT_MARKER))
        output_rows.append({
            **base, **record, "match_score": "%.3f" % score,
            "translator_notes": "; ".join(notes),
        })
    parent = os.path.dirname(os.path.abspath(args.csv))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    scores = [float(row["match_score"]) for row in output_rows if row["match_score"]]
    print("resource #%d: %d spoken subtitles + %d silent clips" %
          (args.resource, len(scores), len(output_rows) - len(scores)))
    print("manifest mapping: minimum score %.3f" % min(scores))
    print("wrote %d rows -> %s" % (len(output_rows), args.csv))

def cmd_export_records(args):
    """Export subtitle records when an audio-bank manifest is not ready yet."""
    records = subtitle_records(
        args.inventory_dir, args.resource,
        args.message_id_min, args.message_id_max)
    selected_ids = set(args.message_id or ())
    if selected_ids:
        found_ids = {record["message_id"] for record in records}
        missing_ids = sorted(selected_ids - found_ids)
        if missing_ids:
            raise ValueError("no visible subtitle record for message IDs: %s" %
                             ", ".join(map(str, missing_ids)))
        records = [record for record in records
                   if record["message_id"] in selected_ids]
    if not records:
        raise ValueError("no visible subtitle records in the requested range")
    output_rows = []
    for record in records:
        output_rows.append({
            "audio_id": "r%04d-m%04d" %
                        (args.resource, record["message_id"]),
            "resource_index": args.resource,
            "speaker": "",
            "match_score": "",
            "manifest_text": "",
            "translated": "",
            "translator_notes": (
                "translate %d fragments separated by %s" %
                (record["visible_part_count"], FRAGMENT_MARKER)
                if record["visible_part_count"] > 1 else ""),
            **record,
        })
    parent = os.path.dirname(os.path.abspath(args.csv))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    print("resource #%d: exported %d subtitle records -> %s" %
          (args.resource, len(output_rows), args.csv))
