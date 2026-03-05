# Apple Music Vinyl Emulator - Implementation Plan

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Core playback (apple_music + sonos_controller) | ✅ Done |
| 2 | NFC interface + player.py loop | ✅ Done |
| 3 | Flask web UI (search, album, track, verify, settings) | ✅ Done |
| 4 | Hardware procurement + Pi OS setup | ✅ Done |
| 5 | Deploy to Pi + implement PN532NFC | ⏳ Waiting on NFC HAT |
| 6 | systemd production services | ✅ Done |

**Current test count: 139 tests, all passing.**

---

## Context
Build a physical vinyl emulator: placing an NFC card on a reader triggers that album or song to play on Sonos via Apple Music. Hardware is a Raspberry Pi Zero 2 W + Waveshare PN532 NFC HAT + NTAG213 tags. All coding and testing happens on Mac first using emulated NFC - hardware is only introduced at Phase 4.

## Development Approach: Test Driven Development (TDD)
Write a failing test first, implement the minimum code to make it pass, repeat. This applies to all core modules. The web UI uses Flask's test client for route testing.

Test infrastructure:
- Framework: `pytest`
- HTTP mocking: `unittest.mock.patch` on `urllib.request.urlopen`
- SoCo mocking: `unittest.mock.patch` on `soco.SoCo`
- Shared fixtures: `tests/conftest.py`
- File system tests: monkeypatch `app.CONFIG_PATH` to a temp file

---

## Confirmed Technical Facts (from prototype testing)
- `sn=3` - account-specific Sonos/Apple Music service number, confirmed stable
- Album URI format (`x-rincon-cpcontainer`) fails with UPnP Error 714 - confirmed dead end, not a config issue
- Working track URI: `x-sonos-http:song%3a{track_id}.mp4?sid=204&flags=8232&sn={sn}` (purchased/library tracks)
  - `flags=8232` for purchased/library tracks; `flags=73768` for streaming-only tracks
  - `%3a` is percent-encoded `:` - must be encoded in the URI
  - Sonos replaces this URI with `x-sonosapi-hls-static:song%3a{id}?...` in the stored queue (HLS delivery)
- Album playback requires queuing individual tracks - confirmed by inspecting Sonos queue during native app playback
- iTunes Search API provides usable track IDs (no auth required)
- Full album tracklist: `https://itunes.apple.com/lookup?id={album_id}&entity=song`
  - Returns album row first (`wrapperType: "collection"`) then tracks (`wrapperType: "track"`)
  - Must filter to `wrapperType == "track"` before sorting by `trackNumber`
- Album search: `https://itunes.apple.com/search?term={query}&entity=album`
- Song search: `https://itunes.apple.com/search?term={query}&entity=song`
- Track lookup: `https://itunes.apple.com/lookup?id={track_id}` (returns single track)
- iTunes API key field names: `trackId`, `collectionId`, `artistName`, `trackName`, `collectionName`, `artworkUrl100`, `trackNumber`, `wrapperType`
- Artwork URL: `artworkUrl100` is 100×100px - replace `100x100bb` with `600x600bb` in URL for higher resolution; applied internally, so all returned dicts already have high-res URLs
- Behavior on new tag scan: replace immediately (stop current, start new)
- Speaker: global default set in config (single speaker, no per-tag)
- Mac environment: Python 3.9, use `python3` / `pip3`

### Apple Music / Sonos SMAPI Integration (hard-won findings)
- Apple Music service type on Sonos: `52231` (= 204 × 256 + 7), `sid=204`
- Apple Music uses AppLink authentication - token stored encrypted on the Sonos speaker
- **Apple Music UDN format:** `SA_RINCON52231_X_#Svc52231-{token}-Token`
  - Found by browsing Sonos favorites (`FV:2`) and inspecting `<r:resMD>` fields
  - `_lookup_apple_music_udn(speaker, sn)` matches `sn={sn}` in the `<res>` URI to extract the right UDN
- **Sonos SMAPI lookup trigger:** Sonos calls `GetMediaMetadata` on Apple Music SMAPI when a track is added via `AddURIToQueue`. It uses the DIDL `item id` to construct the SMAPI request - **`id="-1"` causes this lookup to fail silently**, storing only `object.item` / `application/octet-stream`
- **Correct item ID format:** `10032028song%3a{track_id}` - Sonos content-browser ID for Apple Music library/purchased songs
  - `10032028` = Apple Music musicTrack prefix
  - `10092064` = Apple Music audioBroadcast (radio)
  - `1006206c` = Apple Music playlist container
