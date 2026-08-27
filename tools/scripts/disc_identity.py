# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Tell which release a disc image is, before anything reads it as one."""
from __future__ import annotations

import os
import re
from pathlib import Path

SEARCH_BYTES = 3 * 1024 * 1024

_BOOT = re.compile(rb"(SLUS|SLPS|SLPM|SLES|SLED|SCUS|SCPS)_[0-9]{3}\.[0-9]{2}")

#: Boot prefix to the region it means.
REGIONS = {
    "SLUS": "usa", "SCUS": "usa",
    "SLPS": "japan", "SLPM": "japan", "SCPS": "japan",
    "SLES": "europe", "SLED": "europe",
}

#: What this project can read, and what each is for.
ROLES = {
    "usa": "the release everything is built from",
    "japan": "the original script, used as a translator reference",
    "europe": "not a source: its text is already a translation",
}


class DiscError(ValueError):
    """The image is not one this project can use, or cannot be read."""


def identify(path: str | os.PathLike[str]) -> tuple[str, str]:
    """``(boot name, region)`` for *path*."""
    image = Path(path).expanduser()
    if not image.is_file():
        raise DiscError(f"no such disc image: {image}")
    try:
        with open(image, "rb") as handle:
            head = handle.read(SEARCH_BYTES)
    except OSError as exc:
        raise DiscError(f"cannot read {image}: {exc}") from exc

    match = _BOOT.search(head)
    if match is None:
        raise DiscError(
            f"{image.name} does not look like a PlayStation 2 disc image: "
            f"no boot executable is named in its first "
            f"{SEARCH_BYTES // (1024 * 1024)} MB")
    boot = match.group(0).decode("ascii")
    return boot, REGIONS[boot.split("_")[0]]


def describe(path: str | os.PathLike[str]) -> str:
    """One line naming the disc, for a message a person has to act on."""
    boot, region = identify(path)
    return f"{Path(path).name} is {boot} ({region}) -- {ROLES[region]}"
