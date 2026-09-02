#!/usr/bin/env python3
"""Index the VP2 chapter-title typeface and its cross-resource donor glyphs."""
import argparse
import base64
import csv
import functools
import hashlib
import os
import struct
import unicodedata

from .paths import DATA_DIR, PROJECT_ROOT, TOOLS_DIR

HERE = os.fspath(TOOLS_DIR)

from . import slz
from . import triace_ps2_unpack as triace
from . import vp2_dcms as dcms
from . import vp2_cutscene_subtitles as subtitles
from .scene_fonts import append_glyph_blocks
from .scene_codec import pack_tokens
from .scene_glyphs import glyph_value, set_glyph_value


HARVESTED_DONORS_DEFAULT = os.path.join(
    os.fspath(DATA_DIR), "vp2-chapter-title-donors.csv")


CHAPTER_RECORDS_DEFAULT = os.path.join(
    os.fspath(PROJECT_ROOT), "data", "chapter-records.csv")
TITLE_NAMES_DEFAULT = os.path.join(
    os.fspath(PROJECT_ROOT), "data", "glyph-names", "title.csv")


def read_chapter_records(path=None):
    """Return source-free structural chapter record identities."""
    with open(path or CHAPTER_RECORDS_DEFAULT, newline="",
              encoding="utf-8-sig") as handle:
        return tuple(
            (int(row["resource"]), int(row["message_id"]))
            for row in csv.DictReader(handle))


def read_title_names(path=None):
    """Return SHA-1 bitmap digest bytes mapped to identified glyphs."""
    with open(path or TITLE_NAMES_DEFAULT, newline="",
              encoding="utf-8-sig") as handle:
        return {
            bytes.fromhex(row["digest"]): row["character"]
            for row in csv.DictReader(handle)
            if row.get("digest") and row.get("character") != ""
        }


CHAPTER_RECORDS = frozenset(read_chapter_records())

UNICASE = True


class FileIsoForTitleFace:
    """File-mode reader that exposes ``read_entry(resource)`` like IsoBuffer."""

    def __init__(self, handle, table, total):
        self.handle = handle
        self.table = table
        self.total = total

    def read_entry(self, resource):
        return dcms.read_entry(self.handle, self.table, self.total, resource)


def load_font(iso, resource):
    """Return (expanded DCMS, font layout) for a PK1 scene resource."""
    raw = iso.read_entry(resource)
    if not raw or triace.classify(raw, len(raw)) != "pk1":
        return None
    for tag, offset, length in dcms.parse_pk1(raw):
        if tag != "DCMS":
            continue
        packed = raw[offset:offset + length]
        if packed[:4] != b"SLZ\x02":
            return None
        expanded = bytearray(slz.decompress(packed))
        return expanded, subtitles.font_layout(expanded)
    return None


def glyph_blocks(expanded, layout):
    start, size = layout["font_start"], layout["glyph_bytes"]
    return [bytes(expanded[start + slot * size:start + (slot + 1) * size])
            for slot in range(layout["glyph_count"])]


def message_slots(expanded, layout):
    """Yield (message_id, part_index, [slot, ...]) for every message part."""
    metadata = {
        "table_start": struct.unpack_from("<I", expanded, 0x24)[0],
        "text_start": struct.unpack_from("<I", expanded, 0x28)[0],
        "text_end": struct.unpack_from("<I", expanded, 0x2C)[0],
        "glyph_base": layout["glyph_base"],
        "glyph_count": layout["glyph_count"],
    }
    pointers, next_offset = subtitles.message_pointers(expanded, metadata)
    base, count = layout["glyph_base"], layout["glyph_count"]
    for _, message_id, offset in pointers:
        record = expanded[metadata["text_start"] + offset:
                          metadata["text_start"] + next_offset[offset]]
        for index, _, part in subtitles.split_nonempty(record):
            slots = [slot for slot in
                     (subtitles.token_slot(token, base, count)
                      for token in subtitles.byte_tokens(part))
                     if slot is not None]
            if slots:
                yield message_id, index, slots


