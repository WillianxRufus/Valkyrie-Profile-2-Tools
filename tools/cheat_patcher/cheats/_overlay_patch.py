# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Shared exact-word editing for cheats backed by loadable overlays."""

from dataclasses import dataclass
import struct

from .. import battle_overlay, main_overlay, menu_overlay, resource3_overlay


BATTLE_LOAD_ADDRESS = 0x0036D900


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    allocation_size: int
    label: str
    change_count: int
    overlay_offsets: tuple
    old_stored_size: int
    new_stored_size: int
    stream_offset: int = 0
    fixed_span: int = 0


def _validate_base(output, load_address, owner):
    observed = (struct.unpack_from("<I", output, 8)[0]
                if len(output) >= 12 else None)
    if observed != load_address:
        found = "missing" if observed is None else "0x%08X" % observed
        raise ValueError(
            "%s load-base validation failed; expected 0x%08X, found %s"
            % (owner, load_address, found)
        )


def _patch_words(output, load_address, label, patches, guards=()):
    """Return an image with exact full-word conditions and writes applied."""
    _validate_base(output, load_address, label)
    offsets = tuple(address - load_address for address, _, _ in patches)
    if any(offset < 0 or offset + 4 > len(output) for offset in offsets):
        raise ValueError("%s target falls outside its overlay" % label)
    observed = tuple(
        struct.unpack_from("<I", output, offset)[0] for offset in offsets
    )
    originals = tuple(original for _, original, _ in patches)
    replacements = tuple(replacement for _, _, replacement in patches)
    if observed == replacements:
        raise ValueError("%s is already patched" % label)
    if observed != originals:
        raise ValueError(
            "%s target validation failed; expected %s, found %s"
            % (label,
               "/".join("0x%08X" % word for word in originals),
               "/".join("0x%08X" % word for word in observed))
        )
    for address, expected in guards:
        offset = address - load_address
        if offset < 0 or offset + 4 > len(output):
            raise ValueError(
                "%s condition EE 0x%08X falls outside its overlay"
                % (label, address)
            )
        actual = struct.unpack_from("<I", output, offset)[0]
        if actual != expected:
            raise ValueError(
                "%s condition validation failed at EE 0x%08X; expected "
                "0x%08X, found 0x%08X"
                % (label, address, expected, actual)
            )
    patched = bytearray(output)
    for offset, replacement in zip(offsets, replacements):
        struct.pack_into("<I", patched, offset, replacement)
    return bytes(patched), offsets


def patch_main(resource, label, patches, guards=()):
    resource = bytes(resource)
    old = main_overlay.read(resource)
    output, offsets = _patch_words(
        old.output, main_overlay.LOAD_ADDRESS, label, patches, guards
    )
    rebuilt, new_size = main_overlay.replace(resource, output)
    if main_overlay.read(rebuilt).output != output:
        raise ValueError("%s did not read back exactly" % label)
    return ResourcePatch(
        rebuilt, len(resource), label, len(patches), offsets,
        old.stored_size, new_size,
    )


def patch_battle(resource, label, patches, guards=()):
    resource = bytes(resource)
    old = battle_overlay.read(resource)
    output, offsets = _patch_words(
        old.output, BATTLE_LOAD_ADDRESS, label, patches, guards
    )
    rebuilt, new_size = battle_overlay.replace(resource, output)
    if battle_overlay.read(rebuilt).output != output:
        raise ValueError("%s did not read back exactly" % label)
    return ResourcePatch(
        rebuilt, len(resource), label, len(patches), offsets,
        old.stored_size, new_size, old.stream_offset, old.item_span,
    )


def patch_menu(resource, resource_number, owner, mode, label, patches, guards=()):
    resource = bytes(resource)
    old = menu_overlay.read(resource, resource_number, owner, mode)
    output, offsets = _patch_words(
        old.output, 0x00495500, label, patches, guards
    )
    rebuilt, new_size = menu_overlay.replace(
        resource, output, resource_number, owner, mode
    )
    new = menu_overlay.read(rebuilt, resource_number, owner, mode)
    if new.output != output or rebuilt[old.wrapper_span:] != resource[old.wrapper_span:]:
        raise ValueError("%s did not read back exactly" % label)
    return ResourcePatch(
        rebuilt, len(resource), label, len(patches), offsets,
        old.stored_size, new_size, old.stream_offset, old.wrapper_span,
    )


def patch_resource3_bytes(resource, label, patches):
    """Apply address/original-byte/replacement-byte triples to resource 3."""
    resource = bytes(resource)
    old = resource3_overlay.read(resource)
    _validate_base(old.output, resource3_overlay.LOAD_ADDRESS, label)
    offsets = tuple(address - resource3_overlay.LOAD_ADDRESS
                    for address, _, _ in patches)
    if any(offset < 0 or offset >= len(old.output) for offset in offsets):
        raise ValueError("%s target falls outside the resource 3 overlay" % label)
    observed = tuple(old.output[offset] for offset in offsets)
    originals = tuple(original for _, original, _ in patches)
    replacements = tuple(replacement for _, _, replacement in patches)
    if observed == replacements:
        raise ValueError("%s is already patched" % label)
    if observed != originals:
        raise ValueError(
            "%s byte validation failed; expected %s, found %s"
            % (label,
               "/".join("0x%02X" % byte for byte in originals),
               "/".join("0x%02X" % byte for byte in observed))
        )
    output = bytearray(old.output)
    for offset, replacement in zip(offsets, replacements):
        output[offset] = replacement
    output = bytes(output)
    rebuilt, new_size = resource3_overlay.replace(resource, output)
    if resource3_overlay.read(rebuilt).output != output:
        raise ValueError("%s did not read back exactly" % label)
    return ResourcePatch(
        rebuilt, len(resource), label, len(patches), offsets,
        old.stored_size, new_size, old.stream_offset,
    )


def patch_resource3_words(resource, label, patches, guards=()):
    resource = bytes(resource)
    old = resource3_overlay.read(resource)
    output, offsets = _patch_words(
        old.output, resource3_overlay.LOAD_ADDRESS, label, patches, guards
    )
    rebuilt, new_size = resource3_overlay.replace(resource, output)
    if resource3_overlay.read(rebuilt).output != output:
        raise ValueError("%s did not read back exactly" % label)
    return ResourcePatch(
        rebuilt, len(resource), label, len(patches), offsets,
        old.stored_size, new_size, old.stream_offset,
    )
