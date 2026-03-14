# Development Guide

## Prerequisites

- Python 3.11+
- Git

## Setup

```bash
git clone https://github.com/markwmccall/vinyl-emulator.git
cd vinyl-emulator
./scripts/dev-setup.sh
```

This creates a virtualenv, installs dependencies, and generates SSL certs for `vinyl-mac.local`.

## Running locally

```bash
./scripts/dev-service.sh start   # start (HTTPS on port 443)
./scripts/dev-service.sh stop
./scripts/dev-service.sh restart
./scripts/dev-service.sh logs
```

Opens at `https://vinyl-mac.local`. In dev mode (`INVOCATION_ID` not set), production-only features (Updates, Restart App, Reboot) show a hint instead of controls.

> The web UI has no authentication — only expose it on a trusted network.

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

All tests must pass before committing.

## Project structure

```
app.py                  Flask web app + NFC background thread
core/
  nfc_interface.py      NFC abstraction: MockNFC (stdin), PN532NFC (hardware)
  sonos_player.py       Sonos UPnP/SOAP: queue and play tracks via SoCo
  updater.py            Standalone update script (launched detached by app.py)
providers/
  apple_music.py        Apple Music: iTunes Search API + SMAPI authenticated search
  smapi_client.py       Sonos SMAPI SOAP client (shared across music providers)
  sonos_api.py          Sonos Control API OAuth client
data/
  tags.json             NFC tag history (runtime, not committed)
scripts/
  dev-setup.sh          One-time Mac dev environment setup
  dev-service.sh        Mac dev server manager (start/stop/restart/logs)
  setup.sh              One-shot device setup script
  install.sh            One-curl fresh install from latest GitHub release
  release.sh            Cut a release (bumps VERSION, tags, pushes)
  service.sh            Manage vinyl-web systemd service on device
etc/                    systemd service file
config.json             Runtime config (not committed)
templates/              Jinja2 HTML templates
static/                 CSS and assets
tests/                  pytest test suite
docs/                   Architecture notes, research, backlog
poc/                    Proof-of-concept scripts (not used at runtime)
```

## Configuration

`config.json` keys:

| Key | Description |
|-----|-------------|
| `speaker_ip` | Sonos speaker IP |
| `sn` | Apple Music service number (assigned by Sonos) |
| `nfc_mode` | `mock` for local dev, `pn532` with hardware |
| `auto_update` | `true` to enable hourly automatic updates |

## Dev vs production

The app detects production by checking for `INVOCATION_ID` in the environment (set automatically by systemd). Features that only make sense in production (Updates, Auto-Update, Restart App, Reboot) are hidden in dev with a hint message.

## Tag format

| Tag string | What plays |
|------------|-----------|
| `apple:1440903625` | Full album (collection ID from iTunes) |
| `apple:track:1440904001` | Single song (track ID from iTunes) |
| `apple:playlist:p.XYZ` | Personal playlist |

Tags are written as NDEF text records. NTAG213 cards (144 bytes) are more than large enough.

## Service management (on device)

```bash
sudo systemctl status vinyl-web   # check if running
sudo systemctl restart vinyl-web  # restart
sudo journalctl -u vinyl-web -f   # follow logs
```

## Creating a release

```bash
./scripts/release.sh 1.0.0
```

This updates `VERSION`, commits, pushes, and creates the tag. GitHub Actions then runs tests and publishes the GitHub Release automatically.

## Reference

| Topic | Link |
|-------|------|
| **SoCo** (Sonos Python library) | [github.com/SoCo/SoCo](https://github.com/SoCo/SoCo) · [docs.python-soco.com](https://docs.python-soco.com) |
| **iTunes Search API** | [developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html) |
| **Sonos UPnP / SMAPI** | [developer.sonos.com](https://developer.sonos.com) · [soco.readthedocs.io/en/latest/api/soco.music_services](https://soco.readthedocs.io/en/latest/api/soco.music_services.html) |
| **PN532 NFC HAT** | [Waveshare PN532 HAT wiki](https://www.waveshare.com/wiki/PN532_NFC_HAT) |
| **Adafruit CircuitPython PN532** | [github.com/adafruit/Adafruit_CircuitPython_PN532](https://github.com/adafruit/Adafruit_CircuitPython_PN532) |
| **NDEF / NFC Data Exchange Format** | [ndeflib.readthedocs.io](https://ndeflib.readthedocs.io) |
| **Flask** | [flask.palletsprojects.com](https://flask.palletsprojects.com) |
