# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Unlock every sealstone when one sealstone is restored."""

from dataclasses import dataclass

from . import _sealstone_overlay
from .. import injected_code


LABEL = "Restore A Sealstone To Unlock All"
PATCHES = (
    (0x0049A6AC, 0x0002143F, 0x34020001),
    (0x0049A930, 0xA2020004, 0x087FB740),
    (0x0049A934, 0x826205E8, 0x00000000),
)
GUARDS = ((0x0049A6AC, 0x0002143F),)
INJECT_ADDRESS = 0x01FEDD00
INJECT_WORDS = (
    0x341B0000, 0x34150044, 0x00000000, 0x00000000, 0x34090018,
    0x113B000F, 0x00000000, 0x34090040, 0x113B000C, 0x00000000,
    0x34090010, 0x113B0009, 0x00000000, 0x3409000F, 0x113B0006,
    0x00000000, 0x3409001F, 0x113B0003, 0x00000000, 0xA2020004,
    0xA2060002, 0x26100006, 0x277B0001, 0x0375482A, 0x1520FFEB,
    0x00000000, 0x341B0000, 0x34150000, 0x34090000, 0x826205E8,
    0x08126A4E, 0x00000000,
)


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def patch_resource_866(resource):
    return _sealstone_overlay.patch(resource, 866, LABEL, PATCHES, GUARDS)


def patch_resource_867(resource):
    return _sealstone_overlay.patch(resource, 867, LABEL, PATCHES, GUARDS)


def patch_executable(data):
    return injected_code.patch_executable(
        data, "restore all sealstones routine",
        (injected_code.Write(INJECT_ADDRESS, INJECT_WORDS),),
    )


RESOURCE_PATCHERS = ((866, patch_resource_866), (867, patch_resource_867))
ISO_FILE_PATCHERS = ((injected_code.EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
