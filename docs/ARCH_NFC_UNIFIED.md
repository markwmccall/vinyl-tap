# Architecture: Unified NFC + Web Process

## Problem

The current design runs two separate OS processes:

- `vinyl-player.service` → `player.py` — NFC polling loop
- `vinyl-web.service` → `app.py` — Flask web app

Both processes access the same PN532 hardware over I2C. When the web app needs to write or verify a tag, it sends `SIGTERM` to the player to free the bus. But `SIGTERM` interrupts the player mid-I2C-transfer (at the kernel ioctl level), leaving the PN532 waiting for bytes that never arrive. The PN532 holds the clock line low indefinitely. The bus hangs. Only a hardware power cycle recovers it.

A secondary issue: the player sees the same card on every 0.5 s poll, so holding a card on the reader re-queues the album repeatedly.

## Solution

Merge both services into a single Python process. The NFC polling loop becomes a **background daemon thread** inside `app.py`. Flask handles HTTP in the main thread. A single shared `PN532NFC` instance is protected by `threading.Lock`.

### Why this works

- No inter-process signalling. No SIGTERM. No EINTR. No bus hangs.
- Web routes that need NFC simply acquire the lock, do their operation (takes < 100 ms), and release it. The NFC thread resumes on the next poll.
- Maximum wait for a web route is one poll cycle: 0.5 s. Acceptable for UX.

---

## New architecture

```
app.py
├── Flask routes (main thread, threaded=True so each request gets its own thread)
├── _nfc_lock  (threading.Lock — one holder at a time)
├── _nfc       (shared PN532NFC or MockNFC instance)
└── _nfc_thread (daemon thread — NFC polling loop)
```

### NFC thread state machine (debounce)

```
state = IDLE
last_tag = None

loop:
    with _nfc_lock:
        tag_data = _nfc.read_tag()   # blocks up to 0.5 s, lock held during I2C

    if tag_data is None:
        state = IDLE
        last_tag = None
        continue

    if tag_data == last_tag:
        continue                     # same card still present — ignore

    last_tag = tag_data
    state = PLAYING
    play(tag_data)                   # Sonos queue + play (network, no lock needed)
```

Holding a card on the reader: first tap plays, every subsequent read matches
`last_tag` so nothing happens. Removing and re-tapping: `None` clears
`last_tag`, next tap triggers play. Works correctly for all cases.

### Lock protocol for web routes

```python
acquired = _nfc_lock.acquire(timeout=2.0)
if not acquired:
    return jsonify({"error": "NFC busy, try again"}), 503
try:
    # safe to use _nfc here
finally:
    _nfc_lock.release()
```

---

## Files changed

### `app.py` — main changes

1. **Add** `import threading` and `import signal` (signal only needed for clean shutdown).
2. **Add** module-level `_nfc_lock = threading.Lock()` and `_nfc = None`.
3. **Add** `_nfc_loop(config_path)` function — the background polling loop (see above).
4. **Add** `_start_nfc_thread(config_path)` — initialises `_nfc`, starts daemon thread. Only runs in `pn532` mode; no-ops in `mock` mode.
5. **Update** `/write-tag` — remove `_stop_player_if_active` / `_start_player` calls; acquire `_nfc_lock` instead.
6. **Update** `/read-tag` — same lock pattern.
7. **Remove** `_stop_player_if_active()`, `_start_player()`, `time.sleep(1)` (all obsolete).
8. **Remove** `/player/status` and `/player/control` routes (no longer meaningful — there is no separate player process).
9. **Update** `__main__` block: call `_start_nfc_thread(CONFIG_PATH)` before `app.run()`.

### `templates/settings.html`

Remove the player status badge and Stop/Start Player buttons. With a unified process, these controls no longer exist. (The NFC loop always runs when the app runs.)

### `player.py` — keep as CLI tool only

`player.py` remains useful for:
- `python3 player.py --simulate apple:1440903625` — test playback without a card
- `python3 player.py --read` — read one tag and print it

It is **no longer a systemd service**. No changes to the file itself needed.

### `etc/vinyl-player.service` — remove from systemd

The service file can stay in the repo for reference but is not installed. The `setup.sh` update handles this.

### `setup.sh`

1. Change `[5/5]` to install and enable only `vinyl-web.service` (rename to `vinyl.service` optionally, or keep the name).
2. Remove the `vinyl-player` lines from `systemctl enable`, `systemctl restart`, and the `sudoers` entry (the `sudo systemctl start/stop vinyl-player` rule is no longer needed).

