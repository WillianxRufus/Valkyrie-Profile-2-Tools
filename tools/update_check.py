# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Check GitHub Releases for a newer packaged build of these tools."""

from __future__ import annotations

import json
import queue
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import app_meta


TIMEOUT_SECONDS = 5
USER_AGENT = "%s/%s" % (app_meta.PROJECT_NAME, app_meta.VERSION)
_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    version: str
    html_url: str
    parts: tuple


def _owner_repo(project_url: str) -> str:
    return "/".join(project_url.rstrip("/").split("/")[-2:])


def parse_version(tag: str) -> Optional[tuple]:
    body = tag.strip().lstrip("vV")
    if not _VERSION_RE.match(body):
        return None
    return tuple(int(piece) for piece in body.split("."))


def is_newer(release: ReleaseInfo, current: tuple) -> bool:
    return release.parts > current


def current_version_tuple() -> tuple:
    parsed = parse_version(app_meta.VERSION)
    return parsed or (0,)


def latest_release_url() -> str:
    return "https://api.github.com/repos/%s/releases/latest" % _owner_repo(
        app_meta.PROJECT_URL
    )


def fetch_latest_release() -> Optional[ReleaseInfo]:
    """Return the latest release if it is newer than the running build."""
    request = urllib.request.Request(
        latest_release_url(),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return None
            data = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None

    tag = (data.get("tag_name") or "").strip()
    html_url = (data.get("html_url") or "").strip()
    parts = parse_version(tag)
    if not parts or not html_url:
        return None

    release = ReleaseInfo(
        tag=tag, version=tag.lstrip("vV"), html_url=html_url, parts=parts,
    )
    if not is_newer(release, current_version_tuple()):
        return None
    return release


def worker(sink: "queue.Queue[Optional[ReleaseInfo]]") -> None:
    """Background entry point: fetch once and post the result to *sink*."""
    try:
        sink.put(fetch_latest_release())
    except BaseException:                       # pragma: no cover - safety net
        sink.put(None)


def is_release_build() -> bool:
    """``True`` when the process is the packaged PyInstaller binary."""
    return bool(getattr(sys, "frozen", False))
