# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _cli():
    spec = importlib.util.spec_from_file_location(
        "_vp2_translate_cli", ROOT / "vp2_translate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CliDefaultsTests(unittest.TestCase):

    def setUp(self):
        self.cli = _cli()
        self.parser = self.cli._parser()

    def _from_elsewhere(self, argv):
        """Parse *argv* with the process sitting somewhere unrelated."""
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as elsewhere:
            os.chdir(elsewhere)
            try:
                return self.parser.parse_args(argv)
            finally:
                os.chdir(previous)

    def test_generate_and_build_agree_on_one_workspace(self):
        generate = self._from_elsewhere(["generate", "image.iso"])
        build = self._from_elsewhere(["build", "image.iso"])
        self.assertEqual(generate.workspace, build.workspace)

    def test_path_defaults_are_absolute(self):
        cases = {
            "generate --workspace": self._from_elsewhere(
                ["generate", "image.iso"]).workspace,
            "build --workspace": self._from_elsewhere(
                ["build", "image.iso"]).workspace,
            "build LANGUAGE": self.cli.resolve_pack(
                self._from_elsewhere(["build", "image.iso"]).language),
        }
        for name, value in cases.items():
            with self.subTest(argument=name):
                self.assertTrue(Path(value).is_absolute(), value)

    def test_defaults_sit_inside_the_installation(self):
        for argv, attribute in ((["generate", "i.iso"], "workspace"),
                                (["build", "i.iso"], "workspace")):
            value = Path(getattr(self._from_elsewhere(argv), attribute))
            with self.subTest(argv=argv, attribute=attribute):
                self.assertEqual(
                    ROOT, Path(os.path.commonpath([ROOT, value])))

    def test_a_language_names_a_pack_inside_the_installation(self):
        """`build image.iso sv-SE` must not depend on the caller's directory."""
        parsed = self._from_elsewhere(["build", "image.iso", "sv-SE"])
        self.assertEqual("sv-SE", parsed.language)
        pack = self.cli.resolve_pack(parsed.language)
        self.assertEqual(ROOT / "translations" / "sv-SE", pack)

    def test_a_language_may_still_be_a_pack_path(self):
        """A pack outside translations/ is still reachable by path."""
        given = ROOT / "translations" / "pt-BR"
        parsed = self._from_elsewhere(["build", "image.iso", os.fspath(given)])
        self.assertEqual(given, self.cli.resolve_pack(parsed.language))

    def test_an_explicit_relative_path_is_still_the_caller_s(self):
        """Anchoring the default must not seize an argument the user gave."""
        parsed = self.parser.parse_args(
            ["build", "image.iso", "--workspace", "somewhere"])
        self.assertEqual("somewhere", parsed.workspace)


if __name__ == "__main__":
    unittest.main()
