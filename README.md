# Vinyl Emulator

<img src="static/logo.svg" width="80" alt="Vinyl Emulator logo">

[![Tests](https://github.com/markwmccall/vinyl-emulator/actions/workflows/tests.yml/badge.svg)](https://github.com/markwmccall/vinyl-emulator/actions/workflows/tests.yml)

> **Work in progress.** The software is functional and tested. The web UI, Sonos playback, NFC card taps, and tag writing are all working.

Tap an NFC card → an album or song plays on your Sonos speaker.

Inspired by [Mark Hank's Sonos/Spotify Vinyl Emulator](https://www.hackster.io/mark-hank/sonos-spotify-vinyl-emulator-3be63d), this project adapts the concept for **Apple Music** and adds a full web UI for searching, writing, and verifying tags - no terminal required after initial setup.

---

## How it works

Each physical NFC card stores a short tag string (`apple:1440903625` for an album, `apple:track:1440904001` for a single song). When a card is tapped on the reader, the Raspberry Pi reads the tag, looks up the tracks via the iTunes API, and queues them on your Sonos speaker.

A Flask web app running on the same Pi lets you:
- Search Apple Music for albums or songs
- Write a tag to any NFC card
- Play directly to Sonos from the browser
- Verify what's written on any card

---

## Hardware

| Item | Notes | Approx. Price |
|------|-------|---------------|
| **Raspberry Pi Zero 2 W** (with headers pre-soldered) | Compact, WiFi built-in. Pi 3B+ also works. | $15 |
| **Waveshare PN532 NFC HAT** | Plugs directly onto the Pi GPIO - no wiring needed. Search "Waveshare PN532 NFC HAT Raspberry Pi". | $18–22 |
| **microSD card** (16 GB+, Class 10) | For Raspberry Pi OS Lite (headless) | $8–12 |
| **Raspberry Pi power supply** (5V/2.5A USB-C) | Official Pi supply recommended | $8–12 |
| **NTAG213 NFC cards or stickers** (25–50 pack) | One per album/song. 144-byte capacity is plenty. | $10–15 |

**Total: ~$60–75**

> **Tip:** The Pi Zero 2 W often ships without a GPIO header. Order the version with headers pre-soldered, or budget time to solder a 2×20 pin header yourself.

---

## Raspberry Pi setup

### 1. Flash the SD card

Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Select **Raspberry Pi OS Lite (64-bit)**. Before writing, open the settings (gear icon) and configure:

- Hostname: `vinyl-pi`
- Enable SSH
- Set a username and password
- Configure your WiFi network

### 2. Assemble the hardware

Attach the PN532 NFC HAT to the Pi's 40-pin GPIO header. Before powering on, set the HAT's interface switches to **I2C** - refer to the [Waveshare PN532 HAT wiki](https://www.waveshare.com/wiki/PN532_NFC_HAT) for the exact switch positions.

Insert the SD card and power on. Wait about 60 seconds, then SSH in:

```bash
ssh pi@vinyl-pi.local
```

### 3. Verify the HAT is detected

Before running setup, confirm the PN532 HAT is visible on the I2C bus:

```bash
sudo i2cdetect -y 1
```

You should see `24` appear in the grid at address `0x24`. If nothing appears, check that the HAT is firmly seated on the GPIO pins and the interface switches are set to I2C.

### 4. Clone and run setup

```bash
git clone https://github.com/markwmccall/vinyl-emulator.git
cd vinyl-emulator
chmod +x setup.sh && ./setup.sh
```

`setup.sh` does everything in one shot:
- Installs system packages (`python3-pip`, `python3-dev`, `libxml2-dev`, `libxslt-dev`)
- Enables the I2C interface (required for the PN532 HAT)
- Creates a Python venv and installs all dependencies including the Adafruit PN532 library
- Creates `config.json` with `nfc_mode=pn532`
- Installs and enables the `vinyl-web` systemd service

It will prompt you to reboot at the end - I2C requires a reboot to take effect.

> **Note for Pi Zero 2 W users:** The first run compiles `lxml` (a Sonos dependency) from source, which can take 10–20 minutes on the Zero's ARM CPU. This is a one-time cost - subsequent runs are fast.

### 5. Configure

After rebooting, open `http://vinyl-pi.local:5000` in your browser and go to **Settings**. Use the **Discover** button to find your Sonos speaker IP, and the **Detect** button to find your `sn` value automatically. See [Configuration](#configuration) for details on `sn`.

---

## Updating

To update to the latest code on the Pi:

```bash
cd ~/vinyl-emulator
git pull
./setup.sh
```

`setup.sh` is safe to re-run - it skips `config.json` if it already exists and restarts services when done.

---

## Troubleshooting

**`http://vinyl-pi.local:5000` doesn't load**
- Check the service is running: `sudo systemctl status vinyl-web`
- Check the Pi is on the network: `ping vinyl-pi.local`
- Try the IP address directly if mDNS isn't resolving

**HAT not detected by the test script**
- Confirm the interface switches on the HAT are set to I2C (not SPI or UART)
- Check the HAT is firmly seated - all 40 pins engaged
- I2C must be enabled: `sudo raspi-config` → Interface Options → I2C
- Verify with `sudo i2cdetect -y 1` - PN532 should appear at address `0x24`

**Music doesn't play after tapping a card**
- Check `sudo systemctl status vinyl-web` for errors
- Confirm `speaker_ip` and `sn` are set correctly in Settings
- Try Play Now from the web UI to rule out a Sonos configuration issue

**`sn` detection finds nothing**
- You need at least one Apple Music item saved as a Sonos favorite
- Try small values manually: `3` or `5` are common
- Save the value and test with Play Now

**Speaker IP keeps changing**
- This is handled automatically - the system stores your speaker's room name and rediscovers it if the IP changes after a router reboot

---

## Development setup

```bash
pip3 install -r requirements-dev.txt
cp config.json.example config.json   # set nfc_mode: "mock"
python3 app.py                        # binds to 127.0.0.1:5000
```

---

## Configuration

`config.json` is created by `setup.sh` on the Pi, or manually from `config.json.example` for local development. It is never committed to git.

| Key | Description |
|-----|-------------|
| `speaker_ip` | IP address of your Sonos speaker. Use the Discover button in Settings to find it. |
| `sn` | Apple Music service number assigned by Sonos - identifies which Apple Music account is linked. Use the **Detect** button in Settings to find it automatically (requires at least one Apple Music favorite saved in the Sonos app). If detection finds nothing, try small numbers like `3` or `5`. To confirm the value is correct, save and try playing an album or track. |
| `nfc_mode` | `mock` for development (reads tag strings from stdin), `pn532` for Raspberry Pi with the Waveshare HAT. |

---

## Running

**Web UI:**
```bash
python3 app.py                        # binds to 127.0.0.1:5000
python3 app.py --host 0.0.0.0         # accessible from other devices on the network
```

Open `http://localhost:5000` (or `http://vinyl-pi.local:5000` from your phone).

> **Security note:** The web UI has no authentication. It is intended for use on a trusted home network only - do not expose port 5000 to the internet.

**Player CLI (testing/debugging):**
```bash
python3 player.py --simulate apple:1440903625  # play once without a card
python3 player.py --read                       # read one tag, print its content, exit
```

On the Pi, NFC polling runs automatically inside the `vinyl-web` process. To manage the service:
```bash
sudo systemctl status vinyl-web   # check if running
sudo systemctl restart vinyl-web  # restart
sudo journalctl -u vinyl-web -f   # follow logs
```

---

## Web UI pages

| Page | URL | Description |
|------|-----|-------------|
| Search | `/` | Search albums or songs by name |
| Album | `/album/{id}` | Track listing, Play Now, Write to Tag |
| Song | `/track/{id}` | Single track, Play Now, Write to Tag |
| Verify Tag | `/verify` | Read a card and show what album/song it points to |
| Collection | `/collection` | Browse, sort, and delete written tags |
| Settings | `/settings` | Speaker IP, account number, NFC mode |

---

## Tag format

| Tag string | What plays |
|------------|-----------|
| `apple:1440903625` | Full album (collection ID from iTunes) |
| `apple:track:1440904001` | Single song (track ID from iTunes) |

Tags are written as NDEF text records. NTAG213 cards (144 bytes) are more than large enough.

---

## iPhone NFC shortcut

Write `http://vinyl-pi.local:5000` as a URL record on a spare NTAG213 sticker and stick it on the Pi enclosure. Tapping it with an iPhone opens Safari directly to the web UI - no app needed.

---

## Project structure

```
app.py              Flask web app (search, play, write-tag, verify)
player.py           CLI tool: --simulate (play without a card), --read (read one tag)
apple_music.py      iTunes Search API: search albums/songs, fetch tracks
sonos_controller.py Sonos SOAP/UPnP: queue and play tracks via SoCo
nfc_interface.py    NFC abstraction: MockNFC (stdin), PN532NFC (Pi)
setup.sh            One-shot Pi setup script
etc/                systemd service file templates
config.json         Runtime config (speaker IP, sn, NFC mode) - not committed
templates/          Jinja2 HTML templates
static/             CSS
tests/              pytest test suite
docs/PLAN.md        Architecture notes and Sonos SMAPI findings
docs/TODO.md        Backlog
```

---

## Tests

```bash
python -m pytest tests/ -v
```

---

## Acknowledgements

Concept adapted from [Sonos / Spotify Vinyl Emulator](https://www.hackster.io/mark-hank/sonos-spotify-vinyl-emulator-3be63d) by Mark Hank.
