# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Allow the same attack to occupy multiple CampAttack slots."""

from . import _overlay_patch


RESOURCE = 647
OWNER = "CampAttack"
MODE = 1
LABEL = "Dupe Attacks"
GUARDS = ((0x00499AF4, 0x1460FFD8),)
PATCHES = ((0x00499AF0, 0x28A30004, 0x28A30000),)


def patch_resource(resource):
    return _overlay_patch.patch_menu(
        resource, RESOURCE, OWNER, MODE, LABEL, PATCHES, GUARDS
    )
