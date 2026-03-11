import json
import pytest
from unittest.mock import ANY, patch, MagicMock
import providers


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
        with patch.object(providers.get_provider("apple"), "search_albums", return_value=SAMPLE_ALBUMS):
            resp = client.get("/search?q=Test Album")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Album"
        assert data[0]["artist"] == "Test Artist"

    def test_song_search_returns_songs(self, client):
        with patch.object(providers.get_provider("apple"), "search_songs", return_value=SAMPLE_SONGS):
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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert resp.status_code == 200

    def test_renders_track_names(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"Track One" in resp.data
        assert b"Track Two" in resp.data

    def test_track_names_are_linked(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"/track/1440904001" in resp.data
        assert b"/track/1440904002" in resp.data

    def test_renders_album_and_artist(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"Test Album" in resp.data
        assert b"Test Artist" in resp.data

    def test_unknown_album_returns_404(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=[]):
            resp = client.get("/album/9999999")
        assert resp.status_code == 404


class TestTrack:
    def test_returns_200(self, client):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert resp.status_code == 200

    def test_renders_track_name(self, client):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert b"Track One" in resp.data

    def test_renders_artist_and_album(self, client):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert b"Test Artist" in resp.data
        assert b"Test Album" in resp.data

    def test_shows_tag_string(self, client):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/track/1440904001")
        assert b"apple:track:1440904001" in resp.data

    def test_unknown_track_returns_404(self, client):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=[]):
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

    def test_mock_ioerror_returns_409(self, client, temp_config, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "TAGS_PATH", str(tmp_path / "tags.json"))
        mock_nfc = MagicMock()
        mock_nfc.write_tag.side_effect = IOError("write failed")
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 409

    def test_mock_nfc_init_error_returns_503(self, client, temp_config):
        with patch("app._make_nfc", side_effect=RuntimeError("not installed")):
            resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 503


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

    def test_force_overwrites_without_confirm(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = "apple:1440903625"
        resp = client.post("/write-tag", json={"album_id": "1440903625", "force": True})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"
        mock_nfc.write_tag.assert_called_once_with("apple:1440903625")

    def test_locked_tag_returns_409(self, client, tmp_path, monkeypatch):
        # Locked tag has content; force=True skips confirm and attempts write
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = "apple:1440903625"
        mock_nfc.write_tag.side_effect = IOError("Tag is read-only (locked)")
        resp = client.post("/write-tag", json={"album_id": "1440903625", "force": True})
        assert resp.status_code == 409
        assert "locked" in resp.get_json()["error"]

    def test_no_tag_present_returns_409_with_helpful_message(self, client, tmp_path, monkeypatch):
        mock_nfc = self._pn532_config(tmp_path, monkeypatch)
        mock_nfc.read_tag.return_value = None
        mock_nfc.write_tag.side_effect = IOError("Tag is read-only (locked)")
        resp = client.post("/write-tag", json={"album_id": "1440903625"})
        assert resp.status_code == 409
        assert "No tag present" in resp.get_json()["error"]

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

    def test_mock_not_implemented_returns_501(self, client, temp_config):
        mock_nfc = MagicMock()
        mock_nfc.write_url_tag.side_effect = NotImplementedError("not implemented")
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.post("/write-url-tag")
        assert resp.status_code == 501

    def test_mock_nfc_init_error_returns_503(self, client, temp_config):
        with patch("app._make_nfc", side_effect=RuntimeError("not installed")):
            resp = client.post("/write-url-tag")
        assert resp.status_code == 503

    def test_pn532_lock_busy_returns_503(self, client, tmp_path, monkeypatch):
        import app, json
        config_file = tmp_path / "config_wu.json"
        config_file.write_text(json.dumps({"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"}))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        monkeypatch.setattr(app, "_nfc", MagicMock())
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        monkeypatch.setattr(app, "_nfc_lock", mock_lock)
        resp = client.post("/write-url-tag")
        assert resp.status_code == 503

    def test_pn532_ioerror_no_tag_returns_409(self, client, tmp_path, monkeypatch):
        import app, json
        config_file = tmp_path / "config_wu2.json"
        config_file.write_text(json.dumps({"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"}))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = None
        mock_nfc.write_url_tag.side_effect = IOError("write failed")
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        resp = client.post("/write-url-tag")
        assert resp.status_code == 409
        assert "No tag present" in resp.get_json()["error"]

    def test_pn532_ioerror_locked_tag_returns_409(self, client, tmp_path, monkeypatch):
        import app, json
        config_file = tmp_path / "config_wu3.json"
        config_file.write_text(json.dumps({"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"}))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = "apple:1440903625"
        mock_nfc.write_url_tag.side_effect = IOError("read-only")
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        resp = client.post("/write-url-tag")
        assert resp.status_code == 409
        assert "read-only" in resp.get_json()["error"]


class TestAlbumPage:
    def test_shows_album_id(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"1440903625" in resp.data

    def test_shows_tag_string(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/album/1440903625")
        assert b"apple:1440903625" in resp.data


class TestPlay:
    def test_plays_album(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"album_id": "1440903625"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_TRACKS, ANY, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_plays_track(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"track_id": "1440904001"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_SINGLE_TRACK, ANY, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_returns_ok(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=[]), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"album_id": "9999999"})
        assert resp.status_code == 404
        mock_play.assert_not_called()

    def test_unknown_track_returns_404(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=[]), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play", json={"track_id": "9999999"})
        assert resp.status_code == 404
        mock_play.assert_not_called()


class TestSettings:
    def test_get_returns_200(self, client, temp_config):
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_renders_menu_rows(self, client, temp_config):
        resp = client.get("/settings")
        assert b"/settings/sonos" in resp.data
        assert b"/settings/nfc" in resp.data
        assert b"/settings/sticker" in resp.data
        assert b"/settings/hardware" in resp.data

    def test_shows_speaker_detail(self, client, temp_config):
        resp = client.get("/settings")
        assert b"Family Room" in resp.data

    def test_shows_nfc_detail(self, client, temp_config):
        resp = client.get("/settings")
        assert b"mock" in resp.data


class TestSettingsSonos:
    def test_get_returns_200(self, client, temp_config):
        resp = client.get("/settings/sonos")
        assert resp.status_code == 200

    def test_post_saves_speaker_ip_and_sn(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        client.post("/settings/sonos", data={
            "speaker_ip": "10.0.0.8",
            "speaker_name": "Kitchen",
            "sn": "5",
            "csrf_token": "test-token",
        })
        saved = json.loads(temp_config.read_text())
        assert saved["speaker_ip"] == "10.0.0.8"
        assert saved["speaker_name"] == "Kitchen"
        assert saved["sn"] == "5"

    def test_post_sets_saved_flag(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/sonos", data={
            "speaker_ip": "10.0.0.12",
            "speaker_name": "",
            "sn": "3",
            "csrf_token": "test-token",
        })
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower()

    def test_post_csrf_missing_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/sonos", data={
            "speaker_ip": "10.0.0.8", "sn": "5",
        })
        assert resp.status_code == 403

    def test_post_csrf_wrong_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/sonos", data={
            "speaker_ip": "10.0.0.8", "sn": "5", "csrf_token": "wrong",
        })
        assert resp.status_code == 403


class TestSettingsNfc:
    def test_get_returns_200(self, client, temp_config):
        resp = client.get("/settings/nfc")
        assert resp.status_code == 200

    def test_post_saves_nfc_mode(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        client.post("/settings/nfc", data={
            "nfc_mode": "pn532",
            "csrf_token": "test-token",
        })
        saved = json.loads(temp_config.read_text())
        assert saved["nfc_mode"] == "pn532"

    def test_post_sets_saved_flag(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/nfc", data={
            "nfc_mode": "mock",
            "csrf_token": "test-token",
        })
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower()

    def test_post_csrf_missing_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/nfc", data={"nfc_mode": "mock"})
        assert resp.status_code == 403

    def test_post_csrf_wrong_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/nfc", data={
            "nfc_mode": "mock", "csrf_token": "wrong",
        })
        assert resp.status_code == 403


