import json
import pytest
from unittest.mock import MagicMock


# --- iTunes API sample data ---

SAMPLE_SEARCH_RESPONSE = {
    "resultCount": 1,
    "results": [
        {
            "wrapperType": "collection",
            "collectionId": 1440903625,
            "collectionName": "Test Album",
            "artistName": "Test Artist",
            "artworkUrl100": "https://example.com/100x100bb.jpg",
        }
    ],
}

# Note: first item is the album row (wrapperType "collection") - must be filtered out
SAMPLE_SONG_SEARCH_RESPONSE = {
    "resultCount": 2,
    "results": [
        {
            "wrapperType": "track",
            "trackId": 1440904001,
            "trackName": "Track One",
            "trackNumber": 1,
            "artistName": "Test Artist",
            "collectionName": "Test Album",
            "artworkUrl100": "https://example.com/100x100bb.jpg",
        },
        {
            "wrapperType": "track",
            "trackId": 1440904002,
            "trackName": "Track Two",
            "trackNumber": 2,
            "artistName": "Test Artist",
            "collectionName": "Test Album",
            "artworkUrl100": "https://example.com/100x100bb.jpg",
        },
    ],
}

SAMPLE_TRACK_LOOKUP_RESPONSE = {
    "resultCount": 1,
    "results": [
        {
            "wrapperType": "track",
            "trackId": 1440904001,
            "trackName": "Track One",
            "trackNumber": 1,
            "artistName": "Test Artist",
            "collectionName": "Test Album",
            "artworkUrl100": "https://example.com/100x100bb.jpg",
        },
    ],
}

SAMPLE_LOOKUP_RESPONSE = {
    "resultCount": 3,
    "results": [
        {
            "wrapperType": "collection",
            "collectionId": 1440903625,
            "collectionName": "Test Album",
            "artistName": "Test Artist",
            "releaseDate": "1999-03-15T08:00:00Z",
            "copyright": "℗ 1999 Test Records",
        },
        {
            "wrapperType": "track",
            "trackId": 1440904001,
            "trackName": "Track One",
            "trackNumber": 1,
            "artistName": "Test Artist",
            "collectionName": "Test Album",
            "collectionId": 1440903625,
            "artworkUrl100": "https://example.com/100x100bb.jpg",
            "trackTimeMillis": 285333,
        },
        {
            "wrapperType": "track",
            "trackId": 1440904002,
            "trackName": "Track Two",
            "trackNumber": 2,
            "artistName": "Test Artist",
            "collectionName": "Test Album",
            "collectionId": 1440903625,
            "artworkUrl100": "https://example.com/100x100bb.jpg",
            "trackTimeMillis": 193000,
        },
    ],
}


# --- Mock SoCo speaker ---

@pytest.fixture
def mock_speaker(mocker):
    speaker = MagicMock()
    mocker.patch("soco.SoCo", return_value=speaker)
    return speaker


# --- Flask test client ---

@pytest.fixture
def client():
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# --- Temp config file ---

@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "sn": "3",
        "speaker_ip": "10.0.0.12",
        "speaker_name": "Family Room",
        "nfc_mode": "mock"
    }))
    import app
    monkeypatch.setattr(app, "CONFIG_PATH", str(config_file))
    return config_file
