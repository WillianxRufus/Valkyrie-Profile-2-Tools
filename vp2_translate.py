#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Manage local VP2 translator workspaces and source-free language packs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.scripts.translation_pack import PackError, load_pack
from tools.scripts.workspace_extract import generate_workspace
from tools.scripts.public_build import build_iso
from tools.scripts.paths import PROJECT_ROOT, WORKSPACE_DIR


DEFAULT_WORKSPACE = str(WORKSPACE_DIR)
DEFAULT_PACK = str(PROJECT_ROOT / "translations" / "pt-BR")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check", action="store_true",
        help="verify this build carries everything it needs, then exit")
    commands = parser.add_subparsers(dest="command", required=False)

    check = commands.add_parser("check-pack", help="validate one language pack")
    check.add_argument("pack")

    generate = commands.add_parser(
        "generate", help="generate the local reference and internal build state")
    generate.add_argument("images", nargs="*", metavar="IMAGE",
                          help="disc image(s): the USA release, and "
                               "optionally the Japanese one for its original "
                               "script")
    generate.add_argument("--jp-image", help=argparse.SUPPRESS)
    generate.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                          help="where to write it (default: %(default)s)")

    build = commands.add_parser(
        "build", help="build a translated ISO from a generated workspace")
    build.add_argument("usa_image")
    build.add_argument("--pack", default=DEFAULT_PACK,
                       help="language pack to build (default: %(default)s)")
    build.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                       help="the workspace `generate` made (default: %(default)s)")
    build.add_argument("--output")
    build.add_argument(
        "--no-verify", action="store_true",
        help="skip read-back verification (faster, less safe)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_check:
        from tools.scripts.public_release import self_check
        return self_check()
    if not args.command:
        parser.error("a command is required")
    try:
        if args.command == "generate":
            images = list(args.images)
            if args.jp_image:
                images.append(args.jp_image)
            if not images:
                raise PackError("give at least one disc image")
            details = generate_workspace(
                images, args.workspace)
            print(
                "generated "
                f"{details['scene_sheets'] + details['container_sheets'] + details['chapter_sheets']} "
                "source sheet(s), "
                f"{details['scene_lines'] + details['container_lines'] + details['chapter_lines']} row(s)")
        elif args.command == "build":
            output = build_iso(
                args.usa_image, args.pack, workspace=args.workspace,
                output=args.output, no_verify=args.no_verify)
            print(f"built {output}")
        elif args.command == "check-pack":
            rows = load_pack(args.pack)
            print(f"pack ok: {len(rows)} translated record(s)")
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
