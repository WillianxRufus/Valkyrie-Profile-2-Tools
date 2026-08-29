#!/usr/bin/env python3
r"""
    py -3 tools/scripts/add_original_jp.py              # dry-run
    py -3 tools/scripts/add_original_jp.py --write      # rewrite
    py -3 tools/scripts/add_original_jp.py pt-BR --write
"""

import subprocess
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import translation_columns as tc


DEFAULT_TRANSLATIONS = tc.script_relative_default_translations()
COLUMN = "original_jp"

subprocess.run(
    ["git", "config", "core.hooksPath", ".githooks"],
    check=True
)

def add_one(translation_path, reference_path, write):
    if not os.path.isfile(reference_path):
        return "missing-reference"
    if not tc.reference_has_populated_column(reference_path, COLUMN):
        lookup = tc.load_reference(reference_path)
        if lookup is None:
            return "missing-column"
        return "empty-reference"

    lookup = tc.load_reference(reference_path)
    fields, rows = tc.read_table(translation_path)
    if COLUMN in fields:
        changed = tc.fill_value(rows, COLUMN, lookup)
        verb = "filled" if write else "would-fill"
        if changed == 0:
            return "no-change"
        if write:
            tc.write_table(translation_path, fields, rows)
        return verb
    position = tc.insert_position(fields, COLUMN)
    new_fields = fields[:position] + [COLUMN] + fields[position:]
    tc.fill_value(rows, COLUMN, lookup)
    verb = "added" if write else "would-add"
    if write:
        tc.write_table(translation_path, new_fields, rows)
    return verb


def run(translations_root, languages, write):
    counts = {"added": 0, "filled": 0, "no-change": 0,
              "missing-reference": 0, "missing-column": 0, "empty-reference": 0}
    touched = 0
    for lang, rel, abs_path in tc.iter_translation_tables(translations_root):
        if languages and lang not in languages:
            continue
        status = add_one(abs_path, tc.reference_path_for(translations_root, lang, rel), write)
        counts[status] = counts.get(status, 0) + 1
        if status in ("added", "filled"):
            touched += 1
            print("%s/%s: %s" % (lang, rel, status))
        elif write is False and status in ("would-add", "would-fill"):
            touched += 1
            print("%s/%s: %s" % (lang, rel, status))
    verb = "wrote" if write else "would change"
    print("\n%s %d table(s): %d updated, %d no-change, %d missing-reference, "
          "%d missing-column, %d empty-reference"
          % (verb, sum(counts.values()), touched,
             counts["no-change"], counts["missing-reference"],
             counts["missing-column"], counts["empty-reference"]))
    return 0 if (write or touched == 0) else 1


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("languages", nargs="*",
                        help="language folder(s) under opensource/translations; "
                             "default = every folder")
    parser.add_argument("--translations-root", default=DEFAULT_TRANSLATIONS,
                        help="path to opensource/translations (default: %(default)s)")
    parser.add_argument("--write", action="store_true",
                        help="rewrite the translator tables; default is to report only")
    args = parser.parse_args()
    return run(args.translations_root, set(args.languages), args.write)


if __name__ == "__main__":
    sys.exit(main())
