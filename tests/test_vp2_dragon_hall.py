import csv
import tempfile
import unittest
from pathlib import Path

from tools.scripts import build_patchers
from tools.scripts import sle
from tools.scripts import slz_compress
from tools.scripts import vp2_container_text as container_text
from tools.scripts import vp2_dragon_hall as dragon


def fixture_resource():
    expanded = bytearray((index * 37) & 0xFF for index in range(4480))
    prompt = container_text.encode_codepage(dragon.ORIGINAL_EN)
    next_text = container_text.encode_codepage(dragon.NEXT_EN)
    expanded[dragon.PROMPT_OFFSET:dragon.NEXT_TEXT_OFFSET] = prompt
    expanded[dragon.NEXT_TEXT_OFFSET:
             dragon.NEXT_TEXT_OFFSET + len(next_text)] = next_text
    stream = dragon.protect(
        slz_compress.compress(expanded, mode=2, cache_dir=""))
    return b"prefix" + stream + b"suffix"


class DragonHallPromptTests(unittest.TestCase):
    def test_patch_preserves_resource_and_stream_size(self):
        raw = fixture_resource()
        rebuilt, details = dragon.patch_raw(raw, "Choose a stone?")
        self.assertEqual(len(raw), len(rebuilt))
        self.assertEqual(dragon.extract_english(rebuilt), "Choose a stone?")
        self.assertEqual(details["wrapper"], "SLE")
        self.assertEqual(sle.decompress(
            rebuilt[details["stream_offset"]:]),
            sle.decompress(raw[details["stream_offset"]:])[:dragon.PROMPT_OFFSET]
            + container_text.encode_codepage("Choose a stone?").ljust(
                dragon.PROMPT_SIZE, b"\0")
            + sle.decompress(raw[details["stream_offset"]:])[
                dragon.NEXT_TEXT_OFFSET:])

    def test_rejects_text_larger_than_fixed_slot(self):
        with self.assertRaisesRegex(ValueError, "fixed slot"):
            dragon.patch_raw(fixture_resource(), "This text is far too long")

    def test_container_manifest_dispatches_the_custom_record(self):
        class MemoryIso:
            def __init__(self, raw):
                self.raw = raw

            def read_entry(self, _resource):
                return self.raw

            def write_entry(self, _resource, raw):
                self.raw = bytes(raw)

        with tempfile.TemporaryDirectory() as temporary:
            sheet = Path(temporary) / "container-0328.csv"
            with sheet.open("w", encoding="utf-8", newline="") as target:
                fields = [
                    "kind", "resource", "message_id", "message_index",
                    "record_kind", "original_en", "translated", "notes",
                ]
                writer = csv.DictWriter(target, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "kind": "container", "resource": "328",
                    "message_id": str(dragon.MESSAGE_ID), "message_index": "",
                    "record_kind": "dragon_hall_prompt",
                    "original_en": dragon.ORIGINAL_EN,
                    "translated": "Choose a stone?", "notes": "",
                })
            iso = MemoryIso(fixture_resource())
            result = build_patchers.patch_container_resource_in_memory(
                iso, {
                    "resource": "328", "sheet": str(sheet),
                    "flags": "shared-font-glyphs",
                })
        self.assertEqual(result["written"], 1)
        self.assertEqual(dragon.extract_english(iso.raw), "Choose a stone?")


if __name__ == "__main__":
    unittest.main()
