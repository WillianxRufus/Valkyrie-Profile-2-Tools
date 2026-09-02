# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

import ast
import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.scripts import vp2_container_text, workspace_extract
from tools.scripts.translation_pack import _read_csv
from tools.scripts.workspace_extract import (
    _export_chapters,
    _looks_like_stream_chain,
    _normalize_source_sheet,
    _replace_generated_tree,
)


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class WorkspaceExtractTests(unittest.TestCase):
    def test_stream_chain_candidate_uses_header_shape(self):
        structured = bytearray(0x100)
        structured[4:8] = (3).to_bytes(4, "little")
        structured[8:12] = (0x20).to_bytes(4, "little")
        self.assertTrue(_looks_like_stream_chain(bytes(structured)))
        structured[8:12] = (0x21).to_bytes(4, "little")
        self.assertFalse(_looks_like_stream_chain(bytes(structured)))

    def test_runtime_has_no_private_top_level_sibling_imports(self):
        scripts = Path(__file__).parents[1] / "tools" / "scripts"
        sibling_names = {path.stem for path in scripts.glob("*.py")}
        leaks = []
        for path in scripts.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".", 1)[0] in sibling_names:
                            leaks.append(f"{path.name}:{node.lineno}:{alias.name}")
                elif (isinstance(node, ast.ImportFrom) and node.level == 0
                      and (node.module or "").split(".", 1)[0] in sibling_names):
                    leaks.append(f"{path.name}:{node.lineno}:{node.module}")
        self.assertEqual([], leaks)

    def test_scene_sheet_gets_shared_workspace_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scene.csv"
            write_csv(path, [
                "resource", "message_id", "original_en", "original_jp",
                "translated",
            ], [{
                "resource": "31", "message_id": "7",
                "original_en": "English", "original_jp": "Japanese",
                "translated": "must not survive regeneration",
            }])
            self.assertEqual(1, _normalize_source_sheet(path, "scene"))
            fields, rows = _read_csv(path)
            self.assertEqual("kind", fields[0])
            self.assertIn("message_index", fields)
            self.assertIn("notes", fields)
            self.assertEqual("scene", rows[0]["kind"])
            self.assertEqual("", rows[0]["translated"])

    def test_container_record_kind_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "container.csv"
            write_csv(path, [
                "resource", "message_id", "kind", "original_en",
                "original_jp", "translated",
            ], [{
                "resource": "10", "message_id": "2021+1", "kind": "token",
                "original_en": "English", "original_jp": "Japanese",
                "translated": "",
            }])
            self.assertEqual(1, _normalize_source_sheet(path, "container"))
            fields, rows = _read_csv(path)
            self.assertIn("record_kind", fields)
            self.assertNotEqual(fields.index("kind"), fields.index("record_kind"))
            self.assertEqual("container", rows[0]["kind"])
            self.assertEqual("token", rows[0]["record_kind"])

    def test_container_export_joins_japanese_to_string_token_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "japanese.iso"
            image.touch()
            output = root / "container-0010.csv"
            metadata = {
                "text_start": 0, "text_end": 1, "font_start": 1,
                "glyph_count": 1,
            }
            token_rows = [{
                "key": "2000", "offset": 0, "byte_length": 1,
                "original_en": "Danger.",
            }]
            args = SimpleNamespace(
                iso=str(image), csv=str(output), resource=10,
                jp_iso=str(image), jp_glyphs="glyphs.csv",
                jp_names="names.csv",
            )
            with (
                mock.patch.object(
                    vp2_container_text.triace, "load_table",
                    return_value=("VP2", 1, [])),
                mock.patch.object(
                    vp2_container_text, "container", return_value=b""),
                mock.patch.object(
                    vp2_container_text, "read_messages",
                    return_value=(metadata, [])),
                mock.patch.object(
                    vp2_container_text, "walk_block", return_value=token_rows),
                mock.patch.object(
                    vp2_container_text, "japanese_text",
                    return_value={"2000": "\u6765\u308b\u308f\u2026"}),
                mock.patch("builtins.print"),
            ):
                vp2_container_text.cmd_export(args)

            _fields, rows = _read_csv(output)
            self.assertEqual("\u6765\u308b\u308f\u2026", rows[0]["original_jp"])

    def test_chapter_export_uses_region_specific_japanese_message_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            usa = root / "usa.iso"
            japanese = root / "japanese.iso"
            usa.touch()
            japanese.touch()
            records = root / "chapter-records.csv"
            output = root / "chapters.csv"
            write_csv(records, [
                "chapter", "resource", "message_id", "japanese_message_id",
            ], [{
                "chapter": "1", "resource": "1197", "message_id": "2739",
                "japanese_message_id": "2765",
            }])
            decoded = [
                (0, 2765, (None, None), "\u795e\u306b\u53db\u304d\u3057\u8005"),
            ]
            with (
                mock.patch.object(
                    workspace_extract.triace, "load_table",
                    return_value=("VP2", 1, [])),
                mock.patch.object(
                    workspace_extract.vp2_title_face, "FileIsoForTitleFace"),
                mock.patch.object(
                    workspace_extract.vp2_title_face, "build_face",
                    return_value=({}, {})),
                mock.patch.object(
                    workspace_extract.vp2_title_face, "decode_title",
                    return_value="defiers of the Gods"),
                mock.patch.object(
                    workspace_extract.vp2_jp_glyphs, "load_glyph_names",
                    return_value={}),
                mock.patch.object(
                    workspace_extract.vp2_jp_glyphs, "decode_resource",
                    return_value=(decoded, 10, 1)),
            ):
                self.assertEqual(1, _export_chapters(
                    usa, records, output, japanese,
                    root / "japanese-glyphs.csv", root / "jp.csv"))

            _fields, rows = _read_csv(output)
            self.assertEqual("defiers of the Gods", rows[0]["original_en"])
            self.assertEqual(
                "\u795e\u306b\u53db\u304d\u3057\u8005", rows[0]["original_jp"])

    def test_source_snapshot_replacement_is_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "internal"
            generated = root / "staging" / "internal"
            target.mkdir(parents=True)
            generated.mkdir(parents=True)
            (target / "old.txt").write_text("old", encoding="utf-8")
            (generated / "new.txt").write_text("new", encoding="utf-8")
            _replace_generated_tree(target, generated)
            self.assertFalse((target / "old.txt").exists())
            self.assertEqual("new", (target / "new.txt").read_text("utf-8"))
            self.assertFalse((root / ".internal-previous").exists())


if __name__ == "__main__":
    unittest.main()
