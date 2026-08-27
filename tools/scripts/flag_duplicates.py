#!/usr/bin/env python3
"""Flag duplicated lines across scene/container/worldmap SHEETs."""
import argparse
import csv
import os
from collections import defaultdict


from .paths import PROJECT_ROOT, TOOLS_DIR

HERE = os.fspath(TOOLS_DIR)
ROOT = os.fspath(PROJECT_ROOT)
SCENES_DIR = os.path.join(ROOT, "data", "vp2", "scenes")

NEW_COLUMN = "copy_status"
STATUS_PRIMARY = "primary"
STATUS_DUPLICATE = "duplicate"

AUTHORITATIVE = "!workspace"

AUTHORITATIVE_RECORD = "!workspace-resource"

WORKSPACE_CLAIM = "!workspace-claim"


def _normalize_text(text):
    r"""Collapse whitespace so 'a b' and 'a\nb' hash the same."""
    return " ".join((text or "").split())


def _load_sheets(scenes_dir):
    """Return ``{path: list_of_rows}`` for every CSV in ``scenes_dir``."""
    out = {}
    for fname in sorted(os.listdir(scenes_dir)):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(scenes_dir, fname)
        from . import normalize_sheet_newlines
        rows, fieldnames, _ = normalize_sheet_newlines.read_rows(path)
        out[path] = (rows, fieldnames)
    return out


def _detect_duplicates(sheets, en_only=False):
    """Return ``{key: [(path, row_index), ...]}`` for shared rows."""
    groups = defaultdict(list)
    for path, (rows, _) in sheets.items():
        for i, row in enumerate(rows):
            en = _normalize_text(row.get("original_en"))
            if not en:
                continue
            if en_only:
                key = (en,)
            else:
                jp = _normalize_text(row.get("original_jp"))
                key = (en, jp)
            groups[key].append((path, i))
    return {key: locs for key, locs in groups.items() if len(locs) > 1}


def _pick_primary(locs, rows_for_path):
    """Return the location of the primary copy."""
    def score(loc):
        path, idx = loc
        row = rows_for_path[path][idx]
        translated = bool((row.get("translated") or "").strip())
        try:
            resource = int(row.get("resource", ""))
        except ValueError:
            resource = 0
        try:
            msg_id = int(row.get("message_id", ""))
        except ValueError:
            msg_id = 0
        return (0 if translated else 1, resource, msg_id, idx)
    return min(locs, key=score)


def _ensure_column(fieldnames):
    """Return ``fieldnames`` with ``copy_status`` appended if missing."""
    if NEW_COLUMN in fieldnames:
        return fieldnames
    return list(fieldnames) + [NEW_COLUMN]


