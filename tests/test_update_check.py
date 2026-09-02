# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only

"""Pure-function tests for the GitHub release check."""

import json
import queue
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import app_meta, update_check  # noqa: E402


class ParseVersionTests(unittest.TestCase):
    def test_plain_semver(self):
        self.assertEqual((0, 1, 1), update_check.parse_version("0.1.1"))

    def test_lowercase_v_prefix(self):
        self.assertEqual((1, 2, 3), update_check.parse_version("v1.2.3"))

    def test_uppercase_v_prefix(self):
        self.assertEqual((4, 0), update_check.parse_version("V4.0"))

    def test_two_part_version(self):
        self.assertEqual((2, 10), update_check.parse_version("v2.10"))

    def test_prerelease_tag_is_rejected(self):
        self.assertIsNone(update_check.parse_version("v0.2.0-rc1"))

    def test_non_numeric_tag_is_rejected(self):
        self.assertIsNone(update_check.parse_version("latest"))

    def test_empty_tag_is_rejected(self):
        self.assertIsNone(update_check.parse_version(""))

    def test_trailing_garbage_is_rejected(self):
        self.assertIsNone(update_check.parse_version("1.0.0+build"))


class IsNewerTests(unittest.TestCase):
    def test_minor_bump_is_newer(self):
        release = update_check.ReleaseInfo(
            tag="v0.1.2", version="0.1.2", html_url="x", parts=(0, 1, 2))
        self.assertTrue(update_check.is_newer(release, (0, 1, 1)))

    def test_same_version_is_not_newer(self):
        release = update_check.ReleaseInfo(
            tag="v0.1.1", version="0.1.1", html_url="x", parts=(0, 1, 1))
        self.assertFalse(update_check.is_newer(release, (0, 1, 1)))

    def test_older_version_is_not_newer(self):
        release = update_check.ReleaseInfo(
            tag="v0.1.0", version="0.1.0", html_url="x", parts=(0, 1, 0))
        self.assertFalse(update_check.is_newer(release, (0, 1, 1)))

    def test_major_bump_is_newer(self):
        release = update_check.ReleaseInfo(
            tag="v1.0.0", version="1.0.0", html_url="x", parts=(1, 0, 0))
        self.assertTrue(update_check.is_newer(release, (0, 9, 9)))


class EndpointTests(unittest.TestCase):
    def test_latest_release_url_uses_the_project_owner_and_name(self):
        url = update_check.latest_release_url()
        self.assertIn("api.github.com/repos/", url)
        self.assertTrue(url.endswith("/releases/latest"))
        owner, name, *_ = url.split("/repos/", 1)[1].split("/")
        repo_url = app_meta.PROJECT_URL.rstrip("/")
        self.assertTrue(repo_url.endswith("/" + owner + "/" + name),
                        "%s vs %s/%s" % (repo_url, owner, name))


class FetchLatestReleaseTests(unittest.TestCase):
    def _payload(self, tag, html_url="https://example/release"):
        return json.dumps({
            "tag_name": tag, "html_url": html_url, "name": tag,
        }).encode("utf-8")

    def _response(self, body):
        response = mock.MagicMock()
        response.status = 200
        response.read.return_value = body
        return response

    def test_returns_release_when_newer_than_running_build(self):
        response = self._response(self._payload("v0.1.2"))
        with mock.patch.object(
                update_check, "current_version_tuple",
                return_value=(0, 1, 1)), \
                mock.patch.object(
                    update_check.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            release = update_check.fetch_latest_release()
        self.assertIsNotNone(release)
        self.assertEqual("v0.1.2", release.tag)
        self.assertEqual("0.1.2", release.version)
        self.assertEqual("https://example/release", release.html_url)
        self.assertEqual((0, 1, 2), release.parts)

    def test_returns_none_when_remote_is_same_version(self):
        response = self._response(self._payload("v0.1.1"))
        with mock.patch.object(
                update_check, "current_version_tuple",
                return_value=(0, 1, 1)), \
                mock.patch.object(
                    update_check.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            self.assertIsNone(update_check.fetch_latest_release())

    def test_returns_none_when_remote_is_older(self):
        response = self._response(self._payload("v0.1.5"))
        with mock.patch.object(
                update_check, "current_version_tuple",
                return_value=(0, 2, 0)), \
                mock.patch.object(
                    update_check.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            self.assertIsNone(update_check.fetch_latest_release())

    def test_returns_none_on_network_failure(self):
        with mock.patch.object(
                update_check, "current_version_tuple",
                return_value=(0, 1, 1)), \
                mock.patch.object(
                    update_check.urllib.request, "urlopen",
                    side_effect=urllib.error.URLError("offline")):
            self.assertIsNone(update_check.fetch_latest_release())

    def test_returns_none_on_invalid_json(self):
        response = self._response(b"not-json")
        with mock.patch.object(
                update_check, "current_version_tuple",
                return_value=(0, 1, 1)), \
                mock.patch.object(
                    update_check.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            self.assertIsNone(update_check.fetch_latest_release())

    def test_returns_none_when_tag_is_missing_or_unparseable(self):
        for missing in ({}, {"html_url": "x"},
                        {"tag_name": "latest", "html_url": "x"},
                        {"tag_name": "v0.1.0", "html_url": ""}):
            response = self._response(json.dumps(missing).encode("utf-8"))
            with mock.patch.object(
                    update_check, "current_version_tuple",
                    return_value=(0, 1, 1)), \
                    mock.patch.object(
                        update_check.urllib.request, "urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value = response
                self.assertIsNone(
                    update_check.fetch_latest_release(), missing)


class WorkerTests(unittest.TestCase):
    def test_worker_posts_none_when_there_is_no_update(self):
        sink = queue.Queue()
        with mock.patch.object(
                update_check, "fetch_latest_release",
                return_value=None):
            update_check.worker(sink)
        self.assertIsNone(sink.get_nowait())

    def test_worker_posts_a_release_when_available(self):
        sink = queue.Queue()
        release = update_check.ReleaseInfo(
            tag="v9.9.9", version="9.9.9",
            html_url="https://example", parts=(9, 9, 9))
        with mock.patch.object(
                update_check, "fetch_latest_release",
                return_value=release):
            update_check.worker(sink)
        self.assertIs(release, sink.get_nowait())


class ReleaseBuildDetectionTests(unittest.TestCase):
    def test_returns_false_in_normal_python(self):
        self.assertFalse(update_check.is_release_build())

    def test_returns_true_when_sys_frozen_is_set(self):
        previous = getattr(sys, "frozen", None)
        sys.frozen = True
        try:
            self.assertTrue(update_check.is_release_build())
        finally:
            if previous is None:
                del sys.frozen
            else:
                sys.frozen = previous


if __name__ == "__main__":
    unittest.main()
