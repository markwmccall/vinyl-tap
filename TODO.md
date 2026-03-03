# TODO

Items from code review. See commit history for context.

---

## Deployment

- [ ] **Port 80** — Serve on `http://vinyl-pi.local` instead of port 5000 using authbind or nginx.
- [ ] **mDNS** — Confirm `vinyl-pi.local` resolves from Mac and iPhone once Pi is on network.

## Hardware

- [ ] **Verify PN532 HAT detects** — Run Adafruit test script after NFC HAT arrives.
- [ ] **End-to-end test on Pi** — Write tag via web UI, scan tag, music plays.
- [ ] **Reboot test** — Tap tag after cold boot, music plays without SSH.
