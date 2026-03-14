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
.venv/bin/python -m pytest tests/ -v
```

All tests must pass before committing.

## Project structure

```
app.py              Flask web app + NFC background thread
player.py           CLI tool: --simulate (play without a card), --read (read one tag)
apple_music.py      iTunes Search API: search albums/songs, fetch tracks
sonos_player.py     Sonos SOAP/UPnP: queue and play tracks via SoCo
nfc_interface.py    NFC abstraction: MockNFC (stdin), PN532NFC (Pi)
updater.py          Standalone update script (launched detached by app.py)
scripts/setup.sh    One-shot Pi setup script
scripts/install.sh  One-curl fresh install from latest GitHub release
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
| **Raspberry Pi I2C** | [raspberrypi.com/documentation/computers/raspberry-pi.html](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#i2c) |
