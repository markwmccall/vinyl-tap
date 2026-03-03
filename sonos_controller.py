import html
import json
import re
import xml.sax.saxutils as saxutils
import soco
from apple_music import build_track_uri

_APPLE_MUSIC_SERVICE_TYPE = "52231"  # = 204 * 256 + 7


def get_speakers():
    devices = soco.discover() or []
    return [{"name": d.player_name, "ip": d.ip_address} for d in devices]


def _rediscover_speaker(speaker_name, config_path):
    """Find speaker by room name via multicast discovery, update speaker_ip in
    config.json, and return the new IP address.

    Called automatically when a Sonos operation fails — handles the case where
    DHCP assigned a new IP to the speaker since it was last saved in config.
    """
    devices = soco.discover() or set()
    for d in devices:
        if d.player_name == speaker_name:
            with open(config_path) as f:
                config = json.load(f)
            config["speaker_ip"] = d.ip_address
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            return d.ip_address
    raise Exception(f"Speaker '{speaker_name}' not found on network")


def _lookup_apple_music_udn(speaker, sn):
    """Find the Apple Music account UDN for the given serial number by scanning
    Sonos favorites, which store the full authenticated account UDN in their
    DIDL metadata. Falls back to the bare service-type UDN if not found.
    """
    fallback = f"SA_RINCON{_APPLE_MUSIC_SERVICE_TYPE}_"
    try:
        result = speaker.contentDirectory.Browse([
            ("ObjectID", "FV:2"),
            ("BrowseFlag", "BrowseDirectChildren"),
            ("Filter", "*"),
            ("StartingIndex", 0),
            ("RequestedCount", 100),
            ("SortCriteria", ""),
        ])
        data = result.get("Result", "")
        for res_uri, resmd_raw in re.findall(
            r"<[^>]+:res[^>]*>([^<]*)</[^>]+:res>.*?<[^>]+:resMD>([^<]*)</[^>]+:resMD>",
            data,
            re.DOTALL,
        ):
            if f"sn={sn}" not in res_uri:
                continue
            decoded = html.unescape(resmd_raw)
            m = re.search(
                r"SA_RINCON" + _APPLE_MUSIC_SERVICE_TYPE + r"[^<\"&\s]{0,80}", decoded
            )
            if m:
                return m.group(0)
    except Exception:
        pass
    return fallback


def _build_track_didl(track, udn):
    """Build DIDL-Lite metadata matching the native Sonos app format.

    Uses the Sonos content-browser item ID format (10032028song%3a{track_id})
    so Sonos can resolve the SMAPI GetMediaMetadata call and populate the
    queue with full title/artist/album metadata from Apple Music.
    """
    e = saxutils.escape
    item_id = f"10032028song%3a{track['track_id']}"
    return (
        '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
        ' xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"'
        ' xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        f'<item id="{item_id}" parentID="{item_id}" restricted="true">'
        f'<dc:title>{e(track["name"])}</dc:title>'
        '<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
        f'<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{e(udn)}</desc>'
        '</item>'
        '</DIDL-Lite>'
    )


def detect_apple_music_sn(speaker_ip):
    """Scan Sonos favorites for an Apple Music URI and extract the sn value.

    Returns the sn as a string, or None if not found (e.g., no Apple Music
    favorites saved in Sonos).
    """
    speaker = soco.SoCo(speaker_ip)
    try:
        result = speaker.contentDirectory.Browse([
            ("ObjectID", "FV:2"),
            ("BrowseFlag", "BrowseDirectChildren"),
            ("Filter", "*"),
            ("StartingIndex", 0),
            ("RequestedCount", 100),
            ("SortCriteria", ""),
        ])
        data = result.get("Result", "")
        for res_uri in re.findall(r"<(?:[^>]+:)?res[^>]*>([^<]*)</(?:[^>]+:)?res>", data):
            uri = html.unescape(res_uri)
            if "sid=204" not in uri:
                continue
            m = re.search(r"[?&]sn=(\d+)", uri)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def get_now_playing(speaker_ip):
    """Return info about the current track, or None if stopped.

    Checks transport state first so paused tracks are still shown.
    """
    try:
        speaker = soco.SoCo(speaker_ip)
        transport = speaker.get_current_transport_info()
        state = transport.get("current_transport_state", "STOPPED")
        if state not in ("PLAYING", "PAUSED_PLAYBACK", "TRANSITIONING"):
            return None
        info = speaker.get_current_track_info()
        if not info.get("title"):
            return None
        track_id = None
        m = re.search(r"song%3[aA](\d+)\.mp4", info.get("uri", ""))
        if m and "sid=204" in info.get("uri", ""):
            track_id = int(m.group(1))
        return {
            "title": info["title"],
            "artist": info.get("artist", ""),
            "album": info.get("album", ""),
            "track_id": track_id,
            "paused": state == "PAUSED_PLAYBACK",
        }
    except Exception:
        return None


def pause(speaker_ip, speaker_name=None, config_path=None):
    try:
        soco.SoCo(speaker_ip).pause()
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            soco.SoCo(new_ip).pause()
        else:
            raise


def resume(speaker_ip, speaker_name=None, config_path=None):
    try:
        soco.SoCo(speaker_ip).play()
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            soco.SoCo(new_ip).play()
        else:
            raise


def stop(speaker_ip, speaker_name=None, config_path=None):
    try:
        soco.SoCo(speaker_ip).stop()
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            soco.SoCo(new_ip).stop()
        else:
            raise


def next_track(speaker_ip, speaker_name=None, config_path=None):
    try:
        soco.SoCo(speaker_ip).next()
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            soco.SoCo(new_ip).next()
        else:
            raise


def prev_track(speaker_ip, speaker_name=None, config_path=None):
    try:
        soco.SoCo(speaker_ip).previous()
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            soco.SoCo(new_ip).previous()
        else:
            raise


def _do_play_album(speaker, track_dicts, sn):
    udn = _lookup_apple_music_udn(speaker, sn)
    speaker.clear_queue()
    for track in track_dicts:
        uri = build_track_uri(track["track_id"], sn)
        metadata = _build_track_didl(track, udn)
        speaker.avTransport.AddURIToQueue([
            ("InstanceID", 0),
            ("EnqueuedURI", uri),
            ("EnqueuedURIMetaData", metadata),
            ("DesiredFirstTrackNumberEnqueued", 0),
            ("EnqueueAsNext", 0),
        ])
    speaker.play_from_queue(0)


def play_album(speaker_ip, track_dicts, sn, speaker_name=None, config_path=None):
    if not track_dicts:
        return
    try:
        _do_play_album(soco.SoCo(speaker_ip), track_dicts, sn)
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            _do_play_album(soco.SoCo(new_ip), track_dicts, sn)
        else:
            raise
