# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Shared writer for the two identical sealstone overlay resources."""

from .. import direct_overlay
from . import _overlay_patch


LOAD_ADDRESS = 0x00495500
MODE = 3
FIXED_SPAN = 0x8910
RESOURCES = (866, 867)


def patch(resource, resource_number, label, patches, guards):
    resource = bytes(resource)
    owner = "Sealstone overlay"
    old = direct_overlay.read(
        resource, resource_number, owner, MODE, FIXED_SPAN
    )
    output, offsets = _overlay_patch._patch_words(
        old.output, LOAD_ADDRESS, label, patches, guards
    )
    rebuilt, new_size = direct_overlay.replace(
        resource, output, resource_number, owner, MODE, FIXED_SPAN
    )
    if direct_overlay.read(
            rebuilt, resource_number, owner, MODE, FIXED_SPAN
    ).output != output:
        raise ValueError("%s did not read back exactly" % label)
    return _overlay_patch.ResourcePatch(
        rebuilt, len(resource), "%s resource %d" % (label, resource_number),
        len(patches), offsets, old.stored_size, new_size,
        fixed_span=FIXED_SPAN,
    )