def build_face(iso, skip_patched=False):
    """Name title-face bitmaps from the tracked digest-to-character map."""
    del skip_patched
    names = read_title_names()
    face = {}
    sources = {}
    for resource in sorted({resource for resource, _ in CHAPTER_RECORDS}):
        loaded = load_font(iso, resource)
        if loaded is None:
            raise ValueError(
                "chapter resource #%d is not a PK1 scene font" % resource)
        expanded, layout = loaded
        blocks = glyph_blocks(expanded, layout)
        for slot, block in enumerate(blocks):
            digest = hashlib.sha1(block).digest()
            character = names.get(digest)
            if character is None:
                continue
            face[digest] = character
            sources.setdefault(digest, (resource, slot))
    if not face:
        raise ValueError("no chapter-title glyph matched the supported image")
    return face, sources


def decode_title(iso, resource, message_id, expected="", donor_iso=None,
                 face=None):
    loaded = load_font(iso, resource)
    if loaded is None:
        raise ValueError("chapter resource #%d is not a PK1 scene font" % resource)
    expanded, layout = loaded
    face = read_title_names() if face is None else face
    blocks = glyph_blocks(expanded, layout)
    installed = {}
    if expected:
        source = donor_iso or iso
        _, donors = donor_index(source, skip_patched=donor_iso is None)
        harvested = read_harvested_donors()
        composable = _composition_art(source, donors, harvested, layout)
        for character in dict.fromkeys(expected):
            try:
                bitmap, _, _, _ = glyph_art(source, character, donors,
                                            harvested, composable, layout)
            except ValueError:
                continue
            installed.setdefault(hashlib.sha1(bytes(bitmap)).digest(), character)
    _, slots = title_record(expanded, layout, message_id)
    characters = []
    for slot in slots:
        digest = hashlib.sha1(blocks[slot]).digest()
        character = face.get(digest)
        if character is None:
            character = installed.get(digest)
        if character is None:
            if expected:
                characters.append("?")
                continue
            raise ValueError(
                "chapter resource #%d message %d has an unnamed title glyph"
                % (resource, message_id))
        characters.append(character)
    return "".join(characters)


def scan(iso, resources, face):
    """Report every resource carrying face bitmaps, with decoded title records."""
    found, unnamed = [], {}
    for resource in resources:
        try:
            loaded = load_font(iso, resource)
        except (ValueError, struct.error, IndexError):
            continue
        if loaded is None:
            continue
        expanded, layout = loaded
        try:
            blocks = glyph_blocks(expanded, layout)
        except (ValueError, IndexError):
            continue
        digests = [hashlib.sha1(block).digest() for block in blocks]
        named = {slot: face[digest] for slot, digest in enumerate(digests)
                 if digest in face}
        solid = {slot for slot in named if any(blocks[slot])}
        if len(solid) < 3:
            continue
        records = []
        try:
            for message_id, index, slots in message_slots(expanded, layout):
                if len(slots) < 3 or not any(slot in solid for slot in slots):
                    continue
                if any(slot not in named for slot in slots):
                    for slot in slots:
                        if slot not in named:
                            unnamed.setdefault(digests[slot], []).append(
                                (resource, slot))
                records.append((message_id, index,
                                "".join(named.get(slot, "?") for slot in slots)))
        except (ValueError, struct.error, IndexError):
            pass
        found.append((resource, layout["glyph_count"], named, records))
    return found, unnamed


def donor_index(iso, skip_patched=False):
    """Return (digest -> character, character -> (resource, slot)) for the face."""
    face, sources = build_face(iso, skip_patched)
    donors = {}
    for digest, character in face.items():
        donors.setdefault(character, sources[digest])
    return face, donors


def find_donor(donors, character):
    """Look a character up in the donor map, honouring the unicase face."""
    if character in donors:
        return donors[character]
    for candidate, location in donors.items():
        if UNICASE and candidate.lower() == character.lower():
            return location
    return None


@functools.lru_cache(maxsize=None)
def read_harvested_donors(path=None):
    """``character -> (pixels, metric, bytes)`` for the European harvest."""
    path = path or HARVESTED_DONORS_DEFAULT
    if not os.path.exists(path):
        return {}
    harvested = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            character = row.get("character", "")
            if not character or not row.get("pixels"):
                continue
            harvested[character] = (
                base64.b64decode(row["pixels"]),
                base64.b64decode(row.get("metric") or ""),
                int(row.get("bytes") or 0))
    return harvested


def find_harvested(harvested, character):
    """The harvest, looked up the same unicase way as the donor map."""
    if character in harvested:
        return harvested[character]
    for candidate, art in harvested.items():
        if UNICASE and candidate.lower() == character.lower():
            return art
    return None


