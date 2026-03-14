import json
from unittest.mock import patch, MagicMock
from providers.apple_music import AppleMusicProvider

SAMPLE_UDN = "SA_RINCON52231_X_#Svc52231-f7c0f087-Token"

SAMPLE_TRACKS = [
    {
        "track_id": 1440904001,
        "name": "Track One",
        "track_number": 1,
        "artist": "Test Artist",
        "album": "Test Album",
        "artwork_url": "https://example.com/600x600bb.jpg",
    },
    {
        "track_id": 1440904002,
        "name": "Track Two",
        "track_number": 2,
        "artist": "Test Artist",
        "album": "Test Album",
        "artwork_url": "https://example.com/600x600bb.jpg",
    },
]

_real_provider = AppleMusicProvider()


def _make_provider(udn=SAMPLE_UDN):
    """Return a MagicMock provider that delegates URI/DIDL building to the real impl."""
    p = MagicMock()
    p.lookup_udn.return_value = udn
    p.build_track_uri.side_effect = _real_provider.build_track_uri
    p.build_track_didl.side_effect = _real_provider.build_track_didl
    return p


def _get_enqueued(mock_speaker, call_index):
    """Extract the EnqueuedURI and EnqueuedURIMetaData from an AddURIToQueue call."""
    call_params = dict(mock_speaker.avTransport.AddURIToQueue.call_args_list[call_index][0][0])
    return call_params["EnqueuedURI"], call_params["EnqueuedURIMetaData"]


class TestPlayAlbum:
    def test_clears_queue_first(self, mock_speaker):
        from core.sonos_player import play_album
        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3")
        mock_speaker.clear_queue.assert_called_once()

    def test_adds_all_tracks(self, mock_speaker):
        from core.sonos_player import play_album
        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3")
        assert mock_speaker.avTransport.AddURIToQueue.call_count == 2

    def test_adds_tracks_with_correct_metadata(self, mock_speaker):
        from core.sonos_player import play_album
        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3")

        uri0, meta0 = _get_enqueued(mock_speaker, 0)
        assert uri0 == _real_provider.build_track_uri(SAMPLE_TRACKS[0]["track_id"], "3")
        assert "<dc:title>Track One</dc:title>" in meta0
        assert f"10032028song%3a{SAMPLE_TRACKS[0]['track_id']}" in meta0
        assert SAMPLE_UDN in meta0

        uri1, meta1 = _get_enqueued(mock_speaker, 1)
        assert uri1 == _real_provider.build_track_uri(SAMPLE_TRACKS[1]["track_id"], "3")
        assert "<dc:title>Track Two</dc:title>" in meta1
        assert f"10032028song%3a{SAMPLE_TRACKS[1]['track_id']}" in meta1

    def test_metadata_uses_apple_music_desc(self, mock_speaker):
        from core.sonos_player import play_album
        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3")
        _, meta = _get_enqueued(mock_speaker, 0)
        assert "SA_RINCON52231_" in meta
        assert "RINCON_AssociatedZPUDN" not in meta

    def test_starts_playback(self, mock_speaker):
        from core.sonos_player import play_album
        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3")
        mock_speaker.play_from_queue.assert_called_once_with(0)

    def test_does_nothing_for_empty_track_list(self, mock_speaker):
        from core.sonos_player import play_album
        play_album("10.0.0.12", [], MagicMock(), "3")
        mock_speaker.clear_queue.assert_not_called()
        mock_speaker.play_from_queue.assert_not_called()


