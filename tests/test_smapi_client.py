"""Tests for the SMAPI SOAP client."""
import io
import urllib.error
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from providers.smapi_client import (
    AuthTokenExpired,
    SmapiClient,
    SmapiError,
    _xml_escape,
)


# --- Sample SMAPI XML responses ---

SEARCH_RESPONSE = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <searchResponse xmlns="http://www.sonos.com/Services/1.1">
      <searchResult>
        <index>0</index>
        <count>2</count>
        <total>42</total>
        <mediaCollection>
          <id>album:1440902935</id>
          <itemType>album</itemType>
          <title>OK Computer</title>
          <artist>Radiohead</artist>
          <albumArtURI>https://example.com/art1.jpg</albumArtURI>
        </mediaCollection>
        <mediaMetadata>
          <id>track:1440903001</id>
          <itemType>track</itemType>
          <title>Paranoid Android</title>
          <artist>Radiohead</artist>
          <album>OK Computer</album>
          <albumArtURI>https://example.com/art2.jpg</albumArtURI>
        </mediaMetadata>
      </searchResult>
    </searchResponse>
  </s:Body>
</s:Envelope>"""

GET_METADATA_RESPONSE = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <getMetadataResponse xmlns="http://www.sonos.com/Services/1.1">
      <getMetadataResult>
        <index>0</index>
        <count>2</count>
        <total>12</total>
        <mediaMetadata>
          <id>track:1440903001</id>
          <title>Airbag</title>
          <artist>Radiohead</artist>
          <album>OK Computer</album>
        </mediaMetadata>
        <mediaMetadata>
          <id>track:1440903002</id>
          <title>Paranoid Android</title>
          <artist>Radiohead</artist>
          <album>OK Computer</album>
        </mediaMetadata>
      </getMetadataResult>
    </getMetadataResponse>
  </s:Body>
</s:Envelope>"""

GET_MEDIA_METADATA_RESPONSE = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <getMediaMetadataResponse xmlns="http://www.sonos.com/Services/1.1">
      <mediaMetadata>
        <id>track:1440903001</id>
        <title>Paranoid Android</title>
        <artist>Radiohead</artist>
        <album>OK Computer</album>
        <albumArtURI>https://example.com/art.jpg</albumArtURI>
      </mediaMetadata>
    </getMediaMetadataResponse>
  </s:Body>
</s:Envelope>"""

REFRESH_TOKEN_RESPONSE = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <refreshAuthTokenResponse xmlns="http://www.sonos.com/Services/1.1">
      <authToken>NewTokenValue123</authToken>
      <privateKey>9999999999</privateKey>
    </refreshAuthTokenResponse>
  </s:Body>
</s:Envelope>"""

AUTH_EXPIRED_FAULT = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <s:Fault>
      <faultcode>s:Client</faultcode>
      <faultstring>AuthTokenExpired</faultstring>
      <detail>
        <ErrorCode>SOAP-ENV:Client-AuthTokenExpired</ErrorCode>
      </detail>
    </s:Fault>
  </s:Body>
</s:Envelope>"""

GENERIC_FAULT = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <s:Fault>
      <faultcode>s:Server</faultcode>
      <faultstring>Something went wrong</faultstring>
      <detail>
        <ErrorCode>999</ErrorCode>
      </detail>
    </s:Fault>
  </s:Body>
</s:Envelope>"""


def _make_client():
    return SmapiClient(
        endpoint="https://sonos-music.apple.com/ws/SonosSoap",
        token="test_token",
        key="test_key",
        household_id="Sonos_test_household_abc123",
    )


