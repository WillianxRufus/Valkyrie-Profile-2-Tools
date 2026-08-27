#!/usr/bin/env python3
"""Install and verify target-language glyphs in unused shared-font slots."""
import argparse
import csv
import hashlib
import os
import struct

from . import slz
from . import slz_compress

from .paths import DATA_DIR, TOOLS_DIR

HERE = os.fspath(TOOLS_DIR)

from . import triace_ps2_unpack as triace
from . import vp2_cutscene_subtitles as subtitles
from . import vp2_dcms as dcms


SHARED_FONT_ENTRY = 8

SHARED_ACCENT_DONORS = os.fspath(DATA_DIR / "shared-font-accent-donors.csv")

def load_slot_assignments(path=None):
    """Load the target character-to-token map from package configuration."""
    path = path or os.path.join(os.path.dirname(__file__), "shared_font_slots.csv")
    with open(path, newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assignments = {}
    used_tokens = set()
    for row in rows:
        character = row["character"]
        token = int(row["token"], 0)
        if len(character) != 1:
            raise ValueError("shared-font character must be one code point: %r" % character)
        if character in assignments or token in used_tokens:
            raise ValueError("duplicate shared-font character or token: %r" % row)
        assignments[character] = token
        used_tokens.add(token)
    return assignments


SHARED_EXTENSION_TOKENS = load_slot_assignments()


def _round_up(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def shared_font_stream(archive):
    """Find entry 8's 95-glyph shared font in its four-stream ZLS chain."""
    at = 0
    while at + 0x20 <= len(archive) and archive[at:at + 4] == b"ZLS\0":
        outer_size, span = struct.unpack_from("<I4xI", archive, at + 4)
        if span < 0x20 or at + span > len(archive):
            raise ValueError("shared-font entry has an invalid ZLS span")
        inner = archive[at + 0x10:at + span]
        if inner[:3] == b"SLZ":
            expanded = slz.decompress(inner)
            if expanded.startswith(b"mcps2lib 1.50"):
                layout = subtitles.font_layout(expanded)
                if (layout["glyph_count"] >= 95 and
                        layout["glyph_bytes"] == 448 and
                        layout["glyph_base"] == 1):
                    return at, outer_size, span, inner, expanded, layout
        at += span
    raise ValueError("entry 8's 95-glyph shared font was not found")


GLYPH_COUNT_FIELD = 0x20 + 5 * 4


def grow_font_for(expanded, layout, wanted_count):
    """Return ``expanded`` with room for ``wanted_count`` glyph slots."""
    if wanted_count <= layout["glyph_count"]:
        return bytes(expanded), layout
    metric_end = layout["text_end"] + wanted_count * 2
    if metric_end > layout["font_start"]:
        raise ValueError(
            "shared font cannot hold %d glyphs: its metric table would "
            "reach %d and the glyph data starts at %d"
            % (wanted_count, metric_end, layout["font_start"]))
    added = (wanted_count - layout["glyph_count"]) * layout["glyph_bytes"]
    grown = bytearray(expanded)
    grown[layout["font_end"]:layout["font_end"]] = bytes(added)
    struct.pack_into("<I", grown, GLYPH_COUNT_FIELD, wanted_count)
    return bytes(grown), subtitles.font_layout(bytes(grown))


def _composed_shared_glyph(font, layout, character):
    """``(block, metric)`` for *character*, or ``None``."""
    from . import vp2_glyph_compose as glyph_compose

    recipe = glyph_compose.COMPOSITES.get(character)
    if recipe is None:
        return None
    base, donor, _position = recipe
    mark = subtitles.ACCENT_MARKS.get(donor)
    if mark is None:
        return None
    base_slot = ord(base) - 0x20
    if not 0 <= base_slot < layout["glyph_count"]:
        return None
    source = subtitles.glyph_bitmap(font, layout, base_slot)
    try:
        block = glyph_compose.compose_character(
            source, character, glyph_compose.unpack(mark["pixels"]),
            mark["rows"], donor_bottom=mark.get("donor_bottom"))
    except ValueError:
        return None
    return bytes(block), subtitles.glyph_metric(font, layout, base_slot)


def patch_shared_font(archive, characters, accent_tokens=None):
    """Install ``characters`` into globally-unused slots of shared font"""
    accent_tokens = accent_tokens or SHARED_EXTENSION_TOKENS
    unknown = set(characters) - set(accent_tokens)
    if unknown:
        raise ValueError("no shared-font token assigned for %s" %
                         ", ".join(sorted(map(repr, unknown))))
    requested = sorted(set(characters), key=lambda char: accent_tokens[char])
    at, old_outer_size, span, inner, expanded, layout = shared_font_stream(
        archive)
    old_stored = struct.unpack_from("<I", inner, 4)[0]
    wanted_count = max(
        [layout["glyph_count"]]
        + [accent_tokens[character] - layout["glyph_base"] + 1
           for character in requested])
    expanded, layout = grow_font_for(expanded, layout, wanted_count)
    grew_to = wanted_count if wanted_count > 95 else 0
    rebuilt_font = bytearray(expanded)
    donors = subtitles.read_accent_donors(SHARED_ACCENT_DONORS)
    installed = []
    for character in requested:
        token = accent_tokens[character]
        target_slot = token - 1
        if not 0 <= target_slot < layout["glyph_count"]:
            raise ValueError("shared-font token 0x%02X is outside the font" % token)
        if character in donors:
            block, metric, glyph_bytes = donors[character]
            if glyph_bytes != layout["glyph_bytes"]:
                raise ValueError("incompatible shared-font donor for %r" % character)
        else:
            composed = _composed_shared_glyph(rebuilt_font, layout, character)
            if composed is not None:
                block, metric = composed
            else:
                base, mark = subtitles.ACCENTS[character]
                base_slot = ord(base) - 0x20
                source = subtitles.glyph_bitmap(
                    rebuilt_font, layout, base_slot)
                vertical_shift = -2 if mark == "tilde" else 0
                block = subtitles.accented_block(
                    source, mark, vertical_shift=vertical_shift)
                metric = subtitles.glyph_metric(
                    rebuilt_font, layout, base_slot)
        start = layout["font_start"] + target_slot * layout["glyph_bytes"]
        rebuilt_font[start:start + layout["glyph_bytes"]] = block
        metric_at = layout["text_end"] + target_slot * 2
        rebuilt_font[metric_at:metric_at + 2] = metric
        installed.append((character, token, target_slot))

    packed = slz_compress.compress(bytes(rebuilt_font), mode=inner[3],
                                   optimal=False)
    if _round_up(len(packed), 4) + 0x10 > span:
        tighter = slz_compress.compress(bytes(rebuilt_font), mode=inner[3],
                                        optimal=True)
        if len(tighter) < len(packed):
            packed = tighter
    if slz.decompress(packed) != bytes(rebuilt_font):
        raise ValueError("shared-font compression round-trip failed")
    new_outer_size = _round_up(len(packed), 4)
    new_span = max(span, _round_up(0x10 + new_outer_size, 128))
    if grew_to and new_span != span:
        raise ValueError(
            "shared font grown to %d glyphs compresses to %d bytes and only "
            "%d fit inside entry 8's existing ZLS span; drop a character "
            "from the install rather than moving the stream behind it"
            % (grew_to, len(packed), span - 0x10))
    suffix = archive[at + span:]
    used = len(suffix.rstrip(b"\0"))
    if at + new_span + used > len(archive):
        raise ValueError("shared font needs a %d-byte ZLS span but entry 8 "
                         "has only %d bytes of trailing slack" %
                         (new_span, len(archive) - at - span - used))

    rebuilt = bytearray(len(archive))
    rebuilt[:at + 0x10] = archive[:at + 0x10]
    inner_at = at + 0x10
    rebuilt[inner_at:inner_at + len(packed)] = packed
    struct.pack_into("<I", rebuilt, at + 4, new_outer_size)
    struct.pack_into("<I", rebuilt, at + 0x0C, new_span)
    suffix_at = at + new_span
    rebuilt[suffix_at:suffix_at + len(suffix)] = suffix[
        :len(rebuilt) - suffix_at]
    if any(suffix[len(rebuilt) - suffix_at:]):
        raise ValueError("moving the final entry-8 stream would truncate data")
    if new_span != span and rebuilt[suffix_at:suffix_at + 4] == b"ZLS\0":
        struct.pack_into("<I", rebuilt, suffix_at + 8, new_span)
    check = slz.decompress(rebuilt[inner_at:at + new_span])
    if check != bytes(rebuilt_font):
        raise ValueError("rebuilt shared font did not read back")
    return bytes(rebuilt), {
        "wrapper_offset": at,
        "span": span,
        "span_after": new_span,
        "suffix_shift": new_span - span,
        "outer_before": old_outer_size,
        "outer_after": new_outer_size,
        "stored_before": old_stored,
        "stored_after": len(packed) - 16,
        "installed": installed,
        "font": bytes(rebuilt_font),
        "already_installed": False,
        "glyph_count": layout["glyph_count"],
        "grew_to": grew_to,
        "span_spare": (span - 0x10) - len(packed),
    }


def install_glyphs(archive, characters, accent_tokens=None):
    """Idempotent installer."""
    accent_tokens = accent_tokens or SHARED_EXTENSION_TOKENS
    unknown = set(characters) - set(accent_tokens)
    if unknown:
        raise ValueError("no shared-font token assigned for %s" %
                         ", ".join(sorted(map(repr, unknown))))
    if not characters:
        return archive, {
            "installed": [],
            "already_installed": True,
            "no_op": True,
        }

    donors = subtitles.read_accent_donors(SHARED_ACCENT_DONORS)
    _, _, _, _, expanded, layout = shared_font_stream(archive)
    needed = []
    for character in sorted(set(characters), key=lambda c: accent_tokens[c]):
        if character in donors and donors[character][0] is not None:
            block = donors[character][0]
        else:
            base, mark = subtitles.ACCENTS[character]
            base_slot = ord(base) - 0x20
            source = subtitles.glyph_bitmap(
                expanded, layout, base_slot)
            vertical_shift = -2 if mark == "tilde" else 0
            block = subtitles.accented_block(
                source, mark, vertical_shift=vertical_shift)
        target_slot = accent_tokens[character] - 1
        glyph_start = layout["font_start"] + target_slot * layout["glyph_bytes"]
        current = bytes(expanded[
            glyph_start:glyph_start + layout["glyph_bytes"]])
        if hashlib.sha1(current).digest() != hashlib.sha1(block).digest():
            needed.append(character)
    if not needed:
        return archive, {
            "installed": [],
            "already_installed": True,
            "no_op": True,
        }
    rebuilt, info = patch_shared_font(archive, needed, accent_tokens)
    info["no_op"] = False
    return rebuilt, info


def write_entry8_to_iso(iso_path, rebuilt_archive):
    """Replace entry 8 of ``iso_path`` in place with ``rebuilt_archive``."""
    with open(iso_path, "r+b") as handle:
        _, total, table = triace.load_table(handle)
        handle.seek(table[SHARED_FONT_ENTRY] * triace.SECTOR)
        handle.write(rebuilt_archive)


def read_entry8(iso_path):
    """Return the raw bytes of entry 8 from ``iso_path``."""
    with open(iso_path, "rb") as handle:
        _, total, table = triace.load_table(handle)
        return dcms.read_entry(handle, table, total, SHARED_FONT_ENTRY)


def install_for_iso(iso_path, characters, accent_tokens=None):
    """End-to-end: read entry 8 from ``iso_path``, install, write back."""
    original = read_entry8(iso_path)
    rebuilt, info = install_glyphs(original, characters, accent_tokens)
    if info.get("no_op"):
        return info
    write_entry8_to_iso(iso_path, rebuilt)
    return info


def verify_shared_font_output(iso, expected_archive, info):
    with open(iso, "rb") as handle:
        _, total, table = triace.load_table(handle)
        actual = dcms.read_entry(handle, table, total, SHARED_FONT_ENTRY)
    if not info.get("no_op") and actual != expected_archive:
        raise ValueError("verification failed: shared-font entry bytes differ")
    if not info.get("no_op"):
        _, _, _, _, expanded, _ = shared_font_stream(actual)
        if expanded != info["font"]:
            raise ValueError("verification failed: shared font did not read back")


def describe_install(info):
    """Render an install info dict as one human-readable line."""
    if info.get("no_op"):
        return "shared-font already installed; no change"
    installed = ", ".join(
        "%s=0x%02X" % (char, token)
        for char, token, _ in info["installed"])
    return ("entry #%d: installed %s; SLZ %d -> %d bytes; suffix shift %d"
            % (SHARED_FONT_ENTRY, installed,
               info["stored_before"], info["stored_after"],
               info["suffix_shift"]))


def _cmd_install(args):
    characters = set(args.characters)
    info = install_for_iso(args.iso, characters)
    print(describe_install(info))
    if info.get("no_op"):
        return
    print("verified: %s" % args.iso)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--characters", default="".join(SHARED_EXTENSION_TOKENS),
                        help="characters to install (default: full lowercase "
                             "configured shared-font profile)")
    sub = parser.add_subparsers(dest="command", required=True)
    install_p = sub.add_parser(
        "install",
        help="install (or no-op) accent glyphs into the working ISO's "
             "entry 8")
    install_p.add_argument("iso")
    install_p.set_defaults(func=_cmd_install)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
