import threading
from unittest.mock import MagicMock, patch

import pytest

import core.nfc_service as nfc_service
import core.config as core_config


SAMPLE_TRACKS = [
    {"track_id": 1440904001, "name": "Track One", "album": "Test Album",
     "artist": "Test Artist", "artwork_url": "https://example.com/art.jpg",
     "album_id": 1440903625}
]

SAMPLE_PLAYLIST_INFO = {"title": "My Playlist", "artwork_url": "https://example.com/pl.jpg"}


@pytest.fixture(autouse=True)
def reset_nfc_state(tmp_path, monkeypatch):
    """Isolate NFC loop state and data dir for each test."""
    monkeypatch.setattr(core_config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core_config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(core_config, "TAGS_PATH", str(tmp_path / "tags.json"))
    monkeypatch.setattr(nfc_service, "_nfc_last_tag", None)


class TestAutoRecord:
    def test_album_tag_not_in_collection_is_recorded(self, tmp_path):
        parsed = {"service": "apple", "type": "album", "id": "1440903625"}
        nfc_service._auto_record("apple:1440903625", parsed, SAMPLE_TRACKS)
        tags = core_config._load_tags()
        assert len(tags) == 1
        assert tags[0]["tag_string"] == "apple:1440903625"
        assert tags[0]["name"] == "Test Album"
        assert tags[0]["artist"] == "Test Artist"
        assert tags[0]["type"] == "album"
        assert tags[0]["album_id"] == 1440903625

    def test_track_tag_is_recorded(self, tmp_path):
        parsed = {"service": "apple", "type": "track", "id": "1440904001"}
        nfc_service._auto_record("apple:track:1440904001", parsed, SAMPLE_TRACKS)
        tags = core_config._load_tags()
        assert tags[0]["name"] == "Track One"
        assert tags[0]["track_id"] == 1440904001
        assert tags[0]["album_id"] is None

    def test_playlist_tag_is_recorded(self, tmp_path):
        parsed = {"service": "apple", "type": "playlist", "id": "p.abc123"}
        nfc_service._auto_record("apple:playlist:p.abc123", parsed, SAMPLE_PLAYLIST_INFO)
        tags = core_config._load_tags()
        assert tags[0]["name"] == "My Playlist"
        assert tags[0]["playlist_id"] == "p.abc123"

    def test_failure_does_not_raise(self, tmp_path):
        parsed = {"service": "apple", "type": "album", "id": "123"}
        # Pass empty list — indexing provider_result[0] will raise IndexError
        nfc_service._auto_record("apple:123", parsed, [])
        # Should not raise; tags file untouched
        assert core_config._load_tags() == []


class TestNfcLoopAutoRegister:
    def _make_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        import json
        config_file.write_text(json.dumps({
            "sn": "3", "speaker_ip": "10.0.0.1",
            "speaker_name": "Test", "nfc_mode": "mock",
        }))

    def _run_loop(self, tmp_path, read_side_effects, tracks, monkeypatch, record_tag_side_effect=None):
        """Run _nfc_loop until KeyboardInterrupt (a BaseException, not caught by the loop)."""
        self._make_config(tmp_path)
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = read_side_effects + [KeyboardInterrupt()]
        monkeypatch.setattr(nfc_service, "_nfc", mock_nfc)

        provider = MagicMock()
        provider.get_album_tracks.return_value = tracks

        kwargs = {}
        if record_tag_side_effect is not None:
            kwargs["record_tag_patch"] = patch("core.nfc_service.record_tag", side_effect=record_tag_side_effect)

        with patch("core.nfc_service.get_provider", return_value=provider), \
             patch("core.nfc_service.play_album"), \
             patch("core.nfc_service.play_playlist"):
            try:
                nfc_service._nfc_loop(str(tmp_path / "config.json"))
            except KeyboardInterrupt:
                pass
        return provider

    def test_unknown_tag_is_auto_registered(self, tmp_path, monkeypatch):
        self._run_loop(tmp_path, ["apple:1440903625", None], SAMPLE_TRACKS, monkeypatch)
        tags = core_config._load_tags()
        assert len(tags) == 1
        assert tags[0]["tag_string"] == "apple:1440903625"

    def test_known_tag_is_not_re_registered(self, tmp_path, monkeypatch):
        core_config.record_tag("apple:1440903625", {"name": "Already There", "type": "album"})
        self._run_loop(tmp_path, ["apple:1440903625", None], SAMPLE_TRACKS, monkeypatch)
        tags = core_config._load_tags()
        assert len(tags) == 1
        assert tags[0]["name"] == "Already There"  # not overwritten

    def test_auto_record_failure_does_not_stop_loop(self, tmp_path, monkeypatch):
        self._make_config(tmp_path)
        mock_nfc = MagicMock()
        mock_nfc.read_tag.side_effect = [
            "apple:1440903625", None,
            "apple:9999999", None,
            KeyboardInterrupt(),
        ]
        monkeypatch.setattr(nfc_service, "_nfc", mock_nfc)

        provider = MagicMock()
        provider.get_album_tracks.return_value = SAMPLE_TRACKS

        with patch("core.nfc_service.get_provider", return_value=provider), \
             patch("core.nfc_service.play_album"), \
             patch("core.nfc_service.play_playlist"), \
             patch("core.nfc_service.record_tag", side_effect=RuntimeError("disk full")):
            try:
                nfc_service._nfc_loop(str(tmp_path / "config.json"))
            except KeyboardInterrupt:
                pass
        # Loop reached second tag — play_album called twice
        assert provider.get_album_tracks.call_count == 2
