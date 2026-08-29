#!/usr/bin/env python3
r"""Strip ``original_en`` and ``original_jp`` from every translator table.

Removes both columns in place.  Any other column is preserved bit-for-bit
(UTF-8, CRLF terminators, quoting).  Tables that do not carry either column
are left alone.

The script does not touch ``opensource/workspace/reference`` -- that is the
provenance tree, not the translation tree.  It also skips ``build-profile.csv``
and any non-CSV file.

    py -3 opensource\tools\scripts\strip_original_columns.py              # dry-run
    py -3 opensource\tools\scripts\strip_original_columns.py --write      # rewrite
    py -3 opensource\tools\scripts\strip_original_columns.py pt-BR --write
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import translation_columns as tc


DEFAULT_TRANSLATIONS = tc.script_relative_default_translations()
TARGETS = ("original_en", "original_jp")


def strip_one(translation_path, write):
    fields, rows = tc.read_table(translation_path)
    keep = [name for name in fields if name not in TARGETS]
    if keep == fields:
        return "no-change"
    new_rows = [{k: row.get(k, "") for k in keep} for row in rows]
    verb = "stripped" if write else "would-strip"
    if write:
        tc.write_table(translation_path, keep, new_rows)
    return verb


def run(translations_root, languages, write):
    touched = no_change = 0
    for lang, rel, abs_path in tc.iter_translation_tables(translations_root):
        if languages and lang not in languages:
            continue
        status = strip_one(abs_path, write)
        if status == "no-change":
            no_change += 1
        else:
            touched += 1
            print("%s/%s: %s" % (lang, rel, status))
    verb = "wrote" if write else "would change"
    print("\n%s %d table(s): %d stripped, %d already clean"
          % (verb, touched + no_change, touched, no_change))
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