class TestDetectAppleMusicSn:
    def test_returns_sn_from_favorites(self, mock_speaker):
        xml = (
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            '<item><res protocolInfo="sonos.com-http:*:audio/mp4:*">'
            'x-sonos-http:song%3A1440904001.mp4?sid=204&amp;flags=8232&amp;sn=3'
            '</res></item>'
            '</DIDL-Lite>'
        )
        mock_speaker.contentDirectory.Browse.return_value = {"Result": xml}
        assert AppleMusicProvider().detect_sn(mock_speaker) == "3"

    def test_ignores_non_apple_music_services(self, mock_speaker):
        xml = (
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            '<item><res protocolInfo="x-sonosapi-stream:*:*:*">'
            'x-sonosapi-stream:s23895?sid=333&amp;flags=8292&amp;sn=7'
            '</res></item>'
            '</DIDL-Lite>'
        )
        mock_speaker.contentDirectory.Browse.return_value = {"Result": xml}
        assert AppleMusicProvider().detect_sn(mock_speaker) is None

    def test_returns_none_when_no_apple_music_favorites(self, mock_speaker):
        mock_speaker.contentDirectory.Browse.return_value = {"Result": "<DIDL-Lite></DIDL-Lite>"}
        assert AppleMusicProvider().detect_sn(mock_speaker) is None

    def test_returns_none_on_exception(self, mock_speaker):
        mock_speaker.contentDirectory.Browse.side_effect = Exception("network error")
        assert AppleMusicProvider().detect_sn(mock_speaker) is None


class TestGetNowPlaying:
    def _setup_playing(self, mock_speaker, state="PLAYING"):
        mock_speaker.get_current_transport_info.return_value = {
            "current_transport_state": state
        }
        mock_speaker.get_current_track_info.return_value = {
            "title": "Track One",
            "artist": "Test Artist",
            "album": "Test Album",
            "uri": "x-sonos-http:song%3a1440904001.mp4?sid=204&flags=8232&sn=3",
        }

    def test_returns_track_info_when_playing(self, mock_speaker):
        self._setup_playing(mock_speaker)
        from core.sonos_player import get_now_playing
        result = get_now_playing("10.0.0.12")
        assert result["title"] == "Track One"
        assert result["artist"] == "Test Artist"
        assert result["album"] == "Test Album"

    def test_paused_is_false_when_playing(self, mock_speaker):
        self._setup_playing(mock_speaker, state="PLAYING")
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12")["paused"] is False

    def test_paused_is_true_when_paused(self, mock_speaker):
        self._setup_playing(mock_speaker, state="PAUSED_PLAYBACK")
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12")["paused"] is True

    def test_returns_none_when_stopped(self, mock_speaker):
        mock_speaker.get_current_transport_info.return_value = {
            "current_transport_state": "STOPPED"
        }
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12") is None

    def test_extracts_track_id_from_apple_music_uri(self, mock_speaker):
        self._setup_playing(mock_speaker)
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12")["track_id"] == 1440904001

    def test_extracts_track_id_from_decoded_uri(self, mock_speaker):
        # Sonos may URL-decode the stored URI, returning song: instead of song%3a
        mock_speaker.get_current_transport_info.return_value = {
            "current_transport_state": "PLAYING"
        }
        mock_speaker.get_current_track_info.return_value = {
            "title": "Track One",
            "artist": "Test Artist",
            "album": "Test Album",
            "uri": "x-sonos-http:song:1440904001.mp4?sid=204&flags=8232&sn=3",
        }
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12")["track_id"] == 1440904001

    def test_extracts_track_id_from_hls_static_uri(self, mock_speaker):
        # Sonos normalises to x-sonosapi-hls-static: without .mp4 when reporting back
        mock_speaker.get_current_transport_info.return_value = {
            "current_transport_state": "PLAYING"
        }
        mock_speaker.get_current_track_info.return_value = {
            "title": "Track One",
            "artist": "Test Artist",
            "album": "Test Album",
            "uri": "x-sonosapi-hls-static:song%3a1440904001?sid=204&flags=8232&sn=3",
        }
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12")["track_id"] == 1440904001

    def test_track_id_is_none_for_non_apple_music(self, mock_speaker):
        mock_speaker.get_current_transport_info.return_value = {
            "current_transport_state": "PLAYING"
        }
        mock_speaker.get_current_track_info.return_value = {
            "title": "Some Radio",
            "artist": "",
            "album": "",
            "uri": "x-sonosapi-stream:s23895?sid=254&flags=8232",
        }
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12")["track_id"] is None

    def test_returns_none_on_exception(self, mock_speaker):
        mock_speaker.get_current_transport_info.side_effect = Exception("network error")
        from core.sonos_player import get_now_playing
        assert get_now_playing("10.0.0.12") is None


