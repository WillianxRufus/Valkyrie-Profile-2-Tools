# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""The window, and the promises it makes about what will be patched."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cheat_patcher import catalog, gui  # noqa: E402
from tools.cheat_patcher.build import PATCHERS  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_every_patch_is_described(self):
        """A patch nobody can read about is one nobody can choose."""
        self.assertEqual(sorted(PATCHERS), sorted(catalog.BY_NAME))
        for cheat in catalog.CHEATS:
            with self.subTest(cheat=cheat.name):
                self.assertTrue(cheat.title.strip())
                self.assertTrue(cheat.summary.strip())

    def test_a_bang_cheat_drags_the_anti_cheat_patch_in(self):
        """Without it the game freezes, so the choice is not left open."""
        self.assertEqual(("disable-anti-cheat", "battle-anti-freeze"),
                         catalog.required_with(["battle-anti-freeze"]))

    def test_an_ordinary_cheat_does_not(self):
        self.assertEqual(("angel-slayer",),
                         catalog.required_with(["angel-slayer"]))

    def test_selecting_nothing_asks_for_nothing(self):
        self.assertEqual((), catalog.required_with([]))

    def test_the_order_is_the_catalog_order_however_it_is_asked_for(self):
        self.assertEqual(
            catalog.required_with(["angel-slayer", "disable-anti-cheat"]),
            catalog.required_with(["disable-anti-cheat", "angel-slayer"]))


def _window():
    if gui.TK_IMPORT_ERROR is not None:
        raise unittest.SkipTest(f"no Tk: {gui.TK_IMPORT_ERROR}")
    try:
        root = gui.Tk()
    except Exception as exc:                     # pragma: no cover - headless
        raise unittest.SkipTest(f"no display: {exc!r}")
    root.withdraw()
    return root


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.root = _window()
        self.addCleanup(self.root.destroy)
        self.app = gui.App(self.root)

    def test_it_wears_the_translation_builder_s_clothes(self):
        """The pair should look like one pair, so the assets are shared."""
        for name in (gui.ICON_ICO, gui.ICON_PNG, gui.BACKDROP_PNG):
            with self.subTest(asset=name):
                self.assertIsNotNone(gui.asset_path(name), name)
        translator = ROOT.parent / "opensource" / "vp2_translate.py"
        if translator.is_file():
            source = translator.read_text(encoding="utf-8")
            for key, value in gui.DARK.items():
                with self.subTest(colour=key):
                    self.assertIn(f'"{key}": "{value}"', source)

    def test_every_cheat_has_a_box_and_starts_on(self):
        self.assertEqual(sorted(catalog.BY_NAME),
                         sorted(self.app.cheat_boxes))
        self.assertEqual(sorted(catalog.BY_NAME),
                         sorted(self.app.selected_cheats()))

    def test_unticking_the_anti_cheat_box_does_not_take(self):
        """A (!) cheat is still selected, so it must stay on."""
        self.app.cheat_vars[catalog.ANTI_CHEAT].set(False)
        self.assertTrue(self.app.cheat_vars[catalog.ANTI_CHEAT].get())
        self.assertEqual("disabled",
                         str(self.app.cheat_boxes[catalog.ANTI_CHEAT].cget("state")))

    def test_it_frees_up_once_nothing_needs_it(self):
        for cheat in catalog.CHEATS:
            if cheat.requires_anti_cheat:
                self.app.cheat_vars[cheat.name].set(False)
        self.assertEqual("normal",
                         str(self.app.cheat_boxes[catalog.ANTI_CHEAT].cget("state")))
        self.app.cheat_vars[catalog.ANTI_CHEAT].set(False)
        self.assertNotIn(catalog.ANTI_CHEAT, self.app.selected_cheats())

    def test_a_running_patch_takes_every_control_away(self):
        self.assertTrue(self.app.locked)
        self.app._set_busy(True)
        for widget, _idle in self.app.locked:
            with self.subTest(widget=str(widget)):
                self.assertEqual("disabled", str(widget.cget("state")))
        self.app._set_busy(False)
        self.assertEqual("normal", str(self.app.patch_btn.cget("state")))

    def test_the_copy_percentage_drives_the_bar(self):
        self.app._track_progress("copy: 50%")
        self.assertAlmostEqual(45, float(self.app.progress["value"]))
        self.app._track_progress("verify: reading every patched region back")
        self.assertAlmostEqual(96, float(self.app.progress["value"]))

    def test_the_output_name_is_shown_before_anything_is_written(self):
        self.app.source_var.set(str(ROOT / "somewhere" / "VP2.iso"))
        self.app.output_var.set(str(ROOT / "build"))
        self.assertIn(".iso", self.app.output_label.cget("text"))


if __name__ == "__main__":
    unittest.main()
