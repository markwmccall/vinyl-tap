import json
import re
import soco


def get_speakers():
    devices = soco.discover() or []
    return [{"name": d.player_name, "ip": d.ip_address} for d in devices]


def _rediscover_speaker(speaker_name, config_path):
    """Find speaker by room name via multicast discovery, update speaker_ip in
    config.json, and return the new IP address.

    Called automatically when a Sonos operation fails - handles the case where
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
        m = re.search(r"song(?:%3[aA]|:)(\d+)(?:\.mp4)?", info.get("uri", ""))
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


def get_volume(speaker_ip):
    try:
        return soco.SoCo(speaker_ip).volume
    except Exception:
        return None


def set_volume(speaker_ip, value, speaker_name=None, config_path=None):
    try:
        soco.SoCo(speaker_ip).volume = int(value)
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            soco.SoCo(new_ip).volume = int(value)
        else:
            raise


def _do_play_album(speaker, track_dicts, provider, sn):
    coordinator = speaker.group.coordinator
    udn = provider.lookup_udn(coordinator, sn)
    coordinator.clear_queue()
    for track in track_dicts:
        uri = provider.build_track_uri(track["track_id"], sn)
        metadata = provider.build_track_didl(track, udn)
        coordinator.avTransport.AddURIToQueue([
            ("InstanceID", 0),
            ("EnqueuedURI", uri),
            ("EnqueuedURIMetaData", metadata),
            ("DesiredFirstTrackNumberEnqueued", 0),
            ("EnqueueAsNext", 0),
        ])
    coordinator.play_from_queue(0)


def _do_play_playlist(speaker, playlist_id, title, provider, sn):
    coordinator = speaker.group.coordinator
    udn = provider.lookup_udn(coordinator, sn)
    uri = provider.build_playlist_uri(playlist_id, sn)
    metadata = provider.build_playlist_didl(playlist_id, title, udn)
    coordinator.avTransport.SetAVTransportURI([
        ("InstanceID", 0),
        ("CurrentURI", uri),
        ("CurrentURIMetaData", metadata),
    ])
    coordinator.avTransport.Play([("InstanceID", 0), ("Speed", 1)])


def play_playlist(speaker_ip, playlist_id, title, provider, sn, speaker_name=None, config_path=None):
    try:
        _do_play_playlist(soco.SoCo(speaker_ip), playlist_id, title, provider, sn)
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            _do_play_playlist(soco.SoCo(new_ip), playlist_id, title, provider, sn)
        else:
            raise


def play_album(speaker_ip, track_dicts, provider, sn, speaker_name=None, config_path=None):
    if not track_dicts:
        return
    try:
        _do_play_album(soco.SoCo(speaker_ip), track_dicts, provider, sn)
    except Exception:
        if speaker_name and config_path:
            new_ip = _rediscover_speaker(speaker_name, config_path)
            _do_play_album(soco.SoCo(new_ip), track_dicts, provider, sn)
        else:
            raise