def _summarize(sheets, duplicates):
    """Return ``(dup_pairs, primary_count, duplicate_count, untouched_files)``."""
    dup_pairs = len(duplicates)
    primary_count = sum(1 for locs in duplicates.values()
                        for _ in [1])  # one primary per pair
    duplicate_count = sum(len(locs) - 1 for locs in duplicates.values())
    flagged = {path for locs in duplicates.values() for path, _ in locs}
    untouched = len(sheets) - len(flagged)
    return dup_pairs, primary_count, duplicate_count, untouched


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenes-dir", default=SCENES_DIR)
    parser.add_argument("--resource", type=int, action="append",
                        help="Restrict to a subset of resource indices; "
                             "matches files of the form resource-RRRR-*.csv "
                             "or container-RRRR.csv.")
    parser.add_argument("--write", action="store_true",
                        help="Persist the flag column.  Default: dry-run "
                             "summary only.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-pick the primary even on rows already "
                             "flagged.  Default: leave existing copy_status "
                             "alone.")
    parser.add_argument("--en-only", action="store_true",
                        help="Key on original_en alone.  Default keys on "
                             "(original_en, original_jp) so a row whose JP "
                             "is a different word stays a separate line.  "
                             "Use --en-only when many JP cells are missing.")
    args = parser.parse_args()

    sheets = _load_sheets(args.scenes_dir)
    if args.resource:
        wanted = set(args.resource)
        sheets = {path: (rows, fn)
                  for path, (rows, fn) in sheets.items()
                  if any(_fname_to_resource(path) == r for r in wanted)}

    duplicates = _detect_duplicates(sheets, en_only=args.en_only)
    rows_for_path = {p: rows for p, (rows, _) in sheets.items()}

    print(f"scanned {len(sheets)} SHEETs")
    dup_pairs, primary_count, duplicate_count, untouched = _summarize(
        sheets, duplicates)
    print(f"duplicated (en, msg_id) pairs: {dup_pairs}")
    print(f"  primary rows tagged: {primary_count}")
    print(f"  duplicate rows tagged: {duplicate_count}")
    print(f"  untouched SHEETs: {untouched}")

    if not args.write:
        print("\n--dry-run, nothing written.  pass --write to persist.")
        return

    written = 0
    for path, (rows, fieldnames) in sheets.items():
        new_fieldnames = _ensure_column(fieldnames)
        # Mark all rows in this sheet: primary or duplicate per group.
        for locs in duplicates.values():
            primary = _pick_primary(locs, rows_for_path)
            for loc in locs:
                # ``loc`` is (path, row_index); only touch rows that belong
                # to the SHEET we're writing in this iteration.
                if loc[0] != path:
                    continue
                row = rows[loc[1]]
                current = (row.get(NEW_COLUMN) or "").strip()
                if current and not args.overwrite:
                    continue
                row[NEW_COLUMN] = (STATUS_PRIMARY if loc == primary
                                           else STATUS_DUPLICATE)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        written += 1
    print(f"\nwrote {written} SHEETs")


def _fname_to_resource(path):
    """Return the resource index encoded in the SHEET filename, or None."""
    base = os.path.basename(path)
    # resource-0033-scenes.csv -> 33; container-0641.csv -> 641
    parts = base.replace(".csv", "").split("-")
    if len(parts) >= 2:
        try:
            return int(parts[-1])
        except ValueError:
            return None
    return None


def _normalize_text(text):
    """Same collapse as above; duplicated here so callers can use the helper."""
    return " ".join((text or "").split())


def resolve_duplicates(rows, primary_lookup=None, en_only=False, kind=None,
                       replaced=None):
    """Fill empty ``translated`` columns from a translation of the same line."""
    def _key(row):
        en = _normalize_text(row.get("original_en"))
        jp = "" if en_only else _normalize_text(row.get("original_jp"))
        return (kind, en, jp)

    if primary_lookup is None:
        primary_lookup = {}
        for row in rows:
            translated = (row.get("translated") or "").strip()
            if translated:
                primary_lookup.setdefault(_key(row), translated)
    filled = 0
    for row in rows:
        en = _normalize_text(row.get("original_en"))
        if not en:
            continue
        own = (row.get("translated") or "").strip()
        key = _key(row)
        # The sheet for this row's own resource wins over the same
        # English written for another one.  See AUTHORITATIVE_RECORD.
        resource = (row.get("resource") or "").strip()
        written = None
        claimed = False
        if resource:
            written = primary_lookup.get(
                (AUTHORITATIVE_RECORD, kind, resource) + key[1:])
            claimed = ((WORKSPACE_CLAIM, kind, resource) + key[1:]
                       in primary_lookup)
        if not written and not claimed:
            written = primary_lookup.get((AUTHORITATIVE,) + key)
        if written:
            if _normalize_text(written) != _normalize_text(own):
                row["translated"] = written
                # Only an actual *replacement* is worth announcing.  A row
                # that was empty is the ordinary case and would drown it.
                if replaced is not None and own:
                    replaced.append((row, own, written))
                filled += 1
            continue
        if own:
            continue
        if claimed:
            continue
        primary = primary_lookup.get(key)
        if primary:
            row["translated"] = primary
            filled += 1
    return rows, filled


def resolve_duplicates_from_path(sheet_path):
    """Read ``sheet_path`` and apply ``resolve_duplicates`` to its rows."""
    with open(sheet_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    rows, _ = resolve_duplicates(rows)
    return rows


if __name__ == "__main__":
    main()
