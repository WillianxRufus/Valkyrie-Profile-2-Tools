#!/usr/bin/env python3
"""Translate the area name the map screen draws, inside each map's ``PAMM``."""
import argparse
import csv
import os
import sys

from . import slz
from . import slz_compress
from . import triace_ps2_unpack as triace
from . import vp2_container_text as container
from . import vp2_dcms as dcms
from . import vp2_shared_font as shared_font

PAMM = "PAMM"


class AreaNameTooLong(ValueError):
    """The translation does not fit the field, or its row."""


def accent_tokens():
    """The shared-font extension slots, so an accented name encodes."""
    return shared_font.SHARED_EXTENSION_TOKENS


def pamm_row(raw):
    """Return ``(offset, length)`` of the archive's PAMM row, or ``None``."""
    for tag, offset, length in dcms.parse_pk1(raw):
        if tag == PAMM:
            return offset, length
    return None


def name_field(payload, encoded_name):
    """Locate the name as a whole NUL-delimited field, and its padding."""
    start = 0
    while True:
        at = payload.find(encoded_name, start)
        if at < 0:
            return None
        end = at + len(encoded_name)
        delimited = ((at == 0 or payload[at - 1] == 0)
                     and end < len(payload) and payload[end] == 0)
        if delimited:
            pad = end
            while pad < len(payload) and payload[pad] == 0:
                pad += 1
            return at, pad - at
        start = at + 1


MAX_NAME = 48


def candidate_names(path):
    """Yield ``(english, translated)`` for the name-like rows of one sheet."""
    with open(path, newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            english = (row.get("original_en") or "").strip()
            translated = (row.get("translated") or "").strip()
            if not english or not translated:
                continue
            if len(english) > MAX_NAME or len(translated) > MAX_NAME:
                continue
            if "<" in english:
                continue
            if "\n" in english or "\n" in translated:
                continue
            yield english, translated


def patch_area_name(raw, english, translated, tokens=None):
    """Rewrite the map-screen area name in *raw*'s PAMM payload."""
    tokens = accent_tokens() if tokens is None else tokens
    row = pamm_row(raw)
    if row is None:
        return raw, None
    offset, length = row
    stored = bytes(raw[offset:offset + length])
    if stored[:3] not in (b"SLZ", b"SLE"):
        return raw, None
    payload = bytearray(slz.decompress(stored))

    encoded = container.encode_codepage(english, accent_tokens=tokens)[:-1]
    located = name_field(bytes(payload), encoded)
    if located is None:
        return raw, None
    at, field = located

    replacement = container.encode_codepage(translated, accent_tokens=tokens)[:-1]
    if len(replacement) >= field:
        raise AreaNameTooLong(
            "%r needs %d byte(s) but the map-name field holds %d"
            % (translated, len(replacement) + 1, field))

    expanded_before = len(payload)
    payload[at:at + field] = replacement + b"\0" * (field - len(replacement))
    if len(payload) != expanded_before:
        raise AssertionError("PAMM expanded size changed")

    packed = slz_compress.compress(bytes(payload), mode=stored[3], optimal=True)
    if slz.decompress(packed) != bytes(payload):
        raise ValueError("PAMM re-encode did not round trip")
    if len(packed) > length:
        raise AreaNameTooLong(
            "%r re-encodes to %d byte(s), %d more than the PAMM row holds; "
            "the archive would have to grow" % (translated, len(packed),
                                                len(packed) - length))

    patched = bytearray(raw)
    patched[offset:offset + length] = packed.ljust(length, b"\0")
    return bytes(patched), {
        "offset": at,
        "field": field,
        "needs": len(replacement) + 1,
        "expanded": len(payload),
        "stored_before": length,
        "stored_after": len(packed),
    }


def area_names(path):
    """Read ``(english, translated, [resource, ...])`` from an area sheet."""
    with open(path, newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            english = (row.get("original_en") or "").strip()
            translated = (row.get("translated") or "").strip()
            where = (row.get("also_shown_in") or "").split()
            if english and translated and where:
                yield english, translated, [int(item) for item in where]


def patch_iso_in_memory(iso, english, translated, resources, tokens=None,
                        report=None):
    """Patch every named resource inside an ``IsoBuffer``-like object."""
    tokens = accent_tokens() if tokens is None else tokens
    patched = 0
    for resource in resources:
        raw = iso.read_entry(resource)
        if not raw:
            continue
        try:
            new_raw, info = patch_area_name(raw, english, translated, tokens)
        except AreaNameTooLong as exc:
            if report is not None:
                report.append((resource, str(exc)))
            continue
        if info is None:
            continue
        iso.write_entry(resource, new_raw)
        patched += 1
        if report is not None:
            report.append((resource, info))
    return patched


def cmd_report(args):
    """Say what each area name would cost, without writing anything."""
    tokens = accent_tokens()
    with open(args.iso, "rb") as handle:
        _name, total, table = triace.load_table(handle)
        print("%-28s %-6s %-7s %-7s %s"
              % ("area", "res", "field", "needs", "stored"))
        fits = refused = absent = 0
        for english, translated, resources in area_names(args.csv):
            for resource in resources:
                raw = dcms.read_entry(handle, table, total, resource)
                if not raw:
                    continue
                try:
                    _patched, info = patch_area_name(
                        raw, english, translated, tokens)
                except AreaNameTooLong as exc:
                    refused += 1
                    print("%-28s %-6d %s" % (english[:28], resource, exc))
                    continue
                if info is None:
                    absent += 1
                    continue
                fits += 1
                print("%-28s %-6d %-7d %-7d %d -> %d (%+d)"
                      % (english[:28], resource, info["field"], info["needs"],
                         info["stored_before"], info["stored_after"],
                         info["stored_after"] - info["stored_before"]))
    print("\n%d name(s) fit in place, %d refused, %d resource(s) carry no copy"
          % (fits, refused, absent))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser(
        "report", help="show the fit for every area name, writing nothing")
    report.add_argument("iso")
    report.add_argument(
        "csv", nargs="?",
        default=os.path.join("data", "vp2", "translate", "dialogue",
                             "scene-0029.csv"),
        help="the area sheet naming each area and where it is drawn")
    report.set_defaults(func=cmd_report)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