class TestTransport:
    def test_pause_calls_speaker_pause(self, mock_speaker):
        from core.sonos_player import pause
        pause("10.0.0.12")
        mock_speaker.pause.assert_called_once()

    def test_resume_calls_speaker_play(self, mock_speaker):
        from core.sonos_player import resume
        resume("10.0.0.12")
        mock_speaker.play.assert_called_once()

    def test_stop_calls_speaker_stop(self, mock_speaker):
        from core.sonos_player import stop
        stop("10.0.0.12")
        mock_speaker.stop.assert_called_once()


class TestSpeakerSelfHealing:
    """play_album retries with a rediscovered IP when the cached IP fails."""

    def _make_config(self, tmp_path, speaker_ip="10.0.0.12", speaker_name="Living Room"):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "speaker_ip": speaker_ip,
            "speaker_name": speaker_name,
            "sn": "3",
            "nfc_mode": "mock",
        }))
        return config_file

    def _mock_device(self, name="Living Room", ip="10.0.0.99"):
        d = MagicMock()
        d.player_name = name
        d.ip_address = ip
        return d

    def test_uses_cached_ip_when_playback_succeeds(self, mocker, tmp_path):
        from core.sonos_player import play_album
        config_file = self._make_config(tmp_path)
        mocker.patch("soco.SoCo", return_value=MagicMock())
        mock_discover = mocker.patch("soco.discover")
        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3",
                   speaker_name="Living Room", config_path=str(config_file))
        mock_discover.assert_not_called()

    def test_rediscovers_on_play_failure(self, mocker, tmp_path):
        from core.sonos_player import play_album
        config_file = self._make_config(tmp_path)

        old_speaker = MagicMock()
        old_speaker.group.coordinator = old_speaker
        old_speaker.clear_queue.side_effect = Exception("connection refused")
        new_speaker = MagicMock()
        new_speaker.group.coordinator = new_speaker
        mocker.patch("soco.SoCo", side_effect=[old_speaker, new_speaker])
        mocker.patch("soco.discover", return_value={self._mock_device()})

        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3",
                   speaker_name="Living Room", config_path=str(config_file))

        new_speaker.clear_queue.assert_called_once()
        new_speaker.play_from_queue.assert_called_once_with(0)

    def test_updates_config_ip_after_rediscovery(self, mocker, tmp_path):
        from core.sonos_player import play_album
        config_file = self._make_config(tmp_path)

        old_speaker = MagicMock()
        old_speaker.group.coordinator = old_speaker
        old_speaker.clear_queue.side_effect = Exception("connection refused")
        new_speaker = MagicMock()
        new_speaker.group.coordinator = new_speaker
        mocker.patch("soco.SoCo", side_effect=[old_speaker, new_speaker])
        mocker.patch("soco.discover", return_value={self._mock_device(ip="10.0.0.99")})

        play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3",
                   speaker_name="Living Room", config_path=str(config_file))

        saved = json.loads(config_file.read_text())
        assert saved["speaker_ip"] == "10.0.0.99"

    def test_raises_if_speaker_not_found_after_rediscovery(self, mocker, tmp_path):
        import pytest
        from core.sonos_player import play_album
        config_file = self._make_config(tmp_path)

        old_speaker = MagicMock()
        old_speaker.group.coordinator = old_speaker
        old_speaker.clear_queue.side_effect = Exception("connection refused")
        mocker.patch("soco.SoCo", return_value=old_speaker)
        mocker.patch("soco.discover", return_value={self._mock_device(name="Other Room")})

        with pytest.raises(Exception, match="Living Room"):
            play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3",
                       speaker_name="Living Room", config_path=str(config_file))

    def test_raises_without_rediscovery_if_no_speaker_name(self, mock_speaker, tmp_path):
        import pytest
        from core.sonos_player import play_album
        mock_speaker.clear_queue.side_effect = Exception("connection refused")

        with pytest.raises(Exception, match="connection refused"):
            play_album("10.0.0.12", SAMPLE_TRACKS, _make_provider(), "3")


