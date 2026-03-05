import json
import pytest
from unittest.mock import ANY, patch, MagicMock


SAMPLE_ALBUMS = [
    {"id": 1440903625, "name": "Test Album", "artist": "Test Artist",
     "artwork_url": "https://example.com/600x600bb.jpg"},
]

SAMPLE_SONGS = [
    {"id": 1440904001, "name": "Track One", "artist": "Test Artist",
     "album": "Test Album", "artwork_url": "https://example.com/600x600bb.jpg"},
]

SAMPLE_TRACKS = [
    {"track_id": 1440904001, "name": "Track One", "track_number": 1,
     "artist": "Test Artist", "album": "Test Album", "album_id": 1440903625,
     "artwork_url": "https://example.com/600x600bb.jpg",
     "duration": "4:45", "release_year": "1999", "copyright": "℗ 1999 Test Records"},
    {"track_id": 1440904002, "name": "Track Two", "track_number": 2,
     "artist": "Test Artist", "album": "Test Album", "album_id": 1440903625,
     "artwork_url": "https://example.com/600x600bb.jpg",
     "duration": "3:13", "release_year": "1999", "copyright": "℗ 1999 Test Records"},
]

SAMPLE_SINGLE_TRACK = [
    {"track_id": 1440904001, "name": "Track One", "track_number": 1,
     "artist": "Test Artist", "album": "Test Album", "album_id": 1440903625,
     "artwork_url": "https://example.com/600x600bb.jpg",
     "duration": "4:45", "release_year": "1999", "copyright": "℗ 1999 Test Records"},
]


class TestIndex:
    def test_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_renders_search_form(self, client):
        resp = client.get("/")
        assert b"search" in resp.data.lower()


