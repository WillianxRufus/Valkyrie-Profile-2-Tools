# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Extract and patch the Dragon Hall stone-selection prompt."""

from __future__ import annotations

import struct

from . import sle
from . import slz_compress
from . import vp2_container_text as container_text


RESOURCES = (328, 330, 338, 340, 342, 346, 348, 354, 372, 382, 388)
MESSAGE_ID = 0xE80
PROMPT_OFFSET = MESSAGE_ID
PROMPT_SIZE = 20
ORIGINAL_EN = "Insert which stone?"
ORIGINAL_JP = "どの石をはめますか？"
JP_PROMPT = bytes(range(0x65, 0x6F)) + b"\0"
NEXT_TEXT_OFFSET = PROMPT_OFFSET + PROMPT_SIZE
NEXT_EN = "Sunlight Stone"


def protect(slz_blob: bytes) -> bytes:
    if len(slz_blob) < sle.HEADER_SIZE or slz_blob[:3] != b"SLZ":
        raise ValueError("not an SLZ stream")
    stored_size = struct.unpack_from("<I", slz_blob, 4)[0]
    end = sle.HEADER_SIZE + stored_size
    if end != len(slz_blob):
        raise ValueError("SLZ stream length does not match its header")
    protected = bytearray(slz_blob)
    for position in range(stored_size):
        plain = protected[sle.HEADER_SIZE + position]
        addend = (3 + 3 * position) & 0xFF
        protected[sle.HEADER_SIZE + position] = (
            (plain ^ sle.KEY[position & 0x0F]) + addend
        ) & 0xFF
    protected[2] = ord("E")
    return bytes(protected)


def _sle_candidates(raw: bytes):
    start = 0
    while True:
        offset = raw.find(b"SLE", start)
        if offset < 0:
            return
        start = offset + 3
        if offset + sle.HEADER_SIZE > len(raw):
            continue
        stored_size = struct.unpack_from("<I", raw, offset + 4)[0]
        end = offset + sle.HEADER_SIZE + stored_size
        if end > len(raw):
            continue
        try:
            expanded = sle.decompress(raw[offset:end])
        except (ValueError, IndexError, struct.error):
            continue
        yield offset, end, stored_size, raw[offset:end], expanded


def _english_stream(raw: bytes):
    signature = container_text.encode_codepage(NEXT_EN)
    for candidate in _sle_candidates(raw):
        expanded = candidate[4]
        if expanded[NEXT_TEXT_OFFSET:NEXT_TEXT_OFFSET + len(signature)] == signature:
            return candidate
    raise ValueError("SPDDragonHall.bin prompt stream was not found")


def extract_english(raw: bytes, *, accent_tokens=None) -> str:
    expanded = _english_stream(raw)[4]
    text, consumed = container_text.render_codepage(
        expanded,
        {"text_start": 0, "text_end": NEXT_TEXT_OFFSET},
        PROMPT_OFFSET,
        accent_tokens=accent_tokens,
    )
    if consumed > PROMPT_SIZE:
        raise ValueError("Dragon Hall prompt overruns its fixed slot")
    return text


def extract_japanese(raw: bytes) -> str:
    for candidate in _sle_candidates(raw):
        expanded = candidate[4]
        if expanded[PROMPT_OFFSET:PROMPT_OFFSET + len(JP_PROMPT)] == JP_PROMPT:
            return ORIGINAL_JP
    raise ValueError("Japanese SPDDragonHall.bin prompt stream was not found")


def source_row(resource: int, raw: bytes, japanese_raw: bytes | None = None):
    if resource not in RESOURCES:
        raise ValueError(f"resource {resource} is not a Dragon Hall prompt owner")
    english = extract_english(raw)
    if english != ORIGINAL_EN:
        raise ValueError(
            f"resource {resource}: expected {ORIGINAL_EN!r}, found {english!r}")
    japanese = extract_japanese(japanese_raw) if japanese_raw is not None else ""
    return {
        "kind": "container",
        "resource": str(resource),
        "message_id": str(MESSAGE_ID),
        "message_index": "",
        "record_kind": "dragon_hall_prompt",
        "offset": str(PROMPT_OFFSET),
        "byte_length": str(PROMPT_SIZE),
        "original_en": english,
        "original_jp": japanese,
        "translated": "",
        "notes": "",
    }


def patch_raw(raw: bytes, translated: str, *, accent_tokens=None):
    offset, end, stored_size, stream, expanded = _english_stream(raw)
    before = extract_english(raw, accent_tokens=accent_tokens)
    if before != ORIGINAL_EN:
        raise ValueError(f"expected {ORIGINAL_EN!r}, found {before!r}")
    encoded = container_text.encode_codepage(
        translated, label="Dragon Hall prompt", accent_tokens=accent_tokens)
    if len(encoded) > PROMPT_SIZE:
        raise ValueError(
            "Dragon Hall prompt uses %d encoded bytes; its fixed slot holds %d "
            "including the terminator" % (len(encoded), PROMPT_SIZE))
    rebuilt = bytearray(expanded)
    rebuilt[PROMPT_OFFSET:NEXT_TEXT_OFFSET] = encoded.ljust(PROMPT_SIZE, b"\0")
    compressed = slz_compress.compress(
        rebuilt, mode=stream[3], target_size=stored_size, cache_dir="")
    protected = protect(compressed)
    if len(protected) != len(stream):
        raise AssertionError("exact-size Dragon Hall recompression changed the stream")
    output = raw[:offset] + protected + raw[end:]
    readback = extract_english(output, accent_tokens=accent_tokens)
    expected = container_text.codepage_semantic_text(
        translated, accent_tokens=accent_tokens)
    if readback != expected:
        raise AssertionError(
            f"Dragon Hall prompt readback mismatch: {readback!r} != {expected!r}")
    return output, {
        "wrapper": "SLE",
        "stream_offset": offset,
        "stored_size": stored_size,
        "prompt": readback,
    }


def patch_resource_in_memory(iso, resource: int, supplied, *, accent_tokens=None):
    key = str(MESSAGE_ID)
    row = supplied.get(key)
    if row is None:
        raise ValueError(f"resource {resource}: missing Dragon Hall prompt row {key}")
    extra = sorted(set(supplied) - {key})
    if extra:
        raise ValueError(f"resource {resource}: unexpected Dragon Hall rows {extra}")
    original = bytes(iso.read_entry(resource))
    rebuilt, details = patch_raw(
        original, row["translated"], accent_tokens=accent_tokens)
    iso.write_entry(resource, rebuilt)
    return {"written": 1, "details": details, "font_patch": None}
