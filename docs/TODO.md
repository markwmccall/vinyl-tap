# Vinyl Emulator — TODO / Backlog

## 🔴 Top Priority

- [x] **Speaker IP self-healing** — Sonos speakers get their IP from DHCP, which can change after a router reboot or lease renewal. If the IP changes, all playback silently fails. Fix by storing the speaker room name alongside the IP and re-resolving on failure — no DHCP reservation required.
  - Add `speaker_name` to `config.json` (e.g. `"Living Room"`) alongside existing `speaker_ip`
  - Update the Discover button flow (`/discover` route + Settings page) to save `speaker_name` at the same time as `speaker_ip`
  - Add `resolve_speaker(config_path)` to `sonos_controller.py` — returns a `soco.SoCo` instance using the cached `speaker_ip`; on any `SoCoException` or connection error, runs `soco.discover()`, finds the zone matching `speaker_name`, updates `speaker_ip` in `config.json`, and retries once. Raises if retry also fails.
  - Replace all `soco.SoCo(speaker_ip)` call sites in `sonos_controller.py` with `resolve_speaker(config_path)` — transparent to `app.py` and `player.py`
  - Happy path: zero latency (uses cached IP). On IP change: ~1-2s delay on first tap after the change, then fast again. No user action required.
  - Tests: `test_uses_cached_ip_on_success`, `test_rediscovers_on_connection_failure`, `test_updates_config_after_rediscovery`, `test_raises_if_speaker_not_found_after_rediscovery`


## Housekeeping

- [x] Remove unused files
- [x] Code review — all production modules
- [x] Add MIT license
- [x] Enable Dependabot alerts
- [x] Branch protection on main

## CI / GitHub Actions

- [x] GitHub Actions workflow — pytest on push/PR with badge in README

## Packaging / Dependencies

- [x] Pin dependency versions in `requirements.txt`
- [ ] **Create `pyproject.toml`** — optional; enables `pip install -e .` and scripts entry points

## Hardware (Phase 4)

- [x] Purchase hardware — Pi Zero 2 W, Waveshare PN532 NFC HAT, NTAG213 cards, SD card, power supply
- [x] Flash Raspberry Pi OS Lite — hostname `vinyl-pi`, SSH + SPI enabled
- [ ] **Verify PN532 HAT detects** — run Adafruit test script after NFC HAT arrives

## Pi Deployment (Phase 5)

- [ ] **Implement `PN532NFC.read_tag()`** — use `adafruit_pn532`, poll for NDEF text record
- [ ] **Implement `PN532NFC.write_tag()`** — write NDEF text record to NTAG213
- [ ] **Implement `PN532NFC.write_url_tag()`** — write URL NDEF record to NTAG213
- [ ] **End-to-end test on Pi** — write tag via web UI, scan tag, music plays

## Production (Phase 6)

- [x] systemd service files (`etc/vinyl-player.service`, `etc/vinyl-web.service`)
- [x] `setup.sh` — one-shot Pi setup script
- [ ] **Reboot test** — tap tag after cold boot, music plays without SSH

## Enhancements

- [ ] **Port 80** — serve on `http://vinyl-pi.local` instead of `http://vinyl-pi.local:5000` using authbind or nginx
- [x] Player process management from web UI (Settings page — pn532 mode only)
- [x] iPhone NFC sticker — write URL tag from Settings page
- [ ] **mDNS verification** — confirm `vinyl-pi.local` resolves from Mac and iPhone once Pi is on network