class TestSearch:
    def test_returns_json_albums(self, client):
        with patch("app.apple_music.search_albums", return_value=SAMPLE_ALBUMS):
            resp = client.get("/search?q=Test Album")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Album"
        assert data[0]["artist"] == "Test Artist"

    def test_song_search_returns_songs(self, client):
        with patch("app.apple_music.search_songs", return_value=SAMPLE_SONGS):
            resp = client.get("/search?q=Track+One&type=song")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Track One"
        assert data[0]["album"] == "Test Album"

    def test_empty_query_returns_empty_list(self, client):
        resp = client.get("/search?q=")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_missing_query_returns_empty_list(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestAlbum:
    def test_returns_200(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert resp.status_code == 200

    def test_renders_track_names(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"Track One" in resp.data
        assert b"Track Two" in resp.data

    def test_track_names_are_linked(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"/track/1440904001" in resp.data
        assert b"/track/1440904002" in resp.data

    def test_renders_album_and_artist(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"Test Album" in resp.data
        assert b"Test Artist" in resp.data

    def test_unknown_album_returns_404(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=[]):
            resp = client.get("/album/9999999")
        assert resp.status_code == 404


class TestTrack:
    def test_returns_200(self, client):
        with patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert resp.status_code == 200

    def test_renders_track_name(self, client):
        with patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert b"Track One" in resp.data

    def test_renders_artist_and_album(self, client):
        with patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert b"Test Artist" in resp.data
        assert b"Test Album" in resp.data

    def test_shows_tag_string(self, client):
        with patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert b"apple:track:1440904001" in resp.data

    def test_unknown_track_returns_404(self, client):
        with patch("app.apple_music.get_track", return_value=[]):
            resp = client.get("/track/9999999")
        assert resp.status_code == 404


class TestWriteTag:
    def test_calls_write_tag_with_album_data(self, client, temp_config, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 200
        mock_nfc.write_tag.assert_called_once_with("apple:1440903625")

    def test_returns_written_album_tag_string(self, client, temp_config, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.get_json()["written"] == "apple:1440903625"

    def test_calls_write_tag_with_track_data(self, client, temp_config, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-tag", json={"track_id": "1440904001"})
        assert resp.status_code == 200
        mock_nfc.write_tag.assert_called_once_with("apple:track:1440904001")

    def test_returns_written_track_tag_string(self, client, temp_config, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-tag", json={"track_id": "1440904001"})
        assert resp.get_json()["written"] == "apple:track:1440904001"

    def test_missing_body_returns_400(self, client):
        resp = client.post("/write-tag", data="", content_type="application/json")
        assert resp.status_code == 400

    def test_missing_id_returns_400(self, client):
        resp = client.post("/write-tag", json={"other": "value"})
        assert resp.status_code == 400


class TestWriteTagPN532:
    """Two-step write-tag flow tests using pn532 mode."""

    def _pn532_config(self, tmp_path, monkeypatch):
        import app, json
        config_file = tmp_path / "config_pn532.json"
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.12",
            "speaker_name": "Family Room", "nfc_mode": "pn532",
        }))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        return mock_nfc

    def test_blank_tag_writes_immediately(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = None
        resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"
        mock_nfc.write_tag.assert_called_once_with("apple:1440903625")

    def test_existing_tag_returns_confirm(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = "apple:9999999"
        with patch("app._format_existing_tag", return_value="Some Album by Some Artist"):
            resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "confirm"
        assert data["existing"] == "apple:9999999"
        mock_nfc.write_tag.assert_not_called()

    def test_confirm_contains_existing_display(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = "apple:9999999"
        with patch("app._format_existing_tag", return_value="Test Album by Test Artist"):
            resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.get_json()["existing_display"] == "Test Album by Test Artist"

    def test_existing_unrecognised_tag_shows_raw(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = "spotify:album:abc123"
        resp = client.post("/write-tag", json={"album_id": "1440903625"})
        data = resp.get_json()
        assert data["status"] == "confirm"
        assert data["existing_display"] == "spotify:album:abc123"

    def test_force_skips_read_and_writes(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        resp = client.post("/write-tag", json={"album_id": "1440903625", "force": True})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"
        mock_nfc.read_tag.assert_not_called()
        mock_nfc.write_tag.assert_called_once_with("apple:1440903625")

    def test_locked_tag_returns_409(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = None
        mock_nfc.write_tag.side_effect = IOError("Tag is read-only (locked)")
        resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 409
        assert "locked" in resp.get_json()["error"]

    def test_lock_busy_returns_503(self, client, tmp_path, monkeypatch):
        import app
        self._pn532_config(tmp_path, monkeypatch)
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        monkeypatch.setattr(app, "_nfc_lock", mock_lock)
        resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 503
        assert "busy" in resp.get_json()["error"]


class TestWriteUrlTag:
    def test_calls_write_url_tag(self, client, temp_config):
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-url-tag")
        assert resp.status_code == 200
        mock_nfc.write_url_tag.assert_called_once()

    def test_returns_written_url(self, client, temp_config):
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-url-tag")
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "written" in data

    def test_returns_501_for_pn532(self, client, temp_config, monkeypatch):
        import app, json
        temp_config.write_text(json.dumps({"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"}))
        monkeypatch.setattr(app, "CONFIG_PATH", str(temp_config))
        mock_nfc = MagicMock()
        mock_nfc.write_url_tag.side_effect = NotImplementedError("PN532NFC not yet implemented")
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        resp = client.post("/write-url-tag")
        assert resp.status_code == 501


class TestAlbumPage:
    def test_shows_album_id(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"1440903625" in resp.data

    def test_shows_tag_string(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"apple:1440903625" in resp.data


class TestPlay:
    def test_plays_album(self, client, temp_config):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"album_id": "1440903625"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_TRACKS, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_plays_track(self, client, temp_config):
        with patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"track_id": "1440904001"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_SINGLE_TRACK, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_returns_ok(self, client, temp_config):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album"):
            resp = client.post("/play", json={"album_id": "1440903625"})
        assert resp.get_json()["status"] == "ok"

    def test_missing_body_returns_400(self, client):
        resp = client.post("/play", data="", content_type="application/json")
        assert resp.status_code == 400

    def test_missing_id_returns_400(self, client):
        resp = client.post("/play", json={"other": "value"})
        assert resp.status_code == 400

    def test_unknown_album_returns_404(self, client, temp_config):
        with patch("app.apple_music.get_album_tracks", return_value=[]), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"album_id": "9999999"})
        assert resp.status_code == 404
        mock_play.assert_not_called()

    def test_unknown_track_returns_404(self, client, temp_config):
        with patch("app.apple_music.get_track", return_value=[]), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"track_id": "9999999"})
        assert resp.status_code == 404
        mock_play.assert_not_called()


class TestSettings:
    def test_get_returns_200(self, client, temp_config):
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_get_renders_current_config(self, client, temp_config):
        resp = client.get("/settings")
        assert b"10.0.0.12" in resp.data

    def test_post_saves_config(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        client.post("/settings", data={
            "sn": "5",
            "speaker_ip": "10.0.0.8",
            "nfc_mode": "mock",
            "csrf_token": "test-token",
        })
        saved = json.loads(temp_config.read_text())
        assert saved["sn"] == "5"
        assert saved["speaker_ip"] == "10.0.0.8"

    def test_post_returns_200(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings", data={
            "sn": "3",
            "speaker_ip": "10.0.0.12",
            "nfc_mode": "mock",
            "csrf_token": "test-token",
        })
        assert resp.status_code == 200

    def test_post_rejects_missing_csrf_token(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings", data={
            "sn": "5",
            "speaker_ip": "10.0.0.8",
            "nfc_mode": "mock",
        })
        assert resp.status_code == 403

    def test_post_rejects_wrong_csrf_token(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings", data={
            "sn": "5",
            "speaker_ip": "10.0.0.8",
            "nfc_mode": "mock",
            "csrf_token": "wrong-token",
        })
        assert resp.status_code == 403


class TestSpeakers:
    def test_returns_json_list(self, client):
        with patch("app.get_speakers", return_value=[
            {"name": "Family Room", "ip": "10.0.0.12"},
            {"name": "Foyer", "ip": "10.0.0.8"},
        ]):
            resp = client.get("/speakers")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["name"] == "Family Room"


class TestReadTag:
    def test_album_tag_returns_content_id_and_type(self, client, temp_config):
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = "apple:1440903625"
        with patch("app.MockNFC", return_value=mock_nfc), \
             patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/read-tag")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tag_string"] == "apple:1440903625"
        assert data["tag_type"] == "album"
        assert data["content_id"] == "1440903625"

    def test_track_tag_returns_content_id_and_type(self, client, temp_config):
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = "apple:track:1440904001"
        with patch("app.MockNFC", return_value=mock_nfc), \
             patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/read-tag")
        data = resp.get_json()
        assert data["tag_string"] == "apple:track:1440904001"
        assert data["tag_type"] == "track"
        assert data["content_id"] == "1440904001"

    def test_returns_album_info(self, client, temp_config):
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = "apple:1440903625"
        with patch("app.MockNFC", return_value=mock_nfc), \
             patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/read-tag")
        data = resp.get_json()
        assert data["album"]["name"] == "Test Album"
        assert data["album"]["artist"] == "Test Artist"
        assert "artwork_url" in data["album"]

    def test_invalid_tag_returns_error(self, client, temp_config):
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = "notvalid"
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.get("/read-tag")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["error"] is not None

    def test_tag_query_param_skips_nfc(self, client, temp_config):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/read-tag?tag=apple:1440903625")
        data = resp.get_json()
        assert data["tag_string"] == "apple:1440903625"
        assert data["content_id"] == "1440903625"


class TestVerify:
    def test_returns_200(self, client, temp_config):
        resp = client.get("/verify")
        assert resp.status_code == 200

    def test_renders_read_tag_button(self, client, temp_config):
        resp = client.get("/verify")
        assert b"read" in resp.data.lower() or b"tap" in resp.data.lower()



class TestDetectSn:
    def test_returns_detected_sn(self, client, temp_config):
        with patch("app.detect_apple_music_sn", return_value="3"):
            resp = client.get("/detect-sn")
        assert resp.status_code == 200
        assert resp.get_json()["sn"] == "3"

    def test_returns_404_when_not_found(self, client, temp_config):
        with patch("app.detect_apple_music_sn", return_value=None):
            resp = client.get("/detect-sn")
        assert resp.status_code == 404

    def test_accepts_speaker_ip_param(self, client):
        with patch("app.detect_apple_music_sn", return_value="5"):
            resp = client.get("/detect-sn?speaker_ip=10.0.0.12")
        assert resp.status_code == 200
        assert resp.get_json()["sn"] == "5"

    def test_returns_400_when_no_speaker(self, client, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"sn": "3", "speaker_ip": "", "nfc_mode": "mock"}))
        import app
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        resp = client.get("/detect-sn")
        assert resp.status_code == 400


class TestNowPlaying:
    def test_returns_playing_false_when_nothing_playing(self, client, temp_config):
        with patch("app.get_now_playing", return_value=None):
            resp = client.get("/now-playing")
        assert resp.status_code == 200
        assert resp.get_json()["playing"] is False

    def test_returns_track_info_for_non_apple_music(self, client, temp_config):
        with patch("app.get_now_playing", return_value={
            "title": "Some Radio", "artist": "", "album": "", "track_id": None, "paused": False
        }):
            resp = client.get("/now-playing")
        data = resp.get_json()
        assert data["playing"] is True
        assert data["title"] == "Some Radio"
        assert data["album_id"] is None
        assert data["artwork_url"] is None

    def test_returns_album_id_for_apple_music_track(self, client, temp_config):
        with patch("app.get_now_playing", return_value={
            "title": "Track One", "artist": "Test Artist", "album": "Test Album",
            "track_id": 1440904001, "paused": False,
        }), patch("app.apple_music.get_track", return_value=[{
            "track_id": 1440904001, "name": "Track One", "track_number": 1,
            "artist": "Test Artist", "album": "Test Album",
            "album_id": 1440903625,
            "artwork_url": "https://example.com/600x600bb.jpg",
        }]):
            resp = client.get("/now-playing")
        data = resp.get_json()
        assert data["album_id"] == 1440903625
        assert data["artwork_url"] == "https://example.com/600x600bb.jpg"

    def test_includes_volume_in_response(self, client, temp_config):
        with patch("app.get_now_playing", return_value={
            "title": "Track", "artist": "Artist", "album": "Album", "track_id": None, "paused": False
        }), patch("app.get_volume", return_value=55):
            resp = client.get("/now-playing")
        assert resp.get_json()["volume"] == 55

    def test_returns_playing_false_when_no_speaker(self, client, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"sn": "3", "speaker_ip": "", "nfc_mode": "mock"}')
        import app
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        resp = client.get("/now-playing")
        assert resp.get_json()["playing"] is False


class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_ok_status(self, client):
        resp = client.get("/health")
        assert resp.get_json()["status"] == "ok"


class TestTransport:
    def test_pause_action(self, client, temp_config):
        with patch("app.pause") as mock_pause:
            resp = client.post("/transport", json={"action": "pause"})
        assert resp.status_code == 200
        mock_pause.assert_called_once_with("10.0.0.12", speaker_name="Family Room", config_path=ANY)

    def test_resume_action(self, client, temp_config):
        with patch("app.resume") as mock_resume:
            resp = client.post("/transport", json={"action": "resume"})
        assert resp.status_code == 200
        mock_resume.assert_called_once_with("10.0.0.12", speaker_name="Family Room", config_path=ANY)

    def test_stop_action(self, client, temp_config):
        with patch("app.stop") as mock_stop:
            resp = client.post("/transport", json={"action": "stop"})
        assert resp.status_code == 200
        mock_stop.assert_called_once_with("10.0.0.12", speaker_name="Family Room", config_path=ANY)

    def test_next_action(self, client, temp_config):
        with patch("app.next_track") as mock_next:
            resp = client.post("/transport", json={"action": "next"})
        assert resp.status_code == 200
        mock_next.assert_called_once_with("10.0.0.12", speaker_name="Family Room", config_path=ANY)

    def test_prev_action(self, client, temp_config):
        with patch("app.prev_track") as mock_prev:
            resp = client.post("/transport", json={"action": "prev"})
        assert resp.status_code == 200
        mock_prev.assert_called_once_with("10.0.0.12", speaker_name="Family Room", config_path=ANY)

    def test_invalid_action_returns_400(self, client):
        resp = client.post("/transport", json={"action": "rewind"})
        assert resp.status_code == 400

    def test_returns_ok_and_action(self, client, temp_config):
        with patch("app.pause"):
            resp = client.post("/transport", json={"action": "pause"})
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["action"] == "pause"

    def test_volume_action(self, client, temp_config):
        with patch("app.set_volume") as mock_set:
            resp = client.post("/transport", json={"action": "volume", "value": 42})
        assert resp.status_code == 200
        mock_set.assert_called_once_with("10.0.0.12", 42, speaker_name="Family Room", config_path=ANY)

    def test_volume_missing_value_returns_400(self, client, temp_config):
        resp = client.post("/transport", json={"action": "volume"})
        assert resp.status_code == 400

    def test_volume_out_of_range_returns_400(self, client, temp_config):
        resp = client.post("/transport", json={"action": "volume", "value": 150})
        assert resp.status_code == 400


class TestPlayTag:
    def test_plays_album_tag(self, client, temp_config):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play/tag", json={"tag": "apple:1440903625"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_TRACKS, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_plays_track_tag(self, client, temp_config):
        with patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play/tag", json={"tag": "apple:track:1440904001"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_SINGLE_TRACK, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_invalid_tag_returns_400(self, client, temp_config):
        resp = client.post("/play/tag", json={"tag": "notvalid"})
        assert resp.status_code == 400

    def test_missing_tag_returns_400(self, client):
        resp = client.post("/play/tag", json={})
        assert resp.status_code == 400

    def test_unknown_album_tag_returns_404(self, client, temp_config):
        with patch("app.apple_music.get_album_tracks", return_value=[]), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play/tag", json={"tag": "apple:9999999"})
        assert resp.status_code == 404
        mock_play.assert_not_called()

    def test_unknown_track_tag_returns_404(self, client, temp_config):
        with patch("app.apple_music.get_track", return_value=[]), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play/tag", json={"tag": "apple:track:9999999"})
        assert resp.status_code == 404
        mock_play.assert_not_called()


class TestCollection:
    def test_collection_page_returns_200(self, client, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        resp = client.get("/collection")
        assert resp.status_code == 200

    def test_collection_empty_by_default(self, client, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        resp = client.get("/collection")
        assert b"No tags written yet" in resp.data

    def test_delete_removes_entry(self, client, tmp_path, monkeypatch):
        import app
        tags_file = tmp_path / "tags.json"
        tags_file.write_text(json.dumps([
            {"tag_string": "apple:1440903625", "type": "album", "name": "Test Album",
             "artist": "Test Artist", "artwork_url": "", "album_id": 1440903625,
             "track_id": None, "written_at": "2026-02-28T12:00:00"},
        ]))
        monkeypatch.setattr(app, "TAGS_PATH", str(tags_file))
        resp = client.post("/collection/delete", json={"tag_string": "apple:1440903625"})
        assert resp.status_code == 200
        assert json.loads(tags_file.read_text()) == []

    def test_delete_missing_tag_string_returns_400(self, client, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        resp = client.post("/collection/delete", json={})
        assert resp.status_code == 400

    def test_clear_empties_collection(self, client, tmp_path, monkeypatch):
        import app
        tags_file = tmp_path / "tags.json"
        tags_file.write_text(json.dumps([
            {"tag_string": "apple:1440903625", "type": "album", "name": "Test Album",
             "artist": "Test Artist", "artwork_url": "", "album_id": 1440903625,
             "track_id": None, "written_at": "2026-02-28T12:00:00"},
        ]))
        monkeypatch.setattr(app, "TAGS_PATH", str(tags_file))
        resp = client.post("/collection/clear")
        assert resp.status_code == 200
        assert json.loads(tags_file.read_text()) == []

    def test_write_tag_records_album(self, client, temp_config, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc), \
             patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            client.post("/write-tag", json={"album_id": "1440903625"})
        tags = json.loads((tmp_path / "tags.json").read_text())
        assert len(tags) == 1
        assert tags[0]["tag_string"] == "apple:1440903625"
        assert tags[0]["type"] == "album"

    def test_write_tag_records_track(self, client, temp_config, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        with patch("app.MockNFC", return_value=mock_nfc), \
             patch("app.apple_music.get_track", return_value=SAMPLE_SINGLE_TRACK):
            client.post("/write-tag", json={"track_id": "1440904001"})
        tags = json.loads((tmp_path / "tags.json").read_text())
        assert len(tags) == 1
        assert tags[0]["tag_string"] == "apple:track:1440904001"
        assert tags[0]["type"] == "track"


class TestFormatExistingTag:
    SAMPLE_TRACK = [{"track_id": 1440904001, "name": "Track One", "artist": "Test Artist",
                     "album": "Test Album", "artwork_url": "https://example.com/art.jpg"}]
    SAMPLE_TRACKS = [{"track_id": 1440904001, "name": "Track One", "track_number": 1,
                      "artist": "Test Artist", "album": "Test Album",
                      "artwork_url": "https://example.com/art.jpg"}]

    def test_track_tag_returns_name_and_artist(self):
        from app import _format_existing_tag
        with patch("app.apple_music.get_track", return_value=self.SAMPLE_TRACK):
            assert _format_existing_tag("apple:track:1440904001") == "Track One by Test Artist"

    def test_album_tag_returns_album_and_artist(self):
        from app import _format_existing_tag
        with patch("app.apple_music.get_album_tracks", return_value=self.SAMPLE_TRACKS):
            assert _format_existing_tag("apple:1440903625") == "Test Album by Test Artist"

    def test_empty_track_results_returns_raw_string(self):
        from app import _format_existing_tag
        with patch("app.apple_music.get_track", return_value=[]):
            assert _format_existing_tag("apple:track:1440904001") == "apple:track:1440904001"

    def test_empty_album_results_returns_raw_string(self):
        from app import _format_existing_tag
        with patch("app.apple_music.get_album_tracks", return_value=[]):
            assert _format_existing_tag("apple:1440903625") == "apple:1440903625"

    def test_exception_in_lookup_returns_raw_string(self):
        from app import _format_existing_tag
        with patch("app.apple_music.get_track", side_effect=Exception("network error")):
            assert _format_existing_tag("apple:track:1440904001") == "apple:track:1440904001"


class TestNfcRoutes503:
    """Routes return 503 when _nfc is not initialised (pn532 mode, no hardware)."""

    def _pn532_config(self, tmp_path, monkeypatch):
        import app
        config_file = tmp_path / "config_pn532.json"
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.12",
            "speaker_name": "Family Room", "nfc_mode": "pn532",
        }))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        monkeypatch.setattr(app, "_nfc", None)

    def test_write_tag_503_when_nfc_not_initialised(self, client, tmp_path, monkeypatch):
        self._pn532_config(tmp_path, monkeypatch)
        resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 503
        assert "not initialised" in resp.get_json()["error"]

    def test_write_url_tag_503_when_nfc_not_initialised(self, client, tmp_path, monkeypatch):
        self._pn532_config(tmp_path, monkeypatch)
        resp = client.post("/write-url-tag")
        assert resp.status_code == 503
        assert "not initialised" in resp.get_json()["error"]

    def test_read_tag_error_json_when_nfc_not_initialised(self, client, tmp_path, monkeypatch):
        self._pn532_config(tmp_path, monkeypatch)
        resp = client.get("/read-tag")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["error"] is not None
        assert "not initialised" in data["error"]

    def test_do_record_tag_exception_still_returns_ok(self, client, tmp_path, monkeypatch):
        import app
        self._pn532_config(tmp_path, monkeypatch)
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = None
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with patch("app.apple_music.get_album_tracks", side_effect=Exception("API error")):
            resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestLoadConfig:
    def _write_config(self, tmp_path, monkeypatch, data):
        import app
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))

    def test_valid_config_loads(self, tmp_path, monkeypatch):
        import app
        self._write_config(tmp_path, monkeypatch,
                           {"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "mock"})
        config = app._load_config()
        assert config["sn"] == "3"

    def test_missing_speaker_ip_raises(self, tmp_path, monkeypatch):
        import app
        self._write_config(tmp_path, monkeypatch, {"sn": "3", "nfc_mode": "mock"})
        with pytest.raises(RuntimeError, match="speaker_ip"):
            app._load_config()

    def test_missing_sn_raises(self, tmp_path, monkeypatch):
        import app
        self._write_config(tmp_path, monkeypatch, {"speaker_ip": "10.0.0.12", "nfc_mode": "mock"})
        with pytest.raises(RuntimeError, match="sn"):
            app._load_config()

    def test_missing_nfc_mode_raises(self, tmp_path, monkeypatch):
        import app
        self._write_config(tmp_path, monkeypatch, {"sn": "3", "speaker_ip": "10.0.0.12"})
        with pytest.raises(RuntimeError, match="nfc_mode"):
            app._load_config()

    def test_missing_multiple_fields_names_all(self, tmp_path, monkeypatch):
        import app
        self._write_config(tmp_path, monkeypatch, {})
        with pytest.raises(RuntimeError) as exc_info:
            app._load_config()
        msg = str(exc_info.value)
        assert "sn" in msg
        assert "speaker_ip" in msg
        assert "nfc_mode" in msg


class TestLoadTags:
    def test_returns_empty_list_when_file_missing(self, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        assert app._load_tags() == []

    def test_returns_tags_from_valid_file(self, tmp_path, monkeypatch):
        import app
        tags_file = tmp_path / "tags.json"
        tags_file.write_text(json.dumps([{"tag_string": "apple:1440903625"}]))
        monkeypatch.setattr(app, "TAGS_PATH", str(tags_file))
        assert app._load_tags() == [{"tag_string": "apple:1440903625"}]

    def test_returns_empty_list_on_invalid_json(self, tmp_path, monkeypatch):
        import app
        tags_file = tmp_path / "tags.json"
        tags_file.write_text("not valid json {{{")
        monkeypatch.setattr(app, "TAGS_PATH", str(tags_file))
        assert app._load_tags() == []

    def test_returns_empty_list_on_truncated_json(self, tmp_path, monkeypatch):
        import app
        tags_file = tmp_path / "tags.json"
        tags_file.write_text('[{"tag_string": "apple:1')
        monkeypatch.setattr(app, "TAGS_PATH", str(tags_file))
        assert app._load_tags() == []


class TestPrintInserts:
    def test_single_album_returns_200(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/print?ids=1440903625")
        assert resp.status_code == 200

    def test_renders_album_name(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/print?ids=1440903625")
        assert b"Test Album" in resp.data

    def test_renders_artist(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/print?ids=1440903625")
        assert b"Test Artist" in resp.data

    def test_renders_track_names(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/print?ids=1440903625")
        assert b"Track One" in resp.data
        assert b"Track Two" in resp.data

    def test_multiple_albums(self, client):
        tracks_a = [{"track_id": 1, "name": "Song A", "track_number": 1,
                     "artist": "Artist A", "album": "Album A",
                     "artwork_url": "https://example.com/a.jpg"}]
        tracks_b = [{"track_id": 2, "name": "Song B", "track_number": 1,
                     "artist": "Artist B", "album": "Album B",
                     "artwork_url": "https://example.com/b.jpg"}]
        with patch("app.apple_music.get_album_tracks", side_effect=[tracks_a, tracks_b]):
            resp = client.get("/print?ids=111,222")
        assert resp.status_code == 200
        assert b"Album A" in resp.data
        assert b"Album B" in resp.data

    def test_missing_ids_param_returns_400(self, client):
        resp = client.get("/print")
        assert resp.status_code == 400

    def test_empty_ids_returns_400(self, client):
        resp = client.get("/print?ids=")
        assert resp.status_code == 400

    def test_all_ids_not_found_returns_404(self, client):
        with patch("app.apple_music.get_album_tracks", return_value=[]):
            resp = client.get("/print?ids=9999999")
        assert resp.status_code == 404

    def test_partial_failure_returns_200_with_found_albums(self, client):
        tracks_a = [{"track_id": 1, "name": "Song A", "track_number": 1,
                     "artist": "Artist A", "album": "Album A",
                     "artwork_url": "https://example.com/a.jpg"}]
        with patch("app.apple_music.get_album_tracks", side_effect=[tracks_a, []]):
            resp = client.get("/print?ids=111,999")
        assert resp.status_code == 200
        assert b"Album A" in resp.data


class TestNfcLoop:
    """Tests for the background NFC polling loop and debounce logic."""

    @pytest.fixture
    def pn532_config(self, tmp_path, monkeypatch):
        import app
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.12",
            "speaker_name": "Family Room", "nfc_mode": "pn532",
        }))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        return str(config_file)

    def test_plays_on_card_tap(self, pn532_config, monkeypatch):
        import app
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = ["apple:1440903625", KeyboardInterrupt]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)
        mock_play.assert_called_once()

    def test_debounce_same_card_plays_once(self, pn532_config, monkeypatch):
        import app
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = [
            "apple:1440903625", "apple:1440903625", "apple:1440903625",
            KeyboardInterrupt,
        ]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)
        mock_play.assert_called_once()

    def test_replays_after_card_removed(self, pn532_config, monkeypatch):
        import app
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = [
            "apple:1440903625",  # first tap → play
            None,                # card removed
            "apple:1440903625",  # second tap → play again
            KeyboardInterrupt,
        ]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with patch("app.apple_music.get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)
        assert mock_play.call_count == 2

    def test_start_nfc_thread_no_op_in_mock_mode(self, tmp_path, monkeypatch):
        import app
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "mock",
        }))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        with patch("app.PN532NFC") as mock_pn532:
            app._start_nfc_thread(str(config_file))
        mock_pn532.assert_not_called()
