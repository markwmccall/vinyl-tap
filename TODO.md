# TODO

Items from code review. See commit history for context.

---

## Deployment

- [x] **`setup.sh` uses `--break-system-packages`** — Bypasses PEP 668 safety. Consider switching to a venv.
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
