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
        """Both tools ship, and neither scratches outside the workspace."""
        self.assertTrue(self.spec_path.is_file())
        self.assertTrue((ROOT / "data" / "vp2_cheats.spec").is_file())
        expected_workpath = "--workpath workspace/internal/build"
        for path in (
                ROOT / "Dockerfile",
                ROOT / ".github" / "workflows" / "release.yml",
                ROOT / "docs" / "building-releases.md"):
            source = path.read_text(encoding="utf-8")
            for spec in ("data/vp2_release.spec", "data/vp2_cheats.spec"):
                self.assertIn(spec, source, "%s: %s" % (path, spec))
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

    def test_source_runtime_requirements_are_explicit_and_pip_installable(self):
        requirements = ROOT / "requirements.txt"
        lines = requirements.read_text(encoding="utf-8").splitlines()
        packages = [line.strip() for line in lines
                    if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual([], packages)
        readme = (ROOT / "Readme.md").read_text(encoding="utf-8")
        self.assertIn("pip install -r requirements.txt", readme)
        self.assertIn("import tkinter; tkinter.Tcl()", readme)


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



def _window():
    """A real window, or the reason there cannot be one.

    The release container has Tk but no display, so these skip there and
    run on a developer's machine, which is where the window is used.
    """
    if launcher.TK_IMPORT_ERROR is not None:
        raise unittest.SkipTest(f"no Tk: {launcher.TK_IMPORT_ERROR}")
    try:
        root = launcher.Tk()
    except Exception as exc:                     # pragma: no cover - headless
        raise unittest.SkipTest(f"no display: {exc!r}")
    root.withdraw()
    return root


class WindowTests(unittest.TestCase):

    def setUp(self):
        self.root = _window()
        self.addCleanup(self.root.destroy)
        self.app = launcher.App(self.root)

    def _label_for(self, locale):
        for pack in self.app.packs:
            if pack.locale == locale:
                return pack.label
        self.fail(f"{locale} is not installed")

    def test_the_dropdown_chooses_which_pack_is_built(self):
        """The build must use the language on screen, not the default."""
        import tempfile
        from unittest import mock

        started = []
        with tempfile.TemporaryDirectory() as folder:
            self.app.output_var.set(folder)
            self.app.pack_var.set(self._label_for("sv-SE"))
            image = Path(folder) / "disc.iso"
            with mock.patch.object(launcher.App, "_validated_usa",
                                   return_value=image), \
                    mock.patch.object(launcher, "workspace_summary",
                                      return_value=(True, "ready")), \
                    mock.patch.object(self.app.runner, "start",
                                      side_effect=lambda *a, **k:
                                          started.append((a, k))):
                self.app._start_build()

        self.assertEqual(1, len(started))
        (kind, function, usa, pack), keywords = started[0]
        self.assertEqual("build", kind)
        self.assertIs(launcher.build_iso, function)
        self.assertEqual(ROOT / "translations" / "sv-SE", pack)
        self.assertEqual("disc.sv-SE.iso", Path(keywords["output"]).name)

    def test_a_running_job_takes_every_control_away(self):
        self.assertTrue(self.app.locked)
        for widget, _idle in self.app.locked:
            self.assertNotEqual("disabled", str(widget.cget("state")))

        self.app._set_busy(True)
        for widget, _idle in self.app.locked:
            with self.subTest(widget=str(widget)):
                self.assertEqual("disabled", str(widget.cget("state")))

        self.app._set_busy(False)
        for widget, idle in self.app.locked:
            with self.subTest(widget=str(widget)):
                self.assertEqual(idle, str(widget.cget("state")))

    def test_the_language_dropdown_never_becomes_typable(self):
        """Re-enabling must restore readonly, not normal."""
        self.app._set_busy(True)
        self.app._set_busy(False)
        self.assertEqual("readonly",
                         str(self.app.language_combo.cget("state")))

    def test_the_controls_a_job_reads_are_all_locked(self):
        locked = {str(widget) for widget, _idle in self.app.locked}
        for name, widget in (("language", self.app.language_combo),
                             ("build", self.app.build_btn),
                             ("verify", self.app.verify_chk)):
            with self.subTest(control=name):
                self.assertIn(str(widget), locked)
        self.assertEqual(9, len(self.app.locked))

    def test_verification_is_off_until_asked_for(self):
        """The slow read-back pass is opt-in, so a build finishes sooner."""
        self.assertFalse(self.app.verify_var.get())

    def test_there_is_one_action_and_it_is_the_build(self):
        """Preparing is part of building, so it is not a button any more."""
        self.assertFalse(hasattr(self.app, "prepare_btn"))
        self.assertNotIn("prepare", self.app.items)
        self.assertIn("build", self.app.items)

    def test_the_workspace_line_survives_the_button(self):
        self.app._refresh_workspace()
        self.assertTrue(self.app.workspace_var.get())
        self.assertIn(str(self.app.workspace_label.cget("style")),
                      ("Ok.TLabel", "Warn.TLabel"))

    def test_a_real_percentage_ends_the_indeterminate_sweep(self):
        """An unread disc has no step count, so the bar sweeps until it does."""
        self.app.progress.configure(mode="indeterminate")
        self.app.progress.start(12)
        self.app._track_progress("copy:  40%")
        self.assertEqual("determinate", str(self.app.progress.cget("mode")))
        self.assertAlmostEqual(8, float(self.app.progress["value"]))

    def test_the_workspace_line_updates_as_soon_as_the_disc_is_read(self):
        """Not at the end of the build, which is minutes too late.

        A build that has to read the disc first leaves the window saying
        the workspace is not prepared for the whole run, which is untrue
        from the moment reading finishes.
        """
        from unittest import mock
        self.app.workspace_var.set("Workspace not prepared")
        self.app.workspace_ready = False
        with mock.patch.object(launcher, "workspace_summary",
                               return_value=(True, "Workspace ready · 9 rows")):
            self.app._track_progress("workspace: prepared")
        self.assertTrue(self.app.workspace_ready)
        self.assertEqual("Workspace ready · 9 rows",
                         self.app.workspace_var.get())
        self.assertEqual("Ok.TLabel",
                         str(self.app.workspace_label.cget("style")))

    def test_the_runtime_announces_that_it_prepared_one(self):
        """The window can only react to a line the build actually prints."""
        import inspect
        from tools.scripts import public_build
        source = inspect.getsource(public_build.build_iso)
        self.assertIn('"workspace: prepared"', source)


if __name__ == "__main__":
    unittest.main()