class TestGetSpeakers:
    def test_returns_speaker_list(self):
        from core.sonos_player import get_speakers
        mock_s1 = MagicMock()
        mock_s1.player_name = "Family Room"
        mock_s1.ip_address = "10.0.0.12"
        mock_s2 = MagicMock()
        mock_s2.player_name = "Foyer"
        mock_s2.ip_address = "10.0.0.8"
        with patch("soco.discover", return_value={mock_s1, mock_s2}):
            speakers = get_speakers()
        assert len(speakers) == 2
        names = {s["name"] for s in speakers}
        assert "Family Room" in names
        assert "Foyer" in names

    def test_returns_empty_list_when_none_found(self):
        from core.sonos_player import get_speakers
        with patch("soco.discover", return_value=None):
            speakers = get_speakers()
        assert speakers == []


class TestLookupAppleMusicUdn:
    SAMPLE_UDN = "SA_RINCON52231_X_#Svc52231-f7c0f087-Token"

    def _xml(self, res_uri, resmd):
        return (
            '<DIDL-Lite xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/">'
            f'<item><r:res>{res_uri}</r:res><r:resMD>{resmd}</r:resMD></item>'
            '</DIDL-Lite>'
        )

    def test_returns_udn_when_sn_matches(self, mock_speaker):
        xml = self._xml(
            "x-sonos-http:song%3a1440904001.mp4?sid=204&amp;flags=8232&amp;sn=3",
            self.SAMPLE_UDN,
        )
        mock_speaker.contentDirectory.Browse.return_value = {"Result": xml}
        assert AppleMusicProvider().lookup_udn(mock_speaker, "3") == self.SAMPLE_UDN

    def test_returns_fallback_when_sn_not_in_uri(self, mock_speaker):
        xml = self._xml(
            "x-sonos-http:song%3a1440904001.mp4?sid=204&amp;sn=9",
            self.SAMPLE_UDN,
        )
        mock_speaker.contentDirectory.Browse.return_value = {"Result": xml}
        assert AppleMusicProvider().lookup_udn(mock_speaker, "3") == "SA_RINCON52231_"

    def test_returns_fallback_on_exception(self, mock_speaker):
        mock_speaker.contentDirectory.Browse.side_effect = Exception("network error")
        assert AppleMusicProvider().lookup_udn(mock_speaker, "3") == "SA_RINCON52231_"


class TestGetNowPlayingExtra:
    def test_returns_none_when_title_empty(self, mock_speaker):
        from core.sonos_player import get_now_playing
        mock_speaker.get_current_transport_info.return_value = {
            "current_transport_state": "PLAYING"
        }
        mock_speaker.get_current_track_info.return_value = {
            "title": "", "artist": "", "album": "", "uri": "",
        }
        assert get_now_playing("10.0.0.12") is None