class TestSettingsSticker:
    def test_get_returns_200(self, client, temp_config):
        resp = client.get("/settings/sticker")
        assert resp.status_code == 200


class TestSettingsReboot:
    def test_get_returns_200(self, client, temp_config):
        resp = client.get("/settings/reboot")
        assert resp.status_code == 200

    def test_post_calls_popen(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        with patch("app.subprocess.Popen") as mock_popen:
            resp = client.post("/settings/reboot", data={"csrf_token": "test-token"})
        assert resp.status_code == 302
        mock_popen.assert_called_once_with(["sudo", "reboot"])

    def test_post_redirects_to_hardware_with_rebooting(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        with patch("app.subprocess.Popen"):
            resp = client.post("/settings/reboot", data={"csrf_token": "test-token"},
                               follow_redirects=True)
        assert b"ebooting" in resp.data

    def test_post_csrf_missing_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/reboot", data={})
        assert resp.status_code == 403

    def test_post_csrf_wrong_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/reboot", data={"csrf_token": "wrong"})
        assert resp.status_code == 403


FAKE_HW_STATS = {
    "hostname": "vinyl-pi", "os": "Raspberry Pi OS 12", "kernel": "6.1.0",
    "uptime": "2d 3h 5m", "cpu_model": "Raspberry Pi 4 Model B Rev 1.4",
    "cpu_cores": 4, "cpu_percent": 12.5, "cpu_freq_mhz": 1800, "cpu_temp_c": 48.2,
    "ram_used": "1.2 GB", "ram_total": "3.7 GB", "ram_percent": 32.4,
    "swap_used": "0.0 B", "swap_total": "100.0 MB",
    "disk_used": "8.0 GB", "disk_free": "22.0 GB", "disk_total": "30.0 GB", "disk_percent": 26.7,
    "nfc_connected": True, "throttle_ok": True, "throttle_flags": [],
}


class TestSettingsHardware:
    def test_get_returns_200(self, client, temp_config):
        with patch("app._get_hardware_stats", return_value=FAKE_HW_STATS):
            resp = client.get("/settings/hardware")
        assert resp.status_code == 200

    def test_renders_restart_and_reboot_buttons(self, client, temp_config):
        with patch("app._get_hardware_stats", return_value=FAKE_HW_STATS):
            resp = client.get("/settings/hardware")
        assert b"/settings/restart" in resp.data
        assert b"/settings/reboot" in resp.data

    def test_restarting_query_param_shows_banner(self, client, temp_config):
        with patch("app._get_hardware_stats", return_value=FAKE_HW_STATS):
            resp = client.get("/settings/hardware?restarting=1")
        assert b"estarting" in resp.data

    def test_rebooting_query_param_shows_banner(self, client, temp_config):
        with patch("app._get_hardware_stats", return_value=FAKE_HW_STATS):
            resp = client.get("/settings/hardware?rebooting=1")
        assert b"ebooting" in resp.data

    def test_renders_hw_stats(self, client, temp_config):
        with patch("app._get_hardware_stats", return_value=FAKE_HW_STATS):
            resp = client.get("/settings/hardware")
        assert b"vinyl-pi" in resp.data
        assert b"Raspberry Pi 4 Model B" in resp.data
        assert b"1.2 GB" in resp.data
        assert b"8.0 GB" in resp.data

    def test_renders_nfc_connected(self, client, temp_config):
        stats = {**FAKE_HW_STATS, "nfc_connected": True}
        with patch("app._get_hardware_stats", return_value=stats):
            resp = client.get("/settings/hardware")
        assert b"Connected" in resp.data

    def test_renders_nfc_not_connected(self, client, temp_config):
        stats = {**FAKE_HW_STATS, "nfc_connected": False}
        with patch("app._get_hardware_stats", return_value=stats):
            resp = client.get("/settings/hardware")
        assert b"Not connected" in resp.data

    def test_renders_power_ok(self, client, temp_config):
        stats = {**FAKE_HW_STATS, "throttle_ok": True, "throttle_flags": []}
        with patch("app._get_hardware_stats", return_value=stats):
            resp = client.get("/settings/hardware")
        assert b"OK" in resp.data

    def test_renders_power_warn(self, client, temp_config):
        stats = {**FAKE_HW_STATS, "throttle_ok": False,
                 "throttle_flags": ["Under-voltage detected"]}
        with patch("app._get_hardware_stats", return_value=stats):
            resp = client.get("/settings/hardware")
        assert b"Under-voltage detected" in resp.data

    def test_power_section_hidden_when_unavailable(self, client, temp_config):
        stats = {**FAKE_HW_STATS, "throttle_ok": None, "throttle_flags": None}
        with patch("app._get_hardware_stats", return_value=stats):
            resp = client.get("/settings/hardware")
        assert b"Under-voltage" not in resp.data


class TestGetHardwareStats:
    def test_returns_dict_with_expected_keys(self):
        from app import _get_hardware_stats
        with patch("app.psutil.boot_time", return_value=0), \
             patch("app.psutil.virtual_memory") as mock_mem, \
             patch("app.psutil.swap_memory") as mock_swap, \
             patch("app.psutil.disk_usage") as mock_disk, \
             patch("app.psutil.cpu_percent", return_value=10.0), \
             patch("app.psutil.cpu_count", return_value=4), \
             patch("app.psutil.cpu_freq", return_value=MagicMock(current=1800)), \
             patch("app.subprocess.run", side_effect=FileNotFoundError), \
             patch("builtins.open", side_effect=OSError):
            mock_mem.return_value = MagicMock(used=1e9, total=4e9, percent=25.0)
            mock_swap.return_value = MagicMock(used=0, total=0)
            mock_disk.return_value = MagicMock(used=8e9, free=22e9, total=30e9, percent=26.0)
            stats = _get_hardware_stats()
        assert "hostname" in stats
        assert "cpu_percent" in stats
        assert "ram_used" in stats
        assert "disk_used" in stats
        assert "nfc_connected" in stats
        assert "throttle_ok" in stats

    def test_throttle_ok_parsed(self):
        from app import _get_hardware_stats
        mock_result = MagicMock()
        mock_result.stdout = "throttled=0x0\n"
        with patch("app.psutil.boot_time", return_value=0), \
             patch("app.psutil.virtual_memory", return_value=MagicMock(used=0, total=0, percent=0)), \
             patch("app.psutil.swap_memory", return_value=MagicMock(used=0, total=0)), \
             patch("app.psutil.disk_usage", return_value=MagicMock(used=0, free=0, total=0, percent=0)), \
             patch("app.psutil.cpu_percent", return_value=0), \
             patch("app.psutil.cpu_count", return_value=1), \
             patch("app.psutil.cpu_freq", return_value=None), \
             patch("app.subprocess.run", return_value=mock_result), \
             patch("builtins.open", side_effect=OSError):
            stats = _get_hardware_stats()
        assert stats["throttle_ok"] is True
        assert stats["throttle_flags"] == []

    def test_throttle_warn_parsed(self):
        from app import _get_hardware_stats
        mock_result = MagicMock()
        mock_result.stdout = "throttled=0x50005\n"  # under-voltage + throttled
        with patch("app.psutil.boot_time", return_value=0), \
             patch("app.psutil.virtual_memory", return_value=MagicMock(used=0, total=0, percent=0)), \
             patch("app.psutil.swap_memory", return_value=MagicMock(used=0, total=0)), \
             patch("app.psutil.disk_usage", return_value=MagicMock(used=0, free=0, total=0, percent=0)), \
             patch("app.psutil.cpu_percent", return_value=0), \
             patch("app.psutil.cpu_count", return_value=1), \
             patch("app.psutil.cpu_freq", return_value=None), \
             patch("app.subprocess.run", return_value=mock_result), \
             patch("builtins.open", side_effect=OSError):
            stats = _get_hardware_stats()
        assert stats["throttle_ok"] is False
        assert "Under-voltage detected" in stats["throttle_flags"]

    def test_graceful_on_all_failures(self):
        from app import _get_hardware_stats
        with patch("app.psutil.boot_time", side_effect=Exception), \
             patch("app.psutil.virtual_memory", side_effect=Exception), \
             patch("app.psutil.swap_memory", side_effect=Exception), \
             patch("app.psutil.disk_usage", side_effect=Exception), \
             patch("app.psutil.cpu_percent", side_effect=Exception), \
             patch("app.psutil.cpu_count", side_effect=Exception), \
             patch("app.psutil.cpu_freq", side_effect=Exception), \
             patch("app.subprocess.run", side_effect=Exception), \
             patch("builtins.open", side_effect=OSError):
            stats = _get_hardware_stats()
        assert stats["uptime"] is None
        assert stats["ram_used"] is None
        assert stats["throttle_ok"] is None

    def _file_mock(self, **files):
        """Returns an open() side_effect that serves mock content by path substring."""
        from io import StringIO

        class _FakeFile:
            def __init__(self, content):
                self._content = content
                self._lines = iter(content.splitlines(keepends=True))
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def __iter__(self): return self._lines
            def read(self): return self._content

        def dispatch(path, *a, **kw):
            for key, content in files.items():
                if key in str(path):
                    return _FakeFile(content)
            raise OSError(f"no mock for {path}")
        return dispatch

    def _base_patches(self):
        return [
            patch("app.psutil.boot_time", return_value=0),
            patch("app.psutil.virtual_memory",
                  return_value=MagicMock(used=0, total=0, percent=0)),
            patch("app.psutil.swap_memory", return_value=MagicMock(used=0, total=0)),
            patch("app.psutil.disk_usage",
                  return_value=MagicMock(used=0, free=0, total=0, percent=0)),
            patch("app.psutil.cpu_percent", return_value=0),
            patch("app.psutil.cpu_count", return_value=1),
            patch("app.psutil.cpu_freq", return_value=None),
            patch("app.subprocess.run", side_effect=FileNotFoundError),
        ]

    def test_reads_os_release(self):
        from app import _get_hardware_stats
        import contextlib
        open_fn = self._file_mock(**{"/etc/os-release": 'PRETTY_NAME="Test OS 12"\nID=test\n'})
        with contextlib.ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            stack.enter_context(patch("builtins.open", side_effect=open_fn))
            stats = _get_hardware_stats()
        assert stats["os"] == "Test OS 12"

    def test_reads_proc_cpuinfo(self):
        from app import _get_hardware_stats
        import contextlib
        cpuinfo = "Serial\t: 0000\nModel\t: Raspberry Pi 4 Model B Rev 1.4\n"
        open_fn = self._file_mock(**{"/proc/cpuinfo": cpuinfo})
        with contextlib.ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            stack.enter_context(patch("builtins.open", side_effect=open_fn))
            stats = _get_hardware_stats()
        assert stats["cpu_model"] == "Raspberry Pi 4 Model B Rev 1.4"

    def test_reads_cpu_temp(self):
        from app import _get_hardware_stats
        import contextlib
        open_fn = self._file_mock(**{"thermal_zone0/temp": "51234\n"})
        with contextlib.ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            stack.enter_context(patch("builtins.open", side_effect=open_fn))
            stats = _get_hardware_stats()
        assert stats["cpu_temp_c"] == 51.2


class TestSettingsRestart:
    def test_post_calls_systemctl_restart(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        with patch("app.subprocess.Popen") as mock_popen:
            resp = client.post("/settings/restart", data={"csrf_token": "test-token"})
        assert resp.status_code == 302
        mock_popen.assert_called_once_with(["sudo", "systemctl", "restart", "vinyl-web"])

    def test_post_redirects_to_hardware_with_restarting(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        with patch("app.subprocess.Popen"):
            resp = client.post("/settings/restart", data={"csrf_token": "test-token"},
                               follow_redirects=True)
        assert b"estarting" in resp.data

    def test_post_csrf_missing_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/restart", data={})
        assert resp.status_code == 403

    def test_post_csrf_wrong_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/settings/restart", data={"csrf_token": "wrong"})
        assert resp.status_code == 403


class TestSettingsPlaceholder:
    @pytest.mark.parametrize("section", ["storage", "network"])
    def test_known_sections_return_200(self, client, temp_config, section):
        resp = client.get(f"/settings/{section}")
        assert resp.status_code == 200

    def test_unknown_section_returns_404(self, client, temp_config):
        resp = client.get("/settings/nonexistent")
        assert resp.status_code == 404

    def test_renders_title_and_note(self, client, temp_config):
        # "update" is no longer a placeholder — it has its own page
        resp = client.get("/settings/storage")
        assert b"Storage" in resp.data
        assert b"Coming soon" in resp.data


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
             patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
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
             patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK):
            resp = client.get("/read-tag")
        data = resp.get_json()
        assert data["tag_string"] == "apple:track:1440904001"
        assert data["tag_type"] == "track"
        assert data["content_id"] == "1440904001"

    def test_returns_album_info(self, client, temp_config):
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = "apple:1440903625"
        with patch("app.MockNFC", return_value=mock_nfc), \
             patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
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

    def test_no_card_returns_null_tag_string(self, client, temp_config):
        mock_nfc = MagicMock()
        mock_nfc.read_tag.return_value = None
        with patch("app.MockNFC", return_value=mock_nfc):
            resp = client.get("/read-tag")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tag_string"] is None
        assert data["error"] is None

    def test_tag_query_param_skips_nfc(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/read-tag?tag=apple:1440903625")
        data = resp.get_json()
        assert data["tag_string"] == "apple:1440903625"
        assert data["content_id"] == "1440903625"

    def test_pn532_reads_tag(self, client, tmp_path, monkeypatch):
        import app, json, queue as q
        config_file = tmp_path / "config_rt.json"
        config_file.write_text(json.dumps({"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"}))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        monkeypatch.setattr(app, "_nfc", MagicMock())
        fresh_queue = q.Queue(maxsize=1)
        fresh_queue.put("apple:1440903625")
        monkeypatch.setattr(app, "_nfc_read_queue", fresh_queue)
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/read-tag")
        assert resp.status_code == 200
        assert resp.get_json()["tag_string"] == "apple:1440903625"

    def test_mock_nfc_init_error_returns_error_json(self, client, temp_config):
        with patch("app._make_nfc", side_effect=RuntimeError("not installed")):
            resp = client.get("/read-tag")
        assert resp.status_code == 200
        assert "not installed" in resp.get_json()["error"]

    def test_pn532_drains_stale_queue_item(self, client, tmp_path, monkeypatch):
        import app, json, queue as q
        config_file = tmp_path / "config_drain.json"
        config_file.write_text(json.dumps({"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"}))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        monkeypatch.setattr(app, "_nfc", MagicMock())
        # Use maxsize=2 so a stale second item can sit in the queue after the main get()
        fresh_queue = q.Queue(maxsize=2)
        fresh_queue.put("apple:1440903625")
        fresh_queue.put("apple:9999999999")  # stale item
        monkeypatch.setattr(app, "_nfc_read_queue", fresh_queue)
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/read-tag")
        assert resp.status_code == 200
        assert resp.get_json()["tag_string"] == "apple:1440903625"
        assert fresh_queue.empty()  # stale item was drained

    def test_pn532_no_card_returns_null_tag(self, client, tmp_path, monkeypatch):
        import app, json, queue as q
        config_file = tmp_path / "config_rtb.json"
        config_file.write_text(json.dumps({"sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"}))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        monkeypatch.setattr(app, "_nfc", MagicMock())
        fresh_queue = q.Queue(maxsize=1)
        monkeypatch.setattr(app, "_nfc_read_queue", fresh_queue)
        monkeypatch.setattr(fresh_queue, "get", MagicMock(side_effect=q.Empty))
        resp = client.get("/read-tag")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tag_string"] is None
        assert data["error"] is None


class TestVerify:
    def test_returns_200(self, client, temp_config):
        resp = client.get("/verify")
        assert resp.status_code == 200

    def test_renders_read_tag_button(self, client, temp_config):
        resp = client.get("/verify")
        assert b"read" in resp.data.lower() or b"tap" in resp.data.lower()



class TestDetectSn:
    def test_returns_detected_sn(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "detect_sn", return_value="3"):
            resp = client.get("/detect-sn")
        assert resp.status_code == 200
        assert resp.get_json()["sn"] == "3"

    def test_returns_404_when_not_found(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "detect_sn", return_value=None):
            resp = client.get("/detect-sn")
        assert resp.status_code == 404

    def test_accepts_speaker_ip_param(self, client):
        with patch.object(providers.get_provider("apple"), "detect_sn", return_value="5"):
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
        }), patch.object(providers.get_provider("apple"), "get_track", return_value=[{
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

    def test_get_track_exception_returns_partial_data(self, client, temp_config):
        with patch("app.get_now_playing", return_value={
            "title": "Track One", "artist": "Test Artist", "album": "Test Album",
            "track_id": 1440904001, "paused": False,
        }), patch.object(providers.get_provider("apple"), "get_track", side_effect=Exception("network error")):
            resp = client.get("/now-playing")
        data = resp.get_json()
        assert data["playing"] is True
        assert data["album_id"] is None
        assert data["artwork_url"] is None


class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_ok_status(self, client):
        resp = client.get("/health")
        assert resp.get_json()["status"] == "ok"


class TestLogs:
    def test_returns_200(self, client):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "Mar 05 10:00:00 vinyl-pi vinyl-web[123]: INFO started\n"
            resp = client.get("/logs")
        assert resp.status_code == 200

    def test_shows_log_output(self, client):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "INFO started\n"
            resp = client.get("/logs")
        assert b"INFO started" in resp.data

    def test_no_journalctl_shows_fallback(self, client):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            resp = client.get("/logs")
        assert resp.status_code == 200
        assert b"only available when running under systemd" in resp.data


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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play/tag", json={"tag": "apple:1440903625"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_TRACKS, ANY, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_plays_track_tag(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play/tag", json={"tag": "apple:track:1440904001"})
        assert resp.status_code == 200
        mock_play.assert_called_once_with("10.0.0.12", SAMPLE_SINGLE_TRACK, ANY, "3",
                                          speaker_name="Family Room", config_path=ANY)

    def test_invalid_tag_returns_400(self, client, temp_config):
        resp = client.post("/play/tag", json={"tag": "notvalid"})
        assert resp.status_code == 400

    def test_missing_tag_returns_400(self, client):
        resp = client.post("/play/tag", json={})
        assert resp.status_code == 400

    def test_unknown_album_tag_returns_404(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=[]), \
             patch("app.play_album") as mock_play:
            resp = client.post("/play/tag", json={"tag": "apple:9999999"})
        assert resp.status_code == 404
        mock_play.assert_not_called()

    def test_unknown_track_tag_returns_404(self, client, temp_config):
        with patch.object(providers.get_provider("apple"), "get_track", return_value=[]), \
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
             patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
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
             patch.object(providers.get_provider("apple"), "get_track", return_value=SAMPLE_SINGLE_TRACK):
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
        with patch.object(providers.get_provider("apple"), "get_track", return_value=self.SAMPLE_TRACK):
            assert _format_existing_tag("apple:track:1440904001") == "Track One by Test Artist"

    def test_album_tag_returns_album_and_artist(self):
        from app import _format_existing_tag
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=self.SAMPLE_TRACKS):
            assert _format_existing_tag("apple:1440903625") == "Test Album by Test Artist"

    def test_empty_track_results_returns_raw_string(self):
        from app import _format_existing_tag
        with patch.object(providers.get_provider("apple"), "get_track", return_value=[]):
            assert _format_existing_tag("apple:track:1440904001") == "apple:track:1440904001"

    def test_empty_album_results_returns_raw_string(self):
        from app import _format_existing_tag
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=[]):
            assert _format_existing_tag("apple:1440903625") == "apple:1440903625"

    def test_exception_in_lookup_returns_raw_string(self):
        from app import _format_existing_tag
        with patch.object(providers.get_provider("apple"), "get_track", side_effect=Exception("network error")):
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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", side_effect=Exception("API error")):
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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/print?ids=1440903625")
        assert resp.status_code == 200

    def test_renders_album_name(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/print?ids=1440903625")
        assert b"Test Album" in resp.data

    def test_renders_artist(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
            resp = client.get("/print?ids=1440903625")
        assert b"Test Artist" in resp.data

    def test_renders_track_names(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS):
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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", side_effect=[tracks_a, tracks_b]):
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

    def test_non_digit_ids_returns_400(self, client):
        resp = client.get("/print?ids=abc,def")
        assert resp.status_code == 400

    def test_all_ids_not_found_returns_404(self, client):
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=[]):
            resp = client.get("/print?ids=9999999")
        assert resp.status_code == 404

    def test_partial_failure_returns_200_with_found_albums(self, client):
        tracks_a = [{"track_id": 1, "name": "Song A", "track_number": 1,
                     "artist": "Artist A", "album": "Album A",
                     "artwork_url": "https://example.com/a.jpg"}]
        with patch.object(providers.get_provider("apple"), "get_album_tracks", side_effect=[tracks_a, []]):
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
        monkeypatch.setattr(app, "_nfc_last_tag", None)
        return str(config_file)

    def test_plays_on_card_tap(self, pn532_config, monkeypatch):
        import app
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = ["apple:1440903625", KeyboardInterrupt]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
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
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)
        assert mock_play.call_count == 2

    def test_verify_tag_read_suppresses_loop_playback(self, pn532_config, monkeypatch):
        """Card read by /read-tag should not trigger playback in the NFC loop."""
        import app
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = ["apple:1440903625", KeyboardInterrupt]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        # Simulate /read-tag having already read this card
        monkeypatch.setattr(app, "_nfc_last_tag", "apple:1440903625")
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album") as mock_play:
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)
        mock_play.assert_not_called()

    def test_web_read_pending_delivers_to_queue_skips_play(self, pn532_config, monkeypatch):
        """When _web_read_pending is True, loop puts to queue and skips playback."""
        import app, queue as q
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = ["apple:1440903625", KeyboardInterrupt]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        monkeypatch.setattr(app, "_web_read_pending", True)
        fresh_queue = q.Queue(maxsize=1)
        monkeypatch.setattr(app, "_nfc_read_queue", fresh_queue)
        with patch("app.play_album") as mock_play:
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)
        mock_play.assert_not_called()
        assert fresh_queue.get_nowait() == "apple:1440903625"

    def test_web_read_pending_queue_full_continues(self, pn532_config, monkeypatch):
        """When queue is already full, put_nowait raises Full and loop continues."""
        import app, queue as q
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = ["apple:1440903625", KeyboardInterrupt]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        monkeypatch.setattr(app, "_web_read_pending", True)
        fresh_queue = q.Queue(maxsize=1)
        fresh_queue.put("existing")  # queue already full
        monkeypatch.setattr(app, "_nfc_read_queue", fresh_queue)
        with patch("app.play_album") as mock_play:
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)
        mock_play.assert_not_called()
        assert fresh_queue.get_nowait() == "existing"  # original item unchanged

    def test_start_nfc_thread_starts_thread(self, tmp_path, monkeypatch):
        import app
        config_file = tmp_path / "config_thread.json"
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532",
        }))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        with patch("app.PN532NFC"), \
             patch("app.threading.Thread") as mock_thread:
            mock_instance = MagicMock()
            mock_thread.return_value = mock_instance
            app._start_nfc_thread(str(config_file))
        mock_instance.start.assert_called_once()

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

    def test_read_exception_continues_loop(self, pn532_config, monkeypatch):
        import app
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = [Exception("I2C error"), KeyboardInterrupt]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with pytest.raises(KeyboardInterrupt):
            app._nfc_loop(pn532_config)

    def test_recovery_logged_after_errors_below_threshold(self, pn532_config, monkeypatch):
        """After errors (below threshold) then a successful read, logs recovery."""
        import app
        threshold = app._NFC_MAX_CONSECUTIVE_ERRORS
        mock_nfc = MagicMock()
        # Fewer than threshold errors, then success — no reset attempted.
        mock_nfc.read_tag.side_effect = (
            [Exception("OSError")] * (threshold - 1)
            + ["apple:1440903625", KeyboardInterrupt]
        )
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album"), \
             pytest.raises(KeyboardInterrupt):
            with patch.object(app.log, "info") as mock_info:
                app._nfc_loop(pn532_config)
        recovery_calls = [c for c in mock_info.call_args_list if "recovered" in str(c)]
        assert len(recovery_calls) == 1

    def test_play_exception_continues_loop(self, pn532_config, monkeypatch):
        import app
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = ["apple:1440903625", KeyboardInterrupt]
        monkeypatch.setattr(app, "_nfc", mock_nfc)
        with patch.object(providers.get_provider("apple"), "get_album_tracks", return_value=SAMPLE_TRACKS), \
             patch("app.play_album", side_effect=Exception("Sonos error")):
            with pytest.raises(KeyboardInterrupt):
                app._nfc_loop(pn532_config)

    def test_start_nfc_thread_config_fail_returns(self, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "CONFIG_PATH", str(tmp_path / "nonexistent.json"))
        with patch("app.PN532NFC") as mock_pn532:
            app._start_nfc_thread(str(tmp_path / "nonexistent.json"))
        mock_pn532.assert_not_called()

    def test_start_nfc_thread_pn532_init_fail_returns(self, tmp_path, monkeypatch):
        import app
        config_file = tmp_path / "config_pn.json"
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532",
        }))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        with patch("app.PN532NFC", side_effect=Exception("I2C error")), \
             patch("app.threading.Thread") as mock_thread:
            app._start_nfc_thread(str(config_file))
        mock_thread.assert_not_called()


