# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Read and rebuild resource 22's resident mode-2 main overlay."""

from dataclasses import dataclass
import struct

from . import sle, slz12


RESOURCE = 22
LOAD_ADDRESS = 0x0035EC80


@dataclass(frozen=True)
class Overlay:
    output: bytes
    stored_size: int


def read(resource):
    """Expand the sole final SLE stream and validate its load address."""
    resource = bytes(resource)
    streams = list(sle.iter_streams(resource))
    if len(streams) != 1 or streams[0].offset != 0 or streams[0].next_offset:
        raise ValueError("main overlay does not contain one final SLE stream")
    stream = streams[0]
    if stream.mode != 2:
        raise ValueError(
            "main overlay uses unsupported SLZ mode %d; expected mode 2"
            % stream.mode
        )
    if any(resource[len(stream.encoded):]):
        raise ValueError("main overlay has unknown data after its SLE stream")
    if len(stream.output) < 12:
        raise ValueError("main overlay is too small for its load address")
    observed = struct.unpack_from("<I", stream.output, 8)[0]
    if observed != LOAD_ADDRESS:
        raise ValueError(
            "main overlay load-base validation failed; expected 0x%08X, "
            "found 0x%08X" % (LOAD_ADDRESS, observed)
        )
    return Overlay(stream.output, stream.stored_size)


def replace(resource, output):
    """Recompress an expanded image without changing resource allocation."""
    resource = bytes(resource)
    old = read(resource)
    output = bytes(output)
    if len(output) != len(old.output):
        raise ValueError("main overlay expanded size changed")
    encoded = sle.conceal(slz12.compress(output, 2))
    if len(encoded) > len(resource):
        raise ValueError("recompressed main overlay exceeds resource 22")
    rebuilt = encoded.ljust(len(resource), b"\0")
    new = read(rebuilt)
    if new.output != output:
        raise ValueError("rebuilt main overlay did not expand as requested")
    return rebuilt, new.stored_size
