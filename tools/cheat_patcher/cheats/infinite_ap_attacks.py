# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Remove battle AP costs and the attack-chain limit."""

from . import _overlay_patch


RESOURCE = 1781
LABEL = "Infinite AP And Attacks"
GUARDS = ((0x00397CAC, 0x0262102A),)
PATCHES = (
    (0x003A8CA0, 0xA4A80022, 0x00000000),
    (0x00405E18, 0xA4E30022, 0x00000000),
    (0x0041A00C, 0xA5030022, 0x00000000),
    (0x0041A250, 0x27BDFFB0, 0x03E00008),
)


def patch_resource(resource):
    return _overlay_patch.patch_battle(resource, LABEL, PATCHES, GUARDS)