class TestMakeNfc:
    def test_pn532_import_error_raises_runtime_error(self):
        import app
        with patch("app.PN532NFC", side_effect=ImportError("no module")):
            with pytest.raises(RuntimeError, match="not installed"):
                app._make_nfc({"nfc_mode": "pn532"})

    def test_mock_mode_returns_mock_nfc(self):
        import app
        from nfc_interface import MockNFC
        nfc = app._make_nfc({"nfc_mode": "mock"})
        assert isinstance(nfc, MockNFC)


class TestSigtermHandler:
    def test_acquires_lock_and_exits(self, monkeypatch):
        import app
        mock_lock = MagicMock()
        monkeypatch.setattr(app, "_nfc_lock", mock_lock)
        with pytest.raises(SystemExit):
            app._sigterm_handler(None, None)
        mock_lock.acquire.assert_called_once()


# ---------------------------------------------------------------------------
# Issue #12: Versioning, Release & In-App Update
# ---------------------------------------------------------------------------

class TestApiVersion:
    def test_returns_200(self, client):
        resp = client.get("/api/version")
        assert resp.status_code == 200

    def test_returns_version_key(self, client):
        resp = client.get("/api/version")
        data = resp.get_json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert data["version"]  # non-empty


class TestSettingsUpdatePage:
    def test_get_returns_200(self, client, temp_config):
        resp = client.get("/settings/update")
        assert resp.status_code == 200

    def test_shows_current_version(self, client, temp_config):
        import app
        resp = client.get("/settings/update")
        assert app.VERSION.encode() in resp.data

    def test_mock_mode_hides_update_controls(self, client, temp_config):
        # temp_config sets nfc_mode=mock; update controls should not appear
        resp = client.get("/settings/update")
        assert b"update-controls" not in resp.data

    def test_pn532_mode_shows_update_info(self, client, tmp_path, monkeypatch):
        import app, json
        config_file = tmp_path / "config_pi.json"
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.12", "nfc_mode": "pn532"
        }))
        monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
        monkeypatch.setattr(app, "_update_cache", None)
        with patch("app._check_for_update", return_value={
            "current": "0.1.0", "latest": "0.1.0", "update_available": False
        }):
            resp = client.get("/settings/update")
        # pn532 mode shows the latest version info
        assert b"up to date" in resp.data

    def test_updating_flag_shows_log_section(self, client, temp_config):
        resp = client.get("/settings/update?updating=1")
        assert resp.status_code == 200
        # updating=1 triggers live log polling section
        assert b"update-log" in resp.data or b"pollUpdate" in resp.data

    def test_success_state_deletes_log(self, client, temp_config, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        log.write_text("STATE: running\nSTATE: success\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        client.get("/settings/update")
        assert not log.exists()


class TestUpdateCheck:
    @pytest.fixture(autouse=True)
    def reset_cache(self, monkeypatch):
        import app
        monkeypatch.setattr(app, "_update_cache", None)

    def test_returns_current_version(self, client):
        import app
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = {"tag_name": "v" + app.VERSION}
            resp = client.get("/update/check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["current"] == app.VERSION

    def test_update_available_when_newer_version(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = {"tag_name": "v99.0.0"}
            resp = client.get("/update/check")
        data = resp.get_json()
        assert data["update_available"] is True
        assert data["latest"] == "99.0.0"

    def test_no_update_when_same_version(self, client):
        import app
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = {"tag_name": "v" + app.VERSION}
            resp = client.get("/update/check")
        data = resp.get_json()
        assert data["update_available"] is False

    def test_returns_safe_result_on_network_error(self, client):
        with patch("requests.get", side_effect=Exception("timeout")):
            resp = client.get("/update/check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["update_available"] is False

    def test_cache_populated_after_first_call(self, client):
        import app
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = {"tag_name": "v99.0.0"}
            client.get("/update/check")
        assert app._update_cache is not None
        assert app._update_cache[1]["latest"] == "99.0.0"

    def test_cache_returned_on_second_call(self, client):
        import app
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = {"tag_name": "v99.0.0"}
            client.get("/update/check")
            client.get("/update/check")
        assert mock_get.call_count == 1  # second call used cache


class TestUpdateApply:
    @pytest.fixture(autouse=True)
    def reset_cache(self, monkeypatch):
        import app
        monkeypatch.setattr(app, "_update_cache", None)

    def test_missing_csrf_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/update/apply", data={})
        assert resp.status_code == 403

    def test_wrong_csrf_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/update/apply", data={"csrf_token": "wrong"})
        assert resp.status_code == 403

    def test_update_already_running_returns_409(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        log.write_text("STATE: running\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/update/apply", data={"csrf_token": "test-token"})
        assert resp.status_code == 409

    def test_valid_request_launches_updater(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        monkeypatch.setattr(app, "_update_cache", None)
        with patch("app._check_for_update", return_value={
            "current": "0.1.0", "latest": "1.0.0", "update_available": True
        }):
            with patch("subprocess.Popen") as mock_popen:
                with client.session_transaction() as sess:
                    sess["csrf_token"] = "test-token"
                resp = client.post("/update/apply", data={"csrf_token": "test-token"})
        assert resp.status_code == 302
        assert mock_popen.called
        call_args = mock_popen.call_args[0][0]
        assert "updater.py" in call_args[1]
        assert call_args[2] == "1.0.0"

    def test_valid_request_redirects_to_settings_update(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        with patch("app._check_for_update", return_value={
            "current": "0.1.0", "latest": "0.1.0", "update_available": False
        }):
            with patch("subprocess.Popen"):
                with client.session_transaction() as sess:
                    sess["csrf_token"] = "test-token"
                resp = client.post("/update/apply", data={"csrf_token": "test-token"})
        assert "/settings/update" in resp.headers["Location"]
        assert "updating=1" in resp.headers["Location"]


class TestUpdateStatus:
    def test_returns_idle_when_no_log(self, client, tmp_path, monkeypatch):
        import app
        monkeypatch.setattr(app, "UPDATE_LOG", tmp_path / "no_update.log")
        resp = client.get("/update/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "idle"
        assert data["log"] == []

    def test_parses_running_state(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        log.write_text("STATE: running\nDownloading...\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        resp = client.get("/update/status")
        data = resp.get_json()
        assert data["state"] == "running"

    def test_parses_success_state(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        log.write_text("STATE: running\nInstalling...\nSTATE: success\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        resp = client.get("/update/status")
        data = resp.get_json()
        assert data["state"] == "success"

    def test_parses_failed_state(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        log.write_text("STATE: running\nError: something\nSTATE: failed\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        resp = client.get("/update/status")
        data = resp.get_json()
        assert data["state"] == "failed"

    def test_returns_last_20_lines(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        lines = [f"line {i}" for i in range(30)] + ["STATE: running"]
        log.write_text("\n".join(lines) + "\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        resp = client.get("/update/status")
        data = resp.get_json()
        assert len(data["log"]) == 20

    def test_includes_log_lines(self, client, tmp_path, monkeypatch):
        import app
        log = tmp_path / "update.log"
        log.write_text("Fetching tags\nInstalling deps\nSTATE: success\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        resp = client.get("/update/status")
        data = resp.get_json()
        assert any("Fetching" in line for line in data["log"])

    def test_stale_pid_returns_failed(self, client, tmp_path, monkeypatch):
        """If STATE: running but PID is dead, state should be 'failed'."""
        import app
        log = tmp_path / "update.log"
        # Use PID 1 which always exists, then mock os.kill to simulate dead PID
        log.write_text("STATE: running\nPID: 99999999\nDownloading...\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        with patch("app.os.kill", side_effect=ProcessLookupError):
            resp = client.get("/update/status")
        data = resp.get_json()
        assert data["state"] == "failed"

    def test_running_with_live_pid_stays_running(self, client, tmp_path, monkeypatch):
        """If STATE: running and PID is alive, state stays 'running'."""
        import app
        log = tmp_path / "update.log"
        log.write_text("STATE: running\nPID: 99999999\nDownloading...\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        with patch("app.os.kill", return_value=None):  # PID alive — no exception
            resp = client.get("/update/status")
        data = resp.get_json()
        assert data["state"] == "running"

    def test_running_without_pid_stays_running(self, client, tmp_path, monkeypatch):
        """Old-format log with no PID line: no stale detection, state stays 'running'."""
        import app
        log = tmp_path / "update.log"
        log.write_text("STATE: running\nDownloading...\n")
        monkeypatch.setattr(app, "UPDATE_LOG", log)
        resp = client.get("/update/status")
        data = resp.get_json()
        assert data["state"] == "running"


class TestUpdateAuto:
    def test_missing_csrf_returns_403(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/update/auto", data={})
        assert resp.status_code == 403

    def test_enables_auto_update(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/update/auto", data={"csrf_token": "test-token", "auto_update": "1"})
        assert resp.status_code == 302
        config = json.loads(temp_config.read_text())
        assert config["auto_update"] is True

    def test_disables_auto_update(self, client, temp_config):
        with client.session_transaction() as sess:
            sess["csrf_token"] = "test-token"
        resp = client.post("/update/auto", data={"csrf_token": "test-token"})
        assert resp.status_code == 302
        config = json.loads(temp_config.read_text())
        assert config["auto_update"] is False
