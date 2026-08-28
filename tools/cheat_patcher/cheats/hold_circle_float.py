# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Apply the PNACH pointer write after VP2's airborne velocity update."""

from dataclasses import dataclass

from . import _overlay_patch
from .. import injected_code


RESOURCE = 22
LABEL = "Hold Circle To Float"
HOOK_ADDRESS = 0x003974D4
INJECT_ADDRESS = 0x01FEB800
RETURN_ADDRESS = 0x003974DC

# The second airborne store is the final native write to the player's +0x2C4
# field each frame. Replay it and its following FPU comparison in the injected
# routine before performing the PNACH condition and pointer write.
HOOK_PATCHES = (
    (HOOK_ADDRESS, 0xE60202C4, 0x087FAE00),
    (HOOK_ADDRESS + 4, 0x46001036, 0x00000000),
)
GUARDS = (
    (0x003974B8, 0xE60102C4),
    (RETURN_ADDRESS, 0xC420DED8),
    (0x00397628, 0xAE0002C4),
)

# k0 and k1 are reserved scratch registers. The first two words are the
# displaced instructions. The remaining words implement:
#
#   if (*(u16 *)0x001CA1DC == 0xDFFF)
#       *(u32 *)(*(u32 *)0x0048E1E8 + 0x2C4) = 0xC1061000;
INJECT_WORDS = (
    0xE60202C4,  # swc1 f2, 0x2C4(s0)
    0x46001036,  # c.le.s f2, f0
    0x3C1A001D,  # lui k0, 0x001D
    0x975AA1DC,  # lhu k0, -0x5E24(k0) -> 0x001CA1DC
    0x341BDFFF,  # ori k1, zero, 0xDFFF
    0x175B0006,  # bne k0, k1, return
    0x00000000,
    0x3C1A0049,  # lui k0, 0x0049
    0x8F5AE1E8,  # lw k0, -0x1E18(k0) -> [0x0048E1E8]
    0x3C1BC106,  # lui k1, 0xC106
    0x377B1000,  # ori k1, k1, 0x1000 -> 0xC1061000
    0xAF5B02C4,  # sw k1, 0x2C4(k0)
    0x080E5D37,  # j 0x003974DC
    0x00000000,
)


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def patch_resource(resource):
    return _overlay_patch.patch_main(
        resource, LABEL, HOOK_PATCHES, GUARDS
    )


def patch_executable(data):
    return injected_code.patch_executable(
        data, "Hold Circle To Float routine",
        (injected_code.Write(INJECT_ADDRESS, INJECT_WORDS),),
    )


RESOURCE_PATCHERS = ((RESOURCE, patch_resource),)
ISO_FILE_PATCHERS = ((injected_code.EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
