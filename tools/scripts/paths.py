"""Stable repository paths for modules inside ``tools/scripts``."""

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path


FROZEN = bool(getattr(sys, "frozen", False))

SCRIPTS_DIR = Path(__file__).resolve().parent

if FROZEN:
    # The public bundle carries its small, source-free payload as loose files
    # under the PyInstaller extraction root. VP2_PAYLOAD_ROOT remains a useful
    # compatibility override for callers that prepare a different payload.
    _prepared = os.environ.get("VP2_PAYLOAD_ROOT")
    PROJECT_ROOT = Path(
        _prepared or getattr(sys, "_MEIPASS", SCRIPTS_DIR.parent)).resolve()
    TOOLS_DIR = PROJECT_ROOT / "tools"
else:
    TOOLS_DIR = SCRIPTS_DIR.parent
    PROJECT_ROOT = TOOLS_DIR.parent

# Source-free structural tables live directly under ``data/``.
DATA_DIR = PROJECT_ROOT / "data"

# Keep the established directory so upgrading to the unified executable reuses
# existing generated workspaces and compression state.
APP_DIR_NAME = "ValkyrieProfile2-Translator"


def user_state_root() -> Path:
    """Per-user writable directory for a packaged run."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP_DIR_NAME
    else:
        base = os.environ.get("XDG_CACHE_HOME")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / ".cache" / APP_DIR_NAME
    return Path.home() / ("." + APP_DIR_NAME)


def _writable_root() -> Path:
    """Where this run may write. ``VP2_STATE_ROOT`` overrides both cases."""
    override = os.environ.get("VP2_STATE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if FROZEN:
        return user_state_root()
    return PROJECT_ROOT / "build"


BUILD_DIR = _writable_root()


def _workspace_root() -> Path:
    """Where ``generate`` writes and ``build`` reads it back."""
    override = os.environ.get("VP2_WORKSPACE")
    if override:
        return Path(override).expanduser().resolve()
    if FROZEN:
        return _writable_root() / "workspace"
    return PROJECT_ROOT / "workspace"


WORKSPACE_DIR = _workspace_root()


def output_root() -> Path:
    """Where a finished ISO goes when nobody said."""
    if os.environ.get("VP2_STATE_ROOT") or not FROZEN:
        return BUILD_DIR
    return Path.cwd()

def _cache_root() -> Path:
    """Where compression results are kept between resources."""
    if FROZEN and not os.environ.get("VP2_STATE_ROOT"):
        temporary = Path(tempfile.mkdtemp(prefix="vp2-build-cache-"))
        atexit.register(shutil.rmtree, temporary, ignore_errors=True)
        return temporary
    return PROJECT_ROOT / "workspace" / "internal" / ".cache"


CACHE_ROOT = _cache_root()