### `etc/vinyl-web.service` (or new `etc/vinyl.service`)

No change needed to the service file itself. It already runs `app.py`. The NFC thread starts automatically inside the process.

---

## Mock mode behaviour

In `mock` mode, `_start_nfc_thread` does nothing. `_nfc` stays `None`. Web routes that check for `_nfc is None` return a clear error or fall back to stdin (same as today). The `--simulate` flag in `player.py` continues to work for local dev.

---

## Thread safety notes

- `_nfc_lock` is the only shared resource. All access to the PN532 hardware goes through it.
- `play_album()` makes network calls to Sonos. This does **not** require the lock — it runs after `_nfc_lock` is released in the NFC thread.
- Flask's threaded mode means multiple HTTP requests can run concurrently. Each web route acquires the lock independently. Lock contention is rare and brief (< 0.5 s max wait).
- `_nfc` itself is set once at startup and never reassigned, so no lock is needed to read the reference.

---

## Testing strategy

### Unit tests to add / update

- `test_nfc_loop_debounce_same_card` — verify that same tag read twice only triggers `play_album` once
- `test_nfc_loop_replays_after_card_removed` — None resets state; next tap plays again
- `test_write_tag_acquires_lock` — mock lock, verify acquire/release called
- `test_write_tag_503_when_lock_busy` — lock held by another thread, expect 503
- Remove tests for `_stop_player_if_active` / `_start_player` (functions deleted)
- Remove tests for `/player/status` and `/player/control` (routes deleted)

### Existing tests

All existing write-tag, read-tag, and play route tests continue to pass with minor fixture updates (remove `_stop_player_if_active` / `_start_player` monkeypatching).

---

## Rollout on Pi

1. `git pull` on the Pi.
2. `sudo systemctl stop vinyl-web` (the only running service).
3. `./setup.sh` — reinstalls the service file(s), restarts.
4. Verify: `sudo systemctl status vinyl-web` shows active.
5. Write a tag from the browser — no power cycle needed.
6. Tap the card — music plays.
7. Tap again while card is present — music does not replay.

---

## Implementation steps

Each step ends with all tests passing and a clean commit. The codebase is deployable after every step.

### Step 1 — Add NFC thread + debounce to `app.py`
- Add `import threading` to `app.py`
- Add module-level `_nfc_lock = threading.Lock()` and `_nfc = None`
- Add `_nfc_loop(config_path)` — background polling loop with debounce state machine
- Add `_start_nfc_thread(config_path)` — initialises `_nfc`, starts daemon thread (pn532 mode only)
- Update `__main__` block to call `_start_nfc_thread(CONFIG_PATH)` before `app.run()`
- Add tests: debounce same card, replay after card removed, thread not started in mock mode
- Existing routes and tests unchanged

### Step 2 — Update `/write-tag` and `/read-tag` to use the shared lock
- Replace `_stop_player_if_active` / `_start_player` / `time.sleep(1)` with `_nfc_lock.acquire(timeout=2.0)`
- Remove `_stop_player_if_active()`, `_start_player()`, `import time` (all obsolete)
- Update `/write-tag` and `/read-tag` to use the shared `_nfc` instance via the lock
- Update tests: remove `_stop_player_if_active` / `_start_player` monkeypatching, add lock-busy 503 test

### Step 3 — Remove player-control routes and Settings UI
- Delete `/player/status` and `/player/control` routes from `app.py`
- Remove Stop/Start Player buttons and status badge from `templates/settings.html`
- Delete related tests
- No functional change to NFC or playback behaviour

### Step 4 — Update `setup.sh` and service files; deploy to Pi
- Remove `vinyl-player` from `systemctl enable/restart` in `setup.sh`
- Remove the `sudoers` entry for `vinyl-player` start/stop (no longer needed)
- Re-enable `vinyl-web` auto-start (`sudo systemctl enable vinyl-web`)
- Deploy on Pi: `git pull && ./setup.sh`
- Verify: write a tag, tap it, music plays, no power cycle required

---

## What this does NOT change

- All Flask routes and their behaviour (except the two removed player-control routes).
- The NFC tag format (`apple:{id}`, `apple:track:{id}`).
- Sonos playback logic.
- `config.json` schema.
- `nfc_interface.py` (no changes needed).
- `player.py` (kept as CLI tool).
