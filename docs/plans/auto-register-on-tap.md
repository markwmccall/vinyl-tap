# Plan: Auto-Register Tags on Tap-to-Play

## Problem

`tags.json` is a metadata cache displayed in the Collection UI. It is NOT a gate for
playback — a tag plays fine even if its `tag_string` is absent from the collection.
When a user taps a tag that was written on a different device or before collection
tracking existed, playback succeeds but the item never appears in their collection.

## Goal

After a successful tap-and-play, if the tag's `tag_string` is not already in
`tags.json`, automatically add it with the metadata already fetched during playback.
No extra API calls; no user action required.

## What does NOT change

- Playback logic — no gating, no delay
- The write-tag flow — manual registration via web UI is unchanged
- The `_record_tag` route in app.py — stays as-is for manual writes
- Tag format on physical cards

---

## Data flow

Current tap flow (nfc_service.py `_nfc_loop`):

```
read tag_data
  → parse_tag_data(tag_data) → {service, type, id}
  → get_provider(service)
  → provider.get_album_tracks(id)  /  get_track(id)  /  get_playlist_info(id)
  → play_album() or play_playlist()
```

New tap flow — same steps, plus after successful play:

```
  → if tag_data not in existing collection:
        build metadata dict from provider response
        core_config.record_tag(tag_data, metadata)
```

---

## Files to change

### 1. `core/config.py`

Add a `record_tag(tag_string, metadata)` function. This moves the
deduplicate-and-prepend logic out of app.py so nfc_service.py can call it without
importing from app.py.

```python
def record_tag(tag_string: str, metadata: dict) -> None:
    """Add or replace a tag entry in the collection.

    metadata keys (all optional, stored as-is):
      name, artist, artwork_url, album_id, track_id, playlist_id, type
    written_at is added automatically.
    """
    from datetime import datetime, timezone
    tags = _load_tags()
    tags = [t for t in tags if t.get("tag_string") != tag_string]
    entry = {
        "tag_string": tag_string,
        "type": metadata.get("type", "album"),
        "name": metadata.get("name", ""),
        "artist": metadata.get("artist", ""),
        "artwork_url": metadata.get("artwork_url", ""),
        "album_id": metadata.get("album_id"),
        "track_id": metadata.get("track_id"),
        "playlist_id": metadata.get("playlist_id"),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    tags.insert(0, entry)
    _save_tags(tags)
```

Also add a `tag_in_collection(tag_string) -> bool` helper:

```python
def tag_in_collection(tag_string: str) -> bool:
    """Return True if tag_string already exists in the collection."""
    return any(t.get("tag_string") == tag_string for t in _load_tags())
```

### 2. `core/nfc_service.py`

In `_nfc_loop`, after a successful `play_album()` / `play_playlist()` call, check if
the tag is in the collection and add it if not.

Import at top of file:
```python
from core.config import tag_in_collection, record_tag
```

The insertion point is after the play call (lines 114-121), inside the existing `try`
block, before the existing `log.info`. The loop structure uses `info` (already
`or {}`-applied, always a dict) for playlists and `tracks` (a list) for
albums/tracks. Guard with `if info:` / `if tracks:` so a failed lookup (empty
result) never writes a blank entry:

```python
if tag["type"] == "playlist":
    info = provider.get_playlist_info(tag["id"]) or {}
    play_playlist(config["speaker_ip"], tag["id"], info.get("title", ""),
                  provider, config["sn"],
                  speaker_name=config.get("speaker_name"), config_path=config_path)
    if info and not tag_in_collection(tag_data):
        _auto_record(tag_data, tag, info)
else:
    tracks = (provider.get_track(tag["id"]) if tag["type"] == "track"
              else provider.get_album_tracks(tag["id"]))
    play_album(config["speaker_ip"], tracks, provider, config["sn"],
               speaker_name=config.get("speaker_name"), config_path=config_path)
    if tracks and not tag_in_collection(tag_data):
        _auto_record(tag_data, tag, tracks)
log.info("Playing %s %s", tag['type'], tag['id'])
```

The `tag_in_collection` check is placed after the play call (still inside the try
block) so a play exception skips it automatically.

Add a helper `_auto_record(tag_string, parsed_tag, provider_result)` in
nfc_service.py:

