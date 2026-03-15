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

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

import soco
from core.nfc_interface import MockNFC, PN532NFC, parse_tag_data
from providers import get_provider
from core.sonos_player import get_now_playing, get_speakers, get_volume, next_track, pause, play_album, play_playlist, prev_track, resume, set_volume, stop

import core.nfc_service as nfc_service
import core.updater_service as updater_service
from core.config import CONFIG_PATH, TAGS_PATH, PROJECT_ROOT, VERSION, _load_config, _save_config, _load_tags, _save_tags
from core.updater_service import _check_for_update, _read_update_state, _auto_update_loop

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

IS_PRODUCTION = "INVOCATION_ID" in os.environ

log = logging.getLogger(__name__)

_CONFIG_ERROR_PHRASES = (
    "Config file not found",
    "Config file is not valid JSON",
    "Missing required config fields",
)


@app.errorhandler(RuntimeError)
def handle_config_error(e):
    msg = str(e)
    if any(phrase in msg for phrase in _CONFIG_ERROR_PHRASES):
        log.warning("Config error in request %s: %s", request.path, msg)
        return jsonify({"error": msg}), 503
    raise e


@app.context_processor
def _inject_version():
    return {"app_version": VERSION}


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
        log.warning("Could not get household ID from speaker: %s", e, exc_info=True)
        return ""


def _configure_sonos():
    """If Sonos Control API tokens are present in config, configure providers."""
    try:
        config = _load_config()
    except Exception as e:
        log.warning("_configure_sonos: failed to load config: %s", e, exc_info=True)
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
            cfg = _load_config()
            cfg.setdefault("services", {}).setdefault("sonos", {})
            cfg["services"]["sonos"]["access_token"] = new_access_token
            cfg["services"]["sonos"]["refresh_token"] = new_refresh_token
            _save_config(cfg)
            log.info("Persisted refreshed Sonos token to config")
        except Exception as e:
            log.error("Failed to persist Sonos token: %s", e, exc_info=True)

    provider = get_provider("apple")
    provider.configure_sonos(
        client, access_token, refresh_token, household_id,
        on_token_refresh=_on_sonos_token_refresh,
    )


def _configure_smapi():
    """If SMAPI tokens are present in config, configure the Apple Music provider."""
    try:
        config = _load_config()
    except Exception as e:
        log.warning("_configure_smapi: failed to load config: %s", e, exc_info=True)
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
            cfg = _load_config()
            cfg.setdefault("services", {}).setdefault("apple", {})
            cfg["services"]["apple"]["smapi_token"] = new_token
            cfg["services"]["apple"]["smapi_key"] = new_key
            _save_config(cfg)
            log.info("Persisted refreshed SMAPI token to config")
        except Exception as e:
            log.error("Failed to persist SMAPI token: %s", e, exc_info=True)

    provider = get_provider("apple")
    provider.configure_smapi(token, key, hhid, on_token_refresh=_on_token_refresh)
    log.info("Apple Music SMAPI search enabled (household=%s)", hhid)


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"  # pragma: no cover


def _safe(fn):
    """Call fn(), returning None if any exception is raised."""
    try:
        return fn()
    except Exception:
        return None


def _read_os_release():
    with open("/etc/os-release") as f:
        pairs = {}
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                pairs[k] = v.strip('"')
    return pairs.get("PRETTY_NAME")


def _read_uptime():
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
    return " ".join(parts)


def _read_cpu_model():
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.startswith("Model"):
                return line.split(":", 1)[1].strip()
    return None


def _read_cpu_temp():
    with open("/sys/class/thermal/thermal_zone0/temp") as f:
        return round(int(f.read().strip()) / 1000, 1)


def _read_throttle():
    """Return (throttle_ok, flags) tuple from vcgencmd, or raise on failure."""
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
    return throttled == 0, flags


