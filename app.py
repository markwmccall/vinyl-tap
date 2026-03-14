import argparse
import json
import logging
import os
import queue
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import psutil
from packaging.version import Version

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

import soco
from core.nfc_interface import MockNFC, PN532NFC, parse_tag_data
from providers import get_provider
from core.sonos_player import get_now_playing, get_speakers, get_volume, next_track, pause, play_album, play_playlist, prev_track, resume, set_volume, stop

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = str(PROJECT_ROOT / "config.json")
TAGS_PATH = str(PROJECT_ROOT / "data" / "tags.json")
UPDATE_LOG = PROJECT_ROOT / "update.log"
UPDATER_PATH = PROJECT_ROOT / "core" / "updater.py"

_VERSION_FILE = PROJECT_ROOT / "VERSION"
VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "0.0.0"

IS_PRODUCTION = "INVOCATION_ID" in os.environ

# Cache for GitHub release check: (timestamp, result_dict)
_update_cache = None  # type: tuple | None  (timestamp, result_dict)
_UPDATE_CACHE_TTL = 3600  # 1 hour
GITHUB_REPO = "markwmccall/vinyl-emulator"

log = logging.getLogger(__name__)


@app.context_processor
def _inject_version():
    return {"app_version": VERSION}

# Shared NFC device and lock used by the background polling thread and web routes.
_nfc_lock = threading.Lock()
_nfc = None
_nfc_last_tag = None       # debounce: last tag seen by the loop
_web_read_pending = False  # True while /read-tag is waiting for a card
_nfc_read_queue = queue.Queue(maxsize=1)  # loop posts here when _web_read_pending

# Watchdog: after this many consecutive errors, back off polling and warn.
_NFC_MAX_CONSECUTIVE_ERRORS = 5
_NFC_BACKOFF_SECS = 30


