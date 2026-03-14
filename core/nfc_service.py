import logging
import queue
import threading
import time

from core.config import _load_config
from core.nfc_interface import MockNFC, PN532NFC, parse_tag_data  # noqa: F401 (MockNFC re-exported for patching)
from core.sonos_player import play_album, play_playlist
from providers import get_provider

log = logging.getLogger(__name__)

# Shared NFC device and lock used by the background polling thread and web routes.
_nfc_lock = threading.Lock()
_nfc = None
_nfc_last_tag = None       # debounce: last tag seen by the loop
_web_read_pending = threading.Event()  # set while /read-tag is waiting for a card
_nfc_read_queue = queue.Queue(maxsize=1)  # loop posts here when _web_read_pending is set

# Watchdog: after this many consecutive errors, back off polling and warn.
_NFC_MAX_CONSECUTIVE_ERRORS = 5
_NFC_BACKOFF_SECS = 30


def get_nfc():
    """Return the current NFC device instance (None if not initialised)."""
    return _nfc


def _nfc_loop(config_path):
    """Background NFC polling loop with debounce. Runs in a daemon thread.

    Holds _nfc_lock only during the SPI read (up to 0.5 s). Releases it
    before calling play_album so web routes never wait on a Sonos network call.

    When _web_read_pending is set, the loop delivers the next read result to
    _nfc_read_queue instead of playing, eliminating the race with /read-tag.

    Tracks consecutive errors. After _NFC_MAX_CONSECUTIVE_ERRORS failures
    it logs a warning and backs off to _NFC_BACKOFF_SECS between retries.
    """
    global _nfc_last_tag
    consecutive_errors = 0
    polls_since_log = 0
    error_start_time = None
    _NFC_HEARTBEAT_POLLS = 3600  # log heartbeat roughly every 30 min (at ~0.5s/poll)
    while True:
        try:
            with _nfc_lock:
                tag_data = _nfc.read_tag()
            if consecutive_errors:
                outage_secs = time.time() - error_start_time if error_start_time else 0
                log.info(
                    "NFC reader recovered after %d consecutive errors (outage %.0fs)",
                    consecutive_errors, outage_secs,
                )
                error_start_time = None
            consecutive_errors = 0
            polls_since_log += 1
            if polls_since_log >= _NFC_HEARTBEAT_POLLS:
                log.info("NFC heartbeat: reader healthy, polling normally")
                polls_since_log = 0
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors == 1:
                error_start_time = time.time()
            if consecutive_errors < _NFC_MAX_CONSECUTIVE_ERRORS:
                log.error("NFC read error (%d/%d): %s",
                          consecutive_errors, _NFC_MAX_CONSECUTIVE_ERRORS, e)
            elif consecutive_errors == _NFC_MAX_CONSECUTIVE_ERRORS:
                log.error(
                    "NFC reader unresponsive after %d consecutive errors (%s). "
                    "Will keep retrying every %ds.",
                    consecutive_errors, e, _NFC_BACKOFF_SECS,
                )
            if consecutive_errors >= _NFC_MAX_CONSECUTIVE_ERRORS:
                time.sleep(_NFC_BACKOFF_SECS)
            continue

        if tag_data is None:
            _nfc_last_tag = None
            continue

        if _web_read_pending.is_set():
            # /read-tag is waiting — hand off the result, skip playback.
            # Check before debounce so a card already on the reader is delivered.
            _nfc_last_tag = tag_data
            try:
                _nfc_read_queue.put_nowait(tag_data)
            except queue.Full:
                pass
            continue  # pragma: no cover

        if tag_data == _nfc_last_tag:
            continue  # same card still present - ignore

        _nfc_last_tag = tag_data
        try:
            tag = parse_tag_data(tag_data)
            provider = get_provider(tag["service"])
            config = _load_config()
            if tag["type"] == "playlist":
                info = provider.get_playlist_info(tag["id"]) or {}
                play_playlist(config["speaker_ip"], tag["id"], info.get("title", ""),
                              provider, config["sn"],
                              speaker_name=config.get("speaker_name"), config_path=config_path)
            else:
                tracks = (provider.get_track(tag["id"]) if tag["type"] == "track"
                          else provider.get_album_tracks(tag["id"]))
                play_album(config["speaker_ip"], tracks, provider, config["sn"],
                           speaker_name=config.get("speaker_name"), config_path=config_path)
            log.info("Playing %s %s", tag['type'], tag['id'])
        except Exception as e:
            log.error("NFC play error: %s", e, exc_info=True)


def _start_nfc_thread(config_path):
    """Initialise the shared NFC device and start the background polling thread.

    Only active in pn532 mode. No-op in mock mode so local dev is unaffected.
    """
    global _nfc
    try:
        config = _load_config()
    except Exception as e:
        log.warning("_start_nfc_thread: failed to load config: %s", e)
        return
    if config.get("nfc_mode") != "pn532":
        return
    try:
        _nfc = PN532NFC()
    except Exception as e:
        log.error("Failed to initialise PN532: %s", e)
        return
    t = threading.Thread(target=_nfc_loop, args=(config_path,), daemon=True)
    t.start()
    log.info("NFC thread started")
