import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from packaging.version import Version

from core.config import PROJECT_ROOT, VERSION, _load_config

log = logging.getLogger(__name__)

UPDATE_LOG = PROJECT_ROOT / "update.log"
UPDATER_PATH = PROJECT_ROOT / "core" / "updater.py"

GITHUB_REPO = "markwmccall/vinyl-emulator"

# Cache for GitHub release check: (timestamp, result_dict)
_update_cache = None  # type: tuple | None  (timestamp, result_dict)
_UPDATE_CACHE_TTL = 3600  # 1 hour


def clear_update_cache():
    """Invalidate the in-memory update check cache."""
    global _update_cache
    _update_cache = None


def _check_for_update() -> dict:
    """Return update info, using a 1-hour in-memory cache."""
    global _update_cache
    now = time.time()
    if _update_cache and now - _update_cache[0] < _UPDATE_CACHE_TTL:
        return _update_cache[1]

    result = {"current": VERSION, "latest": VERSION, "update_available": False}
    try:
        import requests as _req
        resp = _req.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        if latest:
            result["latest"] = latest
            result["update_available"] = Version(latest) > Version(VERSION)
    except Exception as e:
        log.warning("Update check failed: %s", e)  # fail open: return current version

    _update_cache = (now, result)
    return result


def _read_update_state():
    """Return (state, log_lines) from update.log. state is 'idle' if no log.

    If state is 'running' but the recorded PID is no longer alive, treats the
    state as 'failed' so a crashed updater doesn't permanently show 'updating'.
    """
    if not UPDATE_LOG.exists():
        return "idle", []
    lines = UPDATE_LOG.read_text().splitlines()
    state = "idle"
    pid = None
    for line in lines:
        if line.startswith("PID:"):
            try:
                pid = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        if line.startswith("STATE:"):
            state = line.split(":", 1)[1].strip()
    if state == "running" and pid is not None:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            state = "failed"
    return state, lines[-20:]


def _auto_update_loop():
    """Check once per hour and apply update automatically if auto_update=true."""
    while True:
        time.sleep(3600)
        try:
            config = _load_config()
            if not config.get("auto_update"):
                continue
            info = _check_for_update()
            if not info.get("update_available"):
                continue
            state, _ = _read_update_state()
            if state == "running":
                continue
            target = info["latest"]
            with open(UPDATE_LOG, "w") as log_file:
                subprocess.Popen(
                    [sys.executable, str(UPDATER_PATH), target],
                    cwd=str(PROJECT_ROOT),
                    start_new_session=True,
                    stdout=log_file,
                    stderr=log_file,
                )
            log.info("Auto-update: launched updater %s → v%s", VERSION, target)
        except Exception as e:
            log.warning("Auto-update loop error: %s", e)
