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
  nfc_service.py        NFC singleton + background polling loop
  sonos_player.py       Sonos UPnP/SOAP: queue and play tracks via SoCo
  hardware_stats.py     Pi hardware stats (CPU, RAM, disk, throttle)
  config.py             Config load/save helpers
  updater_service.py    Auto-update background thread
providers/
  base.py               MusicProvider ABC
  apple_music.py        Apple Music: iTunes Search API
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
tools/                  Diagnostic scripts and research notes
etc/                    systemd service file
config.json             Runtime config (not committed)
templates/              Jinja2 HTML templates
static/                 CSS and assets
tests/                  pytest test suite
docs/                   Development guide
```

## Architecture

`vinyl-web` is a single systemd service running one Python process. Flask and NFC polling
share the same process — NFC runs as a daemon thread.

**Why one process?** Two processes sharing the PN532 over I2C caused bus contention and
hangs. A single process with a `threading.Lock` eliminates this entirely.

Key patterns in `app.py`:
- `_nfc_lock` — all PN532 hardware access serialised through this lock
- `_nfc_loop()` — daemon thread; debounce state machine prevents re-queuing while card held
- `_nfc_session(config)` — context manager used by web routes; acquires lock with 2s timeout → 503 if busy
- `csrf_protected` decorator — applied to all state-mutating routes
- No `/player/status` or `/player/control` routes; `player.py` is a CLI tool only

## NFC hardware notes

The Waveshare PN532 HAT is configured for **SPI mode** (DIP: I0=L, I1=H). NSS (chip select)
is routed to GPIO4 (D4), not the standard CE0 — this is intentional per Waveshare's schematic.

**BCM2835 I2C clock-stretch fix** (SPI build does not need this, but documented for reference):
- Kernel param is `clk_tout_ms`, **not** `timeout` — getting this wrong silently does nothing
- Applied via `/etc/modprobe.d/i2c-bcm2835.conf`; requires a full power-cycle (not reboot) to take effect

**Adafruit PN532 library quirks:**
- The `irq=` constructor parameter is **ignored** — `_wait_ready()` always polls via I2C status byte regardless
- Waveshare docs suggest connecting INT0→D16 "to avoid clock stretching" — this only applies to Waveshare's own library, not Adafruit's
- `reset=board.D20` (RSTPDN) is used; keep the jumper connected — enables software reset after repeated failures

**Reboot vs power-cycle:** A reboot does NOT clear a hung I2C bus. The 3.3V rail stays
energised and the PN532 holds its state. A full power-off is required (or RSTPDN reset if
the kernel timeout is active).

## Sonos playback reference

**Track URI format:**
```
x-sonos-http:song%3a{track_id}.mp4?sid=204&flags=8232&sn={sn}
```

**DIDL format** (the only format confirmed working — `id="-1"` fails silently):
```xml
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
           xmlns:dc="http://purl.org/dc/elements/1.1/"
           xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
  <item id="10032028song%3a{track_id}" parentID="10032028song%3a{track_id}" restricted="true">
    <dc:title>{title}</dc:title>
    <upnp:class>object.item.audioItem.musicTrack</upnp:class>
    <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{udn}</desc>
  </item>
</DIDL-Lite>
```

**Apple Music UDN format:** `SA_RINCON52231_X_#Svc52231-{oadevid}-Token`
- The OADevID suffix is account-specific; discovered dynamically from `FV:2` Sonos Favorites
- `sn=3` → `f7c0f087`, `sn=5` → `7cd348b3` (examples; always look up dynamically)

## SMAPI token bootstrapping: known gap

Playlist search uses SMAPI with Apple Music credentials (`smapi_token`, `smapi_key`,
`smapi_household_id` in `config.json` under `services.apple`). Once a token is in place
it auto-refreshes indefinitely via `refreshAuthToken`. The gap: **there is no in-app
flow to acquire the initial token.**

Apple Music uses the AppLink auth flow, which requires a registered Sonos partner app.
`getAppLink` returns an encrypted response that only official Sonos partner apps can
decode. `GetSessionId` (the simpler UPnP call) only works for "session auth" type services,
not AppLink services like Apple Music.

### Workaround: capture the token via mitmproxy

This is how the initial token was obtained. It intercepts the Sonos app's SMAPI traffic.

**Requirements:** Mac on the same WiFi as the iPhone running the Sonos app.

```bash
pip install mitmproxy
mitmweb --listen-port 8080 \
  --ignore-hosts "10\.0\.0\.\d+" \
  --ignore-hosts "192\.168\.\d+\.\d+"
```

1. Set your iPhone WiFi proxy to `{mac_ip}:8080`
2. Visit `http://mitm.it` on the iPhone and install the mitmproxy CA certificate
3. Open the Sonos app and browse Apple Music (search something, open a playlist)
4. In mitmweb, filter for requests to `sonos-music.apple.com`
5. In any request header, find the `credentials` SOAP header — it contains:
   - `<token>` → `smapi_token`
   - `<key>` → `smapi_key`
   - `<householdId>` → `smapi_household_id`
6. Paste these values into `config.json` under `services.apple` and restart the service

Once set, tokens refresh automatically. Re-capture is only needed if the token becomes
permanently invalidated (e.g. Apple Music account re-linked in the Sonos app).

### Workaround: copy from a working instance

If you already have a working instance with a valid token (e.g. the dev Mac), copy
`services.apple` from that `config.json` to the new instance. The token and household ID
are tied to the Sonos household + Apple Music account, so they are identical across
instances on the same account.

## Multi-service search: what has been ruled out

| Approach | Why ruled out |
|----------|--------------|
| Apple MusicKit API | Requires $99/year Apple Developer account; doesn't cover other services |
| Extract tokens from speaker via UPnP | Credentials are write-only on S2 — speaker deliberately does not expose them |
| soco AppLink flow | soco is not a registered Sonos partner; Apple Music returns error 999 |
| Local SMAPI service on Pi | Sonos S2 (May 2024) routes SMAPI through its cloud — requires public HTTPS |

See `tools/SONOS_API_RESEARCH.md` for full investigation notes and the working SMAPI
request format used by `tools/smapi_probe.py`.

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
