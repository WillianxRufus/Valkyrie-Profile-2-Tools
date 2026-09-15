# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import struct
import unittest

from tools.scripts import fis_images


def dtt_record(box, x_scale=8, y_scale=16):
    left, top, right, bottom = box
    return struct.pack(
        "<8H", 0x100, 1,
        left * x_scale + x_scale // 2,
        top * y_scale + y_scale // 2,
        right * x_scale + x_scale // 2,
        bottom * y_scale + y_scale // 2,
        right - left + 1, bottom - top + 1)


class FisImageLayoutTests(unittest.TestCase):
    def test_victory_labels_use_independent_half_width_boxes(self):
        root = Path(__file__).parents[1]
        pack = root / "translations" / "pt-BR"
        images = pack / "images"
        name = "fis-1721-decrypted-slz-0x0-80.png"
        document = json.loads(
            (pack / "fis-image-layouts.json").read_text(encoding="utf-8"))
        rows = document["images"][name]["dtt"]["records"]
        configured = {row["index"]: row for row in rows}

        originals = [
            (4, 9, 400, 60),
            tuple(configured[2]["from"]),
            tuple(configured[3]["from"]),
            (4, 113, 174, 141),
            tuple(configured[5]["from"]),
        ]
        body = b"".join(dtt_record(box) for box in originals)
        table = struct.pack("<4sI8x", b"DTT\0", len(body)) + body

        patched, changed = fis_images._patch_dtt_layout(
            table, images, name, (512, 256))

        records = fis_images._dtt_tables(patched)[0][1]
        for index, row in configured.items():
            self.assertEqual(tuple(row["to"]),
                             fis_images._dtt_box(patched, records[index - 1]))
            self.assertEqual((8, 16),
                             fis_images._dtt_geometry(
                                 patched, records[index - 1])[1:])
        self.assertGreater(changed, 0)

        same, changed = fis_images._patch_dtt_layout(
            patched, images, name, (512, 256))
        self.assertEqual(patched, same)
        self.assertEqual(0, changed)

    def test_full_scale_dtt_geometry_remains_supported(self):
        record = dtt_record((2, 59, 67, 81), 32, 32)
        self.assertEqual(((2, 59, 67, 81), 32, 32),
                         fis_images._dtt_geometry(record, 0))


if __name__ == "__main__":
    unittest.main()
