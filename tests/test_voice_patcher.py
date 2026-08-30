# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Synthetic, source-free round trips for the voice extractor/patcher."""

import csv
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.voice_patcher import audio, build, layout  # noqa: E402


TABLE_OFFSET = 0x200000
TOTAL = 0x0C00
SEED = 0x49287491
SIGNATURE = 0x516F6699
MASK = 0xFFFFFFFF
BANK = 1483
BANK_OFFSET = 0x210000
BANK_LENGTH = 0x1000
CLIP_ID = 0x8028
UNMAPPED_ENTRY = 685
UNMAPPED_OFFSET = 0x212000
UNMAPPED_LENGTH = 0x800
UNMAPPED_CLIP_ID = 0x0B00


def synthetic_bank():
    data = bytearray(BANK_LENGTH)
    struct.pack_into("<IHH", data, 0, 1, 1, 1)
    sub = 0x800
    data[sub:sub + 4] = b"SEQW"
    struct.pack_into("<I", data, sub + 4, 0x40)
    struct.pack_into("<H", data, sub + 0x1A, CLIP_ID)
    data[sub + 0x40:sub + 0x44] = b"WAV "
    struct.pack_into("<III", data, sub + 0x44, 0x60, 0x20, 0)
    struct.pack_into("<I", data, sub + 0x50, 64)
    data[sub + 0x60:sub + 0xA0] = audio.SILENCE_FRAME * 4
    data[sub + 0x91] = 1
    return bytes(data)


def synthetic_unmapped_entry(tail_flag=7):
    data = bytearray(UNMAPPED_LENGTH)
    data[:4] = b"SEQW"
    struct.pack_into("<I", data, 4, 0x80)
    data[0x80:0x84] = b"WAV "
    struct.pack_into("<III", data, 0x88, 0x80, 0x1C, 64)
    struct.pack_into("<HH", data, 0xA0, 0x1C, UNMAPPED_CLIP_ID)
    struct.pack_into("<I", data, 0xA4, 0x14)
    struct.pack_into("<I", data, 0xB4, 0)
    data[0x100:0x140] = audio.SILENCE_FRAME * 4
    if tail_flag == 3:
        data[0x111] = 2
        data[0x121] = 6
    data[0x131] = tail_flag
    return bytes(data)


def encrypted_index():
    decoded = [0] * (TOTAL * 3)
    decoded[BANK] = BANK_OFFSET // layout.SECTOR
    decoded[TOTAL + BANK] = BANK_LENGTH // layout.SECTOR
    decoded[UNMAPPED_ENTRY] = UNMAPPED_OFFSET // layout.SECTOR
    decoded[TOTAL + UNMAPPED_ENTRY] = UNMAPPED_LENGTH // layout.SECTOR
    raw = decoded[:]
    key = SEED
    for index in range(TOTAL):
        raw[index] ^= key
        key = (key ^ ((key << 1) & MASK)) & MASK
        raw[TOTAL + index] ^= key
        key = (key ^ (~SEED & MASK)) & MASK
        raw[2 * TOTAL + index] ^= key
        key = (key ^ ((key << 2) & MASK) ^ SEED) & MASK
    raw[0] = SIGNATURE
    return struct.pack("<%dI" % len(raw), *raw)


def synthetic_iso(path, boot="SLUS_214.52"):
    image = bytearray(UNMAPPED_OFFSET + UNMAPPED_LENGTH)
    image[0x1000:0x1000 + len(boot)] = boot.encode("ascii")
    index = encrypted_index()
    image[TABLE_OFFSET:TABLE_OFFSET + len(index)] = index
    image[BANK_OFFSET:BANK_OFFSET + BANK_LENGTH] = synthetic_bank()
    image[UNMAPPED_OFFSET:UNMAPPED_OFFSET + UNMAPPED_LENGTH] = (
        synthetic_unmapped_entry()
    )
    path.write_bytes(image)


def write_wav(path, samples):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(audio.SAMPLE_RATE)
        output.writeframes(struct.pack("<%dh" % len(samples), *samples))