class TestTransportSelfHealing:
    def test_pause_heals_on_exception(self, mocker):
        from core.sonos_player import pause
        old_speaker = MagicMock()
        old_speaker.pause.side_effect = Exception("connection refused")
        new_speaker = MagicMock()
        mocker.patch("soco.SoCo", side_effect=[old_speaker, new_speaker])
        mocker.patch("core.sonos_player._rediscover_speaker", return_value="10.0.0.99")
        pause("10.0.0.12", speaker_name="Living Room", config_path="/tmp/config.json")
        new_speaker.pause.assert_called_once()

    def test_pause_raises_without_speaker_info(self, mocker):
        import pytest
        from core.sonos_player import pause
        speaker = MagicMock()
        speaker.pause.side_effect = Exception("connection refused")
        mocker.patch("soco.SoCo", return_value=speaker)
        with pytest.raises(Exception, match="connection refused"):
            pause("10.0.0.12")

    def test_resume_heals_on_exception(self, mocker):
        from core.sonos_player import resume
        old_speaker = MagicMock()
        old_speaker.play.side_effect = Exception("connection refused")
        new_speaker = MagicMock()
        mocker.patch("soco.SoCo", side_effect=[old_speaker, new_speaker])
        mocker.patch("core.sonos_player._rediscover_speaker", return_value="10.0.0.99")
        resume("10.0.0.12", speaker_name="Living Room", config_path="/tmp/config.json")
        new_speaker.play.assert_called_once()

    def test_resume_raises_without_speaker_info(self, mocker):
        import pytest
        from core.sonos_player import resume
        speaker = MagicMock()
        speaker.play.side_effect = Exception("connection refused")
        mocker.patch("soco.SoCo", return_value=speaker)
        with pytest.raises(Exception, match="connection refused"):
            resume("10.0.0.12")

    def test_stop_heals_on_exception(self, mocker):
        from core.sonos_player import stop
        old_speaker = MagicMock()
        old_speaker.stop.side_effect = Exception("connection refused")
        new_speaker = MagicMock()
        mocker.patch("soco.SoCo", side_effect=[old_speaker, new_speaker])
        mocker.patch("core.sonos_player._rediscover_speaker", return_value="10.0.0.99")
        stop("10.0.0.12", speaker_name="Living Room", config_path="/tmp/config.json")
        new_speaker.stop.assert_called_once()

    def test_stop_raises_without_speaker_info(self, mocker):
        import pytest
        from core.sonos_player import stop
        speaker = MagicMock()
        speaker.stop.side_effect = Exception("connection refused")
        mocker.patch("soco.SoCo", return_value=speaker)
        with pytest.raises(Exception, match="connection refused"):
            stop("10.0.0.12")

    def test_next_heals_on_exception(self, mocker):
        from core.sonos_player import next_track
        old_speaker = MagicMock()
        old_speaker.next.side_effect = Exception("connection refused")
        new_speaker = MagicMock()
        mocker.patch("soco.SoCo", side_effect=[old_speaker, new_speaker])
        mocker.patch("core.sonos_player._rediscover_speaker", return_value="10.0.0.99")
        next_track("10.0.0.12", speaker_name="Living Room", config_path="/tmp/config.json")
        new_speaker.next.assert_called_once()

    def test_next_raises_without_speaker_info(self, mocker):
        import pytest
        from core.sonos_player import next_track
        speaker = MagicMock()
        speaker.next.side_effect = Exception("connection refused")
        mocker.patch("soco.SoCo", return_value=speaker)
        with pytest.raises(Exception, match="connection refused"):
            next_track("10.0.0.12")

    def test_prev_heals_on_exception(self, mocker):
        from core.sonos_player import prev_track
        old_speaker = MagicMock()
        old_speaker.previous.side_effect = Exception("connection refused")
        new_speaker = MagicMock()
        mocker.patch("soco.SoCo", side_effect=[old_speaker, new_speaker])
        mocker.patch("core.sonos_player._rediscover_speaker", return_value="10.0.0.99")
        prev_track("10.0.0.12", speaker_name="Living Room", config_path="/tmp/config.json")
        new_speaker.previous.assert_called_once()

    def test_prev_raises_without_speaker_info(self, mocker):
        import pytest
        from core.sonos_player import prev_track
        speaker = MagicMock()
        speaker.previous.side_effect = Exception("connection refused")
        mocker.patch("soco.SoCo", return_value=speaker)
        with pytest.raises(Exception, match="connection refused"):
            prev_track("10.0.0.12")

    def test_get_volume_returns_none_on_exception(self, mocker):
        from core.sonos_player import get_volume
        mocker.patch("soco.SoCo", side_effect=Exception("unreachable"))
        assert get_volume("10.0.0.12") is None

    def test_set_volume_heals_on_exception(self, mocker):
        from core.sonos_player import set_volume
        new_speaker = MagicMock()
        mocker.patch("soco.SoCo", side_effect=[Exception("unreachable"), new_speaker])
        mocker.patch("core.sonos_player._rediscover_speaker", return_value="10.0.0.99")
        set_volume("10.0.0.12", 42, speaker_name="Living Room", config_path="/tmp/config.json")
        assert new_speaker.volume == 42

    def test_set_volume_raises_without_speaker_info(self, mocker):
        import pytest
        from core.sonos_player import set_volume
        mocker.patch("soco.SoCo", side_effect=Exception("unreachable"))
        with pytest.raises(Exception, match="unreachable"):
            set_volume("10.0.0.12", 42)
