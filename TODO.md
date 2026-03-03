# TODO

Items from code review. See commit history for context.

---

## Correctness

- [x] **Wrong HTTP status on empty track list** — `app.py` returns `200 {"status": "ok"}` when `get_album_tracks()` / `get_track()` returns empty. Should return `404`.
- [x] **`_load_config()` KeyError on missing fields** — No validation that `speaker_ip`, `sn`, `nfc_mode` exist. Crashes with unhelpful error if config is incomplete.
- [x] **`_load_tags()` crashes on invalid JSON** — `json.load()` not wrapped in try/except. Corrupted `tags.json` brings down the app.

---

## Code Quality

- [x] **Duplicate JS in album.html / track.html** — `writeTag()` and `postAction()` are identical in both templates. Extract to a shared `static/player.js`.
- [x] **No structured logging** — No use of Python `logging` module. Hard to debug production issues on the Pi.

---

## Deployment

- [ ] **systemd missing `RestartSec`** — `Restart=on-failure` with no delay creates tight restart loop on persistent errors. Add `RestartSec=5` to both service files.
- [ ] **No resource limits in service units** — Add `MemoryLimit=256M` to prevent runaway process consuming all Pi memory.
- [ ] **`setup.sh` uses `--break-system-packages`** — Bypasses PEP 668 safety. Consider switching to a venv.
- [ ] **Port 80** — Serve on `http://vinyl-pi.local` instead of port 5000 using authbind or nginx.
- [ ] **mDNS** — Confirm `vinyl-pi.local` resolves from Mac and iPhone once Pi is on network.

## Hardware

- [ ] **Verify PN532 HAT detects** — Run Adafruit test script after NFC HAT arrives.
- [ ] **End-to-end test on Pi** — Write tag via web UI, scan tag, music plays.
- [ ] **Reboot test** — Tap tag after cold boot, music plays without SSH.

---

## Features

- [ ] **Print album art** — From the album/track page, print a CD jewel case front insert (120mm × 120mm square). Should include album art, title, and artist. Options: browser `@media print` stylesheet on a `/print/<album_id>` route, or PDF generation. Consider including a small NFC tap icon or instructions on the reverse.
- [ ] **Apple Music playlists** — Support writing playlist tags and playing playlists on Sonos. Requires research into whether iTunes Search API exposes user playlists (it likely doesn't — may need Apple Music API with OAuth) and whether Sonos can play Apple Music playlist URIs via SMAPI.
- [ ] **Multi-service support (Spotify, etc.)** — Add support for additional Sonos-connected music services. UX: per-search service tabs (Apple Music | Spotify) so users can mix services across cards. Tag format already supports this (`apple:xxx`, `spotify:xxx`).
- [ ] **Research: Sonos cross-service search via SoCo** — Investigate whether `soco.music_services.MusicServiceClient` or the UPnP ContentDirectory `Search()` action can query all user-configured services in one call (the way the Sonos app does). If feasible, this would let the app search without managing per-service API credentials.
