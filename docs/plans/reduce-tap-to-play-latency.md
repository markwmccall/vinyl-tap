# Reduce Tap-to-Play Latency

## Problem Statement

After tapping an NFC card, music takes several seconds to start. Investigation of
the Pi logs reveals two issues:

1. **Sequential `AddURIToQueue` calls block playback.** For a 14-track album each
   UPnP call takes ~0.35 s, so ~5 s elapses queuing all tracks before
   `play_from_queue(0)` is ever issued. Music could start after the first track is
   queued.

2. **The iTunes API call and NFC detection are invisible.** `get_album_tracks` uses
   `urllib.request`, not urllib3, so nothing is logged. There is also no timestamp
   for when the tag was detected. Without these we cannot measure end-to-end latency
   or know how much time the iTunes round-trip costs on the Pi.

## Goals

- Start playback as soon as track 1 is queued; continue adding remaining tracks while
  the speaker is already playing.
- Add timing logs so each phase (tag detect → provider fetch → play commanded) is
  measurable from `journalctl`.

## Out of Scope

- Caching `lookup_udn` (the FV:2 Browse) — it was fast (<1 s) in the observed session.
- Any changes to the playlist path (`_do_play_playlist`) — playlists are a single
  `AddURIToQueue` call so they have no queuing delay.
- Single-track path — only one `AddURIToQueue`, no change needed.

---

## Phase 1 — Timing Logs

### File: `core/nfc_service.py`

In `_nfc_loop`, wrap the play sequence with `time.time()` checkpoints logged at
INFO level so they survive the default log level:

```
t0 = time.time()              # tag detected (just after debounce passes)
...provider call...
t1 = time.time()              # provider returned
...play_album / play_playlist call...
t2 = time.time()              # play commanded
log.info(
    "Tap-to-play timing: tag_detect→provider %.2fs, provider→play %.2fs, total %.2fs",
    t1 - t0, t2 - t1, t2 - t0,
)
```

`t0` is set immediately after the debounce check (after `_nfc_last_tag = tag_data`).
The three log values correspond to:
- `tag_detect→provider`: time spent in `get_album_tracks` / `get_track` /
  `get_playlist_info` (the iTunes or SMAPI call).
- `provider→play`: time spent inside `play_album` / `play_playlist` (Sonos UPnP).
- `total`: full end-to-end from tag recognised to play commanded.

The existing `log.info("Playing %s %s", ...)` line is replaced by the timing log
so there is exactly one INFO line per tap (no duplication).

### Verification after Phase 1

1. Run `.venv/bin/python -m pytest tests/test_nfc_service.py -v` — all tests pass.
2. Tap a card on the Pi and confirm `journalctl` shows the timing line.

---

## Phase 2 — Play After First Track

### File: `core/sonos_player.py`

Change `_do_play_album` so that after the first track is queued, `play_from_queue(0)`
is called immediately, and the remaining tracks are queued after that.

Current logic:
```python
def _do_play_album(speaker, track_dicts, provider, sn):
    coordinator = speaker.group.coordinator
    udn = provider.lookup_udn(coordinator, sn)
    coordinator.clear_queue()
    for track in track_dicts:
        uri = provider.build_track_uri(track["track_id"], sn)
        metadata = provider.build_track_didl(track, udn)
        coordinator.avTransport.AddURIToQueue([...])
    coordinator.play_from_queue(0)
```

New logic:
```python
def _do_play_album(speaker, track_dicts, provider, sn):
    coordinator = speaker.group.coordinator
    udn = provider.lookup_udn(coordinator, sn)
    coordinator.clear_queue()
    for i, track in enumerate(track_dicts):
        uri = provider.build_track_uri(track["track_id"], sn)
        metadata = provider.build_track_didl(track, udn)
        coordinator.avTransport.AddURIToQueue([...])
        if i == 0:
            coordinator.play_from_queue(0)
    # remaining tracks continue to be added while speaker is playing
```

No other files change — `play_album` (the public wrapper with rediscovery retry)
calls `_do_play_album` unchanged.

### Edge cases

- **Single-track album / list:** `i == 0` triggers on the only track, then the loop
  ends. Behaviour is identical to today.
- **Empty track list:** `play_album` already guards with `if not track_dicts: return`
  before calling `_do_play_album`, so `_do_play_album` is never called with an empty
  list.
- **Rediscovery retry:** If the first attempt fails, the retry calls `_do_play_album`
  fresh — the new speaker's queue is also cleared before adding, so no stale tracks.

### Verification after Phase 2

1. Run `.venv/bin/python -m pytest tests/test_core_sonos_player.py -v` — all existing
   tests pass.
2. The new test (see below) verifies `play_from_queue` is called after track 1, and
   remaining tracks are added after.

---

## Test Cases

### `tests/test_core_sonos_player.py` — new test

`test_play_album_starts_after_first_track`:
- Patch `soco.SoCo` with a mock speaker (same fixture as existing tests).
- Call `play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3")` with a
  2-track `SAMPLE_TRACKS`.
- Assert `play_from_queue` was called exactly once.
- Assert `play_from_queue` was called *after* the first `AddURIToQueue` but *before*
  the second `AddURIToQueue`.
  - Technique: use `mock_speaker.method_calls` (ordered list) to verify call order:
    `AddURIToQueue[0]` comes before `play_from_queue`, which comes before
    `AddURIToQueue[1]`.

### `tests/test_nfc_service.py` — new test

`test_nfc_loop_logs_timing`:
- Patch `time.time` to return a controlled sequence (e.g. `[0.0, 1.5, 4.0]`
  representing t0/t1/t2).
- Run `_nfc_loop` for one tag event (same pattern as existing loop tests).
- Assert `log.info` was called with a message matching `"Tap-to-play timing"` and
  containing the expected delta values.

---

## Implementation Order

1. Write `test_play_album_starts_after_first_track` (failing).
2. Change `_do_play_album` in `core/sonos_player.py`.
3. Confirm new test passes; confirm all `test_core_sonos_player.py` tests pass.
4. Write `test_nfc_loop_logs_timing` (failing).
5. Add timing instrumentation to `_nfc_loop` in `core/nfc_service.py`.
6. Confirm new test passes; confirm all `test_nfc_service.py` tests pass.
7. Run full suite: `.venv/bin/python -m pytest tests/ -v`.

## Open Questions

None — all edge cases above are resolved.
