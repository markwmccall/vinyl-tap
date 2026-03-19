# Plan: Rename Project to Vinyl Tap

## Summary of Changes

| Old | New |
|---|---|
| `vinyl-emulator` (repo/hyphenated) | `vinyl-tap` |
| `Vinyl Emulator` (display name) | `Vinyl Tap` |
| `vinyl-pi` (Pi hostname) | `vinyltap` → `vinyltap.local` |
| `vinyl-mac` (Mac dev hostname) | `vinyltap-dev` → `vinyltap-dev.local` |
| `vinyl-web` (systemd service) | `vinyltap` |
| `etc/vinyl-web.service` (file) | `etc/vinyltap.service` |
| `/etc/sudoers.d/vinyl-emulator-update` | `/etc/sudoers.d/vinyltap-update` |
| `markwmccall/vinyl-emulator` (GitHub) | `markwmccall/vinyl-tap` |

---

## Part 1: GitHub Repository Rename

Done AFTER the PR merges to main, to keep CI green during the transition.

### Step 1.1 — Rename the repo on GitHub
```bash
gh repo rename vinyl-tap --repo markwmccall/vinyl-emulator
```

### Step 1.2 — Update local git remote
```bash
git remote set-url origin https://github.com/markwmccall/vinyl-tap.git
```

---

## Part 2: Code Changes

### `core/updater_service.py`
- `GITHUB_REPO` constant:
  - `"markwmccall/vinyl-emulator"` → `"markwmccall/vinyl-tap"`

### `core/updater.py`
- Display name in docstring (line 3):
  - `Vinyl Emulator` → `Vinyl Tap`
- Service name references (3 occurrences):
  - Line 75: `print("Restarting vinyl-web service...", flush=True)` → `vinyltap`
  - Line 76: `run(["sudo", "systemctl", "restart", "vinyl-web"])` → `vinyltap`
  - Line 108: `run(["sudo", "systemctl", "restart", "vinyl-web"])` → `vinyltap`

### `app.py`
- Service name references (2 occurrences):
  - `vinyl-web` → `vinyltap`

### `providers/sonos_api.py`
- Hostname references:
  - `vinyl-pi` → `vinyltap`
  - `vinyl-mac` → `vinyltap-dev`
  - `vinyl-emulator` → `vinyl-tap`

---

## Part 3: Template Changes

### `templates/base.html`
- Page title (line 6): `Vinyl Emulator` → `Vinyl Tap`
- Nav logo text (line 18): `...Vinyl Emulator</a>` → `...Vinyl Tap</a>`

### `templates/settings_music.html`
- Pi hostname placeholder: `vinyl-pi` → `vinyltap`

### `templates/logs.html`
- Service name displayed in UI: `vinyl-web` → `vinyltap`

### `templates/settings_hardware.html`
- Service name displayed in UI (2 occurrences): `vinyl-web` → `vinyltap`

---

## Part 4: Script Changes

### `scripts/setup.sh`

**Note**: `setup.sh` does NOT set the Pi hostname — it reads it dynamically via
`PI_HOSTNAME="$(hostname)"`. The Pi hostname change is a separate manual step
(Part 9). Only the comment and service references need updating here.

Changes:
- Line 2: script comment: `vinyl-emulator` → `vinyl-tap`
- Line 7: comment URL: `http://vinyl-pi.local:5000` → `https://vinyltap.local`
- Line 16: banner echo: `Vinyl Emulator Setup` → `Vinyl Tap Setup`
- Line 69: `systemctl stop vinyl-web` → `systemctl stop vinyltap`
- Line 100: `sed` pattern replacing template paths:
  - `s|/home/pi/vinyl-emulator|$REPO_DIR|g` → `s|/home/pi/vinyl-tap|$REPO_DIR|g`
- Line 101: service template filename:
  - `"$REPO_DIR/etc/vinyl-web.service"` → `"$REPO_DIR/etc/vinyltap.service"`
- Line 102: installed service name:
  - `sudo tee /etc/systemd/system/vinyl-web.service` → `sudo tee /etc/systemd/system/vinyltap.service`
- Line 105: `systemctl enable vinyl-web` → `systemctl enable vinyltap`
- Line 106: `systemctl restart vinyl-web` → `systemctl restart vinyltap`
- Line 110: sudoers entry service name:
  - `NOPASSWD: /bin/systemctl restart vinyl-web` → `NOPASSWD: /bin/systemctl restart vinyltap`
- Line 111: sudoers file path:
  - `/etc/sudoers.d/vinyl-emulator-update` → `/etc/sudoers.d/vinyltap-update`
