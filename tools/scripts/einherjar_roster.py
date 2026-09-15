# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

import collections
import csv
import re

from .paths import DATA_DIR

ROSTERS_PATH = DATA_DIR / "einherjar-rosters.csv"
MATERIALIZATION_MARKER = "Perform materialization?"
RUN_BEFORE_MARKER = 4
RUN_AFTER_MARKER = 3
RELEASE_LINES = 8

JOIN_LINE = re.compile(r"^(.+?) <PART> has joined the party\.$")
STORY_CAST = frozenset({
    "Dylan", "Lezard", "Leone", "Arngrim", "Mithra",
    "Lenneth", "Silmeria", "Brahms", "Hrist", "Freya", "Valkyrie",
})


def _text(value):
    return " ".join((value or "").split())


def load_rosters(path=None):
    source = path or ROSTERS_PATH
    rosters = {}
    try:
        with open(source, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                resource = (row.get("resource") or "").strip()
                name = (row.get("einherjar") or "").strip()
                if resource and name:
                    rosters.setdefault(resource, set()).add(name)
    except (OSError, csv.Error, UnicodeDecodeError):
        return {}
    return {key: frozenset(value) for key, value in rosters.items()}


def _join_block(rows):
    return [(row, found.group(1)) for row, found in
            ((row, JOIN_LINE.match(_text(row.get("original_en"))))
             for row in rows)
            if found]


def _story_run(names):
    return {index for index, name in enumerate(names)
            if name in STORY_CAST and (
                (index > 0 and names[index - 1] in STORY_CAST)
                or (index + 1 < len(names) and names[index + 1] in STORY_CAST))}


def site_einherjar(rows):
    names = [name for _, name in _join_block(rows)]
    story = _story_run(names)
    return [name for index, name in enumerate(names) if index not in story]


def is_site(rows):
    return any(_text(row.get("original_en")) == MATERIALIZATION_MARKER
               for row in rows)


def _message_number(row):
    try:
        return int((row.get("message_id") or "").strip())
    except ValueError:
        return None


def _materialization_run(rows):
    by_number = {}
    for row in rows:
        number = _message_number(row)
        if number is not None:
            by_number[number] = row
    marker = next((number for number, row in by_number.items()
                   if _text(row.get("original_en")) == MATERIALIZATION_MARKER),
                  None)
    if marker is None:
        return []
    return [by_number[number]
            for number in range(marker - RUN_BEFORE_MARKER,
                                marker + RUN_AFTER_MARKER + 1)
            if number in by_number
            and not _text(by_number[number].get("speaker"))]


def suppressed_rows(rows, rosters=None):
    table = load_rosters() if rosters is None else rosters
    joins = _join_block(rows)
    names = [name for _, name in joins]
    story = _story_run(names)
    story_rows = {id(joins[index][0]) for index in story}
    offered = {name for index, name in enumerate(names) if index not in story}
    known = offered.union(*table.values())
    site = is_site(rows)
    spoken = collections.Counter(_text(row.get("speaker")) for row in rows)
    release = bool(known) and all(spoken.get(name, 0) >= RELEASE_LINES
                                  for name in known)
    if not (site or release):
        return []
    run = {id(row) for row in _materialization_run(rows)} if site else set()
    suppressed = []
    for row in rows:
        if id(row) in story_rows:
            continue
        english = _text(row.get("original_en"))
        if (id(row) in run
                or _text(row.get("speaker")) in known
                or (site and (JOIN_LINE.match(english) or english in offered))):
            suppressed.append(row)
    return suppressed


WEAPON_TYPES = ("Light Warrior", "Heavy Warrior", "Archer", "Sorcerer")
DEBUG_PLACEHOLDER = re.compile(r"^ERROR!!\(v\d+\)$")


def load_table(path=None):
    source = path or ROSTERS_PATH
    empty = {"weapon": {}, "weapon_type": {}, "fallback": set(), "release": {}}
    table = {"weapon": {}, "weapon_type": {}, "fallback": set(), "release": {}}
    try:
        with open(source, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                resource = (row.get("resource") or "").strip()
                name = (row.get("einherjar") or "").strip()
                role = (row.get("role") or "").strip()
                if not (resource and name):
                    continue
                if role == "weapon":
                    table["weapon"].setdefault(resource, set()).add(name)
                    table["weapon_type"][resource] = (
                        row.get("weapon_type") or "").strip()
                elif role == "release":
                    table["release"].setdefault(resource, set()).add(name)
                elif role == "fallback":
                    table["fallback"].add(name)
    except (OSError, csv.Error, UnicodeDecodeError):
        return empty
    return table


def soul_reading(rows, weapon_type):
    readings = _materialization_run(rows)[:len(WEAPON_TYPES)]
    if weapon_type not in WEAPON_TYPES or len(readings) < len(WEAPON_TYPES):
        return None
    return readings[WEAPON_TYPES.index(weapon_type)]


def acceptance_block(rows):
    run = _materialization_run(rows)
    if not run:
        return {}
    by_number = {}
    for row in rows:
        number = _message_number(row)
        if number is not None:
            by_number[number] = row
    block, seen = {}, set()
    number = int(run[0]["message_id"]) - 1
    while number in by_number:
        speaker = _text(by_number[number].get("speaker"))
        if not speaker or speaker in seen:
            break
        seen.add(speaker)
        block[by_number[number]["message_id"]] = speaker
        number -= 1
    return block


def weapon_block(rows, roster, weapon_type, fallback):
    run = _materialization_run(rows)
    if not run:
        return {}
    readings = run[:len(WEAPON_TYPES)]
    drawn_reading = soul_reading(rows, weapon_type)
    joins = _join_block(rows)
    names = [name for _, name in joins]
    story_ids = {joins[index][0]["message_id"] for index in _story_run(names)}
    accepting = acceptance_block(rows)
    block = {}
    for row in rows:
        message_id = row["message_id"]
        found = JOIN_LINE.match(_text(row.get("original_en")))
        if found and message_id not in story_ids:
            name = found.group(1)
            block[message_id] = ("join", name,
                                 name in roster or name in fallback)
        elif message_id in accepting:
            name = accepting[message_id]
            block[message_id] = ("acceptance", name,
                                 name in roster or name in fallback)
        elif any(row is reading for reading in readings):
            block[message_id] = ("soul", "", drawn_reading is None
                                 or row is drawn_reading)
        elif any(row is record for record in run):
            block[message_id] = ("prompt", "", True)
    return block


def _known_einherjar(table):
    return set(table["fallback"]).union(*table["weapon"].values(),
                                        *table["release"].values())


def einherjar_view(rows, table=None):
    table = load_table() if table is None else table
    resource = next(((row.get("resource") or "").strip()
                     for row in rows if (row.get("resource") or "").strip()),
                    "")
    weapon = table["weapon"].get(resource)
    released = table["release"].get(resource)
    if weapon is None and released is None:
        return {}
    known = _known_einherjar(table)
    view = {}
    if weapon is not None and is_site(rows):
        view.update(weapon_block(rows, weapon, table["weapon_type"].get(resource, ""),
                                 table["fallback"]))
    accepting = acceptance_block(rows)
    release_lines = {row["message_id"]: _text(row.get("speaker")) for row in rows
                     if _text(row.get("speaker")) in known
                     and row["message_id"] not in accepting}
    if release_lines and released is None:
        return view
    appears = set(released or ())
    if weapon is not None:
        appears |= set(weapon) | set(table["fallback"])
    for message_id, name in release_lines.items():
        view[message_id] = ("release", name, name in (released or ()))
    for row in rows:
        english = _text(row.get("original_en"))
        if (english in known and not _text(row.get("speaker"))
                and row["message_id"] not in view):
            view[row["message_id"]] = ("name", english, english in appears)
    return view


def hidden_message_ids(rows, table=None):
    hidden = {row["message_id"] for row in rows
              if DEBUG_PLACEHOLDER.match(_text(row.get("original_en")))}
    hidden.update(message_id for message_id, (_, _, drawn)
                  in einherjar_view(rows, table).items() if not drawn)
    return hidden