ACCENTED_METRIC_BYTE = 0x0F


def lift_mark(accented, base):
    """The pixels an accent adds, as ``(dx, y, value)`` around the base."""
    ink = [(x, y) for y in range(28) for x in range(32)
           if glyph_value(base, x, y)]
    if not ink:
        raise ValueError("cannot lift a mark against an empty base")
    centre = (min(x for x, _y in ink) + max(x for x, _y in ink)) // 2
    mark = []
    for y in range(28):
        for x in range(32):
            value = glyph_value(accented, x, y)
            if value and not glyph_value(base, x, y):
                mark.append((x - centre, y, value))
    if not mark:
        raise ValueError("the accented glyph adds nothing to its base")
    return mark


def apply_mark(base, mark):
    """Set a lifted mark over *base*, never erasing the letter underneath."""
    block = bytearray(base)
    ink = [(x, y) for y in range(28) for x in range(32)
           if glyph_value(block, x, y)]
    centre = (min(x for x, _y in ink) + max(x for x, _y in ink)) // 2
    for dx, y, value in mark:
        x = centre + dx
        if not glyph_value(block, x, y):
            set_glyph_value(block, x, y, value)
    return bytes(block)


def compose_accented(character, art):
    """Build *character* from a base and a mark lifted off a harvested pair."""
    decomposed = unicodedata.normalize("NFD", character)
    if len(decomposed) != 2:
        return None
    base_character, combining = decomposed
    base = _lookup(art, base_character)
    if base is None:
        return None
    for candidate, (block, _metric) in art.items():
        parts = unicodedata.normalize("NFD", candidate)
        if len(parts) != 2 or parts[1] != combining or candidate == character:
            continue
        donor_base = _lookup(art, parts[0])
        if donor_base is None:
            continue
        try:
            mark = lift_mark(block, donor_base[0])
        except ValueError:
            continue
        metric = bytes(base[1][:1]) + bytes([ACCENTED_METRIC_BYTE])
        return apply_mark(base[0], mark), metric, candidate
    return None

SUBTITLE_MARK_NUDGE = {"ã": -1}

def _stamp(base, grid, mark_rows, above, clearance, nudge):
    """Place a mark grid over or under *base* and return the merged block."""
    from . import vp2_glyph_compose as glyph_compose
    body = glyph_compose.unpack(bytes(base))
    body_rows = glyph_compose.ink_rows(body)
    if not body_rows:
        raise ValueError("the base letter has no ink")
    body_left, body_right = glyph_compose.ink_columns(body, body_rows)
    mark_left, mark_right = glyph_compose.ink_columns(grid, mark_rows)
    dx = int(round((body_left + body_right) / 2
                   - (mark_left + mark_right) / 2)) + nudge
    if above:
        dy = body_rows[0] - mark_rows[-1] - 1 - clearance
    else:
        dy = body_rows[-1] - mark_rows[0] + 1 + clearance
    out = [list(row) for row in body]
    for y in mark_rows:
        target_y = y + dy
        if not 0 <= target_y < glyph_compose.HEIGHT:
            raise ValueError("the mark does not fit in the cell")
        for x in range(glyph_compose.WIDTH):
            if not grid[y][x]:
                continue
            target_x = x + dx
            if not 0 <= target_x < glyph_compose.WIDTH:
                raise ValueError("the mark does not fit beside the body")
            out[target_y][target_x] = max(out[target_y][target_x], grid[y][x])
    return glyph_compose.pack(out)


def compose_with_subtitle_mark(character, art, marks=None):
    """Build *character* from an ornate base and a subtitle-face mark."""
    from . import vp2_glyph_compose as glyph_compose
    if marks is None:
        marks = subtitles.ACCENT_MARKS
    recipe = glyph_compose.COMPOSITES.get(character)
    if recipe is None:
        return None
    base_character, donor, position = recipe
    mark = marks.get(donor)
    base = _lookup(art, base_character)
    if mark is None or base is None:
        return None
    grid = glyph_compose.unpack(mark["pixels"])
    nudge = SUBTITLE_MARK_NUDGE.get(character, 0)
    for clearance in range(glyph_compose.DEFAULT_CLEARANCE, -9, -1):
        try:
            block = _stamp(base[0], grid, mark["rows"],
                           position != "below", clearance, nudge)
        except ValueError:
            continue
        metric = bytes(base[1][:1]) + bytes([ACCENTED_METRIC_BYTE])
        return block, metric, "subtitle face"
    return None


