#!/usr/bin/env python3
r"""Helpers shared by the original-column maintenance scripts.

Three scripts operate on translator tables under ``opensource/translations``
and pull reference text from ``opensource/workspace/reference``:

* :mod:`scripts.add_original_en`        -- add or refresh an ``original_en`` column
* :mod:`scripts.add_original_jp`        -- add or refresh an ``original_jp`` column
* :mod:`scripts.strip_original_columns` -- drop both columns

The reference tables carry ``resource,message_id,original_en,original_jp,<extra>``
while a translator table carries ``resource,message_id,translated,notes``.  The
join key is ``(resource, message_id)`` -- the two tables are not necessarily
row-aligned (a translation file may have fewer rows than the reference when a
newly surfaced row has not yet been handed off) and a row present in the
translator table but absent from the reference simply leaves the new column
blank.  Reference-only columns (``speaker``, ``scene_line``, ``details``,
``record_kind``, ``chapter``, ``occurrences``, ``resources``) are never copied.

Column placement when inserting a new column, in order:

* ``add_original_en`` looks for ``original_jp`` first, then ``english_en``,
  then ``translated`` -- so the two originals sit side by side, ``jp``
  before ``en``.
* ``add_original_jp`` looks for ``original_en`` first, then ``english_en``,
  then ``translated`` -- same outcome, opposite arrival order.

That covers the green field, the ``original_en``-only state, the
``original_jp``-only state, and a hypothetical English review column.
"""
import csv
import io
import os


PRIMARY_KEYS = ("resource", "message_id")
ANCHOR_CHAINS = {
    "original_en": ("original_jp", "english_en", "translated"),
    "original_jp": ("original_en", "english_en", "translated"),
}


def open_csv(path, mode="r"):
    """Open *path* with UTF-8 BOM tolerance and no implicit newline mangling."""
    return io.open(path, mode, encoding="utf-8-sig", newline="")


def load_reference(path):
    """Return ``{key: {"original_en": ..., "original_jp": ...}}`` or *None*.

    *None* means the reference is missing or its mandatory columns are
    absent -- callers skip the matching translator table rather than guess.

    A reference with a populated ``original_en`` (or ``original_jp``) column
    is considered usable even when some individual cells are empty; the
    caller decides which column matters.
    """
    if not os.path.isfile(path):
        return None
    with open_csv(path) as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if not {"resource", "message_id", "original_en", "original_jp"} <= set(fields):
            return None
        lookup = {}
        for row in reader:
            key = (row.get("resource", ""), row.get("message_id", ""))
            lookup[key] = {
                "original_en": row.get("original_en", "") or "",
                "original_jp": row.get("original_jp", "") or "",
            }
        return lookup


def reference_has_populated_column(path, column):
    """True if *path* has at least one non-empty *column* value."""
    lookup = load_reference(path)
    if not lookup:
        return False
    return any(bool(row.get(column, "")) for row in lookup.values())


def read_table(path):
    """Return ``(fields, rows)``; rows are plain dicts."""
    with open_csv(path) as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fields, rows


def write_table(path, fields, rows):
    """Rewrite *path* in the project's CSV dialect (CRLF, UTF-8)."""
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(buf.getvalue())


def has_target_columns(fields, targets=("original_en", "original_jp")):
    """True if any of *targets* appears in *fields*."""
    return any(name in fields for name in targets)


def insert_position(fields, column):
    """Index where *column* should be inserted in *fields*.

    Honours the rules described in the module docstring.  When *column* has
    no anchor chain the column lands at the end of *fields* -- the only
    legal position for a green-field table that lacks ``translated``.
    """
    for anchor in ANCHOR_CHAINS.get(column, ()):
        if anchor in fields:
            return fields.index(anchor)
    return len(fields)


def row_key(row):
    return (row.get("resource", ""), row.get("message_id", ""))


def fill_value(rows, column, lookup):
    """Stamp *column* onto every row whose key is in *lookup*."""
    changed = 0
    for row in rows:
        match = lookup.get(row_key(row))
        if not match:
            row.setdefault(column, "")
            continue
        value = match.get(column, "")
        if row.get(column, "") != value:
            row[column] = value
            changed += 1
        elif column not in row:
            row[column] = value
    return changed


def iter_translation_tables(translations_root):
    """Yield ``(lang, rel_path, abs_path)`` for every CSV under *translations_root*.

    Skips build/config files (``build-profile.csv``, ``pack.toml``) that are
    not translator tables.  Languages are detected as direct subdirectories
    of *translations_root*.
    """
    if not os.path.isdir(translations_root):
        return
    for lang_dir in sorted(os.listdir(translations_root)):
        lang_path = os.path.join(translations_root, lang_dir)
        if not os.path.isdir(lang_path):
            continue
        for root, _dirs, files in os.walk(lang_path):
            for name in sorted(files):
                if not name.endswith(".csv"):
                    continue
                if name == "build-profile.csv":
                    continue
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, lang_path)
                yield lang_dir, rel_path.replace(os.sep, "/"), abs_path


def reference_path_for(translations_root, lang, rel_path):
    """Mirror *rel_path* under ``opensource/workspace/reference``.

    *translations_root* is expected to be ``opensource/translations``; the
    sibling ``workspace/reference`` carries the matching files.
    """
    here = os.path.dirname(os.path.abspath(translations_root))
    return os.path.join(here, "workspace", "reference", rel_path.replace("/", os.sep))


def script_relative_default_translations():
    """Resolve ``opensource/translations`` from this script's location.

    The helper module lives at ``opensource/tools/scripts/``; two levels up
    is ``opensource``, and ``translations`` is its child.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "translations"))