def _get_household_id_upnp(speaker_ip: str) -> str:
    """Fetch the Sonos household ID from the local speaker via UPnP SOAP."""
    soap_body = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body><u:GetHouseholdID xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1">'
        "</u:GetHouseholdID></s:Body></s:Envelope>"
    )
    req = urllib.request.Request(
        f"http://{speaker_ip}:1400/DeviceProperties/Control",
        data=soap_body.encode(),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": '"urn:schemas-upnp-org:service:DeviceProperties:1#GetHouseholdID"',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
        import re
        m = re.search(r"<CurrentHouseholdID>([^<]+)</CurrentHouseholdID>", body)
        return m.group(1) if m else ""
    except Exception as e:
        log.warning("Could not get household ID from speaker: %s", e)
        return ""


def _load_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    # In-memory migration: flat "sn" → services.apple.sn (and vice versa)
    if "sn" in config and "services" not in config:
        config.setdefault("services", {}).setdefault("apple", {})
        config["services"]["apple"]["sn"] = config["sn"]
    elif "services" in config and "apple" in config["services"]:
        config.setdefault("sn", config["services"]["apple"].get("sn"))
    required = ["speaker_ip", "sn", "nfc_mode"]
    missing = [k for k in required if k not in config]
    if missing:
        raise RuntimeError(f"Missing required config fields: {', '.join(missing)}")
    return config


def _configure_sonos():
    """If Sonos Control API tokens are present in config, configure providers."""
    try:
        config = _load_config()
    except Exception:
        return
    sonos_cfg = config.get("services", {}).get("sonos", {})
    access_token = sonos_cfg.get("access_token")
    refresh_token = sonos_cfg.get("refresh_token")
    household_id = sonos_cfg.get("household_id")
    client_key = sonos_cfg.get("client_key")
    client_secret = sonos_cfg.get("client_secret")
    if not (access_token and refresh_token and household_id and client_key and client_secret):
        return

    from providers.sonos_api import SonosControlClient
    client = SonosControlClient(client_key, client_secret)

    def _on_sonos_token_refresh(new_access_token, new_refresh_token):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            cfg.setdefault("services", {}).setdefault("sonos", {})
            cfg["services"]["sonos"]["access_token"] = new_access_token
            cfg["services"]["sonos"]["refresh_token"] = new_refresh_token
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
            log.info("Persisted refreshed Sonos token to config")
        except Exception as e:
            log.warning("Failed to persist Sonos token: %s", e)

    provider = get_provider("apple")
    provider.configure_sonos(
        client, access_token, refresh_token, household_id,
        on_token_refresh=_on_sonos_token_refresh,
    )


def _configure_smapi():
    """If SMAPI tokens are present in config, configure the Apple Music provider."""
    try:
        config = _load_config()
    except Exception:
        return
    apple_cfg = config.get("services", {}).get("apple", {})
    token = apple_cfg.get("smapi_token")
    key = apple_cfg.get("smapi_key")
    hhid = apple_cfg.get("smapi_household_id")
    if not (token and key and hhid):
        return

    def _on_token_refresh(new_token, new_key):
        """Persist refreshed SMAPI tokens to config.json."""
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            cfg.setdefault("services", {}).setdefault("apple", {})
            cfg["services"]["apple"]["smapi_token"] = new_token
            cfg["services"]["apple"]["smapi_key"] = new_key
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
            log.info("Persisted refreshed SMAPI token to config")
        except Exception as e:
            log.warning("Failed to persist SMAPI token: %s", e)

    provider = get_provider("apple")
    provider.configure_smapi(token, key, hhid, on_token_refresh=_on_token_refresh)
    log.info("Apple Music SMAPI search enabled (household=%s)", hhid)


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"  # pragma: no cover


def _get_hardware_stats():
    stats = {}

    # System
    try:
        stats["hostname"] = os.uname().nodename
    except Exception:  # pragma: no cover
        stats["hostname"] = None

    try:
        with open("/etc/os-release") as f:
            pairs = {}
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    pairs[k] = v.strip('"')
        stats["os"] = pairs.get("PRETTY_NAME")
    except Exception:
        stats["os"] = None

    try:
        stats["kernel"] = os.uname().release
    except Exception:  # pragma: no cover
        stats["kernel"] = None

    try:
        uptime_secs = int(time.time() - psutil.boot_time())
        d, rem = divmod(uptime_secs, 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        parts = []
        if d:
            parts.append(f"{d}d")
        if h:
            parts.append(f"{h}h")
        parts.append(f"{m}m")
        stats["uptime"] = " ".join(parts)
    except Exception:
        stats["uptime"] = None

    # Processor
    try:
        cpu_model = None
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Model"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
        stats["cpu_model"] = cpu_model
    except Exception:
        stats["cpu_model"] = None

    try:
        stats["cpu_cores"] = psutil.cpu_count(logical=False) or psutil.cpu_count()
    except Exception:
        stats["cpu_cores"] = None

    try:
        stats["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    except Exception:
        stats["cpu_percent"] = None

    try:
        freq = psutil.cpu_freq()
        stats["cpu_freq_mhz"] = round(freq.current) if freq else None
    except Exception:
        stats["cpu_freq_mhz"] = None

    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            stats["cpu_temp_c"] = round(int(f.read().strip()) / 1000, 1)
    except Exception:
        stats["cpu_temp_c"] = None

    # Memory
    try:
        mem = psutil.virtual_memory()
        stats["ram_used"] = _fmt_bytes(mem.used)
        stats["ram_total"] = _fmt_bytes(mem.total)
        stats["ram_percent"] = mem.percent
    except Exception:
        stats["ram_used"] = stats["ram_total"] = stats["ram_percent"] = None

    try:
        swap = psutil.swap_memory()
        stats["swap_used"] = _fmt_bytes(swap.used)
        stats["swap_total"] = _fmt_bytes(swap.total)
    except Exception:
        stats["swap_used"] = stats["swap_total"] = None

    # Storage
    try:
        disk = psutil.disk_usage("/")
        stats["disk_used"] = _fmt_bytes(disk.used)
        stats["disk_free"] = _fmt_bytes(disk.free)
        stats["disk_total"] = _fmt_bytes(disk.total)
        stats["disk_percent"] = disk.percent
    except Exception:
        stats["disk_used"] = stats["disk_free"] = stats["disk_total"] = stats["disk_percent"] = None

    # NFC reader
    stats["nfc_connected"] = _nfc is not None

    # Power throttling (Raspberry Pi only — vcgencmd)
    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=2,
        )
        hex_val = result.stdout.strip().split("=")[-1]
        throttled = int(hex_val, 16)
        flags = []
        if throttled & 0x1:     flags.append("Under-voltage detected")
        if throttled & 0x2:     flags.append("Arm frequency capped")
        if throttled & 0x4:     flags.append("Currently throttled")
        if throttled & 0x8:     flags.append("Soft temperature limit active")
        if throttled & 0x10000: flags.append("Under-voltage has occurred")
        if throttled & 0x20000: flags.append("Arm frequency has been capped")
        if throttled & 0x40000: flags.append("Throttling has occurred")
        if throttled & 0x80000: flags.append("Soft temperature limit has occurred")
        stats["throttle_ok"] = throttled == 0
        stats["throttle_flags"] = flags
    except Exception:
        stats["throttle_ok"] = None
        stats["throttle_flags"] = None

    return stats



def _load_tags():
    if not os.path.exists(TAGS_PATH):
        return []
    try:
        with open(TAGS_PATH) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def _save_tags(tags):
    with open(TAGS_PATH, "w") as f:
        json.dump(tags, f, indent=2)


def _record_tag(tag_string, tag_type, name, artist, artwork_url, album_id=None, track_id=None, playlist_id=None):
    tags = _load_tags()
    tags = [t for t in tags if t["tag_string"] != tag_string]
    tags.insert(0, {
        "tag_string": tag_string,
        "type": tag_type,
        "name": name,
        "artist": artist,
        "artwork_url": artwork_url,
        "album_id": album_id,
        "track_id": track_id,
        "playlist_id": playlist_id,
        "written_at": datetime.utcnow().isoformat(),
    })
    _save_tags(tags)


def _make_nfc(config):
    if config.get("nfc_mode") == "pn532":
        try:
            return PN532NFC()
        except ImportError:
            raise RuntimeError(
                "PN532 hardware libraries not installed - "
                "run setup.sh on a Raspberry Pi to install them"
            )
    return MockNFC()


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

        if _web_read_pending:
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
            log.info(f"Playing {tag['type']} {tag['id']}")
        except Exception as e:
            log.error(f"NFC play error: {e}")


def _start_nfc_thread(config_path):
    """Initialise the shared NFC device and start the background polling thread.

    Only active in pn532 mode. No-op in mock mode so local dev is unaffected.
    """
    global _nfc
    try:
        config = _load_config()
    except Exception:
        return
    if config.get("nfc_mode") != "pn532":
        return
    try:
        _nfc = PN532NFC()
    except Exception as e:
        log.error(f"Failed to initialise PN532: {e}")
        return
    t = threading.Thread(target=_nfc_loop, args=(config_path,), daemon=True)
    t.start()
    log.info("NFC thread started")


def _format_existing_tag(tag_string):
    """Return human-readable display name for an existing tag, or raw string if unrecognised."""
    try:
        tag = parse_tag_data(tag_string)
    except ValueError:
        return tag_string
    try:
        provider = get_provider(tag["service"])
        if tag["type"] == "track":
            tracks = provider.get_track(tag["id"])
            if tracks:
                return f"{tracks[0]['name']} by {tracks[0]['artist']}"
        elif tag["type"] == "playlist":
            info = provider.get_playlist_info(tag["id"])
            if info:
                return f"{info['title']} (playlist)"
        else:
            tracks = provider.get_album_tracks(tag["id"])
            if tracks:
                return f"{tracks[0]['album']} by {tracks[0]['artist']}"
    except Exception:
        pass
    return tag_string


def _do_record_tag(tag_data, data):
    provider = get_provider("apple")
    if "playlist_id" in data:
        info = provider.get_playlist_info(data["playlist_id"]) or {}
        _record_tag(tag_data, "playlist", info.get("title", ""), "",
                    info.get("artwork_url", ""), playlist_id=data["playlist_id"])
    elif "track_id" in data:
        tracks = provider.get_track(data["track_id"])
        if tracks:
            t = tracks[0]
            _record_tag(tag_data, "track", t["name"], t["artist"],
                        t.get("artwork_url", ""), album_id=t.get("album_id"),
                        track_id=t["track_id"])
    else:
        tracks = provider.get_album_tracks(data["album_id"])
        if tracks:
            t = tracks[0]
            _record_tag(tag_data, "album", t["album"], t["artist"],
                        t.get("artwork_url", ""), album_id=data["album_id"])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    search_type = request.args.get("type", "album")
    provider = get_provider("apple")
    if search_type == "playlist":
        if not q:
            # Return personal playlists when no query
            playlists = provider.list_playlists() if hasattr(provider, "list_playlists") else []
            return jsonify(playlists)
        return jsonify(provider.search_playlists(q))
    if not q:
        return jsonify([])
    if search_type == "song":
        return jsonify(provider.search_songs(q))
    return jsonify(provider.search_albums(q))


@app.route("/playlists")
def playlists():
    provider = get_provider("apple")
    items = provider.list_playlists() if hasattr(provider, "list_playlists") else []
    return jsonify(items)


@app.route("/album/<int:album_id>")
def album(album_id):
    tracks = get_provider("apple").get_album_tracks(album_id)
    if not tracks:
        abort(404)
    return render_template("album.html", album_id=album_id, tracks=tracks, show_now_playing=True)


@app.route("/playlist/<playlist_id>")
def playlist_page(playlist_id):
    provider = get_provider("apple")
    info = provider.get_playlist_info(playlist_id)
    if not info:
        abort(404)
    tracks = provider.get_playlist_tracks(playlist_id)
    return render_template("playlist.html", playlist_id=playlist_id, info=info, tracks=tracks, show_now_playing=True)


@app.route("/track/<int:track_id>")
def track(track_id):
    tracks = get_provider("apple").get_track(track_id)
    if not tracks:
        abort(404)
    return render_template("track.html", track_id=track_id, track=tracks[0], show_now_playing=True)


@app.route("/print")
def print_inserts():
    ids_param = request.args.get("ids", "")
    if not ids_param:
        abort(400)
    album_ids = [int(i) for i in ids_param.split(",") if i.strip().isdigit()]
    if not album_ids:
        abort(400)
    albums = []
    provider = get_provider("apple")
    for album_id in album_ids:
        tracks = provider.get_album_tracks(album_id)
        if tracks:
            albums.append({
                "album_id": album_id,
                "name": tracks[0]["album"],
                "artist": tracks[0]["artist"],
                "artwork_url": tracks[0]["artwork_url"],
                "release_year": tracks[0].get("release_year", ""),
                "copyright": tracks[0].get("copyright", ""),
                "tracks": tracks,
            })
    if not albums:
        abort(404)
    return render_template("print.html", albums=albums)


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.route("/write-tag", methods=["POST"])
def write_tag():
    data = request.get_json()
    if not data or ("track_id" not in data and "album_id" not in data and "playlist_id" not in data):
        return jsonify({"error": "album_id, track_id, or playlist_id required"}), 400
    config = _load_config()
    tag_data = (f"apple:track:{data['track_id']}" if "track_id" in data
                else f"apple:playlist:{data['playlist_id']}" if "playlist_id" in data
                else f"apple:{data['album_id']}")
    force = data.get("force", False)

    if config.get("nfc_mode") == "pn532":
        if _nfc is None:
            return jsonify({"error": "NFC not initialised"}), 503
        acquired = _nfc_lock.acquire(timeout=2.0)
        if not acquired:
            return jsonify({"error": "NFC busy, try again"}), 503
        try:
            pre_read = _nfc.read_tag()
            if not force and pre_read:
                return jsonify({
                    "status": "confirm",
                    "existing": pre_read,
                    "existing_display": _format_existing_tag(pre_read),
                })
            try:
                _nfc.write_tag(tag_data)
            except IOError as e:
                if pre_read is None:
                    return jsonify({"error": "No tag present - place a card on the reader"}), 409
                return jsonify({"error": str(e)}), 409
        finally:
            _nfc_lock.release()
    else:
        try:
            nfc = _make_nfc(config)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 503
        try:
            nfc.write_tag(tag_data)
        except IOError as e:
            return jsonify({"error": str(e)}), 409

    try:
        _do_record_tag(tag_data, data)
    except Exception:
        pass
    return jsonify({"status": "ok", "written": tag_data})


@app.route("/write-url-tag", methods=["POST"])
def write_url_tag():
    url = request.host_url.rstrip("/")
    config = _load_config()
    if config.get("nfc_mode") == "pn532":
        if _nfc is None:
            return jsonify({"error": "NFC not initialised"}), 503
        acquired = _nfc_lock.acquire(timeout=2.0)
        if not acquired:
            return jsonify({"error": "NFC busy, try again"}), 503
        try:
            pre_read = _nfc.read_tag()
            try:
                _nfc.write_url_tag(url)
            except NotImplementedError as e:
                return jsonify({"error": str(e)}), 501
            except IOError as e:
                if pre_read is None:
                    return jsonify({"error": "No tag present - place a card on the reader"}), 409
                return jsonify({"error": str(e)}), 409
        finally:
            _nfc_lock.release()
    else:
        try:
            nfc = _make_nfc(config)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 503
        try:
            nfc.write_url_tag(url)
        except NotImplementedError as e:
            return jsonify({"error": str(e)}), 501
    return jsonify({"status": "ok", "written": url})


@app.route("/play", methods=["POST"])
def play():
    data = request.get_json()
    if not data or ("track_id" not in data and "album_id" not in data and "playlist_id" not in data):
        return jsonify({"error": "album_id, track_id, or playlist_id required"}), 400
    config = _load_config()
    provider = get_provider("apple")
    if "playlist_id" in data:
        info = provider.get_playlist_info(data["playlist_id"]) or {}
        play_playlist(config["speaker_ip"], data["playlist_id"], info.get("title", ""),
                      provider, config["sn"],
                      speaker_name=config.get("speaker_name"), config_path=CONFIG_PATH)
    else:
        if "track_id" in data:
            tracks = provider.get_track(data["track_id"])
        else:
            tracks = provider.get_album_tracks(data["album_id"])
        if not tracks:
            return jsonify({"error": "not found"}), 404
        play_album(config["speaker_ip"], tracks, provider, config["sn"],
                   speaker_name=config.get("speaker_name"), config_path=CONFIG_PATH)
    return jsonify({"status": "ok"})


@app.route("/settings")
def settings():
    config = _load_config()
    return render_template("settings.html", config=config)


@app.route("/settings/sonos", methods=["GET", "POST"])
def settings_sonos():
    config = _load_config()
    saved = False
    if request.method == "POST":
        token = request.form.get("csrf_token", "")
        if not token or token != session.get("csrf_token"):
            abort(403)
        config["speaker_ip"] = request.form.get("speaker_ip", config["speaker_ip"])
        config["speaker_name"] = request.form.get("speaker_name", config.get("speaker_name", ""))
        config["sn"] = request.form.get("sn", config["sn"])
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        saved = True
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return render_template("settings_sonos.html", config=config, saved=saved,
                           csrf_token=session["csrf_token"])


@app.route("/settings/music")
def settings_music():
    config = _load_config()
    sonos_cfg = config.get("services", {}).get("sonos", {})
    connected = bool(sonos_cfg.get("access_token") and sonos_cfg.get("household_id"))
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return render_template(
        "settings_music.html",
        config=config,
        sonos_connected=connected,
        sonos_household_id=sonos_cfg.get("household_id", ""),
        csrf_token=session["csrf_token"],
    )


@app.route("/settings/music/credentials", methods=["POST"])
def settings_music_credentials():
    token = request.form.get("csrf_token", "")
    if not token or token != session.get("csrf_token"):
        abort(403)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    cfg.setdefault("services", {}).setdefault("sonos", {})
    cfg["services"]["sonos"]["client_key"] = request.form.get("client_key", "").strip()
    cfg["services"]["sonos"]["client_id"] = request.form.get("client_id", "").strip()
    cfg["services"]["sonos"]["client_secret"] = request.form.get("client_secret", "").strip()
    cfg["services"]["sonos"]["redirect_uri"] = request.form.get("redirect_uri", "").strip()
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return redirect(url_for("settings_music") + "?saved=1")


@app.route("/sonos/auth")
def sonos_auth():
    config = _load_config()
    sonos_cfg = config.get("services", {}).get("sonos", {})
    client_key = sonos_cfg.get("client_key")
    client_secret = sonos_cfg.get("client_secret")
    redirect_uri = sonos_cfg.get("redirect_uri")
    if not (client_key and client_secret and redirect_uri):
        return jsonify({"error": "Sonos client credentials not configured"}), 400

    from providers.sonos_api import SonosControlClient
    client = SonosControlClient(client_key, client_secret)
    state = secrets.token_hex(16)
    session["sonos_oauth_state"] = state
    if request.args.get("show_code"):
        session["sonos_show_code"] = True
    auth_url = client.get_auth_url(redirect_uri, state)
    return redirect(auth_url)


@app.route("/sonos/callback")
def sonos_callback():
    error = request.args.get("error")
    if error:
        log.warning("Sonos OAuth error: %s", error)
        return redirect(url_for("settings_music") + "?error=" + error)

    code = request.args.get("code")
    state = request.args.get("state")
    if not code or state != session.get("sonos_oauth_state"):
        return redirect(url_for("settings_music") + "?error=state_mismatch")

    # Debug mode: show the auth code so it can be tested manually
    if session.pop("sonos_show_code", False):
        from flask import render_template_string
        return render_template_string(
            "<h2>Authorization Code</h2><p>Copy this code to use in the Sonos token test page:</p>"
            "<pre style='font-size:1.2em;padding:12px;background:#f4f4f4'>{{ code }}</pre>"
            "<p><a href='/settings/music'>Back to Settings</a></p>",
            code=code,
        )

    try:
        config = _load_config()
        sonos_cfg = config.get("services", {}).get("sonos", {})
        client_key = sonos_cfg.get("client_key")
        client_secret = sonos_cfg.get("client_secret")
        redirect_uri = sonos_cfg.get("redirect_uri")

        from providers.sonos_api import SonosControlClient
        client = SonosControlClient(client_key, client_secret)
        access_token, refresh_token, _ = client.exchange_code(code, redirect_uri)

        # Get household ID from the local speaker via UPnP (Control API /households
        # requires commercial approval; local UPnP is always available).
        speaker_ip = config.get("speaker_ip", "")
        household_id = _get_household_id_upnp(speaker_ip) if speaker_ip else ""
        if not household_id:
            return redirect(url_for("settings_music") + "?error=no_households")

        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        cfg.setdefault("services", {}).setdefault("sonos", {})
        cfg["services"]["sonos"]["access_token"] = access_token
        cfg["services"]["sonos"]["refresh_token"] = refresh_token
        cfg["services"]["sonos"]["household_id"] = household_id
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)

        _configure_sonos()
        log.info("Sonos account connected (household=%s)", household_id)
    except Exception as e:
        log.error("Sonos OAuth callback failed: %s", e)
        return redirect(url_for("settings_music") + "?error=callback_failed")

    return redirect(url_for("settings_music") + "?connected=1")


@app.route("/sonos/status")
def sonos_status():
    config = _load_config()
    sonos_cfg = config.get("services", {}).get("sonos", {})
    connected = bool(sonos_cfg.get("access_token") and sonos_cfg.get("household_id"))
    return jsonify({
        "connected": connected,
        "household_id": sonos_cfg.get("household_id", "") if connected else "",
    })


@app.route("/sonos/disconnect", methods=["POST"])
def sonos_disconnect():
    token = request.form.get("csrf_token", "")
    if not token or token != session.get("csrf_token"):
        abort(403)
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        cfg.get("services", {}).get("sonos", {}).clear()
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        provider = get_provider("apple")
        provider._sonos_client = None
        provider._sonos_access_token = None
        provider._sonos_refresh_token = None
        provider._sonos_household_id = None
        provider._on_sonos_token_refresh = None
    except Exception as e:
        log.warning("Failed to disconnect Sonos: %s", e)
    return redirect(url_for("settings_music") + "?disconnected=1")


@app.route("/settings/nfc", methods=["GET", "POST"])
def settings_nfc():
    if request.method == "POST":
        config = _load_config()
        token = request.form.get("csrf_token", "")
        if not token or token != session.get("csrf_token"):
            abort(403)
        config["nfc_mode"] = request.form.get("nfc_mode", config["nfc_mode"])
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        return redirect(url_for("settings_hardware", nfc_saved=1))
    return redirect(url_for("settings_hardware"))


@app.route("/settings/sticker")
def settings_sticker():
    return render_template("settings_sticker.html")


@app.route("/settings/reboot", methods=["GET", "POST"])
def settings_reboot():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    if request.method == "POST":
        token = request.form.get("csrf_token", "")
        if not token or token != session.get("csrf_token"):
            abort(403)
        if not IS_PRODUCTION:
            abort(403)
        subprocess.Popen(["sudo", "reboot"])
        return redirect(url_for("settings_hardware", rebooting=1))
    return render_template("settings_reboot.html", rebooting=False,
                           is_production=IS_PRODUCTION,
                           csrf_token=session["csrf_token"])


@app.route("/settings/restart", methods=["POST"])
def settings_restart():
    token = request.form.get("csrf_token", "")
    if not token or token != session.get("csrf_token"):
        abort(403)
    if not IS_PRODUCTION:
        abort(403)
    subprocess.Popen(["sudo", "systemctl", "restart", "vinyl-web"])
    return redirect(url_for("settings_hardware", restarting=1))


@app.route("/settings/hardware")
def settings_hardware():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    restarting = request.args.get("restarting") == "1"
    rebooting = request.args.get("rebooting") == "1"
    nfc_saved = request.args.get("nfc_saved") == "1"
    hw = _get_hardware_stats()
    config = _load_config()
    return render_template("settings_hardware.html", csrf_token=session["csrf_token"],
                           restarting=restarting, rebooting=rebooting, hw=hw,
                           is_production=IS_PRODUCTION, config=config, nfc_saved=nfc_saved)



_PLACEHOLDERS = {
    "storage": ("Storage", "Coming soon - depends on issue #18"),
    "network": ("Network", "Coming soon - depends on issue #19"),
}


def _check_for_update() -> dict:
    """Return update info, using a 1-hour in-memory cache."""
    global _update_cache
    now = time.time()
    if _update_cache and now - _update_cache[0] < _UPDATE_CACHE_TTL:
        return _update_cache[1]

    result = {"current": VERSION, "latest": VERSION, "update_available": False}
    try:
        import requests as _req
        resp = _req.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        if latest:
            result["latest"] = latest
            result["update_available"] = Version(latest) > Version(VERSION)
    except Exception:
        pass  # fail open: return current version, no update available

    _update_cache = (now, result)
    return result


def _read_update_state():
    """Return (state, log_lines) from update.log. state is 'idle' if no log.

    If state is 'running' but the recorded PID is no longer alive, treats the
    state as 'failed' so a crashed updater doesn't permanently show 'updating'.
    """
    if not UPDATE_LOG.exists():
        return "idle", []
    lines = UPDATE_LOG.read_text().splitlines()
    state = "idle"
    pid = None
    for line in lines:
        if line.startswith("PID:"):
            try:
                pid = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        if line.startswith("STATE:"):
            state = line.split(":", 1)[1].strip()
    if state == "running" and pid is not None:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            state = "failed"
    return state, lines[-20:]


@app.route("/settings/update")
def settings_update():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    config = _load_config()
    update_info = _check_for_update() if IS_PRODUCTION else None
    state, log_lines = _read_update_state()
    if state == "success":
        UPDATE_LOG.unlink(missing_ok=True)
    return render_template(
        "settings_update.html",
        csrf_token=session["csrf_token"],
        version=VERSION,
        update_info=update_info,
        is_production=IS_PRODUCTION,
        update_state=state,
        log_lines=log_lines,
        auto_update=config.get("auto_update", False),
        updating=request.args.get("updating") == "1",
    )


@app.route("/update/check")
def update_check():
    if request.args.get("force"):
        global _update_cache
        _update_cache = None
    return jsonify(_check_for_update())


@app.route("/update/apply", methods=["POST"])
def update_apply():
    token = request.form.get("csrf_token", "")
    if not token or token != session.get("csrf_token"):
        abort(403)
    state, _ = _read_update_state()
    if state == "running":
        return jsonify({"error": "Update already in progress"}), 409
    info = _check_for_update()
    target = info.get("latest", VERSION)
    log_file = open(UPDATE_LOG, "w")
    subprocess.Popen(
        [sys.executable, str(UPDATER_PATH), target],
        cwd=str(PROJECT_ROOT),
        start_new_session=True,
        stdout=log_file,
        stderr=log_file,
    )
    return redirect(url_for("settings_update", updating=1))


@app.route("/update/status")
def update_status():
    state, lines = _read_update_state()
    return jsonify({"state": state, "log": lines})


@app.route("/update/auto", methods=["POST"])
def update_auto():
    token = request.form.get("csrf_token", "")
    if not token or token != session.get("csrf_token"):
        abort(403)
    config = _load_config()
    config["auto_update"] = request.form.get("auto_update") == "1"
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    return redirect(url_for("settings_update"))


@app.route("/api/version")
def api_version():
    return jsonify({"version": VERSION})


@app.route("/settings/<section>")
def settings_placeholder(section):
    if section not in _PLACEHOLDERS:
        abort(404)
    title, note = _PLACEHOLDERS[section]
    return render_template("settings_placeholder.html", title=title, note=note)


@app.route("/speakers")
def speakers():
    return jsonify(get_speakers())


@app.route("/read-tag")
def read_tag():
    global _web_read_pending
    config = _load_config()
    tag_string = request.args.get("tag")
    if tag_string is None:
        if config.get("nfc_mode") == "pn532":
            if _nfc is None:
                return jsonify({"tag_string": None, "tag_type": None, "content_id": None,
                                "album": None, "error": "NFC not initialised"})
            _web_read_pending = True
            try:
                tag_string = _nfc_read_queue.get(timeout=8.0)
            except queue.Empty:
                tag_string = None
            finally:
                _web_read_pending = False
                # Drain any stale queued result
                while not _nfc_read_queue.empty():
                    try:
                        _nfc_read_queue.get_nowait()
                    except queue.Empty:  # pragma: no cover
                        break
        else:
            try:
                nfc = _make_nfc(config)
            except RuntimeError as e:
                return jsonify({"tag_string": None, "tag_type": None, "content_id": None,
                                "album": None, "error": str(e)})
            tag_string = nfc.read_tag()
    if tag_string is None:
        return jsonify({"tag_string": None, "tag_type": None, "content_id": None,
                        "album": None, "error": None})
    try:
        tag = parse_tag_data(tag_string)
    except ValueError as e:
        return jsonify({"tag_string": tag_string, "tag_type": None, "content_id": None,
                        "album": None, "error": str(e)})
    tag_type = tag["type"]
    content_id = tag["id"]
    try:
        provider = get_provider(tag["service"])
    except KeyError:
        return jsonify({"tag_string": tag_string, "tag_type": tag_type, "content_id": content_id,
                        "album": None, "error": f"Unknown service: {tag['service']!r}"})
    album = None
    if tag_type == "playlist":
        info = provider.get_playlist_info(content_id)
        if info:
            album = {"name": info["title"], "artist": "", "artwork_url": info.get("artwork_url", "")}
    elif tag_type == "track":
        tracks = provider.get_track(content_id)
        if tracks:
            t = tracks[0]
            album = {"name": t["album"], "artist": t["artist"], "artwork_url": t["artwork_url"]}
    else:
        tracks = provider.get_album_tracks(content_id)
        if tracks:
            t = tracks[0]
            album = {"name": t["album"], "artist": t["artist"], "artwork_url": t["artwork_url"]}
    return jsonify({"tag_string": tag_string, "tag_type": tag_type, "content_id": content_id,
                    "album": album, "error": None})



@app.route("/detect-sn")
def detect_sn():
    speaker_ip = request.args.get("speaker_ip") or _load_config().get("speaker_ip", "")
    if not speaker_ip:
        return jsonify({"error": "no speaker configured"}), 400
    sn = get_provider("apple").detect_sn(soco.SoCo(speaker_ip))
    if sn is None:
        return jsonify({"error": "No Apple Music favorites found in Sonos - enter 3 or 5 manually"}), 404
    return jsonify({"sn": sn})



@app.route("/now-playing")
def now_playing():
    config = _load_config()
    if not config.get("speaker_ip"):
        return jsonify({"playing": False})
    info = get_now_playing(config["speaker_ip"])
    if info is None:
        return jsonify({"playing": False})
    result = {
        "playing": True,
        "paused": info["paused"],
        "title": info["title"],
        "artist": info["artist"],
        "album": info["album"],
        "track_id": info["track_id"],
        "album_id": None,
        "artwork_url": None,
    }
    if info["track_id"]:
        try:
            tracks = get_provider("apple").get_track(info["track_id"])
            if tracks:
                result["album_id"] = tracks[0].get("album_id")
                result["artwork_url"] = tracks[0].get("artwork_url")
        except Exception:
            pass  # transient network error - return what we have
    result["volume"] = get_volume(config["speaker_ip"])
    return jsonify(result)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/transport", methods=["POST"])
def transport():
    data = request.get_json()
    action = data.get("action") if data else None
    if action not in ("pause", "resume", "stop", "next", "prev", "volume"):
        return jsonify({"error": "invalid action"}), 400
    config = _load_config()
    name = config.get("speaker_name")
    if action == "pause":
        pause(config["speaker_ip"], speaker_name=name, config_path=CONFIG_PATH)
    elif action == "resume":
        resume(config["speaker_ip"], speaker_name=name, config_path=CONFIG_PATH)
    elif action == "next":
        next_track(config["speaker_ip"], speaker_name=name, config_path=CONFIG_PATH)
    elif action == "prev":
        prev_track(config["speaker_ip"], speaker_name=name, config_path=CONFIG_PATH)
    elif action == "volume":
        value = data.get("value")
        if value is None or not (0 <= int(value) <= 100):
            return jsonify({"error": "value must be 0-100"}), 400
        set_volume(config["speaker_ip"], value, speaker_name=name, config_path=CONFIG_PATH)
    else:
        stop(config["speaker_ip"], speaker_name=name, config_path=CONFIG_PATH)
    return jsonify({"status": "ok", "action": action})


@app.route("/play/tag", methods=["POST"])
def play_tag():
    data = request.get_json()
    tag_string = data.get("tag") if data else None
    if not tag_string:
        return jsonify({"error": "tag required"}), 400
    try:
        tag = parse_tag_data(tag_string)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    config = _load_config()
    try:
        provider = get_provider(tag["service"])
    except KeyError as e:
        return jsonify({"error": str(e)}), 400
    if tag["type"] == "playlist":
        info = provider.get_playlist_info(tag["id"]) or {}
        play_playlist(config["speaker_ip"], tag["id"], info.get("title", ""),
                      provider, config["sn"],
                      speaker_name=config.get("speaker_name"), config_path=CONFIG_PATH)
    else:
        if tag["type"] == "track":
            tracks = provider.get_track(tag["id"])
        else:
            tracks = provider.get_album_tracks(tag["id"])
        if not tracks:
            return jsonify({"error": "not found"}), 404
        play_album(config["speaker_ip"], tracks, provider, config["sn"],
                   speaker_name=config.get("speaker_name"), config_path=CONFIG_PATH)
    return jsonify({"status": "ok"})


@app.route("/collection")
def collection():
    return render_template("collection.html", tags=_load_tags())


@app.route("/collection/delete", methods=["POST"])
def collection_delete():
    data = request.get_json()
    tag_string = data.get("tag_string") if data else None
    if not tag_string:
        return jsonify({"error": "tag_string required"}), 400
    tags = [t for t in _load_tags() if t["tag_string"] != tag_string]
    _save_tags(tags)
    return jsonify({"status": "ok"})


@app.route("/collection/clear", methods=["POST"])
def collection_clear():
    _save_tags([])
    return jsonify({"status": "ok"})


@app.route("/verify")
def verify():
    config = _load_config()
    return render_template("verify.html", nfc_mode=config.get("nfc_mode", "mock"))


@app.route("/logs")
def logs():
    try:
        result = subprocess.run(
            ["journalctl", "-u", "vinyl-web", "-n", "200", "--no-pager", "--output=short-iso"],
            capture_output=True, text=True, timeout=5,
        )
        log_output = result.stdout or "(no log output)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log_output = None
    return render_template("logs.html", log_output=log_output)


def _auto_update_loop():
    """Check once per hour and apply update automatically if auto_update=true."""
    while True:
        time.sleep(3600)
        try:
            config = _load_config()
            if not config.get("auto_update"):
                continue
            info = _check_for_update()
            if not info.get("update_available"):
                continue
            state, _ = _read_update_state()
            if state == "running":
                continue
            target = info["latest"]
            log_file = open(UPDATE_LOG, "w")
            subprocess.Popen(
                [sys.executable, str(UPDATER_PATH), target],
                cwd=str(PROJECT_ROOT),
                start_new_session=True,
                stdout=log_file,
                stderr=log_file,
            )
        except Exception:
            pass


def _sigterm_handler(signum, frame):
    """Wait for any in-progress NFC I2C operation to finish before exiting.

    Without this, SIGTERM (from `systemctl restart`) can kill the process
    mid-I2C-transfer, leaving the PN532 clock-stretching and the bus hung.
    The next start then fails with 'No I2C device at address: 0x24'.
    """
    _nfc_lock.acquire(timeout=2.0)
    sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("providers.sonos_api").setLevel(logging.DEBUG)
    signal.signal(signal.SIGTERM, _sigterm_handler)
    parser = argparse.ArgumentParser(description="Vinyl emulator web UI")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind to (use 0.0.0.0 for Pi)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port to listen on (use 80 with authbind on Pi)")
    parser.add_argument("--ssl-cert", metavar="CERT",
                        help="SSL certificate file (enables HTTPS)")
    parser.add_argument("--ssl-key", metavar="KEY",
                        help="SSL private key file (enables HTTPS)")
    args = parser.parse_args()
    ssl_context = None
    if args.ssl_cert and args.ssl_key:
        ssl_context = (args.ssl_cert, args.ssl_key)
    _configure_sonos()
    _configure_smapi()
    _start_nfc_thread(CONFIG_PATH)
    threading.Thread(target=_auto_update_loop, daemon=True).start()
    # Suppress werkzeug "development server" warning — this is a single-user
    # Pi appliance, not a multi-tenant web service.
    logging.getLogger("werkzeug").addFilter(
        type("", (logging.Filter,), {
            "filter": staticmethod(
                lambda r: "development server" not in r.getMessage()
            )
        })()
    )
    app.run(host=args.host, port=args.port, ssl_context=ssl_context)
