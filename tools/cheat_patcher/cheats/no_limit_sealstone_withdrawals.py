# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Remove the sealstone withdrawal/switching limit."""

from dataclasses import dataclass

from . import _sealstone_overlay


LABEL = "No Limit For Sealstone Withdrawals"
PATCHES = (
    (0x0049E094, 0x92030002, 0x34030064),
    (0x004A0158, 0x92230002, 0x34030064),
    (0x004A0BCC, 0x10600004, 0x10000004),
    (0x004A1420, 0x92440002, 0x34040064),
)
GUARDS = ((0x0049E094, 0x92030002),)


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple = ()


def patch_resource_866(resource):
    return _sealstone_overlay.patch(resource, 866, LABEL, PATCHES, GUARDS)


def patch_resource_867(resource):
    return _sealstone_overlay.patch(resource, 867, LABEL, PATCHES, GUARDS)


RESOURCE_PATCHERS = ((866, patch_resource_866), (867, patch_resource_867))


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
