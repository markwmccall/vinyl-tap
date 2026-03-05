import argparse
import json
import logging
import os
import secrets
import threading
from datetime import datetime

from flask import Flask, abort, jsonify, render_template, request, session

import apple_music
from nfc_interface import MockNFC, PN532NFC, parse_tag_data
from sonos_controller import detect_apple_music_sn, get_now_playing, get_speakers, get_volume, next_track, pause, play_album, prev_track, resume, set_volume, stop

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
TAGS_PATH = os.path.join(os.path.dirname(__file__), "tags.json")

log = logging.getLogger(__name__)

# Shared NFC device and lock used by the background polling thread and web routes.
_nfc_lock = threading.Lock()
_nfc = None


def _load_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    required = ["speaker_ip", "sn", "nfc_mode"]
    missing = [k for k in required if k not in config]
    if missing:
        raise RuntimeError(f"Missing required config fields: {', '.join(missing)}")
    return config



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


def _record_tag(tag_string, tag_type, name, artist, artwork_url, album_id=None, track_id=None):
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
        "written_at": datetime.utcnow().isoformat(),
    })
    _save_tags(tags)


def _make_nfc(config):
    if config.get("nfc_mode") == "pn532":
        try:
            return PN532NFC()
        except ImportError:
            raise RuntimeError(
                "PN532 hardware libraries not installed — "
                "run setup.sh on a Raspberry Pi to install them"
            )
    return MockNFC()


