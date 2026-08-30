# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Structural identities inside VP2 voice banks."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
import struct

from ..scripts.paths import DATA_DIR
from ..scripts.triace_ps2_unpack import SECTOR, load_table


FIRST_VOICE_BANK = 1482
LAST_VOICE_BANK = 1566
VOICE_BANKS = tuple(range(FIRST_VOICE_BANK, LAST_VOICE_BANK + 1))
USA_BOOT = "SLUS_214.52"
JAPAN_BOOT = "SLPM_664.19"
SUPPORTED_BOOTS = {USA_BOOT: "en", JAPAN_BOOT: "jp"}
EXPORTED_NAME = re.compile(
    r"^(?P<bank>\d{4})-(?P<sub>\d{3})-(?P<clip>[0-9a-fA-F]{4})\.wav$",
    re.IGNORECASE,
)
UNMAPPED_NAME = re.compile(
    r"^unmapped-(?P<entry>\d{4})-(?P<sample>\d{3})-"
    r"(?P<clip>[0-9a-fA-F]{4})-(?P<zone>\d+)\.wav$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BankOwner:
    bank: int
    resource: int
    voice_scene: int | None
    slot_count: int


@dataclass(frozen=True)
class Clip:
    sub_index: int
    sub_offset: int
    sub_length: int
    clip_id: int
    payload_offset: int
    payload_length: int
    tail_flag: int


@dataclass(frozen=True)
class UnmappedVoice:
    entry: int
    sample: int
    clip_id: int
    zone: int


@dataclass(frozen=True)
class StandaloneClip:
    sample_index: int
    clip_id: int
    zone: int
    payload_offset: int
    payload_length: int
    tail_flag: int


def load_bank_map(path=None):
    path = Path(path or DATA_DIR / "voice-bank-map.csv")
    owners = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            owner = BankOwner(
                bank=int(row["bank"]),
                resource=int(row["resource"]),
                voice_scene=(
                    int(row["voice_scene"])
                    if row["voice_scene"].strip()
                    else None
                ),
                slot_count=int(row["slot_count"]),
            )
            if owner.bank in owners:
                raise ValueError("duplicate voice-bank map row: %d" % owner.bank)
            if owner.bank not in VOICE_BANKS:
                raise ValueError("voice-bank map row is outside 1482..1566")
            if owner.slot_count <= 0:
                raise ValueError("voice-bank map slot count must be positive")
            owners[owner.bank] = owner
    return owners


def load_unmapped_map(path=None):
    """Load language-dependent samples that have no proven scene owner."""
    path = Path(path or DATA_DIR / "unmapped-voice-map.csv")
    voices = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            voice = UnmappedVoice(
                entry=int(row["entry"]),
                sample=int(row["sample"]),
                clip_id=int(row["clip_id"], 16),
                zone=int(row["zone"]),
            )
            identity = (voice.entry, voice.sample)
            if identity in voices:
                raise ValueError(
                    "duplicate unmapped-voice row: %d sample %d" % identity
                )
            if voice.entry < 0 or voice.sample < 0 or voice.zone < 0:
                raise ValueError("unmapped-voice values must be non-negative")
            voices[identity] = voice
    return voices


def entry_span(table, total, index):
    if not 0 <= index < total:
        raise ValueError("voice bank %d is outside the disc index" % index)
    offset = table[index] * SECTOR
    length = table[total + index] * SECTOR
    if not length:
        raise ValueError("voice bank %d has no allocation" % index)
    return offset, length


def read_index(handle):
    name, total, table = load_table(handle)
    if name != "VP2":
        raise ValueError("the disc index belongs to %s, not VP2" % name)
    return total, table


def parse_bank(data: bytes) -> tuple[Clip, ...]:
    """Parse the PK2-like voice-bank table, including its five slack banks."""
    if len(data) < 8:
        raise ValueError("voice bank is too short for its subfile table")
    count = struct.unpack_from("<I", data, 0)[0]
    if not 0 < count <= 1024 or 4 + count * 4 > len(data):
        raise ValueError("invalid voice-bank subfile count: %d" % count)
    clips = []
    for sub_index in range(count):
        start_sector, sector_count = struct.unpack_from(
            "<HH", data, 4 + sub_index * 4
        )
        if not sector_count:
            continue
        sub_offset = start_sector * SECTOR
        sub_length = sector_count * SECTOR
        if sub_offset < 4 + count * 4 or sub_offset + sub_length > len(data):
            raise ValueError(
                "subfile %d extends outside its voice bank" % sub_index
            )
        subfile = data[sub_offset:sub_offset + sub_length]
        if subfile[:4] != b"SEQW":
            raise ValueError("subfile %d is not SEQW" % sub_index)
        if len(subfile) < 0x1C:
            raise ValueError("subfile %d has a truncated SEQW header" % sub_index)
        wav_offset = struct.unpack_from("<I", subfile, 4)[0]
        if wav_offset + 0x14 > len(subfile) or subfile[
                wav_offset:wav_offset + 4] != b"WAV ":
            raise ValueError("subfile %d has no valid WAV chunk" % sub_index)
        header_length = struct.unpack_from("<I", subfile, wav_offset + 8)[0]
        payload_length = struct.unpack_from("<I", subfile, wav_offset + 0x10)[0]
        payload_offset = (wav_offset + header_length + 0x0F) & ~0x0F
        if (payload_length <= 0 or payload_length % 16 or
                payload_offset + payload_length > len(subfile)):
            raise ValueError("subfile %d has an invalid ADPCM payload" % sub_index)
        clip_id = struct.unpack_from("<H", subfile, 0x1A)[0]
        tail_flag = subfile[payload_offset + payload_length - 15]
        clips.append(Clip(
            sub_index=sub_index,
            sub_offset=sub_offset,
            sub_length=sub_length,
            clip_id=clip_id,
            payload_offset=payload_offset,
            payload_length=payload_length,
            tail_flag=tail_flag,
        ))
    if not clips:
        raise ValueError("voice bank contains no SEQW clips")
    return tuple(clips)


def parse_standalone(data: bytes) -> tuple[StandaloneClip, ...]:
    """Parse independently addressed samples from one standalone SEQW."""
    if len(data) < 0x40 or data[:4] != b"SEQW":
        raise ValueError("standalone voice entry is not SEQW")
    wav_offset = struct.unpack_from("<I", data, 4)[0]
    if (wav_offset + 0x20 > len(data) or
            data[wav_offset:wav_offset + 4] != b"WAV "):
        raise ValueError("standalone SEQW has no valid WAV chunk")
    header_length, table_length = struct.unpack_from(
        "<II", data, wav_offset + 8
    )
    payload_length = struct.unpack_from("<I", data, wav_offset + 0x10)[0]
    payload_offset = (wav_offset + header_length + 0x0F) & ~0x0F
    table_start = wav_offset + 0x20
    table_end = table_start + table_length
    if (header_length < 0x20 or table_end > wav_offset + header_length or
            payload_length <= 0 or payload_length % 16 or
            payload_offset + payload_length > len(data)):
        raise ValueError("standalone SEQW has invalid WAV geometry")

    samples = []
    position = table_start
    while position < table_end:
        if position + 4 > table_end:
            raise ValueError("standalone SEQW has a truncated sample record")
        record_length, clip_id = struct.unpack_from("<HH", data, position)
        if record_length < 0x18 or position + record_length > table_end:
            raise ValueError("standalone SEQW has an invalid sample record")
        cursor = position + 4
        zone = 0
        while (cursor + 0x14 <= position + record_length and
               struct.unpack_from("<I", data, cursor)[0] == 0x14):
            start = struct.unpack_from("<I", data, cursor + 0x10)[0]
            samples.append((clip_id, zone, start))
            cursor += 0x14
            zone += 1
        if not zone or any(data[cursor:position + record_length]):
            raise ValueError("standalone SEQW has an unknown sample record")
        position += record_length
    if position != table_end or not samples:
        raise ValueError("standalone SEQW has no complete sample table")

    starts = [sample[2] for sample in samples]
    if (starts != sorted(starts) or len(starts) != len(set(starts)) or
            any(start % 16 or start >= payload_length for start in starts)):
        raise ValueError("standalone SEQW has invalid sample offsets")
    clips = []
    for sample_index, (clip_id, zone, start) in enumerate(samples):
        end = (starts[sample_index + 1]
               if sample_index + 1 < len(starts) else payload_length)
        slot = data[payload_offset + start:payload_offset + end]
        flags = [slot[offset + 1] for offset in range(0, len(slot), 16)
                 if slot[offset + 1]]
        clips.append(StandaloneClip(
            sample_index=sample_index,
            clip_id=clip_id,
            zone=zone,
            payload_offset=payload_offset + start,
            payload_length=end - start,
            tail_flag=flags[-1] if flags else 0,
        ))
    return tuple(clips)


def exported_filename(bank: int, clip: Clip) -> str:
    return "%04d-%03d-%04x.wav" % (bank, clip.sub_index, clip.clip_id)


def parse_exported_filename(path):
    match = EXPORTED_NAME.match(Path(path).name)
    if not match:
        return None
    return tuple(int(match.group(name), 16 if name == "clip" else 10)
                 for name in ("bank", "sub", "clip"))


def unmapped_filename(entry: int, clip: StandaloneClip) -> str:
    return "unmapped-%04d-%03d-%04x-%d.wav" % (
        entry, clip.sample_index, clip.clip_id, clip.zone
    )


def parse_unmapped_filename(path):
    match = UNMAPPED_NAME.match(Path(path).name)
    if not match:
        return None
    return tuple(int(match.group(name), 16 if name == "clip" else 10)
                 for name in ("entry", "sample", "clip", "zone"))