```python
def _auto_record(tag_string: str, parsed_tag: dict, provider_result) -> None:
    """Build a metadata dict from provider results and record the tag."""
    try:
        meta = {"type": parsed_tag["type"]}
        if parsed_tag["type"] == "playlist":
            # provider_result is the dict from get_playlist_info() (already or {}-applied)
            meta["name"] = provider_result.get("title", "")
            meta["artwork_url"] = provider_result.get("artwork_url", "")
            meta["playlist_id"] = parsed_tag["id"]
        else:
            # provider_result is a list of track dicts from get_album_tracks() / get_track()
            first = provider_result[0]
            meta["name"] = first.get("album", "") if parsed_tag["type"] == "album" else first.get("name", "")
            meta["artist"] = first.get("artist", "")
            meta["artwork_url"] = first.get("artwork_url", "")
            meta["album_id"] = first.get("album_id") if parsed_tag["type"] == "album" else None
            meta["track_id"] = first.get("track_id") if parsed_tag["type"] == "track" else None
        record_tag(tag_string, meta)
        log.info("Auto-registered tag: %s", tag_string)
    except Exception as e:
        log.warning("Auto-register failed for %s: %s", tag_string, e)
```

**Key detail:** `_auto_record` is wrapped in its own `try/except` so a failure to
record never interrupts playback or crashes the loop.

### 3. `app.py` — `_record_tag` refactor

Update the existing `_record_tag` function (lines ~192-207) to delegate to the new
`core_config.record_tag()`:

```python
def _record_tag(tag_string, data):
    parsed = parse_tag_data(tag_string)   # raises ValueError if invalid
    metadata = {
        "type": parsed["type"],
        "name": data.get("name", ""),
        "artist": data.get("artist", ""),
        "artwork_url": data.get("artwork_url", ""),
        "album_id": data.get("album_id"),
        "track_id": data.get("track_id"),
        "playlist_id": data.get("playlist_id"),
    }
    core_config.record_tag(tag_string, metadata)
```

This removes the duplicate deduplicate-and-prepend logic from app.py and keeps a
single implementation in core/config.py.

---

## Test cases

### `tests/test_core_config.py`

- `test_record_tag_adds_to_empty_collection` — call `record_tag("apple:123", {...})`, assert `_load_tags()` has one entry
- `test_record_tag_deduplicates` — add same tag_string twice, assert only one entry
- `test_record_tag_prepends` — add two different tags, assert newest is first
- `test_record_tag_adds_written_at` — assert `written_at` key is present and parseable as ISO 8601
- `test_tag_in_collection_true` — add a tag, assert `tag_in_collection(tag_string)` is `True`
- `test_tag_in_collection_false` — empty collection, assert `tag_in_collection("apple:999")` is `False`

### `tests/test_nfc_service.py` (new file — does not exist yet)

- `test_auto_record_called_on_unknown_tag` — mock `tag_in_collection` to return `False`, confirm `record_tag` is called after play
- `test_auto_record_not_called_on_known_tag` — mock `tag_in_collection` to return `True`, confirm `record_tag` is NOT called
- `test_auto_record_failure_does_not_crash_loop` — mock `record_tag` to raise, confirm loop continues and plays again on next tap

### `tests/test_app.py`

- Update `_record_tag` tests to confirm they still deduplicate and write correctly (now delegating to core_config)

---

## Intermediate verification steps

**After `core/config.py` changes:**
- `grep -n "record_tag\|tag_in_collection" core/config.py` — both functions present
- Run test suite — all existing tests pass, new config tests pass

**After `core/nfc_service.py` changes:**
- Run test suite — all pass
- `grep -n "_auto_record\|tag_in_collection" core/nfc_service.py` — both present

**After `app.py` refactor:**
- Run test suite — all pass
- `grep -n "def _record_tag" app.py` — body now delegates to core_config.record_tag
- Manual smoke test: tap a tag not in collection, confirm it appears in Collection UI

**Final:**
- Full test suite passes
- Tap a physical tag → music plays → Collection UI shows the new entry

---

## Order of operations

1. `core/config.py` — add `record_tag()` and `tag_in_collection()`
2. New tests in `tests/test_core_config.py`
3. Verify: run tests
4. `app.py` — refactor `_record_tag` to delegate to `core_config.record_tag()`
5. Verify: run tests
6. `core/nfc_service.py` — add `_auto_record()`, call it in `_nfc_loop`
7. New tests in `tests/test_nfc_service.py`
8. Verify: run full test suite
9. Open PR

---

## Dependency on external-data-dir plan

This plan is **independent** — it can be implemented before or after external-data-dir.
`record_tag` and `tag_in_collection` use `_load_tags`/`_save_tags` which already
respect whatever `TAGS_PATH` is set to (including after `set_data_dir()`).
