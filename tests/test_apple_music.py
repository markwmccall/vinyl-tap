import json
import pytest
from unittest.mock import patch, MagicMock, call
from tests.conftest import (
    SAMPLE_SEARCH_RESPONSE, SAMPLE_LOOKUP_RESPONSE,
    SAMPLE_SONG_SEARCH_RESPONSE, SAMPLE_TRACK_LOOKUP_RESPONSE,
)
from providers.apple_music import AppleMusicProvider, _upgrade_artwork_url

_p = AppleMusicProvider()


def _make_smapi_provider():
    """Create a provider with mock SMAPI client configured."""
    p = AppleMusicProvider()
    p.configure_smapi("tok", "key", "Sonos_hh_abc")
    return p


def make_mock_response(data):
    """Create a mock urlopen response that works as a context manager."""
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = json.dumps(data).encode()
    return mock_response


class TestBuildTrackUri:
    def test_basic(self):
        uri = _p.build_track_uri(1440904001, "3")
        assert uri == "x-sonos-http:song%3a1440904001.mp4?sid=204&flags=8232&sn=3"

    def test_different_sn(self):
        uri = _p.build_track_uri(9999, "5")
        assert uri == "x-sonos-http:song%3a9999.mp4?sid=204&flags=8232&sn=5"


class TestUpgradeArtworkUrl:
    def test_upgrades_resolution(self):
        assert _upgrade_artwork_url("https://example.com/100x100bb.jpg") == "https://example.com/600x600bb.jpg"

    def test_no_change_if_not_matching(self):
        url = "https://example.com/600x600bb.jpg"
        assert _upgrade_artwork_url(url) == url