def _get_hardware_stats():
    mem = _safe(psutil.virtual_memory)
    swap = _safe(psutil.swap_memory)
    disk = _safe(lambda: psutil.disk_usage("/"))
    freq = _safe(psutil.cpu_freq)
    throttle = _safe(_read_throttle)
    return {
        "hostname":       _safe(lambda: os.uname().nodename),
        "os":             _safe(_read_os_release),
        "kernel":         _safe(lambda: os.uname().release),
        "uptime":         _safe(_read_uptime),
        "cpu_model":      _safe(_read_cpu_model),
        "cpu_cores":      _safe(lambda: psutil.cpu_count(logical=False) or psutil.cpu_count()),
        "cpu_percent":    _safe(lambda: psutil.cpu_percent(interval=0.1)),
        "cpu_freq_mhz":   round(freq.current) if freq else None,
        "cpu_temp_c":     _safe(_read_cpu_temp),
        "ram_used":       _fmt_bytes(mem.used) if mem else None,
        "ram_total":      _fmt_bytes(mem.total) if mem else None,
        "ram_percent":    mem.percent if mem else None,
        "swap_used":      _fmt_bytes(swap.used) if swap else None,
        "swap_total":     _fmt_bytes(swap.total) if swap else None,
        "disk_used":      _fmt_bytes(disk.used) if disk else None,
        "disk_free":      _fmt_bytes(disk.free) if disk else None,
        "disk_total":     _fmt_bytes(disk.total) if disk else None,
        "disk_percent":   disk.percent if disk else None,
        "nfc_connected":  nfc_service.get_nfc() is not None,
        "throttle_ok":    throttle[0] if throttle else None,
        "throttle_flags": throttle[1] if throttle else None,
    }



def _record_tag(tag_string, tag_type, name, artist, artwork_url, album_id=None, track_id=None, playlist_id=None):
    parse_tag_data(tag_string)  # raises ValueError if structurally invalid
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
    except KeyError as e:
        log.debug("Unknown provider for tag %s: %s", tag_string, e)
    except Exception as e:
        log.debug("Could not resolve display name for %s: %s", tag_string, e)
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
        if nfc_service.get_nfc() is None:
            return jsonify({"error": "NFC not initialised"}), 503
        acquired = nfc_service._nfc_lock.acquire(timeout=2.0)
        if not acquired:
            return jsonify({"error": "NFC busy, try again"}), 503
        try:
            pre_read = nfc_service.get_nfc().read_tag()
            if not force and pre_read:
                return jsonify({
                    "status": "confirm",
                    "existing": pre_read,
                    "existing_display": _format_existing_tag(pre_read),
                })
            try:
                nfc_service.get_nfc().write_tag(tag_data)
            except IOError as e:
                if pre_read is None:
                    return jsonify({"error": "No tag present - place a card on the reader"}), 409
                return jsonify({"error": str(e)}), 409
        finally:
            nfc_service._nfc_lock.release()
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
    except Exception as e:
        log.warning("Failed to record tag metadata for %s: %s", tag_data, e)
    return jsonify({"status": "ok", "written": tag_data})


@app.route("/write-url-tag", methods=["POST"])
def write_url_tag():
    url = request.host_url.rstrip("/")
    config = _load_config()
    if config.get("nfc_mode") == "pn532":
        if nfc_service.get_nfc() is None:
            return jsonify({"error": "NFC not initialised"}), 503
        acquired = nfc_service._nfc_lock.acquire(timeout=2.0)
        if not acquired:
            return jsonify({"error": "NFC busy, try again"}), 503
        try:
            pre_read = nfc_service.get_nfc().read_tag()
            try:
                nfc_service.get_nfc().write_url_tag(url)
            except NotImplementedError as e:
                return jsonify({"error": str(e)}), 501
            except IOError as e:
                if pre_read is None:
                    return jsonify({"error": "No tag present - place a card on the reader"}), 409
                return jsonify({"error": str(e)}), 409
        finally:
            nfc_service._nfc_lock.release()
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
        _save_config(config)
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
    cfg = _load_config()
    cfg.setdefault("services", {}).setdefault("sonos", {})
    cfg["services"]["sonos"]["client_key"] = request.form.get("client_key", "").strip()
    cfg["services"]["sonos"]["client_id"] = request.form.get("client_id", "").strip()
    cfg["services"]["sonos"]["client_secret"] = request.form.get("client_secret", "").strip()
    cfg["services"]["sonos"]["redirect_uri"] = request.form.get("redirect_uri", "").strip()
    _save_config(cfg)
    return redirect(url_for("settings_music") + "?saved=1")


