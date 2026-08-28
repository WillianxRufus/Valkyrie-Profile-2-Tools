# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Set every ordinary item stack to 99 when the Items menu opens."""

from dataclasses import dataclass

from . import _overlay_patch
from .. import injected_code


RESOURCE = 644
OWNER = "CampItem"
MODE = 3
LABEL = "All Items 99"
PATCHES = ((0x0049EBB4, 0x19200178, 0x087FAF40),)
GUARDS = ((0x0049EBB4, 0x19200178),)
INJECT_ADDRESS = 0x01FEBC9C
INJECT_WRITES = (
    injected_code.Write(INJECT_ADDRESS, (
        0x341B02A2, 0x136D0031, 0x00000000, 0x341B02A3, 0x136D002E,
        0x00000000, 0x341B02A4, 0x136D002B, 0x00000000, 0x341B02A5,
        0x136D0028, 0x00000000, 0x341B02A6, 0x136D0025, 0x00000000,
        0x341B02A7, 0x136D0022, 0x00000000, 0x341B02B1, 0x136D001F,
        0x00000000, 0x10000017, 0x00000000,
    )),
    injected_code.Write(0x01FEBD00, (
        0x341B02EE, 0x01BBD82A, 0x13600017, 0x00000000, 0x1000FFE2,
        0x00000000, 0x00000000,
    )),
    injected_code.Write(0x01FEBD50, (
        0x34090063, 0xA1C90002, 0x341B0000, 0x08127AEF, 0x00000000,
        0x00000000, 0x11200003, 0x00000000, 0x1000FFF9, 0x00000000,
        0x341B0000, 0x08127C66, 0x00000000,
    )),
)


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def patch_resource(resource):
    return _overlay_patch.patch_menu(
        resource, RESOURCE, OWNER, MODE, LABEL, PATCHES, GUARDS
    )


def patch_executable(data):
    return injected_code.patch_executable(
        data, "All Items 99 routines", INJECT_WRITES
    )


RESOURCE_PATCHERS = ((RESOURCE, patch_resource),)
ISO_FILE_PATCHERS = ((injected_code.EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
