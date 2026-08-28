# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Make recruited characters join with every ability unlocked."""

from dataclasses import dataclass

from .. import injected_code, resource3_overlay


RESOURCE = 3
LABEL = "Characters Join With All Skills, Spells And Attacks Unlocked"
PATCHES = (
    (0x002F3F9C, 0x14200130, 0x00000000),
    (0x002F60C0, 0x000318C0, 0x087FA880),
    (0x002F60C4, 0x00431021, 0x00000000),
)
INJECT_ADDRESS = 0x01FEA1E8
INJECT_WORDS = (
    0x000318C0, 0x10000010, 0x00000000, 0x24030001, 0x1000000D, 0x00000000,
    0x341B0000, 0x3C01003C, 0x342120D4, 0x94210000, 0x1761FFF5, 0x00000000,
    0x341B0018, 0x136EFFF5, 0x00000000, 0x240300FF, 0x00000000, 0x00000000,
    0x3C010036, 0x34210000, 0x341B0000, 0x00431021, 0x080BD832, 0x00000000,
)


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    allocation_size: int
    label: str
    change_count: int
    overlay_offsets: tuple
    old_stored_size: int
    new_stored_size: int


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def patch_resource(resource):
    patched = resource3_overlay.patch_words(resource, LABEL, PATCHES)
    return ResourcePatch(
        patched.data, len(resource), "resource 3 recruitment hooks",
        len(PATCHES), patched.offsets,
        patched.old_stored_size, patched.new_stored_size,
    )


def patch_executable(data):
    return injected_code.patch_executable(
        data, "main executable all-abilities routine",
        (injected_code.Write(INJECT_ADDRESS, INJECT_WORDS),),
    )


RESOURCE_PATCHERS = ((RESOURCE, patch_resource),)
ISO_FILE_PATCHERS = ((injected_code.EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
