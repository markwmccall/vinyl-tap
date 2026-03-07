# Development Guide

## Prerequisites

- Python 3.11+
- Git

## Setup

```bash
git clone https://github.com/markwmccall/vinyl-emulator.git
cd vinyl-emulator
pip3 install -r requirements-dev.txt
cp config.json.example config.json
```

Edit `config.json` and set `nfc_mode` to `mock`. In mock mode, no NFC hardware is needed — the web UI and Sonos playback work normally, and you can trigger playback directly from the browser using Play Now.

## Running locally

```bash
python3 app.py
```

Opens at `http://localhost:5000`. To expose on the network:

```bash
python3 app.py --host 0.0.0.0
```

> The web UI has no authentication — only expose it on a trusted network.

## Tests

```bash
python -m pytest tests/ -v
```

All tests must pass before committing.

## Project structure

```
app.py              Flask web app + NFC background thread
player.py           CLI tool: --simulate (play without a card), --read (read one tag)
apple_music.py      iTunes Search API: search albums/songs, fetch tracks
sonos_controller.py Sonos SOAP/UPnP: queue and play tracks via SoCo
nfc_interface.py    NFC abstraction: MockNFC (stdin), PN532NFC (Pi)
updater.py          Standalone update script (launched detached by app.py)
setup.sh            One-shot Pi setup script
install.sh          One-curl fresh install from latest GitHub release
etc/                systemd service file
config.json         Runtime config (not committed)
templates/          Jinja2 HTML templates
static/             CSS and assets
tests/              pytest test suite
docs/               Architecture notes, research, backlog
```

## Configuration

`config.json` keys:

| Key | Description |
|-----|-------------|
| `speaker_ip` | Sonos speaker IP |
| `sn` | Apple Music service number (assigned by Sonos) |
| `nfc_mode` | `mock` for local dev, `pn532` on Raspberry Pi |
| `auto_update` | `true` to enable daily automatic updates |

## Tag format

| Tag string | What plays |
|------------|-----------|
| `apple:1440903625` | Full album (collection ID from iTunes) |
| `apple:track:1440904001` | Single song (track ID from iTunes) |

Tags are written as NDEF text records. NTAG213 cards (144 bytes) are more than large enough.

## Service management (on Pi)

```bash
sudo systemctl status vinyl-web   # check if running
sudo systemctl restart vinyl-web  # restart
sudo journalctl -u vinyl-web -f   # follow logs
```

## Creating a release

1. Update the `VERSION` file with the new version (e.g. `1.0.0`)
2. Commit and push
3. Push a matching tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

GitHub Actions runs the tests, verifies the tag matches `VERSION`, and creates the GitHub Release automatically.
