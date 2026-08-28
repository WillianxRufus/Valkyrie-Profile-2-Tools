# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Guarantee broken-part and boss drops."""

from . import _overlay_patch


RESOURCE = 1781
LABEL = "100% Drop Rate"
PATCHES = (
    (0x003E2EC8, 0x1483001F, 0x00000000),
    (0x00410CC4, 0x1020001C, 0x00000000),
)
GUARDS = tuple((address, original) for address, original, _ in PATCHES)


def patch_resource(resource):
    return _overlay_patch.patch_battle(resource, LABEL, PATCHES, GUARDS)
