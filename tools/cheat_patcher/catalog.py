# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""What each patch is called and what it does, for people choosing them.

`build.PATCHERS` is the registry a build reads; this is the same set described
for a reader.  The titles and summaries are the ones from the PNACH these
patches were ported from, so a player who knows the cheat by its PCSX2 name
recognises it here.

A cheat marked `(!)` in the PNACH rewrites bytes inside a function, which the
game's checksum notices: it hashes its own code after cutscenes, battles, map
changes and saves, and freezes on a mismatch.  Those cheats therefore need
`disable-anti-cheat` applied with them, which `requires_anti_cheat` records.
"""

from typing import NamedTuple

from .build import PATCHERS


class Cheat(NamedTuple):
    name: str
    title: str
    summary: str
    requires_anti_cheat: bool


ANTI_CHEAT = "disable-anti-cheat"

CHEATS = (
    Cheat(
        ANTI_CHEAT,
        "Disable Anti-Cheat Systems",
        "Stops the checksum that freezes the game after any code change, and "
        "skips the hash itself, which also shortens loads. Required by the "
        "(!) patches below.",
        False,
    ),
    Cheat(
        "battle-anti-freeze",
        "(!) Anti Freeze In Battles",
        "Prevents the freeze when a late-game character is on the active "
        "party early. Safe to leave on; it stops mattering after the Hall of "
        "Valhalla.",
        True,
    ),
    Cheat(
        "angel-slayer",
        "Angel Slayer",
        "Changes Angel Slayer to allow for 3 attacks.",
        False,
    ),
    Cheat(
        "equip-everything",
        "Let Everyone Equip Everything",
        "Allows every armor and weapon to be equipped by every character.",
        False,
    ),
)

BY_NAME = {cheat.name: cheat for cheat in CHEATS}


def required_with(names):
    """The full patch set to build, once dependencies are honoured.

    Selecting a `(!)` patch without the anti-cheat one produces an ISO that
    freezes rather than one that misbehaves, so the dependency is added here
    instead of being left to whoever ticked the boxes.
    """
    chosen = [name for name in BY_NAME if name in set(names)]
    if any(BY_NAME[name].requires_anti_cheat for name in chosen):
        if ANTI_CHEAT not in chosen:
            chosen.append(ANTI_CHEAT)
    return tuple(name for name in BY_NAME if name in set(chosen))


def _check():
    """The catalog and the registry must describe the same set."""
    missing = sorted(set(PATCHERS) - set(BY_NAME))
    extra = sorted(set(BY_NAME) - set(PATCHERS))
    if missing or extra:
        raise RuntimeError(
            "catalog does not match PATCHERS: missing %s, unknown %s"
            % (missing, extra))


_check()
