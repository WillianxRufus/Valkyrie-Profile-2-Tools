# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""The window, and the promises it makes about what will be patched."""

import sys
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cheat_patcher import catalog, gui  # noqa: E402
from tools.cheat_patcher.build import PATCHERS  # noqa: E402
import vp2_cheats  # noqa: E402


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
        self.assertEqual(("disable-anti-cheat", "battle-menu-always"),
                         catalog.required_with(["battle-menu-always"]))
        self.assertEqual(
            ("disable-anti-cheat", "heavenly-punishment-15-ap"),
            catalog.required_with(["heavenly-punishment-15-ap"])
        )
        self.assertEqual(
            ("disable-anti-cheat", "stop-removing-characters"),
            catalog.required_with(["stop-removing-characters"])
        )
        self.assertEqual(
            ("disable-anti-cheat", "mithra-swap", "join-level-1"),
            catalog.required_with(["join-level-1", "mithra-swap"])
        )

    def test_an_ordinary_cheat_does_not(self):
        self.assertEqual(("angel-slayer",),
                         catalog.required_with(["angel-slayer"]))
        self.assertEqual(("99-skill-points",),
                         catalog.required_with(["99-skill-points"]))
        self.assertEqual(
            ("restore-all-sealstones",),
            catalog.required_with(["restore-all-sealstones"])
        )

    def test_selecting_nothing_asks_for_nothing(self):
        self.assertEqual((), catalog.required_with([]))

    def test_the_order_is_the_catalog_order_however_it_is_asked_for(self):
        self.assertEqual(
            catalog.required_with(["angel-slayer", "disable-anti-cheat"]),
            catalog.required_with(["disable-anti-cheat", "angel-slayer"]))

    def test_cli_adds_anti_cheat_for_the_roster_patch(self):
        result = SimpleNamespace(patches=(), output=Path("patched.iso"))
        with mock.patch.object(vp2_cheats, "build_iso", return_value=result) as build:
            self.assertEqual(0, vp2_cheats.main([
                "clean.iso", "--output", "patched.iso", "--patch",
                "stop-removing-characters",
            ]))
        self.assertEqual(
            ("disable-anti-cheat", "stop-removing-characters"),
            build.call_args.kwargs["selected"]
        )


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

    def test_every_cheat_has_a_box_and_only_anti_cheat_starts_on(self):
        self.assertEqual(sorted(catalog.BY_NAME),
                         sorted(self.app.cheat_boxes))
        self.assertEqual((catalog.ANTI_CHEAT,), self.app.selected_cheats())
        for name, variable in self.app.cheat_vars.items():
            self.assertEqual(name == catalog.ANTI_CHEAT, variable.get())

    def test_header_button_toggles_every_cheat_and_tracks_partial_state(self):
        button = self.app.toggle_all_cheats_btn
        self.assertIs(button.master, self.app.cheat_card)
        self.assertEqual(0, int(button.grid_info()["row"]))
        self.assertEqual("Disable all cheats", button.cget("text"))

        button.invoke()
        self.assertFalse(any(variable.get()
                             for variable in self.app.cheat_vars.values()))
        self.assertEqual("Enable all cheats", button.cget("text"))
        self.assertEqual("normal", str(
            self.app.cheat_boxes[catalog.ANTI_CHEAT].cget("state")
        ))

        button.invoke()
        self.assertTrue(all(variable.get()
                            for variable in self.app.cheat_vars.values()))
        self.assertEqual("Disable all cheats", button.cget("text"))
        self.assertEqual("disabled", str(
            self.app.cheat_boxes[catalog.ANTI_CHEAT].cget("state")
        ))

        self.app.cheat_vars["angel-slayer"].set(False)
        self.assertEqual("Disable all cheats", button.cget("text"))

    def test_only_the_cheat_list_owns_scrolling(self):
        self.assertEqual("", self.app.canvas.cget("yscrollcommand"))
        self.assertTrue(self.app.cheat_canvas.cget("yscrollcommand"))
        for box in self.app.cheat_boxes.values():
            self.assertIs(box.master, self.app.cheat_content)

        with (mock.patch.object(self.app.canvas, "winfo_width", return_value=900),
              mock.patch.object(self.app.canvas, "winfo_height", return_value=684)):
            self.app._reflow()
        cheat_height = float(
            self.app.canvas.itemcget(self.app.items["cheats"], "height")
        )
        self.assertGreaterEqual(cheat_height, 180)
        self.assertLessEqual(cheat_height, 300)
        patch_y = self.app.canvas.coords(self.app.items["patch"])[1]
        cheat_y = self.app.canvas.coords(self.app.items["cheats"])[1]
        self.assertGreater(patch_y, cheat_y + cheat_height)

    def test_mouse_wheel_moves_cheats_but_not_fixed_controls(self):
        cheat_event = SimpleNamespace(
            widget=next(iter(self.app.cheat_boxes.values())), num=None,
            delta=-120,
        )
        fixed_event = SimpleNamespace(
            widget=self.app.patch_btn, num=None, delta=-120,
        )
        with mock.patch.object(self.app.cheat_canvas, "yview_scroll") as scroll:
            self.app._scroll_cheats(cheat_event)
            scroll.assert_called_once_with(3, "units")
            self.app._scroll_cheats(fixed_event)
            scroll.assert_called_once()

    def test_unticking_the_anti_cheat_box_does_not_take(self):
        """A (!) cheat is still selected, so it must stay on."""
        self.app.cheat_vars["battle-anti-freeze"].set(True)
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
