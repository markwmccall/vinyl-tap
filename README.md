# Vinyl Emulator

<img src="static/logo.svg" width="80" alt="Vinyl Emulator logo">

[![Tests](https://github.com/markwmccall/vinyl-emulator/actions/workflows/tests.yml/badge.svg)](https://github.com/markwmccall/vinyl-emulator/actions/workflows/tests.yml)

Tap an NFC card → an album or song plays on your Sonos speaker.

Inspired by [Mark Hank's Sonos/Spotify Vinyl Emulator](https://www.hackster.io/mark-hank/sonos-spotify-vinyl-emulator-3be63d), this project adapts the concept for **Apple Music** and adds a full web UI for searching, writing, and verifying tags — no terminal required after initial setup.

---

## How it works

Each physical NFC card stores a reference to an album or song. When a card is tapped on the reader, the Raspberry Pi reads it, looks up the tracks via the iTunes API, and queues them on your Sonos speaker.

A web app running on the Pi lets you:
- Search Apple Music for albums or songs
- Write a tag to any NFC card
- Play directly to Sonos from the browser
- Verify what's written on any card

---

## Hardware

| Item |
|------|
| **Raspberry Pi Zero 2 W** (with headers pre-soldered) |
| **Waveshare PN532 NFC HAT** |
| **microSD card** (16 GB+, Class 10) |
| **Raspberry Pi power supply** (5V/2.5A USB-C) |
| **NTAG213 NFC cards or stickers** (25–50 pack) |

> **Tip:** The Pi Zero 2 W often ships without a GPIO header. Order the version with headers pre-soldered, or budget time to solder a 2×20 pin header yourself.

---

## Setup

### 1. Flash the SD card

Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Select **Raspberry Pi OS Lite (64-bit)**. Before writing, open the settings and configure:

- Hostname: anything you like (e.g. `vinyl-pi`) — this becomes `hostname.local` on your network
- Enable SSH
- Set a username and password
- Configure your WiFi network

### 2. Assemble the hardware

Attach the PN532 NFC HAT to the Pi's 40-pin GPIO header. Before powering on, configure the HAT DIP switches for SPI mode as described in the [Waveshare PN532 HAT wiki](https://www.waveshare.com/wiki/PN532_NFC_HAT):

1. **Set the mode jumper caps** — I0 to L, I1 to H.
2. **Connect RSTPDN to D20** using a jumper cap.
3. **Set the DIP switches** as follows:

   | SCK | MISO | MOSI | NSS | SCL | SDA | RX | TX |
   |-----|------|------|-----|-----|-----|----|----|
   | ON  | ON   | ON   | ON  | OFF | OFF | OFF| OFF|

4. **Leave INT0 unconnected.**

> **Note:** The Waveshare HAT routes NSS (chip select) to GPIO4 (D4), not the standard CE0 (GPIO8). This is handled automatically by the software.

Insert the SD card and power on. Wait about 60 seconds, then SSH in:

```bash
ssh your-username@your-hostname.local
```

### 3. Verify the HAT is detected

```bash
ls /dev/spidev*
```

You should see `/dev/spidev0.0`. If nothing appears, check that the HAT is firmly seated and the DIP switches are set to SPI mode.

### 4. Install

```bash
curl -sSL https://raw.githubusercontent.com/markwmccall/vinyl-emulator/main/scripts/install.sh | bash
```

This downloads the latest release and runs setup — installs dependencies, enables SPI, generates an SSL certificate, creates the config, and installs the `vinyl-web` systemd service. It will prompt you to reboot at the end.

> **Note for Pi Zero 2 W users:** The first run compiles `lxml` from source, which can take 10–20 minutes. This is a one-time cost.

### 5. Configure

After rebooting, open `https://your-hostname.local` in your browser. Your browser will show a security warning for the self-signed certificate — click through to accept it (this is expected for a local device). Go to **Settings**, use the **Discover** button to find your Sonos speaker IP, and the **Detect** button to find your `sn` value automatically.

> **Sonos AppLink redirect URI:** When linking music services via Settings → Music Services, use `https://your-hostname.local/sonos/callback` as the redirect URI.

---

## Updating

Open `http://your-hostname.local` in your browser, go to **Settings → Update**, and click **Update Now**. The app will download and install the latest release and restart itself.

---

## Troubleshooting

**`http://your-hostname.local` doesn't load**
- Check the service is running: `sudo systemctl status vinyl-web`
- Check the Pi is on the network: `ping your-hostname.local`
- Try the IP address directly if mDNS isn't resolving

**HAT not detected**
- Confirm the DIP switches on the HAT are set to SPI mode (I0=L, I1=H) — see the [Waveshare PN532 HAT wiki](https://www.waveshare.com/wiki/PN532_NFC_HAT)
- Check the HAT is firmly seated — all 40 pins engaged
- Verify with `ls /dev/spidev*` — you should see `/dev/spidev0.0`
- If `/dev/spidev0.0` is missing, SPI may not be enabled — re-run `scripts/setup.sh` or run `sudo raspi-config` and enable SPI under Interface Options

**Music doesn't play after tapping a card**
- Check `sudo systemctl status vinyl-web` for errors
- Confirm `speaker_ip` and `sn` are set correctly in Settings
- Try Play Now from the web UI to rule out a Sonos configuration issue

**`sn` detection finds nothing**
- You need at least one Apple Music item saved as a Sonos favorite
- Try small values manually: `3` or `5` are common

**Speaker IP keeps changing**
- Handled automatically — the system stores the speaker's room name and rediscovers it if the IP changes

---

## Configuration

Settings are managed through the web UI at `http://your-hostname.local/settings`. The underlying `config.json` file contains:

| Key | Description |
|-----|-------------|
| `speaker_ip` | IP address of your Sonos speaker. Use the **Discover** button to find it. |
| `sn` | Apple Music service number assigned by Sonos. Use the **Detect** button to find it automatically (requires at least one Apple Music favorite saved in the Sonos app). If detection finds nothing, try `3` or `5`. |

---

## Web UI

| Page | Description |
|------|-------------|
| Search | Search albums or songs by name |
| Album / Song | Track listing, Play Now, Write to Tag |
| Verify Tag | Read a card and show what album/song it points to |
| Collection | Browse, sort, and delete written tags |
| Settings | Speaker IP, account number, updates |

---

## iPhone shortcut

Write `http://your-hostname.local` as a URL record on a spare NTAG213 sticker and stick it on the Pi enclosure. Tapping it with an iPhone opens Safari directly to the web UI — no app needed.

---

## Contributing

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## Acknowledgements

Concept adapted from [Sonos / Spotify Vinyl Emulator](https://www.hackster.io/mark-hank/sonos-spotify-vinyl-emulator-3be63d) by Mark Hank.
