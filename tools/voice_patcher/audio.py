# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""VP2's PlayStation ADPCM codec and the WAV boundary used by the tool."""

from __future__ import annotations

import struct
import wave
from pathlib import Path


FRAME = 16
SAMPLES_PER_FRAME = 28
SAMPLE_RATE = 24000
COEFFICIENTS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
SILENCE_FRAME = bytes((0x0C, 0x00) + (0x00,) * 14)


def decode_adpcm(data: bytes) -> bytes:
    """Decode complete 16-byte PS-ADPCM frames to signed 16-bit PCM."""
    output = bytearray()
    history1 = history2 = 0
    for offset in range(0, len(data) - FRAME + 1, FRAME):
        control, flag = data[offset], data[offset + 1]
        shift = control & 0x0F
        predictor = (control >> 4) & 0x0F
        if predictor >= len(COEFFICIENTS):
            predictor = 0
        if flag == 7:
            break
        if shift > 12:
            shift = 9
        coefficient0, coefficient1 = COEFFICIENTS[predictor]
        for index in range(2, FRAME):
            value = data[offset + index]
            for nibble in (value & 0x0F, value >> 4):
                sample = nibble << 12
                if sample & 0x8000:
                    sample -= 0x10000
                sample >>= shift
                sample += (
                    history1 * coefficient0 + history2 * coefficient1
                ) // 64
                sample = max(-32768, min(32767, sample))
                output += struct.pack("<h", sample)
                history2, history1 = history1, sample
    return bytes(output)


def _encode_frame(samples, history1, history2):
    best = None
    for predictor, (coefficient0, coefficient1) in enumerate(COEFFICIENTS):
        h1, h2 = history1, history2
        maximum = 0
        for sample in samples:
            predicted = (h1 * coefficient0 + h2 * coefficient1) // 64
            maximum = max(maximum, abs(sample - predicted))
            h2, h1 = h1, sample
        shift = 0
        for candidate in range(12, -1, -1):
            if maximum <= 7 * (1 << (12 - candidate)):
                shift = candidate
                break
        step = 1 << (12 - shift)
        h1, h2 = history1, history2
        nibbles = []
        error = 0
        for sample in samples:
            predicted = (h1 * coefficient0 + h2 * coefficient1) // 64
            nibble = int(round((sample - predicted) / step))
            nibble = max(-8, min(7, nibble))
            decoded = max(
                -32768,
                min(32767, ((nibble << 12) >> shift) + predicted),
            )
            error += (sample - decoded) ** 2
            nibbles.append(nibble & 0x0F)
            h2, h1 = h1, decoded
        candidate = (error, predictor, shift, nibbles, h1, h2)
        if best is None or error < best[0]:
            best = candidate
    error, predictor, shift, nibbles, history1, history2 = best
    frame = bytearray(((predictor << 4) | shift, 0))
    for index in range(0, SAMPLES_PER_FRAME, 2):
        frame.append(nibbles[index] | (nibbles[index + 1] << 4))
    return bytes(frame), history1, history2


def encode_adpcm(pcm: bytes) -> bytes:
    """Encode signed 16-bit mono PCM, padding its last 28-sample frame."""
    sample_count = len(pcm) // 2
    samples = list(struct.unpack("<%dh" % sample_count, pcm[:sample_count * 2]))
    if sample_count % SAMPLES_PER_FRAME:
        samples += [0] * (SAMPLES_PER_FRAME - sample_count % SAMPLES_PER_FRAME)
    output = bytearray()
    history1 = history2 = 0
    for index in range(0, len(samples), SAMPLES_PER_FRAME):
        frame, history1, history2 = _encode_frame(
            samples[index:index + SAMPLES_PER_FRAME], history1, history2
        )
        output += frame
    return bytes(output)


def fit_payload(encoded: bytes, target_length: int, tail_flag: int,
                allow_truncate=False) -> bytes:
    """Fit a line to its retail allocation, truncating only when requested."""
    if target_length % FRAME:
        raise ValueError("the game audio slot is not frame-aligned")
    if len(encoded) > target_length:
        if not allow_truncate:
            raise ValueError(
                "encoded audio needs %d bytes but its game slot holds %d"
                % (len(encoded), target_length)
            )
        encoded = encoded[:target_length]
    fitted = encoded + SILENCE_FRAME * ((target_length - len(encoded)) // FRAME)
    if fitted:
        fitted = bytearray(fitted)
        fitted[-FRAME + 1] = tail_flag
        fitted = bytes(fitted)
    return fitted


def read_wav(path) -> bytes:
    """Read the one WAV shape the fixed-rate game playback accepts."""
    path = Path(path)
    try:
        with wave.open(str(path), "rb") as source:
            shape = (
                source.getnchannels(), source.getsampwidth(),
                source.getframerate(), source.getcomptype(),
            )
            if shape != (1, 2, SAMPLE_RATE, "NONE"):
                raise ValueError(
                    "%s must be uncompressed 16-bit mono PCM at %d Hz "
                    "(found %d channel(s), %d-bit, %d Hz, %s)"
                    % (path.name, SAMPLE_RATE, shape[0], shape[1] * 8,
                       shape[2], shape[3])
                )
            return source.readframes(source.getnframes())
    except wave.Error as exc:
        raise ValueError("cannot read WAV %s: %s" % (path, exc)) from exc


def write_wav(path, pcm: bytes) -> None:
    path = Path(path)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)


def statistics(pcm: bytes):
    count = len(pcm) // 2
    if not count:
        return 0, 0.0, 0.0
    samples = struct.unpack("<%dh" % count, pcm)
    peak = max(abs(value) for value in samples)
    rms = (sum(value * value for value in samples) / count) ** 0.5
    voiced = sum(abs(value) > 300 for value in samples) / count
    return peak, rms, voiced
