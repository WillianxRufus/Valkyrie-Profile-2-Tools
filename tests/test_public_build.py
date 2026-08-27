"""Rules about what a public build writes and what it keeps."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class CacheLocationTests(unittest.TestCase):
    """Where a build is allowed to leave things behind.

    Two rules, and they exist for different people.  A source checkout
    keeps its compression cache under the ignored workspace, beside the
    rest of the state generated from the user's image, rather than next
    to the output ISO.  A packaged run keeps it somewhere temporary and
    deletes it: an end user builds their ISO once and should not be left
    with tens of megabytes under their profile that nothing will read
    again.
    """

    def test_a_checkout_caches_inside_the_workspace(self):
        from tools.scripts import paths
        self.assertFalse(paths.FROZEN)
        self.assertEqual(
            (paths.PROJECT_ROOT / "workspace" / "internal" / ".cache"),
            paths.CACHE_ROOT)

    def test_a_packaged_run_writes_its_iso_where_it_was_invoked(self):
        """State goes out of the way; the thing asked for does not.

        BUILD_DIR is the per-user data directory when frozen, which is
        right for caches and wrong for a 4.7 GB disc image: nobody looks
        for their output in AppData, and nothing would have told them.
        """
        from tools.scripts import paths
        self.assertEqual(paths.BUILD_DIR, paths.output_root())
        try:
            paths.FROZEN = True
            self.assertEqual(Path.cwd(), paths.output_root())
        finally:
            paths.FROZEN = False

    def test_the_cache_is_not_beside_the_output_iso(self):
        from tools.scripts import paths
        self.assertNotEqual(paths.BUILD_DIR / ".cache", paths.CACHE_ROOT)

    def test_no_seed_promotion_machinery_exists(self):
        """Seeds are compressed game data; this repository carries none.

        This used to assert a flag was off.  The flag is gone with the code
        behind it: promotion took a build's compression results and wrote
        them back into the repository as tracked files, which is the one
        thing this tree must never do, and a switch is a weaker guarantee
        than an absence.
        """
        import importlib
        for name in ("build_cache", "promote_slz_cache"):
            with self.subTest(module=name):
                with self.assertRaises(ImportError):
                    importlib.import_module(f"tools.scripts.{name}")

        source = (ROOT / "tools" / "scripts").glob("*.py")
        offenders = [p.name for p in source
                     if "PROMOTES_TRACKED_SEEDS" in p.read_text(encoding="utf-8")]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