def _mock_urlopen(response_xml):
    """Return a context-manager mock for urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_xml.encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestSearch:
    @patch("urllib.request.urlopen")
    def test_search_returns_items_and_total(self, mock_open):
        mock_open.return_value = _mock_urlopen(SEARCH_RESPONSE)
        client = _make_client()
        items, total = client.search("Radiohead")

        assert total == 42
        assert len(items) == 2

        album = items[0]
        assert album["id"] == "album:1440902935"
        assert album["title"] == "OK Computer"
        assert album["artist"] == "Radiohead"
        assert album["item_type"] == "album"
        assert album["album_art_uri"] == "https://example.com/art1.jpg"

        track = items[1]
        assert track["id"] == "track:1440903001"
        assert track["title"] == "Paranoid Android"
        assert track["item_type"] == "track"
        assert track["album"] == "OK Computer"

    @patch("urllib.request.urlopen")
    def test_search_sends_correct_soap_action(self, mock_open):
        mock_open.return_value = _mock_urlopen(SEARCH_RESPONSE)
        client = _make_client()
        client.search("test query", search_id="album", index=10, count=25)

        req = mock_open.call_args[0][0]
        assert req.get_header("Soapaction") == '"http://www.sonos.com/Services/1.1#search"'
        body = req.data.decode("utf-8")
        assert "<ns:term>test query</ns:term>" in body
        assert "<ns:id>album</ns:id>" in body
        assert "<ns:index>10</ns:index>" in body
        assert "<ns:count>25</ns:count>" in body

    @patch("urllib.request.urlopen")
    def test_search_includes_credentials(self, mock_open):
        mock_open.return_value = _mock_urlopen(SEARCH_RESPONSE)
        client = _make_client()
        client.search("test")

        body = mock_open.call_args[0][0].data.decode("utf-8")
        assert "<ns:token>test_token</ns:token>" in body
        assert "<ns:key>test_key</ns:key>" in body
        assert "<ns:householdId>Sonos_test_household_abc123</ns:householdId>" in body

    @patch("urllib.request.urlopen")
    def test_search_escapes_xml_in_term(self, mock_open):
        mock_open.return_value = _mock_urlopen(SEARCH_RESPONSE)
        client = _make_client()
        client.search("rock & roll <live>")

        body = mock_open.call_args[0][0].data.decode("utf-8")
        assert "rock &amp; roll &lt;live&gt;" in body


class TestGetMetadata:
    @patch("urllib.request.urlopen")
    def test_get_metadata_returns_tracks(self, mock_open):
        mock_open.return_value = _mock_urlopen(GET_METADATA_RESPONSE)
        client = _make_client()
        items, total = client.get_metadata("album:1440902935")

        assert total == 12
        assert len(items) == 2
        assert items[0]["title"] == "Airbag"
        assert items[1]["title"] == "Paranoid Android"

    @patch("urllib.request.urlopen")
    def test_get_metadata_sends_correct_body(self, mock_open):
        mock_open.return_value = _mock_urlopen(GET_METADATA_RESPONSE)
        client = _make_client()
        client.get_metadata("album:123", index=5, count=10)

        body = mock_open.call_args[0][0].data.decode("utf-8")
        assert "<ns:id>album:123</ns:id>" in body
        assert "<ns:index>5</ns:index>" in body
        assert "<ns:count>10</ns:count>" in body


class TestGetMediaMetadata:
    @patch("urllib.request.urlopen")
    def test_get_media_metadata_returns_item(self, mock_open):
        mock_open.return_value = _mock_urlopen(GET_MEDIA_METADATA_RESPONSE)
        client = _make_client()
        item = client.get_media_metadata("track:1440903001")

        assert item is not None
        assert item["id"] == "track:1440903001"
        assert item["title"] == "Paranoid Android"
        assert item["artist"] == "Radiohead"
        assert item["album"] == "OK Computer"


class TestRefreshAuthToken:
    @patch("urllib.request.urlopen")
    def test_refresh_updates_credentials(self, mock_open):
        mock_open.return_value = _mock_urlopen(REFRESH_TOKEN_RESPONSE)
        client = _make_client()
        assert client.token == "test_token"
        assert client.key == "test_key"

        new_token, new_key = client.refresh_auth_token()

        assert new_token == "NewTokenValue123"
        assert new_key == "9999999999"
        assert client.token == "NewTokenValue123"
        assert client.key == "9999999999"


class TestErrorHandling:
    @patch("urllib.request.urlopen")
    def test_auth_expired_raises_specific_exception(self, mock_open):
        error = urllib.error.HTTPError(
            "https://example.com", 500, "Server Error", {},
            io.BytesIO(AUTH_EXPIRED_FAULT.encode("utf-8")),
        )
        mock_open.side_effect = error
        client = _make_client()

        with pytest.raises(AuthTokenExpired) as exc_info:
            client.search("test")
        assert "AuthTokenExpired" in str(exc_info.value)

    @patch("urllib.request.urlopen")
    def test_generic_fault_raises_smapi_error(self, mock_open):
        error = urllib.error.HTTPError(
            "https://example.com", 500, "Server Error", {},
            io.BytesIO(GENERIC_FAULT.encode("utf-8")),
        )
        mock_open.side_effect = error
        client = _make_client()

        with pytest.raises(SmapiError) as exc_info:
            client.search("test")
        assert exc_info.value.error_code == "999"

    @patch("urllib.request.urlopen")
    def test_fault_in_200_response_raises(self, mock_open):
        mock_open.return_value = _mock_urlopen(AUTH_EXPIRED_FAULT)
        client = _make_client()

        with pytest.raises(AuthTokenExpired):
            client.search("test")


class TestXmlEscape:
    def test_escapes_ampersand(self):
        assert _xml_escape("rock & roll") == "rock &amp; roll"

    def test_escapes_angle_brackets(self):
        assert _xml_escape("<script>") == "&lt;script&gt;"

    def test_escapes_quotes(self):
        assert _xml_escape('say "hello"') == "say &quot;hello&quot;"

    def test_plain_text_unchanged(self):
        assert _xml_escape("Radiohead") == "Radiohead"
