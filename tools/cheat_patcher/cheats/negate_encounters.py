# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Apply the Elusive Air Law encounter-negation effect permanently."""

from . import _overlay_patch


RESOURCE = 22
LABEL = "Negate Encounters"
PATCHES = ((0x0041CB04, 0x10400004, 0x00000000),)
GUARDS = ((0x0041CB04, 0x10400004),)


def patch_resource(resource):
    return _overlay_patch.patch_main(resource, LABEL, PATCHES, GUARDS)
