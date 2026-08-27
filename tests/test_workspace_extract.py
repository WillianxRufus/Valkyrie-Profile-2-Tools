# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

import ast
import csv
import tempfile
import unittest
from pathlib import Path

from tools.scripts.translation_pack import _read_csv
from tools.scripts.workspace_extract import (
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
