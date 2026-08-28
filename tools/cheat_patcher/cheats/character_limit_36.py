# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Raise the permanent roster limit from 33 to 36 characters."""

from . import _overlay_patch


RESOURCE = 22
LABEL = "36 Characters Limit"
PATCHES = ((0x003B5E58, 0x2A620021, 0x2A620024),)
GUARDS = ((0x003B5E58, 0x2A620021),)


def patch_resource(resource):
    return _overlay_patch.patch_main(resource, LABEL, PATCHES, GUARDS)