- Line 115: obsolete sudoers removal:
  - `/etc/sudoers.d/vinyl-emulator` → `/etc/sudoers.d/vinyl-emulator-update`
  (removes the old name that was just renamed above)

### `scripts/dev-setup.sh`

**Note**: This script adds `vinyl-mac.local` to `/etc/hosts` and the macOS
Keychain. After the rename, the old entries must be cleaned up manually before
re-running (see Part 10).

Changes:
- Line 2: comment: `vinyl-emulator` → `vinyl-tap`
- Lines 8-10: cert paths and `HOSTNAME` variable:
  - `vinyl-mac.local` → `vinyltap-dev.local`
- Line 12: banner echo: `Vinyl Emulator` → `Vinyl Tap`
- Line 71: dev key display label:
  - `vinyl-emulator-dev-key` → `vinyl-tap-dev-key`
  (display text only — the actual Sonos credential name is unchanged)

### `scripts/dev-service.sh`

Changes:
- Line 2: comment: `vinyl-emulator` → `vinyl-tap`
- Lines 9-10: cert file paths:
  - `vinyl-mac.local.crt` → `vinyltap-dev.local.crt`
  - `vinyl-mac.local.key` → `vinyltap-dev.local.key`
- Line 39: startup echo:
  - `vinyl-emulator on https://vinyl-mac.local` → `vinyl-tap on https://vinyltap-dev.local`
- Line 81: status echo:
  - `https://vinyl-mac.local` → `https://vinyltap-dev.local`

### `scripts/install.sh`

Changes:
- Line 2: comment: `Vinyl Emulator` → `Vinyl Tap`
- Line 5: raw.githubusercontent.com URL in comment:
  - `vinyl-emulator` → `vinyl-tap`
- Line 12: `REPO` variable:
  - `"markwmccall/vinyl-emulator"` → `"markwmccall/vinyl-tap"`
- Line 13: `INSTALL_DIR` variable:
  - `"${HOME}/vinyl-emulator"` → `"${HOME}/vinyl-tap"`
- Line 16: installer banner echo: `Vinyl Emulator Installer` → `Vinyl Tap Installer`

### `scripts/service.sh`
- Service name (6 occurrences): `vinyl-web` → `vinyltap`
  - Line 2: script comment `vinyl-web service`
  - Lines 7, 11, 15, 19: `systemctl start/stop/restart/status vinyl-web`
  - Line 23: `journalctl -u vinyl-web`

### `scripts/release.sh`
- Repo reference: `vinyl-emulator` → `vinyl-tap`

---

## Part 5: Config and Asset Changes

### `etc/vinyl-web.service` → rename to `etc/vinyltap.service`

1. Create `etc/vinyltap.service` (delete `etc/vinyl-web.service`)
2. Update contents:
   - Line 2: `Description=Vinyl Emulator Web UI` → `Description=Vinyl Tap Web UI`
   - Lines 7-8: path template `/home/pi/vinyl-emulator` → `/home/pi/vinyl-tap`
     (these are substituted by `setup.sh`'s `sed` at install time — the template
     value and the `sed` pattern in `setup.sh` line 100 must match)

### `static/manifest.json`
- PWA display name: `Vinyl Emulator` → `Vinyl Tap`

---

## Part 6: CI/CD Changes

### `.github/workflows/release.yml`
- Release title/name: `Vinyl Emulator` → `Vinyl Tap`

### `.github/workflows/tests.yml`
- No changes needed — confirmed clean.

---

## Part 7: Documentation Changes

### `CLAUDE.md`
- Heading: `Vinyl Emulator` → `Vinyl Tap`

### `README.md`
- All occurrences: `vinyl-emulator` → `vinyl-tap`, `Vinyl Emulator` → `Vinyl Tap`,
  `vinyl-pi` → `vinyltap`, `vinyl-web` → `vinyltap`
- **Exception**: Lines 9 and 168 reference "Sonos/Spotify Vinyl Emulator" — this is
  attribution to Mark Hank's external project. Do NOT change those lines.

### `docs/DEVELOPMENT.md`
- GitHub repo URLs: `markwmccall/vinyl-emulator` → `markwmccall/vinyl-tap`
- Dev Mac hostname: `vinyl-mac` → `vinyltap-dev`
- Service name: `vinyl-web` → `vinyltap`

### `docs/plans/apple-music-token-onboarding.md`
- Project name references: `vinyl emulator` → `Vinyl Tap`

---

## Part 8: Test Changes

### `tests/test_app.py`
- `vinyl-pi` hostname references → `vinyltap`
- `vinyl-web` service name references → `vinyltap`

### `tests/test_core_nfc_interface.py`
- `vinyl-pi` hostname references → `vinyltap`