@app.route("/sonos/auth")
def sonos_auth():
    try:
        config = _load_config()
    except Exception as e:
        log.error("sonos_auth: failed to load config: %s", e, exc_info=True)
        return jsonify({"error": "Configuration error"}), 500
    sonos_cfg = config.get("services", {}).get("sonos", {})
    client_key = sonos_cfg.get("client_key")
    client_secret = sonos_cfg.get("client_secret")
    redirect_uri = sonos_cfg.get("redirect_uri")
    if not (client_key and client_secret and redirect_uri):
        return jsonify({"error": "Sonos client credentials not configured"}), 400

    try:
        from providers.sonos_api import SonosControlClient
        client = SonosControlClient(client_key, client_secret)
    except Exception as e:
        log.error("sonos_auth: failed to create Sonos client: %s", e, exc_info=True)
        return jsonify({"error": "Failed to initialise Sonos client"}), 500
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

        cfg = _load_config()
        cfg.setdefault("services", {}).setdefault("sonos", {})
        cfg["services"]["sonos"]["access_token"] = access_token
        cfg["services"]["sonos"]["refresh_token"] = refresh_token
        cfg["services"]["sonos"]["household_id"] = household_id
        _save_config(cfg)

        _configure_sonos()
        log.info("Sonos account connected (household=%s)", household_id)
    except Exception as e:
        log.error("Sonos OAuth callback failed: %s", e, exc_info=True)
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
        cfg = _load_config()
        cfg.get("services", {}).get("sonos", {}).clear()
        _save_config(cfg)
        provider = get_provider("apple")
        provider._sonos_client = None
        provider._sonos_access_token = None
        provider._sonos_refresh_token = None
        provider._sonos_household_id = None
        provider._on_sonos_token_refresh = None
    except Exception as e:
        log.warning("Failed to disconnect Sonos: %s", e, exc_info=True)
    return redirect(url_for("settings_music") + "?disconnected=1")


@app.route("/settings/nfc", methods=["GET", "POST"])
def settings_nfc():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    if request.method == "POST":
        config = _load_config()
        token = request.form.get("csrf_token", "")
        if not token or token != session.get("csrf_token"):
            abort(403)
        config["nfc_mode"] = request.form.get("nfc_mode", config["nfc_mode"])
        _save_config(config)
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
        try:
            subprocess.Popen(["sudo", "reboot"])
        except OSError as e:
            log.error("Failed to launch reboot: %s", e, exc_info=True)
            abort(500)
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
    try:
        subprocess.Popen(["sudo", "systemctl", "restart", "vinyl-web"])
    except OSError as e:
        log.error("Failed to launch restart: %s", e, exc_info=True)
        abort(500)
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


@app.route("/settings/update")
def settings_update():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    config = _load_config()
    update_info = _check_for_update() if IS_PRODUCTION else None
    state, log_lines = _read_update_state()
    if state == "success":
        updater_service.UPDATE_LOG.unlink(missing_ok=True)
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
        updater_service.clear_update_cache()
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
    with open(updater_service.UPDATE_LOG, "w") as log_file:
        subprocess.Popen(
            [sys.executable, str(updater_service.UPDATER_PATH), target],
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
    _save_config(config)
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
    config = _load_config()
    tag_string = request.args.get("tag")
    if tag_string is None:
        if config.get("nfc_mode") == "pn532":
            nfc_service._web_read_pending.set()
            try:
                if nfc_service.get_nfc() is None:
                    nfc_service._web_read_pending.clear()
                    return jsonify({"tag_string": None, "tag_type": None, "content_id": None,
                                    "album": None, "error": "NFC not initialised"})
                tag_string = nfc_service._nfc_read_queue.get(timeout=8.0)
            except queue.Empty:
                tag_string = None
            finally:
                nfc_service._web_read_pending.clear()
                # Drain any stale queued result
                while not nfc_service._nfc_read_queue.empty():
                    try:
                        nfc_service._nfc_read_queue.get_nowait()
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
    try:
        sn = get_provider("apple").detect_sn(soco.SoCo(speaker_ip))
    except Exception as e:
        log.warning("detect_sn failed for %s: %s", speaker_ip, e)
        return jsonify({"error": "Failed to detect serial number"}), 500
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
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("Could not fetch logs: %s", e)
        log_output = f"(Could not fetch logs: {e})"
    return render_template("logs.html", log_output=log_output)


def _sigterm_handler(signum, frame):
    """Wait for any in-progress NFC I2C operation to finish before exiting.

    Without this, SIGTERM (from `systemctl restart`) can kill the process
    mid-I2C-transfer, leaving the PN532 clock-stretching and the bus hung.
    The next start then fails with 'No I2C device at address: 0x24'.
    """
    nfc_service._nfc_lock.acquire(timeout=2.0)
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
    nfc_service._start_nfc_thread(CONFIG_PATH)
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