def compose_procedural(character, art):
    """Derive title glyphs absent from every USA chapter title."""
    from . import scene_glyphs
    from . import vp2_glyph_compose as glyph_compose

    if character.lower() == "c":
        base = _lookup(art, "o")
        if base is None:
            return None
        grid = glyph_compose.unpack(bytes(base[0]))
        rows = glyph_compose.ink_rows(grid)
        if not rows:
            return None
        left, right = glyph_compose.ink_columns(grid, rows)
        top, bottom = min(rows), max(rows)
        opening_left = right - max(2, (right - left + 1) // 4)
        opening_top = top + max(2, (bottom - top + 1) // 4)
        opening_bottom = bottom - max(2, (bottom - top + 1) // 4)
        for y in range(opening_top, opening_bottom + 1):
            for x in range(opening_left, right + 1):
                grid[y][x] = 0
        return glyph_compose.pack(grid), bytes(base[1]), "procedural o"

    decomposed = unicodedata.normalize("NFD", character)
    if len(decomposed) != 2:
        return None
    base_character, combining = decomposed
    mark = {
        "\u0300": "grave",
        "\u0301": "acute_dotless" if base_character.lower() == "i" else "acute",
        "\u0302": "circumflex",
        "\u0303": "tilde",
        "\u0327": "cedilla",
    }.get(combining)
    base = _lookup(art, base_character)
    if mark is None or base is None:
        return None
    try:
        bitmap = scene_glyphs.accented_block(bytes(base[0]), mark)
    except ValueError:
        return None
    metric = bytes(base[1][:1]) + bytes([ACCENTED_METRIC_BYTE])
    return bitmap, metric, "procedural mark"


def _lookup(art, character):
    """Unicase lookup into a ``character -> (bitmap, metric)`` map."""
    if character in art:
        return art[character]
    for candidate, value in art.items():
        if UNICASE and candidate.lower() == character.lower():
            return value
    return None


def _composition_art(iso, donors, harvested, layout):
    """``character -> (bitmap, metric)`` for everything the face can draw."""
    art = {}
    for character, location in donors.items():
        try:
            block, metric, glyph_bytes = subtitles.donor_glyph(iso, *location)
        except (ValueError, struct.error, IndexError):
            continue
        if glyph_bytes == layout["glyph_bytes"]:
            art[character] = (block, metric)
    for character, (block, metric, glyph_bytes) in harvested.items():
        if glyph_bytes == layout["glyph_bytes"]:
            art.setdefault(character, (block, metric))
    return art


def composable_characters(iso, donors=None, harvested=None, layout=None):
    """Characters the face can compose but neither disc actually cut."""
    if donors is None:
        _face, donors = donor_index(iso)
    harvested = read_harvested_donors() if harvested is None else harvested
    if layout is None:
        _expanded, layout = load_font(iso, sorted(CHAPTER_RECORDS)[0][0])
    art = _composition_art(iso, donors, harvested, layout)
    known = {character.lower() for character in art}
    found = {}
    for base in sorted(known):
        for combining in ("́", "̀", "̂", "̃", "̧"):
            character = unicodedata.normalize("NFC", base + combining)
            if len(character) != 1 or character.lower() in known:
                continue
            composed = compose_accented(character, art)
            if composed is not None:
                found[character] = composed[2]
    return found


def face_alphabet(donors, harvested=None):
    """Every character a title may use, folded the way the face draws it."""
    characters = set(donors) | set(harvested or {})
    if UNICASE:
        characters = {character.lower() for character in characters}
    return "".join(sorted(characters))


def title_record(expanded, layout, message_id):
    """Return the slot run of a resource's chapter-title record."""
    runs = [(index, slots) for mid, index, slots
            in message_slots(expanded, layout) if mid == message_id]
    if len(runs) != 1:
        raise ValueError("expected one chapter-title record for message %d, "
                         "found %d" % (message_id, len(runs)))
    return runs[0]


def glyph_art(iso, character, donors, harvested, composable, layout):
    """The title-face bitmap and metric for *character*, and where it came from."""
    location = find_donor(donors, character)
    if location is not None:
        donor_resource, donor_slot = location
        bitmap, metric, glyph_bytes = subtitles.donor_glyph(
            iso, donor_resource, donor_slot)
    else:
        art = find_harvested(harvested, character)
        if art is not None:
            bitmap, metric, glyph_bytes = art
            donor_resource, donor_slot = "harvested", character
        else:
            composed = (compose_accented(character, composable)
                        or compose_with_subtitle_mark(character, composable)
                        or compose_procedural(character, composable))
            if composed is None:
                raise ValueError(
                    "the chapter-title face has no %r and cannot compose "
                    "one; it offers only %r (the face is unicase, so each "
                    "letter covers both cases). A mark this face carries "
                    "nowhere -- the tilde and the cedilla -- has to be "
                    "authored rather than borrowed."
                    % (character, face_alphabet(donors, harvested)))
            bitmap, metric, source = composed
            glyph_bytes = len(bitmap)
            donor_resource, donor_slot = "composed", source
    if glyph_bytes != layout["glyph_bytes"]:
        raise ValueError("incompatible title donor for %r" % character)
    return bitmap, metric, donor_resource, donor_slot


def fold(character):
    """The character a slot is keyed by; the face draws one bitmap per pair."""
    return character.lower() if UNICASE else character


def write_glyph(expanded, layout, slot, bitmap, metric):
    """Put one bitmap and its advance into an existing slot."""
    start = layout["font_start"] + slot * layout["glyph_bytes"]
    expanded[start:start + layout["glyph_bytes"]] = bitmap
    metric_start = layout["text_end"] + slot * 2
    expanded[metric_start:metric_start + 2] = metric


def title_tokens(title_text, assignment, glyph_base):
    """Encode the title record against the slots its letters ended up in."""
    return pack_tokens([subtitles.slot_token(assignment[fold(character)],
                                             glyph_base)
                        for character in title_text])


def plan_title(expanded, layout, title_text, iso, message_id,
               face=None, donors=None):
    if face is None or donors is None:
        face, donors = donor_index(iso)
    _, current = title_record(expanded, layout, message_id)
    block = sorted(set(current))
    blocks = glyph_blocks(expanded, layout)
    holding = {slot: face.get(hashlib.sha1(blocks[slot]).digest())
               for slot in block}

    def key(character):
        return character.lower() if UNICASE else character

    ordered, seen = [], set()
    for character in title_text:
        if key(character) not in seen:
            seen.add(key(character))
            ordered.append(character)

    def same(left, right):
        if left is None:
            return False
        return left == right or (UNICASE and left.lower() == right.lower())

    assignment, used = {}, set()
    for character in ordered:
        for slot in block:
            if slot not in used and same(holding.get(slot), character):
                assignment[key(character)] = slot
                used.add(slot)
                break

    free = [slot for slot in block if slot not in used]
    missing = [character for character in ordered
               if key(character) not in assignment]

    harvested = read_harvested_donors()
    composable = _composition_art(iso, donors, harvested, layout)
    art = [(character,) + glyph_art(iso, character, donors, harvested,
                                    composable, layout)
           for character in missing]

    installed = []
    for (character, bitmap, metric, donor_resource, donor_slot), slot in zip(
            art, free):
        write_glyph(expanded, layout, slot, bitmap, metric)
        assignment[key(character)] = slot
        used.add(slot)
        installed.append((character, slot, donor_resource, donor_slot))

    released = [slot for slot in block if slot not in used]
    return assignment, installed, released, art[len(free):]


SLOT_CANDIDATES = 12


def place_title(expanded, layout, pending, free_slots, measure=None):
    free = list(free_slots)[:]
    assignment, installed, overflow = {}, [], []
    for item in pending:
        character, bitmap, metric, donor_resource, donor_slot = item
        if not free:
            overflow.append(item)
            continue
        slot = _cheapest_slot(expanded, layout, bitmap, metric, free, measure)
        free.remove(slot)
        write_glyph(expanded, layout, slot, bitmap, metric)
        assignment[fold(character)] = slot
        installed.append((character, slot, donor_resource, donor_slot))
    appended = append_glyph_blocks(
        expanded, layout, [(bitmap, metric)
                           for _c, bitmap, metric, _r, _s in overflow])
    for (character, _bitmap, _metric, donor_resource, donor_slot), slot in zip(
            overflow, appended):
        assignment[fold(character)] = slot
        installed.append((character, slot, donor_resource, donor_slot))
    return assignment, installed, appended


def _cheapest_slot(expanded, layout, bitmap, metric, free, measure):
    """The free slot this glyph compresses smallest in."""
    if measure is None or len(free) == 1:
        return free[0]
    best, best_cost = None, None
    for slot in free[:SLOT_CANDIDATES]:
        trial = bytearray(expanded)
        write_glyph(trial, layout, slot, bitmap, metric)
        cost = measure(bytes(trial))
        if best_cost is None or cost < best_cost:
            best, best_cost = slot, cost
    return best


def resource_list(manifest):
    with open(manifest, newline="", encoding="utf-8-sig") as source:
        return [int(row["index"]) for row in csv.DictReader(source)
                if row["type"] == "pk1"]


def cmd_index(args):
    with open(args.iso, "rb") as handle:
        _, total, table = triace.load_table(handle)
        iso = FileIsoForTitleFace(handle, table, total)
        face, sources = build_face(iso)
        print("named title-face bitmaps: %d" % len(face))
        resources = resource_list(args.manifest)
        found, unnamed = scan(iso, resources, face)

    characters = {}
    for digest, character in face.items():
        resource, slot = sources[digest]
        characters.setdefault(character, []).append((resource, slot, digest))
    for resource, _, named, _ in found:
        for slot, character in named.items():
            entry = (resource, slot, None)
            if not any(existing[0] == resource and existing[1] == slot
                       for existing in characters.get(character, [])):
                characters.setdefault(character, []).append(entry)

    with open(args.csv, "w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(["character", "donor_resource", "donor_slot",
                         "digest", "alternate_donors"])
        for character in sorted(characters, key=lambda c: (c.isupper(), c)):
            entries = characters[character]
            resource, slot, digest = entries[0]
            if digest is None:
                digest = ""
            writer.writerow([
                character, resource, slot, digest.hex() if digest else "",
                ";".join("%d:%d" % (r, s) for r, s, _ in entries[1:])])

    printable = "".join(sorted(
        (c for c in characters if c != " "), key=lambda c: (c.isupper(), c)))
    print("resources carrying the face: %d" % len(found))
    print("characters available: %d -> %s (plus space)"
          % (len(characters), printable))
    if unnamed:
        print("UNNAMED bitmaps still in the face: %d" % len(unnamed))
        for digest, uses in sorted(unnamed.items(), key=lambda kv: -len(kv[1]))[:10]:
            print("   first at resource %d slot %d (%d uses) %s"
                  % (uses[0][0], uses[0][1], len(uses), digest.hex()[:12]))
    for resource, count, _, records in found:
        for message_id, index, text in records:
            print("   #%-5d msg %-6d part %d  %s"
                  % (resource, message_id, index, text))
    print("wrote %s" % args.csv)


def cmd_decode(args):
    with open(args.iso, "rb") as handle:
        _, total, table = triace.load_table(handle)
        iso = FileIsoForTitleFace(handle, table, total)
        face, _ = build_face(iso, skip_patched=True)
        loaded = load_font(iso, args.resource)
        if loaded is None:
            raise ValueError("resource #%d is not a PK1 scene font" % args.resource)
        expanded, layout = loaded
        blocks = glyph_blocks(expanded, layout)
    named = {slot: face[hashlib.sha1(block).digest()]
             for slot, block in enumerate(blocks)
             if hashlib.sha1(block).digest() in face}
    solid = {slot for slot in named if any(blocks[slot])}
    print("resource #%d font=%d glyph_base=0x%X"
          % (args.resource, layout["glyph_count"], layout["glyph_base"]))
    for message_id, index, slots in message_slots(expanded, layout):
        if len(slots) < 3 or not any(slot in solid for slot in slots):
            continue
        print("  msg %-6d part %d slots=%s" % (message_id, index, slots))
        print("           %s" % "".join(named.get(s, "?") for s in slots))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="build the donor index CSV")
    index.add_argument("iso")
    index.add_argument("manifest", help="<iso>.triace.csv from triace_ps2_unpack")
    index.add_argument("csv")
    index.set_defaults(func=cmd_index)
    decode = commands.add_parser("decode", help="decode one resource's title records")
    decode.add_argument("iso")
    decode.add_argument("--resource", type=int, required=True)
    decode.set_defaults(func=cmd_decode)
    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, ValueError, KeyError, IndexError, csv.Error, struct.error) as exc:
        parser.exit(1, "error: %s\n" % exc)


if __name__ == "__main__":
    main()