### `tests/test_sonos_api.py`
- `vinyl-mac` dev hostname references → `vinyltap-dev`

---

## Part 9: Pi Hostname Change (on the Pi, after deploy)

The Pi's hostname is read dynamically at service install time, so the hostname
change must happen on the Pi itself. Do this over SSH after deploying the
updated code.

```bash
# SSH into Pi (still accessible at vinyl-pi.local until rebooted)
ssh pi@vinyl-pi.local

# Change hostname
sudo hostnamectl set-hostname vinyltap
sudo sed -i 's/vinyl-pi/vinyltap/g' /etc/hosts

# Stop and remove old service
sudo systemctl stop vinyl-web
sudo systemctl disable vinyl-web
sudo rm /etc/systemd/system/vinyl-web.service
sudo systemctl daemon-reload

# Update git remote (repo has moved) and pull
cd ~/vinyl-emulator
git remote set-url origin https://github.com/markwmccall/vinyl-tap.git
git pull

# Run setup to install new service (vinyltap) with new hostname cert
./scripts/setup.sh

# Reboot to apply hostname change
sudo reboot
```

After reboot, Pi is accessible at `vinyltap.local`.

---

## Part 10: Mac Dev Environment Update (manual, one-time)

### Step 10.1 — Clean up old dev hostname artifacts

```bash
# Remove old cert from macOS Keychain
sudo security delete-certificate -c "vinyl-mac.local" \
  /Library/Keychains/System.keychain 2>/dev/null || true

# Remove old cert files
rm -f certs/vinyl-mac.local.crt certs/vinyl-mac.local.key

# Remove old /etc/hosts entry
sudo sed -i '' '/vinyl-mac.local/d' /etc/hosts
```

### Step 10.2 — Run dev-setup to create new artifacts

```bash
./scripts/dev-setup.sh
```

This generates a new `vinyltap-dev.local` cert, adds it to the Keychain, and
adds `vinyltap-dev.local` to `/etc/hosts`.

### Step 10.3 — Update Mac hostname (for mDNS/Bonjour)

```bash
sudo scutil --set LocalHostName vinyltap-dev
sudo scutil --set HostName vinyltap-dev
sudo scutil --set ComputerName vinyltap-dev
```

Or via **System Settings → General → Sharing → Local hostname: `vinyltap-dev`**.

---

## Verification Checkpoints

### After each individual file change
- Grep the modified file for any remaining old names before moving on:
  ```bash
  grep -E "vinyl-emulator|vinyl_emulator|Vinyl Emulator|vinyl-pi|vinyl-web|vinyl-mac" <file>
  ```

### After Part 2 (Code changes — Python files)
- Run the full test suite: `.venv/bin/python -m pytest tests/ -v`
- Python changes are highest-risk; tests catch anything broken by the renames.

### After Part 3 (Template changes)
- Run the full test suite again — some tests assert on rendered HTML content.

### After Part 4 (Script changes)
- Grep each modified script for old names (scripts are not covered by pytest).

### After Part 5 (Service file rename)
- Confirm `etc/vinyltap.service` exists with correct contents.
- Confirm `etc/vinyl-web.service` is gone.

### After Parts 6–8 (CI/CD, docs, test changes)
- Run the full test suite one final time.

### Before opening the PR (final gate)
- Full grep scan across all file types:
  ```bash
  grep -r "vinyl-emulator\|vinyl_emulator\|Vinyl Emulator\|vinyl-pi\|vinyl-web\|vinyl-mac" \
    --include="*.py" --include="*.html" --include="*.sh" --include="*.md" \
    --include="*.json" --include="*.yml" --include="*.service" .
  ```
- Smoke test the dev server: confirm browser title reads "Vinyl Tap".

### After Part 9 (Pi hostname change, post-deploy)
- Confirm `vinyltap.local` resolves and the web UI loads.

### After Part 10 (Mac dev environment update)
- Confirm `vinyltap-dev.local` resolves and the dev server starts cleanly.
- Then close issue #17.

---

## Order of Operations

1. Create branch `rename-to-vinyl-tap`
2. Make all code/template/script/doc changes (Parts 2–8), verifying after each part
3. Run final test suite + full grep scan — must be clean
4. Smoke test dev server — title shows "Vinyl Tap"
5. Open PR → merge to main
6. Rename GitHub repo: `gh repo rename vinyl-tap --repo markwmccall/vinyl-emulator`
7. Update local git remote
8. Deploy to Pi + run Part 9 (Pi hostname change) → verify `vinyltap.local`
9. Run Part 10 (Mac dev environment update) → verify `vinyltap-dev.local`
10. Close issue #17
