# Vinyl Emulator — TODO / Backlog

## Packaging / Dependencies

- [ ] **Create `pyproject.toml`** — optional; enables `pip install -e .` and scripts entry points

## Hardware (Phase 4)

- [ ] **Verify PN532 HAT detects** — run Adafruit test script after NFC HAT arrives

## Pi Deployment (Phase 5)

- [ ] **Implement `PN532NFC.read_tag()`** — use `adafruit_pn532`, poll for NDEF text record
- [ ] **Implement `PN532NFC.write_tag()`** — write NDEF text record to NTAG213; before writing, read the tag first:
  - If blank → write immediately
  - If content exists → return existing content to the web UI and prompt the user to confirm overwrite
    - If content matches our format (`apple:…`) → show the human-readable name (e.g. "Hysteria by Def Leppard")
    - If content is unrecognised → show the raw string (e.g. `spotify:album:abc123`)
    - If tag is locked (read-only) → return a clear error rather than silently failing
  - Requires a two-step `/write-tag` flow: first call reads and returns existing content; second call (with `force: true`) performs the write
- [ ] **Implement `PN532NFC.write_url_tag()`** — write URL NDEF record to NTAG213
- [ ] **End-to-end test on Pi** — write tag via web UI, scan tag, music plays

## Production (Phase 6)

- [ ] **Reboot test** — tap tag after cold boot, music plays without SSH

## Enhancements

- [ ] **Port 80** — serve on `http://vinyl-pi.local` instead of `http://vinyl-pi.local:5000` using authbind or nginx
- [ ] **mDNS verification** — confirm `vinyl-pi.local` resolves from Mac and iPhone once Pi is on network