- When SMAPI lookup succeeds, Sonos stores full metadata (title, artist, album, `musicTrack` class) in the queue - no need to include creator/album in submitted DIDL
- `/status/accounts` endpoint on Sonos returns encrypted Apple Music account data - not useful for extracting UDN

---

## Project Structure
```
vinyl-emulator/
├── config.json           # sn value, default speaker IP, nfc_mode - NOT committed to git
├── config.json.example   # Safe template, committed to git
├── .gitignore            # Excludes config.json, __pycache__, *.pyc
├── README.md
├── apple_music.py        # iTunes API: search_albums, search_songs, get_album_tracks, get_track
├── sonos_controller.py   # SoCo queue management: get_speakers, play_album
├── nfc_interface.py      # Abstract NFC layer (mock or real) + parse_tag_data
├── player.py             # Main loop - uses nfc_interface; --simulate, --read flags
├── app.py                # Flask web UI
├── templates/
│   ├── base.html         # Shared layout (nav: Search, Collection, Verify Tag, Settings) + Now Playing bar
│   ├── index.html        # Album/song search with tab toggle + clear button
│   ├── album.html        # Album detail + track listing (linked) + write/play buttons
│   ├── track.html        # Single track detail + write/play buttons + album link
│   ├── verify.html       # Tag verify page (mock: text input; pn532: tap button)
│   ├── collection.html   # Written tag collection with sort + delete + clear all
│   └── settings.html     # Speaker IP + sn + NFC mode + player control + URL sticker
├── static/
│   └── style.css
├── tests/
│   ├── conftest.py       # Shared fixtures: client, temp_config, mock_speaker
│   ├── test_apple_music.py
│   ├── test_sonos_controller.py
│   ├── test_nfc_interface.py
│   ├── test_player.py
│   └── test_app.py
├── etc/
│   ├── vinyl-player.service  # systemd service template (player daemon)
│   └── vinyl-web.service     # systemd service template (web UI)
├── setup.sh              # One-shot Pi setup script (run once after clone)
├── docs/
│   ├── PLAN.md
│   └── TODO.md
└── requirements.txt
```

## .gitignore (minimum)
```
config.json
tags.json
__pycache__/
*.pyc
*.pyo
.env
```

## NFC Tag Format

| Tag string | What plays |
|---|---|
| `apple:{collection_id}` | Full album (all tracks queued in order) |
| `apple:track:{track_id}` | Single song |

Examples: `apple:1440903625` (album), `apple:track:1440904001` (song)
- NTAG213 has 144 bytes - plenty for this
- Human-readable, easy to debug
- Backward compatible: old album tags still work

---

## NFC Hardware Contention (Pi)
On the Pi, `player.py` and `app.py` both need the PN532 HAT. Two processes cannot share one SPI device simultaneously.

**Solution:** Stop `player.py` before writing tags, restart it after.
- Phase 5 (before systemd services exist): `pkill -f player.py`
- Phase 6 (after systemd services exist): `sudo systemctl stop vinyl-player`

The web UI settings page displays this reminder when in `pn532` mode.

---

## Module Design (current implementation)

### apple_music.py
- `search_albums(query)` → `[{id, name, artist, artwork_url}, ...]`
- `search_songs(query)` → `[{id, name, artist, album, artwork_url}, ...]`
- `get_album_tracks(album_id)` → filter `wrapperType == "track"`, sort by `trackNumber` → `[{track_id, name, track_number, artist, album, artwork_url}, ...]`
- `get_track(track_id)` → single-element list: `[{track_id, name, track_number, artist, album, artwork_url}]`
- `build_track_uri(track_id, sn)` → `x-sonos-http:song%3a{track_id}.mp4?sid=204&flags=8232&sn={sn}`
- `build_track_metadata(track)` → DIDL-Lite XML string
- `upgrade_artwork_url(url)` → replaces `100x100bb` with `600x600bb` - called internally

---

### sonos_controller.py
- `get_speakers()` → `[{name, ip}, ...]` via `soco.discover()` (UDP multicast, 5–10 seconds)
- `play_album(speaker_ip, track_dicts, sn)` → clears queue, adds all tracks with URI+metadata, plays from position 0

---

### nfc_interface.py

**`parse_tag_data(tag_string)`** → returns `{"type": "album"|"track", "id": "<id_string>"}`.
Raises `ValueError` with a clear message if format is unrecognised.

- `apple:{id}` → `{"type": "album", "id": "{id}"}`
- `apple:track:{id}` → `{"type": "track", "id": "{id}"}`

