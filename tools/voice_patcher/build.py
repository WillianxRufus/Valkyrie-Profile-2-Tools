# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Transactional extraction and fixed-slot ISO voice replacement."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil

from . import audio
from .layout import (
    JAPAN_BOOT, SUPPORTED_BOOTS, USA_BOOT, VOICE_BANKS, entry_span,
    exported_filename, load_bank_map, parse_bank, parse_exported_filename,
    read_index,
)
from ..scripts import disc_identity
from ..scripts.paths import PROJECT_ROOT, output_root


COPY_CHUNK = 8 * 1024 * 1024
MANIFEST_FIELDS = (
    "region", "resource", "voice_scene", "bank", "sub", "clip_id",
    "relative_path", "slot_bytes", "max_seconds", "seconds", "target_rms",
    "peak", "voiced_pct", "silent", "sha256",
)


@dataclass(frozen=True)
class ExtractionResult:
    output: Path
    region: str
    banks: int
    clips: int
    mapped_banks: int


@dataclass(frozen=True)
class Replacement:
    path: Path
    bank: int
    sub: int
    clip_id: int
    slot_bytes: int
    truncated: bool = False


@dataclass(frozen=True)
class PatchResult:
    output: Path
    region: str
    replacements: tuple[Replacement, ...]


def default_voice_root():
    """Repository-local output in source, current-directory output frozen."""
    if getattr(__import__("sys"), "frozen", False):
        return Path.cwd() / "voices"
    return PROJECT_ROOT / "voices"


def default_patch_output(source):
    source = Path(source)
    return output_root() / (source.stem + "-voice-patched.iso")


def describe_disc(path):
    """Return ``(language folder, boot)`` for the two supported releases."""
    try:
        boot, _region = disc_identity.identify(path)
    except disc_identity.DiscError as exc:
        raise ValueError(str(exc)) from exc
    if boot not in SUPPORTED_BOOTS:
        raise ValueError(
            "unsupported disc %s; select Valkyrie Profile 2 USA (%s) or "
            "Japan (%s)" % (boot, USA_BOOT, JAPAN_BOOT)
        )
    return SUPPORTED_BOOTS[boot], boot


