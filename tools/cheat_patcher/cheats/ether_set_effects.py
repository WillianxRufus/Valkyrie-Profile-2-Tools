# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Give the four Ether equipment records their PNACH passive effects."""

from . import _overlay_patch


RESOURCE = 3
LABEL = "Ether Set Effects"
BYTE_PATCHES = (
    (0x00316A2C, 0x00, 0x03),
    (0x00316EFC, 0x00, 0x05),
    (0x003170F4, 0x00, 0x0A),
    (0x00317324, 0x00, 0x13),
)


def patch_resource(resource):
    return _overlay_patch.patch_resource3_bytes(resource, LABEL, BYTE_PATCHES)
