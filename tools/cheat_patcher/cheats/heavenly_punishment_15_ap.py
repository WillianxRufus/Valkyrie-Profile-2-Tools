# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Make Freya's Heavenly Punishment cost 15 AP."""

from dataclasses import dataclass

from . import _overlay_patch
from .. import injected_code


LABEL = "Heavenly Punishment Costs 15 AP"
RESOURCE3_PATCHES = (
    (0x003067B0, 0x90620000, 0x087FAFC9),
    (0x003067B4, 0x2442FF93, 0x00000000),
)
RESOURCE3_GUARDS = ((0x003067B4, 0x2442FF93),)
BATTLE_PATCHES = (
    (0x0041A528, 0x2442FF67, 0x087FAFC0),
    (0x0041A52C, 0x02021818, 0x00000000),
)
BATTLE_GUARDS = ((0x0041A528, 0x2442FF67),)
INJECT_ADDRESS = 0x01FEBF00
INJECT_WORDS = (
    0x2442FF67, 0x2403002A, 0x14620003, 0x00000000, 0x2402000F,
    0x00000000, 0x02021818, 0x0810694C, 0x00000000, 0x90620000,
    0x2442FF93, 0x2403002A, 0x14620003, 0x00000000, 0x2402000F,
    0x00000000, 0x080C19EE,
)


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def patch_resource3(resource):
    return _overlay_patch.patch_resource3_words(
        resource, LABEL, RESOURCE3_PATCHES, RESOURCE3_GUARDS
    )


def patch_battle(resource):
    return _overlay_patch.patch_battle(
        resource, LABEL, BATTLE_PATCHES, BATTLE_GUARDS
    )


def patch_executable(data):
    return injected_code.patch_executable(
        data, "Heavenly Punishment routine",
        (injected_code.Write(INJECT_ADDRESS, INJECT_WORDS),),
    )


RESOURCE_PATCHERS = ((3, patch_resource3), (1781, patch_battle))
ISO_FILE_PATCHERS = ((injected_code.EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
