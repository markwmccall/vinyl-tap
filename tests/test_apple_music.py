import json
import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import (
    SAMPLE_SEARCH_RESPONSE, SAMPLE_LOOKUP_RESPONSE,
    SAMPLE_SONG_SEARCH_RESPONSE, SAMPLE_TRACK_LOOKUP_RESPONSE,
)


def make_mock_response(data):
    """Create a mock urlopen response that works as a context manager."""
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = json.dumps(data).encode()
    return mock_response


class TestBuildTrackUri:
    def test_basic(self):
        from apple_music import build_track_uri
        uri = build_track_uri(1440904001, "3")
        assert uri == "x-sonos-http:song%3a1440904001.mp4?sid=204&flags=8232&sn=3"

    def test_different_sn(self):
        from apple_music import build_track_uri
        uri = build_track_uri(9999, "5")
        assert uri == "x-sonos-http:song%3a9999.mp4?sid=204&flags=8232&sn=5"


class TestUpgradeArtworkUrl:
    def test_upgrades_resolution(self):
        from apple_music import upgrade_artwork_url
        assert upgrade_artwork_url("https://example.com/100x100bb.jpg") == "https://example.com/600x600bb.jpg"

    def test_no_change_if_not_matching(self):
        from apple_music import upgrade_artwork_url
        url = "https://example.com/600x600bb.jpg"
        assert upgrade_artwork_url(url) == url


class TestSearchAlbums:
    def test_returns_album_list(self):
        from apple_music import search_albums
        mock_resp = make_mock_response(SAMPLE_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_albums("Test Album Test Artist")
        assert len(results) == 1
        assert results[0]["id"] == 1440903625
        assert results[0]["name"] == "Test Album"
        assert results[0]["artist"] == "Test Artist"
        assert "artwork_url" in results[0]

    def test_artwork_url_upgraded(self):
        from apple_music import search_albums
        mock_resp = make_mock_response(SAMPLE_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_albums("Test Album Test Artist")
        assert "600x600bb" in results[0]["artwork_url"]

    def test_empty_results(self):
        from apple_music import search_albums
        mock_resp = make_mock_response({"resultCount": 0, "results": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_albums("xyznotanalbum")
        assert results == []


class TestGetAlbumTracks:
    def test_filters_collection_row(self):
        from apple_music import get_album_tracks
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_album_tracks(1440903625)
        assert len(tracks) == 2

    def test_sorted_by_track_number(self):
        from apple_music import get_album_tracks
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_album_tracks(1440903625)
        assert tracks[0]["name"] == "Track One"
        assert tracks[1]["name"] == "Track Two"

    def test_fields_mapped_correctly(self):
        from apple_music import get_album_tracks
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_album_tracks(1440903625)
        t = tracks[0]
        assert t["track_id"] == 1440904001
        assert t["name"] == "Track One"
        assert t["track_number"] == 1
        assert t["artist"] == "Test Artist"
        assert t["album"] == "Test Album"
        assert "artwork_url" in t

    def test_artwork_url_upgraded(self):
        from apple_music import get_album_tracks
        mock_resp = make_mock_response(SAMPLE_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_album_tracks(1440903625)
        assert "600x600bb" in tracks[0]["artwork_url"]

    def test_skips_results_missing_wrapper_type(self):
        from apple_music import get_album_tracks
        response = {"resultCount": 1, "results": [{"trackId": 1, "trackName": "X"}]}
        mock_resp = make_mock_response(response)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_album_tracks(1440903625)
        assert tracks == []

    def test_sorted_by_disc_then_track_number(self):
        from apple_music import get_album_tracks
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
            tracks = get_album_tracks(1)
        assert [t["name"] for t in tracks] == ["D1T1", "D1T2", "D2T1", "D2T2"]


class TestGetTrack:
    def test_returns_single_item_list(self):
        from apple_music import get_track
        mock_resp = make_mock_response(SAMPLE_TRACK_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_track(1440904001)
        assert len(tracks) == 1

    def test_fields_mapped_correctly(self):
        from apple_music import get_track
        mock_resp = make_mock_response(SAMPLE_TRACK_LOOKUP_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_track(1440904001)
        t = tracks[0]
        assert t["track_id"] == 1440904001
        assert t["name"] == "Track One"
        assert t["artist"] == "Test Artist"
        assert t["album"] == "Test Album"
        assert "artwork_url" in t
        assert "album_id" in t

    def test_returns_empty_list_when_not_found(self):
        from apple_music import get_track
        mock_resp = make_mock_response({"resultCount": 0, "results": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tracks = get_track(9999)
        assert tracks == []


class TestSearchSongs:
    def test_returns_song_list(self):
        from apple_music import search_songs
        mock_resp = make_mock_response(SAMPLE_SONG_SEARCH_RESPONSE)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_songs("Track One Test Artist")
        assert len(results) == 2
        assert results[0]["id"] == 1440904001
        assert results[0]["name"] == "Track One"
        assert results[0]["artist"] == "Test Artist"
        assert results[0]["album"] == "Test Album"
        assert "artwork_url" in results[0]

    def test_empty_results(self):
        from apple_music import search_songs
        mock_resp = make_mock_response({"resultCount": 0, "results": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_songs("xyznotasong")
        assert results == []