**MockNFC** (no hardware):
- `read_tag()` → blocks on `input()` waiting for a typed tag string
- `write_tag(data)` → prints what would be written, returns `True`
- `write_url_tag(url)` → prints what URL would be written, returns `True`

**PN532NFC** (Pi with real hardware):
- `read_tag()` → polls Adafruit PN532 library for NDEF tag (Phase 5)
- `write_tag(data)` → writes NDEF text record to physical tag (Phase 5)
- `write_url_tag(url)` → writes URL NDEF record to physical tag (Phase 5)
- All raise `NotImplementedError` until Phase 5

---

### player.py

CLI flags:
- `--simulate <tag_string>` - parse tag, fetch tracks, play, exit
- `--read` - read one tag from NFC, print it, exit (useful for verifying physical cards)
- (no flag) - run the main NFC loop forever

Tag dispatch:
```python
tag = parse_tag_data(tag_string)   # {"type": "album"|"track", "id": "..."}
if tag["type"] == "track":
    tracks = get_track(tag["id"])
else:
    tracks = get_album_tracks(tag["id"])
play_album(speaker_ip, tracks, sn)
```

---

### app.py (Flask)

**Config path:** `CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")`
Tests monkeypatch `app.CONFIG_PATH` to a temp file via the `temp_config` fixture.

**Routes:**
| Route | Method | Body | Purpose |
|---|---|---|---|
| `/` | GET | - | Search page (Albums / Songs tab toggle) |
| `/search` | GET `?q=&type=` | - | JSON results; `type=song` → songs, default → albums |
| `/album/<id>` | GET | - | Album detail + track listing (each track linked to `/track/<id>`) |
| `/track/<id>` | GET | - | Single track detail |
| `/play` | POST | `{"album_id": "..."}` or `{"track_id": "..."}` | Queues and plays on Sonos |
| `/write-tag` | POST | `{"album_id": "..."}` or `{"track_id": "..."}` | Writes tag via NFC |
| `/read-tag` | GET `?tag=` | - | Reads NFC tag; `?tag=` param bypasses NFC (mock mode) |
| `/verify` | GET | - | Verify Tag page |
| `/settings` | GET | - | Settings form |
| `/settings` | POST | Form: `sn`, `speaker_ip`, `nfc_mode` | Saves to config.json |
| `/speakers` | GET | - | JSON list of Sonos speakers (5–10s, soco.discover) |

**`/read-tag` response shape:**
```json
{
  "tag_string": "apple:1440903625",
  "tag_type": "album",
  "content_id": "1440903625",
  "album": {"name": "Hysteria", "artist": "Def Leppard", "artwork_url": "..."},
  "error": null
}
```

---

## DIDL-Lite Metadata
```xml
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
           xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
           xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
           xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
  <item id="10032028song%3a{track_id}" parentID="10032028song%3a{track_id}" restricted="true">
    <dc:title>{track_name}</dc:title>
    <upnp:class>object.item.audioItem.musicTrack</upnp:class>
    <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{apple_music_udn}</desc>
  </item>
</DIDL-Lite>
```

Key points:
- `id`/`parentID` = `10032028song%3a{track_id}` - tells Sonos how to look up the track via SMAPI
- `desc` must contain the full Apple Music UDN (e.g. `SA_RINCON52231_X_#Svc52231-f7c0f087-Token`), obtained dynamically via `_lookup_apple_music_udn()`
- Do NOT include `dc:creator`, `upnp:album`, or `upnp:albumArtURI` - Sonos populates these from SMAPI
- `id="-1"` does NOT work - SMAPI lookup silently fails, queue stores bare `object.item` with no metadata

---

## Build Order

### Phase 1 - Core Playback ✅
1. `tests/conftest.py` - shared fixtures
2. `apple_music.py` (TDD) - search, lookup, URI building, metadata
3. `sonos_controller.py` (TDD) - play_album, get_speakers
4. Integration verify: Hysteria plays on Family Room with track names + art

### Phase 2 - NFC Interface ✅
5. `nfc_interface.py` (TDD) - MockNFC, PN532NFC stub, parse_tag_data
6. `player.py` - config loading, --simulate flag, main loop, --read flag
7. Verify: `--simulate apple:1440903625` plays and exits; typed tag in loop works

### Phase 3 - Web UI ✅
8. `app.py` routes (TDD) - all routes listed above
9. Templates - index (tabs), album (linked tracks), track, verify, settings, base
10. Verify: Browser search → album → track → write tag (mock); verify tag page works

