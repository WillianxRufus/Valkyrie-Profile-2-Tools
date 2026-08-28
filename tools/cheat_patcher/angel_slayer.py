# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Build and verify the Angel Slayer three-attack ISO patch."""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import struct

from . import sle, slz3, triace


RESOURCE = 3
TARGET_ADDRESS = 0x00315280
ORIGINAL_WORD = 0x80000000
PATCHED_WORD = 0xC0000000
MODULE_LOAD_ADDRESS_OFFSET = 8


@dataclass(frozen=True)
class ResourcePatch:
    data: bytes
    stream_number: int
    stream_offset: int
    module_base: int
    module_offset: int
    old_stored_size: int
    new_stored_size: int
    allocation_size: int


@dataclass(frozen=True)
class BuildResult:
    output: Path
    iso_offset: int
    patch: ResourcePatch


def _word_at(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _target_candidates(resource):
    candidates = []
    for stream in sle.iter_streams(resource):
        if len(stream.output) < MODULE_LOAD_ADDRESS_OFFSET + 4:
            continue
        module_base = _word_at(stream.output, MODULE_LOAD_ADDRESS_OFFSET)
        module_offset = TARGET_ADDRESS - module_base
        if 0 <= module_offset <= len(stream.output) - 4:
            candidates.append((stream, module_base, module_offset,
                               _word_at(stream.output, module_offset)))
    return candidates


def _locate_target(resource, expected_word):
    candidates = _target_candidates(resource)
    matches = [item for item in candidates if item[3] == expected_word]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            "address 0x%08X with word 0x%08X appears in multiple modules"
            % (TARGET_ADDRESS, expected_word)
        )
    observed = ", ".join(
        "stream %d: 0x%08X" % (stream.number, word)
        for stream, _, _, word in candidates
    ) or "no module covers the address"
    raise ValueError(
        "Angel Slayer target validation failed at EE 0x%08X; expected "
        "0x%08X (%s)" % (TARGET_ADDRESS, expected_word, observed)
    )


def patch_resource(resource):
    """Patch resource 3 while preserving its outer allocation."""
    resource = bytes(resource)
    try:
        stream, module_base, module_offset, _ = _locate_target(
            resource, ORIGINAL_WORD
        )
    except ValueError as error:
        if any(item[3] == PATCHED_WORD for item in _target_candidates(resource)):
            raise ValueError("Angel Slayer is already patched in this image") from error
        raise
    if stream.next_offset:
        raise ValueError("target is not in the final SLE stream")
    if stream.mode != 3:
        raise ValueError(
            "target stream uses unsupported SLZ mode %d; expected mode 3"
            % stream.mode
        )
    old_end = stream.offset + len(stream.encoded)
    if any(resource[old_end:]):
        raise ValueError(
            "resource has non-zero data after the final SLE stream; refusing "
            "to overwrite unknown bytes"
        )

    patched_output = bytearray(stream.output)
    struct.pack_into("<I", patched_output, module_offset, PATCHED_WORD)
    new_slz = slz3.compress(bytes(patched_output), next_offset=stream.next_offset)
    new_sle = sle.conceal(new_slz)
    capacity = len(resource) - stream.offset
    if len(new_sle) > capacity:
        raise ValueError(
            "recompressed target stream needs 0x%X bytes but only 0x%X are "
            "available in resource %d" % (len(new_sle), capacity, RESOURCE)
        )

    rebuilt = bytearray(resource)
    rebuilt[stream.offset:] = b"\0" * capacity
    rebuilt[stream.offset:stream.offset + len(new_sle)] = new_sle
    rebuilt = bytes(rebuilt)
    verify_patched_resource(resource, rebuilt)
    return ResourcePatch(
        data=rebuilt,
        stream_number=stream.number,
        stream_offset=stream.offset,
        module_base=module_base,
        module_offset=module_offset,
        old_stored_size=stream.stored_size,
        new_stored_size=len(new_sle) - sle.HEADER_SIZE,
        allocation_size=len(resource),
    )


def verify_patched_resource(original, candidate):
    """Prove that the expanded target word is the only semantic change."""
    if len(original) != len(candidate):
        raise ValueError("resource allocation size changed")
    old_stream, old_base, old_offset, _ = _locate_target(original, ORIGINAL_WORD)
    new_stream, new_base, new_offset, _ = _locate_target(candidate, PATCHED_WORD)
    if (old_stream.number, old_stream.offset, old_base, old_offset) != (
            new_stream.number, new_stream.offset, new_base, new_offset):
        raise ValueError("target stream geometry changed during patching")
    if original[:old_stream.offset] != candidate[:new_stream.offset]:
        raise ValueError("bytes before the target stream changed")
    expected = bytearray(old_stream.output)
    struct.pack_into("<I", expected, old_offset, PATCHED_WORD)
    if bytes(expected) != new_stream.output:
        raise ValueError("expanded stream changed outside the target word")
    new_end = new_stream.offset + len(new_stream.encoded)
    if any(candidate[new_end:]):
        raise ValueError("recompressed stream does not have clean trailing slack")


def default_output_path(source):
    source = Path(source)
    build = Path(__file__).resolve().parent.parent / "build"
    return build / (source.stem + "-angel-slayer-x3.iso")


def build_iso(source, output=None):
    """Copy a clean ISO, patch resource 3, and verify the copy from disk."""
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve() if output else default_output_path(source)
    if not source.is_file():
        raise ValueError("source ISO does not exist: %s" % source)
    if source == output:
        raise ValueError("output must be different from the source ISO")
    if output.exists():
        raise ValueError("output already exists; refusing to overwrite: %s" % output)
    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise ValueError("partial output already exists; remove it first: %s" % partial)

    with source.open("rb") as source_handle:
        source_index = triace.read_index(source_handle)
        iso_offset, allocation = source_index.extent(RESOURCE)
        original_resource = triace.read_resource(
            source_handle, source_index, RESOURCE
        )
    patch = patch_resource(original_resource)
    if patch.allocation_size != allocation:
        raise ValueError("resource allocation changed unexpectedly")

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(source, partial)
        with partial.open("r+b") as candidate_handle:
            candidate_handle.seek(iso_offset)
            candidate_handle.write(patch.data)
            candidate_handle.flush()
            os.fsync(candidate_handle.fileno())
        with partial.open("rb") as candidate_handle:
            candidate_index = triace.read_index(candidate_handle)
            if candidate_index != source_index:
                raise ValueError("ISO resource index changed during patching")
            candidate_resource = triace.read_resource(
                candidate_handle, candidate_index, RESOURCE
            )
        verify_patched_resource(original_resource, candidate_resource)
        if partial.stat().st_size != source.stat().st_size:
            raise ValueError("output ISO size differs from source")
        partial.replace(output)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return BuildResult(output=output, iso_offset=iso_offset, patch=patch)
