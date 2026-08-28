# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Minimal read-only ISO9660 file locator."""

from dataclasses import dataclass
import struct


SECTOR_SIZE = 0x800


@dataclass(frozen=True)
class FileExtent:
    path: str
    offset: int
    size: int


def _primary_volume_descriptor(handle):
    for sector in range(16, 64):
        handle.seek(sector * SECTOR_SIZE)
        descriptor = handle.read(SECTOR_SIZE)
        if len(descriptor) != SECTOR_SIZE or descriptor[1:6] != b"CD001":
            raise ValueError("not an ISO9660 image: missing volume descriptor")
        if descriptor[0] == 1:
            return descriptor
        if descriptor[0] == 255:
            break
    raise ValueError("ISO9660 primary volume descriptor was not found")


def _directory_entries(data):
    entries = []
    position = 0
    while position < len(data):
        length = data[position]
        if length == 0:
            position = (position // SECTOR_SIZE + 1) * SECTOR_SIZE
            continue
        if length < 34 or position + length > len(data):
            raise ValueError("malformed ISO9660 directory record")
        record = data[position:position + length]
        name_length = record[32]
        if 33 + name_length > len(record):
            raise ValueError("truncated ISO9660 file name")
        name_bytes = record[33:33 + name_length]
        if not (name_length == 1 and name_bytes in (b"\0", b"\1")):
            try:
                name = name_bytes.decode("ascii")
            except UnicodeDecodeError as error:
                raise ValueError("non-ASCII ISO9660 file name") from error
            name = name.split(";", 1)[0]
            is_directory = bool(record[25] & 2)
            if name.endswith(".") and not is_directory:
                name = name[:-1]
            entries.append((
                name,
                struct.unpack_from("<I", record, 2)[0],
                struct.unpack_from("<I", record, 10)[0],
                is_directory,
            ))
        position += length
    return entries


def _read_directory(handle, sector, size):
    handle.seek(sector * SECTOR_SIZE)
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("truncated ISO9660 directory")
    return _directory_entries(data)


def locate_file(handle, path):
    """Locate one file by an absolute primary-volume path."""
    components = [item for item in path.replace("\\", "/").split("/") if item]
    if not components:
        raise ValueError("ISO9660 file path is empty")
    descriptor = _primary_volume_descriptor(handle)
    root = descriptor[156:190]
    sector = struct.unpack_from("<I", root, 2)[0]
    size = struct.unpack_from("<I", root, 10)[0]
    current_path = ""
    for number, component in enumerate(components):
        matches = [entry for entry in _read_directory(handle, sector, size)
                   if entry[0].upper() == component.upper()]
        if len(matches) != 1:
            raise ValueError(
                "ISO9660 path /%s has %d matches"
                % ("/".join(components[:number + 1]), len(matches))
            )
        name, sector, size, is_directory = matches[0]
        current_path += "/" + name
        is_last = number == len(components) - 1
        if is_last:
            if is_directory:
                raise ValueError("ISO9660 path is a directory: %s" % current_path)
            return FileExtent(current_path, sector * SECTOR_SIZE, size)
        if not is_directory:
            raise ValueError("ISO9660 path component is not a directory: %s" % current_path)
    raise AssertionError("unreachable empty ISO9660 path")
