# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Release-window and frozen handoff regressions."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import vp2_translate as launcher  # noqa: E402
from tools.scripts import public_build  # noqa: E402


class LauncherLogicTests(unittest.TestCase):
    def test_no_arguments_selects_the_gui(self):
        args = launcher._parser().parse_args([])
        self.assertIsNone(args.command)

    def test_language_packs_are_named_for_people(self):
        packs = launcher.language_packs(ROOT)
        self.assertIn("pt-BR", [pack.locale for pack in packs])
        self.assertTrue(all(pack.path.is_dir() for pack in packs))

    def test_output_name_carries_the_locale(self):
        pack = launcher.LanguagePack("Português", "pt-BR", Path("pack"))
        output = launcher.output_path_for(
            Path("Valkyrie Profile 2.iso"), pack, Path("releases"))
        self.assertEqual(
            Path("releases/Valkyrie Profile 2.pt-BR.iso"), output)

    def test_window_is_centred_and_never_uses_the_withdrawn_sentinel(self):
        class Screen:
            def winfo_screenwidth(self):
                return 1920

            def winfo_screenheight(self):
                return 1080

        self.assertEqual(
            "900x570+510+255",
            launcher.initial_window_geometry(Screen(), 900, 570))


class FrozenRuntimeTests(unittest.TestCase):
    def test_source_build_uses_python_module_mode(self):
        command = public_build.runtime_command(["source.iso"])
        self.assertEqual([sys.executable, "-m", "tools.scripts.vp2_build"],
                         command[:3])

    def test_frozen_build_reenters_the_launcher_without_dash_m(self):
        previous = getattr(sys, "frozen", None)
        sys.frozen = True
        try:
            command = public_build.runtime_command(["source.iso", "--no-verify"])
        finally:
            if previous is None:
                del sys.frozen
            else:
                sys.frozen = previous
        self.assertEqual(
            [sys.executable, "_runtime-build", "source.iso", "--no-verify"],
            command)


class ReleaseSpecTests(unittest.TestCase):
    def setUp(self):
        self.spec_path = ROOT / "data" / "vp2_release.spec"
        self.spec = self.spec_path.read_text(encoding="utf-8")

    def test_spec_and_pyinstaller_work_tree_use_internal_build_storage(self):
        self.assertTrue(self.spec_path.is_file())
        expected_spec = "data/vp2_release.spec"
        expected_workpath = "--workpath workspace/internal/build"
        for path in (
                ROOT / "Dockerfile",
                ROOT / ".github" / "workflows" / "release.yml",
                ROOT / "Readme.md"):
            source = path.read_text(encoding="utf-8")
            self.assertIn(expected_spec, source, path)
            self.assertIn(expected_workpath, source, path)
            self.assertNotIn(
                "--workpath workspace/internal/build/vp2_release", source,
                path)

    def test_double_click_builds_for_the_window_subsystem(self):
        self.assertIn("console=False", self.spec)
        self.assertNotIn('"tkinter", "_tkinter"', self.spec)

    def test_icon_and_backdrop_are_bundled(self):
        self.assertIn("icon=", self.spec)
        for name in (launcher.ICON_ICO, launcher.ICON_PNG,
                     launcher.BACKDROP_PNG):
            self.assertTrue((ROOT / name).is_file(), name)
            self.assertIn(name, self.spec)

    def test_self_check_initializes_tcl_not_just_the_python_wrapper(self):
        source = (ROOT / "tools" / "scripts" / "public_release.py").read_text(
            encoding="utf-8")
        self.assertIn("tkinter.Tcl()", source)
        self.assertIn("_tcl_data/init.tcl", source)
        self.assertIn("_tk_data/tk.tcl", source)

    def test_linux_release_uses_the_same_pinned_container_locally_and_in_ci(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8")
        self.assertIn("FROM ubuntu:24.04", dockerfile)
        self.assertIn("ARG PYTHON_VERSION=3.11.16", dockerfile)
        self.assertIn("ARG PYINSTALLER_VERSION=6.22.2", dockerfile)
        self.assertIn("docker build", workflow)
        self.assertIn('pyinstaller==6.22.2', workflow)


class WindowSmokeTests(unittest.TestCase):
    def test_window_constructs(self):
        try:
            import tkinter
            root = tkinter.Tk()
        except Exception as exc:
            self.skipTest(f"no usable Tk display: {exc}")
        root.withdraw()
        try:
            app = launcher.App(root)
            self.assertEqual(0, app.progress["value"])
            app._track_progress("copy: 50%")
            self.assertAlmostEqual(10, float(app.progress["value"]))
            app._track_progress("[2/10] scene 0033 ok (0.2s)")
            self.assertGreater(float(app.progress["value"]), 20)

            popdown = root.tk.call(
                "ttk::combobox::PopdownWindow", str(app.language_combo))
            listbox = f"{popdown}.f.l"
            self.assertEqual(
                launcher.DARK["surface_hi"],
                root.tk.call(listbox, "cget", "-background"))
            self.assertEqual(
                launcher.DARK["text"],
                root.tk.call(listbox, "cget", "-foreground"))
            self.assertEqual(
                launcher.DARK["accent_dim"],
                root.tk.call(listbox, "cget", "-selectbackground"))
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
