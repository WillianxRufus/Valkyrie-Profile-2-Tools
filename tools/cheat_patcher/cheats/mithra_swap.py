# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Replace Mithra's recruitment event with the PNACH character roster."""

from dataclasses import dataclass
import struct

from .. import elf, injected_code, main_overlay


RESOURCE = 22
LABEL = "Mithra Swap"
PATCHES = (
    (0x003B5DDC, 0x100000B6, 0x00000000),
    (0x003C20C0, 0x2685001E, 0x087FAB60),
)
INJECT_ADDRESS = 0x01FEAD80
INJECT_WORDS = (
    0x24520000, 0x2405000D, 0x0C0ED754, 0x24060032, 0x00000000, 0x2405000D,
    0x0C0ED754, 0x24060032, 0x00000000, 0x2405000D, 0x0C0ED754, 0x24060032,
    0x00000000, 0x2405000D, 0x0C0ED754, 0x24060032, 0x00000000, 0x24050009,
    0x0C0ED754, 0x24060032, 0x00000000, 0x24050008, 0x0C0ED754, 0x2406002D,
    0x00000000, 0x24050001, 0x0C0ED754, 0x2406002F, 0x00000000, 0x2405000A,
    0x0C0ED754, 0x24060037, 0x00000000, 0x24050002, 0x0C0ED754, 0x24060030,
    0x00000000, 0x24050007, 0x0C0ED754, 0x24060008, 0x00000000, 0x24050004,
    0x0C0ED754, 0x24060005, 0x00000000, 0x24050005, 0x0C0ED754, 0x24060007,
    0x00000000, 0x24050031, 0x0C0ED754, 0x24060005, 0x00000000, 0x24050022,
    0x0C0ED754, 0x26460000, 0x00000000, 0x26420000, 0x24120000, 0x02A0202D,
    0x2405003C, 0x080F0832, 0x00000000,
)
LEVEL1_INDICES = (3, 7, 11, 15, 19, 23, 27, 31, 35)
LEVEL1_ONLY_WORDS = tuple(
    0x24060001 if index in LEVEL1_INDICES else 0
    for index in range(len(INJECT_WORDS))
)
INJECT_WORDS_WITH_LEVEL1 = tuple(
    0x24060001 if index in LEVEL1_INDICES else word
    for index, word in enumerate(INJECT_WORDS)
)


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    allocation_size: int
    label: str
    change_count: int
    old_stored_size: int
    new_stored_size: int


@dataclass(frozen=True)
class PatchSet:
    resources: tuple
    files: tuple


def _observed_words(output):
    return tuple(
        struct.unpack_from("<I", output, address - main_overlay.LOAD_ADDRESS)[0]
        for address, _, _ in PATCHES
    )


def patch_main_resource(resource):
    resource = bytes(resource)
    overlay = main_overlay.read(resource)
    observed = _observed_words(overlay.output)
    originals = tuple(original for _, original, _ in PATCHES)
    replacements = tuple(replacement for _, _, replacement in PATCHES)
    if observed == replacements:
        raise ValueError("Mithra Swap is already patched in the main overlay")
    if observed != originals:
        raise ValueError(
            "Mithra Swap condition validation failed; expected %s, found %s"
            % ("/".join("0x%08X" % word for word in originals),
               "/".join("0x%08X" % word for word in observed))
        )
    patched_output = bytearray(overlay.output)
    for address, _, replacement in PATCHES:
        struct.pack_into(
            "<I", patched_output,
            address - main_overlay.LOAD_ADDRESS, replacement
        )
    rebuilt, new_stored_size = main_overlay.replace(resource, patched_output)
    expected = bytearray(overlay.output)
    for address, _, replacement in PATCHES:
        struct.pack_into(
            "<I", expected, address - main_overlay.LOAD_ADDRESS, replacement
        )
    if main_overlay.read(rebuilt).output != bytes(expected):
        raise ValueError("Mithra Swap changed outside its two guarded words")
    return ResourcePatch(
        rebuilt, len(resource), "main overlay Mithra recruitment hook",
        len(PATCHES), overlay.stored_size, new_stored_size,
    )


def patch_executable(data):
    """Install Mithra's routine, preserving prior Level 1 overrides."""
    data = bytes(data)
    zero_words = (0,) * len(INJECT_WORDS)
    try:
        offset = elf.file_offset_for_address(
            data, INJECT_ADDRESS, len(INJECT_WORDS) * 4
        )
        observed = struct.unpack_from(
            "<%dI" % len(INJECT_WORDS), data, offset
        )
    except ValueError:
        observed = zero_words
    if observed == zero_words:
        words = INJECT_WORDS
    elif observed == LEVEL1_ONLY_WORDS:
        words = INJECT_WORDS_WITH_LEVEL1
    else:
        raise ValueError("Mithra Swap injected-code region is not empty")
    return injected_code.patch_executable(
        data, "main executable Mithra Swap routine",
        (injected_code.Write(INJECT_ADDRESS, words, (observed,)),),
    )


RESOURCE_PATCHERS = ((RESOURCE, patch_main_resource),)
ISO_FILE_PATCHERS = ((injected_code.EXECUTABLE_PATH, patch_executable),)


def combine_details(resources, files):
    return PatchSet(tuple(resources), tuple(files))