class LayoutTests(unittest.TestCase):
    def test_exported_name_carries_every_patch_identity(self):
        clip = layout.parse_bank(synthetic_bank())[0]
        name = layout.exported_filename(BANK, clip)
        self.assertEqual("1483-000-8028.wav", name)
        self.assertEqual((BANK, 0, CLIP_ID), layout.parse_exported_filename(name))

    def test_slack_bank_parser_does_not_depend_on_the_generic_classifier(self):
        clips = layout.parse_bank(synthetic_bank())
        self.assertEqual(1, len(clips))
        self.assertEqual(64, clips[0].payload_length)
        self.assertEqual(1, clips[0].tail_flag)

    def test_all_voice_banks_are_mapped_to_resources(self):
        owners = layout.load_bank_map()
        self.assertEqual(85, len(owners))
        self.assertEqual(
            (1297, 1170, 7),
            (owners[1482].resource, owners[1482].voice_scene,
             owners[1482].slot_count),
        )
        self.assertEqual(set(layout.VOICE_BANKS), set(owners))
        self.assertEqual(
            (1337, None, 21),
            (owners[1520].resource, owners[1520].voice_scene,
             owners[1520].slot_count),
        )
        self.assertEqual(
            (1323, None, 16),
            (owners[1562].resource, owners[1562].voice_scene,
             owners[1562].slot_count),
        )

    def test_unmapped_map_and_standalone_sample_identity_are_exact(self):
        voices = layout.load_unmapped_map()
        self.assertEqual(93, len(voices))
        self.assertEqual(
            layout.UnmappedVoice(
                UNMAPPED_ENTRY, 0, UNMAPPED_CLIP_ID, 0
            ),
            voices[(UNMAPPED_ENTRY, 0)],
        )
        self.assertIn((1582, 14), voices)
        self.assertIn((1621, 21), voices)
        clip = layout.parse_standalone(synthetic_unmapped_entry())[0]
        name = layout.unmapped_filename(UNMAPPED_ENTRY, clip)
        self.assertEqual("unmapped-0685-000-0b00-0.wav", name)
        self.assertEqual(
            (UNMAPPED_ENTRY, 0, UNMAPPED_CLIP_ID, 0),
            layout.parse_unmapped_filename(name),
        )
        self.assertEqual(64, clip.payload_length)
        self.assertEqual(7, clip.tail_flag)


class ExtractionTests(unittest.TestCase):
    def test_extracts_to_language_and_known_cutscene_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "usa.iso"
            synthetic_iso(source)
            owner = layout.BankOwner(BANK, 1197, 10, 1)
            with mock.patch.object(build, "VOICE_BANKS", (BANK,)), \
                    mock.patch.object(build, "load_bank_map",
                                      return_value={BANK: owner}), \
                    mock.patch.object(build, "load_unmapped_map",
                                      return_value={}):
                result = build.extract_voices(source, root / "voices")
            wav = result.output / "1197" / "1483-000-8028.wav"
            self.assertTrue(wav.is_file())
            self.assertEqual("en", result.region)
            self.assertEqual(1, result.clips)
            with (result.output / "manifest.csv").open(
                    encoding="utf-8") as manifest:
                rows = list(csv.DictReader(manifest))
            self.assertEqual("1197/1483-000-8028.wav", rows[0]["relative_path"])
            self.assertEqual("10", rows[0]["voice_scene"])

    def test_japanese_disc_uses_jp_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "jp.iso"
            synthetic_iso(source, "SLPM_664.19")
            owner = layout.BankOwner(BANK, 1197, 10, 1)
            with mock.patch.object(build, "VOICE_BANKS", (BANK,)), \
                    mock.patch.object(build, "load_bank_map",
                                      return_value={BANK: owner}), \
                    mock.patch.object(build, "load_unmapped_map",
                                      return_value={}):
                result = build.extract_voices(source, root / "voices")
            self.assertEqual(root / "voices" / "jp", result.output)

    def test_extracts_language_dependent_samples_to_unmapped_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "usa.iso"
            synthetic_iso(source)
            voice = layout.UnmappedVoice(
                UNMAPPED_ENTRY, 0, UNMAPPED_CLIP_ID, 0
            )
            with mock.patch.object(build, "VOICE_BANKS", ()), \
                    mock.patch.object(build, "load_bank_map",
                                      return_value={}), \
                    mock.patch.object(build, "load_unmapped_map",
                                      return_value={(UNMAPPED_ENTRY, 0): voice}):
                result = build.extract_voices(source, root / "voices")
            target = (result.output / "unmapped" /
                      "unmapped-0685-000-0b00-0.wav")
            self.assertTrue(target.is_file())
            self.assertEqual(1, result.unmapped_clips)
            with (result.output / "manifest.csv").open(
                    encoding="utf-8") as manifest:
                rows = list(csv.DictReader(manifest))
            self.assertEqual("unmapped", rows[0]["kind"])