def _nfc_loop(config_path):
    """Background NFC polling loop with debounce. Runs in a daemon thread.

    Holds _nfc_lock only during the I2C read (up to 0.5 s). Releases it
    before calling play_album so web routes never wait on a Sonos network call.
    """
    last_tag = None
    while True:
        try:
            with _nfc_lock:
                tag_data = _nfc.read_tag()
        except Exception as e:
            log.error(f"NFC read error: {e}")
            continue

        if tag_data is None:
            last_tag = None
            continue

        if tag_data == last_tag:
            continue  # same card still present — ignore

        last_tag = tag_data
        try:
            tag = parse_tag_data(tag_data)
            tracks = (apple_music.get_track(tag["id"]) if tag["type"] == "track"
                      else apple_music.get_album_tracks(tag["id"]))
            config = _load_config()
            play_album(config["speaker_ip"], tracks, config["sn"],
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
        if tag["type"] == "track":
            tracks = apple_music.get_track(tag["id"])
            if tracks:
                return f"{tracks[0]['name']} by {tracks[0]['artist']}"
        else:
            tracks = apple_music.get_album_tracks(tag["id"])
            if tracks:
                return f"{tracks[0]['album']} by {tracks[0]['artist']}"
    except Exception:
        pass
    return tag_string


def _do_record_tag(tag_data, data):
    if "track_id" in data:
        tracks = apple_music.get_track(data["track_id"])
        if tracks:
            t = tracks[0]
            _record_tag(tag_data, "track", t["name"], t["artist"],
                        t.get("artwork_url", ""), album_id=t.get("album_id"),
                        track_id=t["track_id"])
    else:
        tracks = apple_music.get_album_tracks(data["album_id"])
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
    if not q:
        return jsonify([])
    if search_type == "song":
        return jsonify(apple_music.search_songs(q))
    return jsonify(apple_music.search_albums(q))


@app.route("/album/<int:album_id>")
def album(album_id):
    tracks = apple_music.get_album_tracks(album_id)
    if not tracks:
        abort(404)
    return render_template("album.html", album_id=album_id, tracks=tracks)


@app.route("/track/<int:track_id>")
def track(track_id):
    tracks = apple_music.get_track(track_id)
    if not tracks:
        abort(404)
    return render_template("track.html", track_id=track_id, track=tracks[0])


@app.route("/print")
def print_inserts():
    ids_param = request.args.get("ids", "")
    if not ids_param:
        abort(400)
    album_ids = [int(i) for i in ids_param.split(",") if i.strip().isdigit()]
    if not album_ids:
        abort(400)
    albums = []
    for album_id in album_ids:
        tracks = apple_music.get_album_tracks(album_id)
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
    if not data or ("track_id" not in data and "album_id" not in data):
        return jsonify({"error": "album_id or track_id required"}), 400
    config = _load_config()
    tag_data = (f"apple:track:{data['track_id']}" if "track_id" in data
                else f"apple:{data['album_id']}")
    force = data.get("force", False)

    if config.get("nfc_mode") == "pn532":
        if _nfc is None:
            return jsonify({"error": "NFC not initialised"}), 503
        acquired = _nfc_lock.acquire(timeout=2.0)
        if not acquired:
            return jsonify({"error": "NFC busy, try again"}), 503
        try:
            if not force:
                existing = _nfc.read_tag()
                if existing:
                    return jsonify({
                        "status": "confirm",
                        "existing": existing,
                        "existing_display": _format_existing_tag(existing),
                    })
            try:
                _nfc.write_tag(tag_data)
            except IOError as e:
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
            try:
                _nfc.write_url_tag(url)
            except NotImplementedError as e:
                return jsonify({"error": str(e)}), 501
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
    if not data or ("track_id" not in data and "album_id" not in data):
        return jsonify({"error": "album_id or track_id required"}), 400
    config = _load_config()
    if "track_id" in data:
        tracks = apple_music.get_track(data["track_id"])
    else:
        tracks = apple_music.get_album_tracks(data["album_id"])
    if not tracks:
        return jsonify({"error": "not found"}), 404
    play_album(config["speaker_ip"], tracks, config["sn"],
               speaker_name=config.get("speaker_name"), config_path=CONFIG_PATH)
    return jsonify({"status": "ok"})


@app.route("/settings", methods=["GET", "POST"])
def settings():
    config = _load_config()
    saved = False
    if request.method == "POST":
        token = request.form.get("csrf_token", "")
        if not token or token != session.get("csrf_token"):
            abort(403)
        config["sn"] = request.form.get("sn", config["sn"])
        config["speaker_ip"] = request.form.get("speaker_ip", config["speaker_ip"])
        config["speaker_name"] = request.form.get("speaker_name", config.get("speaker_name", ""))
        config["nfc_mode"] = request.form.get("nfc_mode", config["nfc_mode"])
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        saved = True
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return render_template("settings.html", config=config, saved=saved,
                           csrf_token=session["csrf_token"])


@app.route("/speakers")
def speakers():
    return jsonify(get_speakers())


@app.route("/read-tag")
def read_tag():
    config = _load_config()
    tag_string = request.args.get("tag")
    if tag_string is None:
        if config.get("nfc_mode") == "pn532":
            if _nfc is None:
                return jsonify({"tag_string": None, "tag_type": None, "content_id": None,
                                "album": None, "error": "NFC not initialised"})
            acquired = _nfc_lock.acquire(timeout=2.0)
            if not acquired:
                return jsonify({"tag_string": None, "tag_type": None, "content_id": None,
                                "album": None, "error": "NFC busy, try again"})
            try:
                tag_string = _nfc.read_tag()
            finally:
                _nfc_lock.release()
        else:
            try:
                nfc = _make_nfc(config)
            except RuntimeError as e:
                return jsonify({"tag_string": None, "tag_type": None, "content_id": None,
                                "album": None, "error": str(e)})
            tag_string = nfc.read_tag()
    try:
        tag = parse_tag_data(tag_string)
    except ValueError as e:
        return jsonify({"tag_string": tag_string, "tag_type": None, "content_id": None,
                        "album": None, "error": str(e)})
    tag_type = tag["type"]
    content_id = tag["id"]
    if tag_type == "track":
        tracks = apple_music.get_track(content_id)
    else:
        tracks = apple_music.get_album_tracks(content_id)
    album = None
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
    sn = detect_apple_music_sn(speaker_ip)
    if sn is None:
        return jsonify({"error": "No Apple Music favorites found in Sonos — enter 3 or 5 manually"}), 404
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
        tracks = apple_music.get_track(info["track_id"])
        if tracks:
            result["album_id"] = tracks[0].get("album_id")
            result["artwork_url"] = tracks[0].get("artwork_url")
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
    if tag["type"] == "track":
        tracks = apple_music.get_track(tag["id"])
    else:
        tracks = apple_music.get_album_tracks(tag["id"])
    if not tracks:
        return jsonify({"error": "not found"}), 404
    play_album(config["speaker_ip"], tracks, config["sn"],
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vinyl emulator web UI")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind to (use 0.0.0.0 for Pi)")
    args = parser.parse_args()
    _start_nfc_thread(CONFIG_PATH)
    app.run(host=args.host, port=5000)