class TestSearchAlbums:
    def test_returns_album_list(self):
        mock_resp = make_mock_response(SAMPLE_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = _p.search_albums("Test Album Test Artist")
        assert len(results) == 1
        assert results[0]["id"] == 1440903625
        assert results[0]["name"] == "Test Album"
        assert results[0]["artist"] == "Test Artist"
        assert "artwork_url" in results[0]

    def test_artwork_url_upgraded(self):
        mock_resp = make_mock_response(SAMPLE_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = _p.search_albums("Test Album Test Artist")
        assert "600x600bb" in results[0]["artwork_url"]

    def test_empty_results(self):
        mock_resp = make_mock_response({"resultCount": 0, "results": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = _p.search_albums("xyznotanalbum")
        assert results == []


class TestGetAlbumTracks:
    def test_filters_collection_row(self):
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_album_tracks(1440903625)
        assert len(tracks) == 2

    def test_sorted_by_track_number(self):
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_album_tracks(1440903625)
        assert tracks[0]["name"] == "Track One"
        assert tracks[1]["name"] == "Track Two"

    def test_fields_mapped_correctly(self):
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_album_tracks(1440903625)
        t = tracks[0]
        assert t["track_id"] == 1440904001
        assert t["name"] == "Track One"
        assert t["track_number"] == 1
        assert t["artist"] == "Test Artist"
        assert t["album"] == "Test Album"
        assert "artwork_url" in t

    def test_artwork_url_upgraded(self):
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_album_tracks(1440903625)
        assert "600x600bb" in tracks[0]["artwork_url"]

    def test_skips_results_missing_wrapper_type(self):
        response = {"resultCount": 1, "results": [{"trackId": 1, "trackName": "X"}]}
        mock_resp = make_mock_response(response)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_album_tracks(1440903625)
        assert tracks == []

    def test_sorted_by_disc_then_track_number(self):
        response = {
            "resultCount": 5,
            "results": [
                {"wrapperType": "collection", "collectionId": 1, "collectionName": "A",
                 "artistName": "X", "releaseDate": "2000-01-01T00:00:00Z", "copyright": ""},
                {"wrapperType": "track", "trackId": 101, "trackName": "D1T1",
                 "trackNumber": 1, "discNumber": 1, "artistName": "X",
                 "collectionName": "A", "collectionId": 1, "artworkUrl100": ""},
                {"wrapperType": "track", "trackId": 201, "trackName": "D2T1",
                 "trackNumber": 1, "discNumber": 2, "artistName": "X",
                 "collectionName": "A", "collectionId": 1, "artworkUrl100": ""},
                {"wrapperType": "track", "trackId": 102, "trackName": "D1T2",
                 "trackNumber": 2, "discNumber": 1, "artistName": "X",
                 "collectionName": "A", "collectionId": 1, "artworkUrl100": ""},
                {"wrapperType": "track", "trackId": 202, "trackName": "D2T2",
                 "trackNumber": 2, "discNumber": 2, "artistName": "X",
                 "collectionName": "A", "collectionId": 1, "artworkUrl100": ""},
            ],
        }
        mock_resp = make_mock_response(response)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_album_tracks(1)
        assert [t["name"] for t in tracks] == ["D1T1", "D1T2", "D2T1", "D2T2"]


class TestGetTrack:
    def test_returns_single_item_list(self):
        mock_resp = make_mock_response(SAMPLE_TRACK_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_track(1440904001)
        assert len(tracks) == 1

    def test_fields_mapped_correctly(self):
        mock_resp = make_mock_response(SAMPLE_TRACK_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_track(1440904001)
        t = tracks[0]
        assert t["track_id"] == 1440904001
        assert t["name"] == "Track One"
        assert t["artist"] == "Test Artist"
        assert t["album"] == "Test Album"
        assert "artwork_url" in t
        assert "album_id" in t

    def test_returns_empty_list_when_not_found(self):
        mock_resp = make_mock_response({"resultCount": 0, "results": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = _p.get_track(9999)
        assert tracks == []


class TestSearchSongs:
    def test_returns_song_list(self):
        mock_resp = make_mock_response(SAMPLE_SONG_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = _p.search_songs("Track One Test Artist")
        assert len(results) == 2
        assert results[0]["id"] == 1440904001
        assert results[0]["name"] == "Track One"
        assert results[0]["artist"] == "Test Artist"
        assert results[0]["album"] == "Test Album"
        assert "artwork_url" in results[0]

    def test_empty_results(self):
        mock_resp = make_mock_response({"resultCount": 0, "results": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = _p.search_songs("xyznotasong")
        assert results == []


# --- SMAPI integration tests ---

class TestSmapiAvailable:
    def test_not_available_by_default(self):
        p = AppleMusicProvider()
        assert not p.smapi_available

    def test_available_after_configure(self):
        p = _make_smapi_provider()
        assert p.smapi_available


class TestSmapiSearchAlbums:
    def test_uses_smapi_when_configured(self):
        p = _make_smapi_provider()
        p._smapi.search = MagicMock(return_value=([
            {"id": "album:1440902935", "title": "OK Computer",
             "artist": "Radiohead", "item_type": "album",
             "album_art_uri": "https://example.com/100x100bb.jpg"},
        ], 1))
        results = p.search_albums("Radiohead")

        assert len(results) == 1
        assert results[0]["id"] == 1440902935
        assert results[0]["name"] == "OK Computer"
        assert results[0]["artist"] == "Radiohead"
        assert "600x600bb" in results[0]["artwork_url"]
        p._smapi.search.assert_called_once_with("Radiohead")

    def test_filters_non_album_items(self):
        p = _make_smapi_provider()
        p._smapi.search = MagicMock(return_value=([
            {"id": "album:123", "title": "Album", "artist": "A", "item_type": "album"},
            {"id": "track:456", "title": "Song", "artist": "A", "item_type": "track"},
        ], 2))
        results = p.search_albums("test")
        assert len(results) == 1
        assert results[0]["name"] == "Album"

    def test_falls_back_to_itunes_on_smapi_error(self):
        p = _make_smapi_provider()
        from providers.smapi_client import SmapiError
        p._smapi.search = MagicMock(side_effect=SmapiError("fail", "500"))
        mock_resp = make_mock_response(SAMPLE_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = p.search_albums("Test Album")
        assert len(results) == 1
        assert results[0]["id"] == 1440903625


class TestSmapiSearchSongs:
    def test_uses_smapi_when_configured(self):
        p = _make_smapi_provider()
        p._smapi.search = MagicMock(return_value=([
            {"id": "track:999", "title": "Creep", "artist": "Radiohead",
             "album": "Pablo Honey", "item_type": "track",
             "album_art_uri": "https://example.com/100x100bb.jpg"},
        ], 1))
        results = p.search_songs("Creep")

        assert len(results) == 1
        assert results[0]["id"] == 999
        assert results[0]["name"] == "Creep"
        assert results[0]["album"] == "Pablo Honey"

    def test_filters_non_track_items(self):
        p = _make_smapi_provider()
        p._smapi.search = MagicMock(return_value=([
            {"id": "album:123", "title": "Album", "artist": "A", "item_type": "album"},
            {"id": "track:456", "title": "Song", "artist": "A", "item_type": "track"},
        ], 2))
        results = p.search_songs("test")
        assert len(results) == 1
        assert results[0]["name"] == "Song"

    def test_strips_song_prefix(self):
        p = _make_smapi_provider()
        p._smapi.search = MagicMock(return_value=([
            {"id": "song:12345", "title": "Song", "artist": "A",
             "album": "B", "item_type": "track", "album_art_uri": ""},
        ], 1))
        results = p.search_songs("test")
        assert len(results) == 1
        assert results[0]["id"] == 12345

    def test_skips_non_numeric_ids(self):
        p = _make_smapi_provider()
        p._smapi.search = MagicMock(return_value=([
            {"id": "track:p.LibraryOnlyXYZ", "title": "Library Track", "artist": "A",
             "album": "B", "item_type": "track", "album_art_uri": ""},
            {"id": "track:99999", "title": "Catalog Track", "artist": "A",
             "album": "B", "item_type": "track", "album_art_uri": ""},
        ], 2))
        results = p.search_songs("test")
        assert len(results) == 1
        assert results[0]["id"] == 99999
        assert results[0]["name"] == "Catalog Track"


class TestSmapiAutoRefresh:
    def test_refreshes_token_on_auth_expired(self):
        from providers.smapi_client import AuthTokenExpired
        p = _make_smapi_provider()
        callback = MagicMock()
        p._on_token_refresh = callback

        # First call raises AuthTokenExpired, refresh succeeds, second call works
        p._smapi.search = MagicMock(side_effect=[
            AuthTokenExpired("expired", "SOAP-ENV:Client-AuthTokenExpired"),
            ([{"id": "album:1", "title": "A", "artist": "B", "item_type": "album"}], 1),
        ])
        p._smapi.refresh_auth_token = MagicMock(return_value=("new_tok", "new_key"))

        results = p.search_albums("test")
        assert len(results) == 1
        p._smapi.refresh_auth_token.assert_called_once()
        callback.assert_called_once_with("new_tok", "new_key")

    def test_falls_back_to_itunes_if_refresh_also_fails(self):
        from providers.smapi_client import AuthTokenExpired, SmapiError
        p = _make_smapi_provider()
        p._smapi.search = MagicMock(
            side_effect=AuthTokenExpired("expired", "SOAP-ENV:Client-AuthTokenExpired")
        )
        p._smapi.refresh_auth_token = MagicMock(
            side_effect=SmapiError("refresh failed", "500")
        )
        mock_resp = make_mock_response(SAMPLE_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = p.search_albums("Test Album")
        # Falls through to iTunes
        assert len(results) == 1
        assert results[0]["id"] == 1440903625


class TestConfigureSmapi:
    def test_configure_smapi_on_app_startup(self, temp_config, monkeypatch):
        """_configure_smapi reads tokens from config and calls provider.configure_smapi."""
        import app
        config = json.loads(temp_config.read_text())
        config["services"] = {"apple": {
            "sn": "3",
            "smapi_token": "test_tok",
            "smapi_key": "test_key",
            "smapi_household_id": "Sonos_hh_test",
        }}
        temp_config.write_text(json.dumps(config))

        # Reset provider to fresh state
        from providers import _providers
        from providers.apple_music import AppleMusicProvider
        fresh = AppleMusicProvider()
        _providers["apple"] = fresh

        app._configure_smapi()
        assert fresh.smapi_available
        assert fresh._smapi.token == "test_tok"
        assert fresh._smapi.household_id == "Sonos_hh_test"

        # Restore original singleton
        _providers["apple"] = AppleMusicProvider()

    def test_configure_smapi_noop_without_tokens(self, temp_config, monkeypatch):
        """_configure_smapi is a no-op when SMAPI tokens are not in config."""
        import app
        from providers import _providers
        from providers.apple_music import AppleMusicProvider
        fresh = AppleMusicProvider()
        _providers["apple"] = fresh

        app._configure_smapi()
        assert not fresh.smapi_available

        _providers["apple"] = AppleMusicProvider()


class TestConfigureSonos:
    def test_sets_sonos_available(self):
        from unittest.mock import MagicMock
        p = AppleMusicProvider()
        client = MagicMock()
        p.configure_sonos(client, "acc-tok", "ref-tok", "hh-123")
        assert p.sonos_available

    def test_stores_household_id(self):
        from unittest.mock import MagicMock
        p = AppleMusicProvider()
        p.configure_sonos(MagicMock(), "acc", "ref", "hh-456")
        assert p._sonos_household_id == "hh-456"

    def test_stores_tokens(self):
        from unittest.mock import MagicMock
        p = AppleMusicProvider()
        p.configure_sonos(MagicMock(), "my-access", "my-refresh", "hh-789")
        assert p._sonos_access_token == "my-access"
        assert p._sonos_refresh_token == "my-refresh"

    def test_stores_on_token_refresh_callback(self):
        from unittest.mock import MagicMock
        p = AppleMusicProvider()
        cb = MagicMock()
        p.configure_sonos(MagicMock(), "a", "r", "hh", on_token_refresh=cb)
        assert p._on_sonos_token_refresh is cb

    def test_not_available_before_configure(self):
        p = AppleMusicProvider()
        assert not p.sonos_available