def _validated_source(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError("source ISO does not exist: %s" % path)
    region, boot = describe_disc(path)
    with path.open("rb") as handle:
        read_index(handle)
    return path, region, boot


def _read_bank(handle, table, total, bank):
    offset, length = entry_span(table, total, bank)
    handle.seek(offset)
    data = handle.read(length)
    if len(data) != length:
        raise ValueError("voice bank %d extends past the ISO" % bank)
    return offset, data


def extract_voices(source, output=None, progress=None, bank_map=None):
    """Decode every USA/Japan voice bank to a reversible folder tree."""
    say = progress or (lambda _message: None)
    source, region, boot = _validated_source(source)
    root = Path(output).expanduser().resolve() if output else default_voice_root()
    destination = root / region
    partial = root / (region + ".partial")
    if destination.exists():
        raise ValueError(
            "voice output already exists; move or remove it first: %s"
            % destination
        )
    if partial.exists():
        raise ValueError(
            "partial voice output already exists; remove it first: %s" % partial
        )
    owners = load_bank_map(bank_map)
    rows = []
    mapped = 0
    root.mkdir(parents=True, exist_ok=True)
    partial.mkdir()
    try:
        with source.open("rb") as handle:
            total, table = read_index(handle)
            for position, bank in enumerate(VOICE_BANKS, 1):
                _offset, bank_data = _read_bank(handle, table, total, bank)
                clips = parse_bank(bank_data)
                owner = owners.get(bank)
                if owner:
                    if len(clips) != owner.slot_count:
                        raise ValueError(
                            "voice bank %d has %d clips, but its scene map "
                            "expects %d" % (bank, len(clips), owner.slot_count)
                        )
                    folder = partial / str(owner.resource)
                    mapped += 1
                else:
                    folder = partial / "unmapped"
                folder.mkdir(exist_ok=True)
                for clip in clips:
                    payload_start = clip.sub_offset + clip.payload_offset
                    payload = bank_data[
                        payload_start:payload_start + clip.payload_length
                    ]
                    pcm = audio.decode_adpcm(payload)
                    name = exported_filename(bank, clip)
                    target = folder / name
                    audio.write_wav(target, pcm)
                    peak, rms, voiced = audio.statistics(pcm)
                    relative = target.relative_to(partial).as_posix()
                    rows.append({
                        "region": region,
                        "resource": owner.resource if owner else "",
                        "voice_scene": (
                            owner.voice_scene
                            if owner and owner.voice_scene is not None
                            else ""
                        ),
                        "bank": bank,
                        "sub": clip.sub_index,
                        "clip_id": "%04x" % clip.clip_id,
                        "relative_path": relative,
                        "slot_bytes": clip.payload_length,
                        "max_seconds": "%.4f" % (
                            clip.payload_length // audio.FRAME
                            * audio.SAMPLES_PER_FRAME / audio.SAMPLE_RATE
                        ),
                        "seconds": "%.4f" % (
                            len(pcm) // 2 / audio.SAMPLE_RATE
                        ),
                        "target_rms": int(rms),
                        "peak": peak,
                        "voiced_pct": "%.1f" % (100 * voiced),
                        "silent": "yes" if rms == 0 else "",
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    })
                say(
                    "extract: bank %d (%d/%d), %d clip(s)"
                    % (bank, position, len(VOICE_BANKS), len(clips))
                )
        with (partial / "manifest.csv").open(
                "w", encoding="utf-8", newline="") as manifest:
            writer = csv.DictWriter(manifest, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        (partial / "README.txt").write_text(
            "Extracted from %s (%s).\n"
            "Files are named <bank>-<subfile>-<clip-id>.wav.\n"
            "Folders named by number are cutscene resources. Some script-"
            "driven banks have no numeric voice-scene field, but are still "
            "grouped under their cutscene resource.\n"
            % (source.name, boot),
            encoding="utf-8",
        )
        partial.replace(destination)
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    say("wrote %d clips to %s" % (len(rows), destination))
    return ExtractionResult(
        output=destination,
        region=region,
        banks=len(VOICE_BANKS),
        clips=len(rows),
        mapped_banks=mapped,
    )


def _find_manifest(folder):
    folder = Path(folder).resolve()
    current = folder
    for _ in range(4):
        candidate = current / "manifest.csv"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


def _old_manifest_identities(manifest):
    identities = {}
    if manifest is None:
        return identities
    with manifest.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if not all(row.get(field) not in (None, "")
                       for field in ("id", "bank", "sub")):
                continue
            stem = row["id"].lower().removeprefix("0x")
            identity = (int(row["bank"]), int(row["sub"]), int(stem, 16))
            previous = identities.setdefault(stem, identity)
            if previous != identity:
                raise ValueError("manifest clip id %s is ambiguous" % stem)
    return identities


def discover_replacements(folder):
    """Identify exported and legacy dub-kit WAVs below *folder*."""
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError("voice folder does not exist: %s" % folder)
    wavs = sorted(path for path in folder.rglob("*")
                  if path.is_file() and path.suffix.lower() == ".wav")
    if not wavs:
        raise ValueError("voice folder contains no WAV files: %s" % folder)
    legacy = _old_manifest_identities(_find_manifest(folder))
    found = {}
    unknown = []
    for path in wavs:
        identity = parse_exported_filename(path)
        if identity is None:
            stem = path.stem.lower().removeprefix("id_").removeprefix("0x")
            identity = legacy.get(stem)
        if identity is None:
            unknown.append(path)
            continue
        if identity in found:
            raise ValueError(
                "two WAV files target bank %d subfile %d: %s and %s"
                % (identity[0], identity[1], found[identity], path)
            )
        found[identity] = path
    if unknown:
        preview = ", ".join(str(path.relative_to(folder)) for path in unknown[:5])
        raise ValueError(
            "%d WAV file(s) have no bank/subfile identity: %s%s"
            % (len(unknown), preview, " ..." if len(unknown) > 5 else "")
        )
    return found


def _copy_with_progress(source, target, say):
    total = source.stat().st_size
    done = last = 0
    with source.open("rb") as reader, target.open("wb") as writer:
        while True:
            chunk = reader.read(COPY_CHUNK)
            if not chunk:
                break
            writer.write(chunk)
            done += len(chunk)
            percent = done * 100 // total if total else 100
            if percent != last:
                say("copy: %d%%" % percent)
                last = percent


def patch_iso(source, voices, output=None, progress=None,
              allow_overlong=False):
    """Copy an ISO, replace selected lines in place, and read them back."""
    say = progress or (lambda _message: None)
    source, region, _boot = _validated_source(source)
    output = (Path(output).expanduser().resolve()
              if output else default_patch_output(source))
    if output == source:
        raise ValueError("output must be different from the source ISO")
    if output.exists():
        raise ValueError("output already exists; refusing to overwrite: %s" % output)
    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise ValueError("partial output already exists; remove it first: %s" % partial)
    selected = discover_replacements(voices)
    pending = []
    with source.open("rb") as handle:
        total, table = read_index(handle)
        banks = {}
        for bank, _sub, _clip_id in selected:
            if bank not in VOICE_BANKS:
                raise ValueError("replacement targets non-voice bank %d" % bank)
            if bank not in banks:
                bank_offset, bank_data = _read_bank(handle, table, total, bank)
                banks[bank] = (bank_offset, bank_data, {
                    clip.sub_index: clip for clip in parse_bank(bank_data)
                })
        for identity, path in sorted(selected.items()):
            bank, sub_index, clip_id = identity
            bank_offset, bank_data, clips = banks[bank]
            clip = clips.get(sub_index)
            if clip is None:
                raise ValueError(
                    "%s targets missing subfile %d in bank %d"
                    % (path.name, sub_index, bank)
                )
            if clip.clip_id != clip_id:
                raise ValueError(
                    "%s says clip %04x, but bank %d subfile %d is %04x"
                    % (path.name, clip_id, bank, sub_index, clip.clip_id)
                )
            pcm = audio.read_wav(path)
            encoded = audio.encode_adpcm(pcm)
            truncated = len(encoded) > clip.payload_length
            maximum = (
                clip.payload_length // audio.FRAME
                * audio.SAMPLES_PER_FRAME / audio.SAMPLE_RATE
            )
            try:
                fitted = audio.fit_payload(
                    encoded, clip.payload_length, clip.tail_flag,
                    allow_truncate=allow_overlong,
                )
            except ValueError as exc:
                duration = len(pcm) // 2 / audio.SAMPLE_RATE
                raise ValueError(
                    "%s is %.3fs but its game slot is %.3fs: %s"
                    % (path.name, duration, maximum, exc)
                ) from exc
            absolute = bank_offset + clip.sub_offset + clip.payload_offset
            pending.append((absolute, fitted, Replacement(
                path=path, bank=bank, sub=sub_index, clip_id=clip_id,
                slot_bytes=clip.payload_length, truncated=truncated,
            )))
            say("prepare: bank %d subfile %d <- %s" % (
                bank, sub_index, path.name
            ))
            if truncated:
                say("warning: %s is overlong and will be trimmed to %.3fs" % (
                    path.name, maximum
                ))
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        say("copy: 0%")
        _copy_with_progress(source, partial, say)
        say("write: applying %d voice replacement(s)" % len(pending))
        with partial.open("r+b") as candidate:
            for offset, payload, _replacement in pending:
                candidate.seek(offset)
                candidate.write(payload)
            candidate.flush()
            os.fsync(candidate.fileno())
        say("verify: reading every replaced slot back from disk")
        with partial.open("rb") as candidate:
            total, table = read_index(candidate)
            for offset, payload, replacement in pending:
                candidate.seek(offset)
                if candidate.read(len(payload)) != payload:
                    raise ValueError(
                        "bank %d subfile %d did not read back byte-for-byte"
                        % (replacement.bank, replacement.sub)
                    )
        if partial.stat().st_size != source.stat().st_size:
            raise ValueError("output ISO size differs from source")
        partial.replace(output)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    say("wrote %s" % output)
    return PatchResult(
        output=output, region=region,
        replacements=tuple(item[2] for item in pending),
    )