### Phase 4 - Hardware Procurement & Pi Setup
**Shopping List (already compiled):**
| Item | Notes | Est. Cost |
|---|---|---|
| Raspberry Pi Zero 2 W (with headers) | WiFi built-in, compact | ~$15 |
| Waveshare PN532 NFC HAT | GPIO, fits Pi Zero W directly, SPI mode | ~$18–22 |
| NTAG213 NFC cards (25–50 pack) | Card or sticker stock | ~$10–15 |
| Micro SD card 16GB+ Class 10 | For Raspberry Pi OS Lite | ~$8–12 |
| USB-C power supply 5V/2.5A | Official Pi supply recommended | ~$8–12 |

**Pi Setup:**
1. Download Raspberry Pi Imager on Mac
2. Flash new SD: **Raspberry Pi OS Lite (32-bit)** - use 32-bit on the Zero 2 W (512MB RAM, 64-bit OS adds overhead without benefit)
3. In Imager settings: username + password, hostname `vinyl-pi`, SSH, WiFi credentials
4. `ssh YOUR_USERNAME@vinyl-pi.local`
5. `sudo apt update && sudo apt upgrade -y`
6. `sudo apt install python3-pip python3-dev git -y`
7. `sudo raspi-config` → Interface Options → SPI → Enable → reboot

**PN532 HAT:**
1. Power off Pi, press HAT onto 40-pin GPIO header
2. Set jumpers to SPI mode (per [Waveshare PN532 HAT Wiki](https://www.waveshare.com/wiki/PN532_NFC_HAT))
3. `pip3 install adafruit-circuitpython-pn532 RPi.GPIO spidev`
4. Run Adafruit test script to confirm HAT detected

### Phase 5 - Deploy to Pi & Real NFC
1. Push project to GitHub from Mac
2. On Pi: `git clone <repo> && cd vinyl-emulator`
3. Run setup script: `chmod +x setup.sh && ./setup.sh`
   - Installs system packages and Python dependencies
   - Enables SPI, substitutes your username/path into systemd service files
   - Creates `config.json` with `nfc_mode=pn532`
   - Enables `vinyl-player` and `vinyl-web` services on boot
   - Prompts to reboot (required for SPI)
4. After reboot: open `http://vinyl-pi.local:5000` → Settings → set speaker IP and sn
5. Implement `PN532NFC.read_tag()` and `PN532NFC.write_tag()` in `nfc_interface.py`
   - Key Adafruit API: `pn532.read_passive_target(timeout=0.5)` for reading, `pn532.ntag2xx_write_block()` for writing
   - Reference: https://docs.circuitpython.org/projects/pn532/en/latest/
6. `sudo systemctl stop vinyl-player` → test write via web UI → `sudo systemctl start vinyl-player` → tap tag → music plays

### Phase 6 - Production

`setup.sh` handles all of this automatically. Manual steps for reference:

**`/etc/systemd/system/vinyl-player.service`**
```ini
[Unit]
Description=Vinyl Emulator NFC Player
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/vinyl-emulator/player.py
WorkingDirectory=/home/pi/vinyl-emulator
Restart=on-failure
User=pi

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/vinyl-web.service`**
```ini
[Unit]
Description=Vinyl Emulator Web UI
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/vinyl-emulator/app.py --host 0.0.0.0
WorkingDirectory=/home/pi/vinyl-emulator
Restart=on-failure
User=pi

[Install]
WantedBy=multi-user.target
```

Steps:
1. `sudo systemctl daemon-reload`
2. `sudo systemctl enable vinyl-player vinyl-web`
3. `sudo systemctl start vinyl-player vinyl-web`
4. Reboot Pi → tap tag → music plays with no manual steps

---

## Verification Checkpoints
| Phase | Test |
|---|---|
| 1 | `pytest tests/` green; Hysteria plays with track names + art in Sonos app |
| 2 | `--simulate` plays and exits; `--read` prints tag and exits; interactive loop responds to typed tag |
| 3 | Browser: search albums/songs, view album (tracks linked), view track, verify tag, settings save |
| 4 | `ssh vinyl-pi.local` works; PN532 HAT detected without errors |
| 5 | Write tag via UI → scan tag → music plays on Pi |
| 6 | Reboot Pi → scan tag → music plays, no manual steps |

---

## requirements.txt
```
flask>=3.1.3
soco>=0.30.14
requests>=2.32.5
```

## requirements-dev.txt
```
-r requirements.txt
pytest>=8.4.2
pytest-mock>=3.15.1
```

Pi-only dependencies (installed by setup.sh, not in requirements.txt):
```
adafruit-circuitpython-pn532
RPi.GPIO
spidev
```
