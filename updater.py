#!/usr/bin/env python3
"""
Vinyl Emulator updater — runs as a detached subprocess launched by app.py.

Usage: python3 updater.py <target_version>
  e.g. python3 updater.py 1.2.0

Writes progress to stdout (app.py redirects this to update.log).
STATE: lines are parsed by /update/status to track progress.
"""
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
ROLLBACK_FILE = PROJECT_ROOT / ".update-rollback"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", flush=True)
    return result


def main(target_version: str) -> None:
    print(f"STATE: running", flush=True)
    print(f"Updating to v{target_version}", flush=True)

    # Save rollback point
    result = run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("STATE: failed", flush=True)
        print("Error: could not determine current git commit", flush=True)
        return
    rollback_commit = result.stdout.strip()
    ROLLBACK_FILE.write_text(rollback_commit)
    print(f"Rollback commit saved: {rollback_commit[:12]}", flush=True)

    # Fetch tags from remote
    result = run(["git", "fetch", "--tags"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("STATE: failed", flush=True)
        print("Error: git fetch failed", flush=True)
        return

    # Ensure we're on main branch (may be detached after a previous update)
    run(["git", "checkout", "main"], cwd=PROJECT_ROOT)

    # Move main to the target release tag (stays on branch, no detached HEAD)
    tag = f"v{target_version}"
    result = run(["git", "reset", "--hard", tag], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"STATE: failed", flush=True)
        print(f"Error: git reset --hard {tag} failed", flush=True)
        run(["git", "reset", "--hard", rollback_commit], cwd=PROJECT_ROOT)
        return

    # Install/update Python dependencies
    pip = str(PROJECT_ROOT / ".venv" / "bin" / "pip")
    result = run([pip, "install", "-r", "requirements.txt"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("Dependency install failed — rolling back", flush=True)
        run(["git", "reset", "--hard", rollback_commit], cwd=PROJECT_ROOT)
        print("STATE: failed", flush=True)
        return

    # Restart the service (requires passwordless sudo via sudoers)
    print("Restarting vinyl-web service...", flush=True)
    result = run(["sudo", "systemctl", "restart", "vinyl-web"])
    if result.returncode != 0:
        print("STATE: failed", flush=True)
        print("Error: systemctl restart failed", flush=True)
        return

    # Wait for the new version to become healthy
    print("Waiting for service to come back up...", flush=True)
    deadline = time.time() + 90
    healthy = False
    while time.time() < deadline:
        time.sleep(5)
        try:
            import urllib.request
            with urllib.request.urlopen("http://localhost/health", timeout=3) as r:
                if r.status == 200:
                    healthy = True
                    break
        except Exception:
            pass

    if healthy:
        print(f"Service healthy — update to v{target_version} complete", flush=True)
        print("STATE: success", flush=True)
        ROLLBACK_FILE.unlink(missing_ok=True)
    else:
        print("Health check timed out — rolling back", flush=True)
        run(["git", "reset", "--hard", rollback_commit], cwd=PROJECT_ROOT)
        run(["sudo", "systemctl", "restart", "vinyl-web"])
        print("STATE: failed", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: updater.py <target_version>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
