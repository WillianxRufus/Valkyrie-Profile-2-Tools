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
        "stop-removing-characters",
        "(!) Stop The Game From Removing Characters",
        "Keeps protected party members when the game rebuilds the active "
        "roster.",
        True,
    ),
    Cheat(
        "36-character-limit",
        "(!) 36 Characters Limit",
        "Raises the permanent roster limit from 33 to 36 characters.",
        True,
    ),
    Cheat(
        "join-all-unlocked",
        "(!) Characters Join With All Skills, Spells And Attacks Unlocked",
        "Recruited characters arrive with every skill, spell and attack "
        "unlocked.",
        True,
    ),
    Cheat(
        "mithra-swap",
        "(!) Mithra Swap",
        "Replaces Mithra's recruitment event with the PNACH special-character "
        "roster.",
        True,
    ),
    Cheat(
        "join-level-1",
        "(!) Characters Join At Level 1",
        "Makes the special recruited characters join at level 1; when Mithra "
        "Swap is also selected, its first nine join levels become 1 too.",
        True,
    ),
    Cheat(
        "heavenly-punishment-15-ap",
        "(!) Heavenly Punishment Costs 15 AP",
        "Reduces Freya's Heavenly Punishment AP cost to 15.",
        True,
    ),
    Cheat(
        "infinite-ap-attacks",
        "(!) Infinite AP And Attacks",
        "Removes AP costs and the attack-chain limit in battle.",
        True,
    ),
    Cheat(
        "battle-menu-always",
        "(!) Battle Menu Always Available",
        "Removes the battle menu cooldown so the menu can always be opened.",
        True,
    ),
    Cheat(
        "dupe-attacks",
        "(!) Dupe Attacks",
        "Allows the same attack to be assigned to multiple attack slots.",
        True,
    ),
    Cheat(
        "100-percent-drop-rate",
        "(!) 100% Drop Rate",
        "Guarantees broken-part and boss drops.",
        True,
    ),
    Cheat(
        "negate-encounters",
        "(!) Negate Encounters",
        "Permanently applies the effect of the Elusive Air Law sealstone.",
        True,
    ),
    Cheat(
        "hold-circle-float",
        "(!) Hold Circle To Float",
        "Lets the field character float after jumping while Circle is held.",
        True,
    ),
    Cheat(
        "equip-everything",
        "Let Everyone Equip Everything",
        "Allows every armor and weapon to be equipped by every character.",
        False,
    ),
    Cheat(
        "ether-set-effects",
        "Ether Set Effects",
        "Gives passive effects to the four pieces of the Ether set.",
        False,
    ),
    Cheat(
        "angel-slayer",
        "Angel Slayer",
        "Changes Angel Slayer to allow for 3 attacks.",
        False,
    ),
    Cheat(
        "restore-all-sealstones",
        "Restore A Sealstone To Unlock All",
        "Unlocks every sealstone when any one is restored. Known issue: the "
        "sealstone menu may show flickering colours at the top.",
        False,
    ),
    Cheat(
        "no-limit-sealstone-withdrawals",
        "No Limit For Sealstone Withdrawals",
        "Removes the switching limit; the number may go negative. Known "
        "issue: the sealstone menu may show flickering colours at the top.",
        False,
    ),
    Cheat(
        "99-skill-points",
        "99 Skill Points",
        "Gives every character 99 skill points in the skill menu.",
        False,
    ),
    Cheat(
        "all-items-99",
        "All Items 99",
        "Sets every ordinary item stack to 99 when the Items menu opens.",
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