class PatchingTests(unittest.TestCase):
    def test_replaces_only_the_payload_and_preserves_iso_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.iso"
            output = root / "output.iso"
            voices = root / "voices"
            voices.mkdir()
            synthetic_iso(source)
            replacement = voices / "1483-000-8028.wav"
            write_wav(replacement, [1200, -1200] * 28)
            before = source.read_bytes()
            result = build.patch_iso(source, voices, output)
            after = output.read_bytes()
            clip = layout.parse_bank(synthetic_bank())[0]
            start = BANK_OFFSET + clip.sub_offset + clip.payload_offset
            end = start + clip.payload_length
            self.assertEqual(before[:start], after[:start])
            self.assertNotEqual(before[start:end], after[start:end])
            self.assertEqual(before[end:], after[end:])
            self.assertEqual(len(before), len(after))
            self.assertEqual(1, len(result.replacements))
            self.assertEqual(1, after[end - 15])

    def test_replaces_only_one_unmapped_sample_slot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.iso"
            output = root / "output.iso"
            voices = root / "voices"
            voices.mkdir()
            synthetic_iso(source)
            replacement = voices / "unmapped-0685-000-0b00-0.wav"
            write_wav(replacement, [900, -900] * 14)
            before = source.read_bytes()
            voice = layout.UnmappedVoice(
                UNMAPPED_ENTRY, 0, UNMAPPED_CLIP_ID, 0
            )
            with mock.patch.object(
                    build, "load_unmapped_map",
                    return_value={(UNMAPPED_ENTRY, 0): voice}):
                result = build.patch_iso(source, voices, output)
            after = output.read_bytes()
            start = UNMAPPED_OFFSET + 0x100
            end = start + 64
            self.assertEqual(before[:start], after[:start])
            self.assertNotEqual(before[start:end], after[start:end])
            self.assertEqual(before[end:], after[end:])
            self.assertEqual("unmapped", result.replacements[0].kind)
            self.assertEqual(UNMAPPED_ENTRY, result.replacements[0].entry)
            self.assertEqual(7, after[end - 15])

    def test_unmapped_loop_flag_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.iso"
            output = root / "output.iso"
            voices = root / "voices"
            voices.mkdir()
            synthetic_iso(source)
            with source.open("r+b") as image:
                image.seek(UNMAPPED_OFFSET)
                image.write(synthetic_unmapped_entry(tail_flag=3))
            replacement = voices / "unmapped-0685-000-0b00-0.wav"
            write_wav(replacement, [700, -700] * 14)
            voice = layout.UnmappedVoice(
                UNMAPPED_ENTRY, 0, UNMAPPED_CLIP_ID, 0
            )
            with mock.patch.object(
                    build, "load_unmapped_map",
                    return_value={(UNMAPPED_ENTRY, 0): voice}):
                build.patch_iso(source, voices, output)
            payload = output.read_bytes()[
                UNMAPPED_OFFSET + 0x100:UNMAPPED_OFFSET + 0x140
            ]
            self.assertEqual(
                [0, 2, 6, 3],
                [payload[offset + 1]
                 for offset in range(0, len(payload), audio.FRAME)],
            )

    def test_legacy_dub_kit_manifest_makes_clip_id_names_reversible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            translated = root / "ptbr-chatterbox"
            translated.mkdir()
            (root / "manifest.csv").write_text(
                "id,bank,sub,slot_bytes\n8028,1483,0,64\n",
                encoding="utf-8",
            )
            write_wav(translated / "8028.wav", [0] * 28)
            found = build.discover_replacements(translated)
            self.assertEqual(
                {(BANK, 0, CLIP_ID): translated / "8028.wav"}, found
            )

    def test_overlong_audio_is_rejected_without_an_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.iso"
            output = root / "output.iso"
            voices = root / "voices"
            voices.mkdir()
            synthetic_iso(source)
            write_wav(voices / "1483-000-8028.wav", [0] * 1000)
            with self.assertRaisesRegex(ValueError, "game slot"):
                build.patch_iso(source, voices, output)
            self.assertFalse(output.exists())
            self.assertFalse(Path(str(output) + ".partial").exists())

    def test_overlong_audio_can_be_deliberately_trimmed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.iso"
            output = root / "output.iso"
            voices = root / "voices"
            voices.mkdir()
            synthetic_iso(source)
            write_wav(voices / "1483-000-8028.wav", [800] * 1000)
            result = build.patch_iso(
                source, voices, output, allow_overlong=True
            )
            self.assertTrue(output.is_file())
            self.assertTrue(result.replacements[0].truncated)

    def test_wrong_game_release_is_rejected_before_copying(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "wrong.iso"
            voices = root / "voices"
            voices.mkdir()
            synthetic_iso(source, "SLES_546.44")
            write_wav(voices / "1483-000-8028.wav", [0] * 28)
            with self.assertRaisesRegex(ValueError, "unsupported disc"):
                build.patch_iso(source, voices, root / "output.iso")


if __name__ == "__main__":
    unittest.main()
