import io
import json
import urllib.error

import pytest
from unittest.mock import patch, MagicMock

from providers.sonos_control import SonosControlClient, SonosAuthError


def make_response(data: dict):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode()
    return mock


def make_http_error(code: int, body: str = ""):
    return urllib.error.HTTPError(
        url=None, code=code, msg="Error", hdrs=None,
        fp=io.BytesIO(body.encode()),
    )


@pytest.fixture
def client():
    return SonosControlClient("test-key", "test-secret")


class TestGetAuthUrl:
    def test_returns_sonos_base_url(self, client):
        url = client.get_auth_url("https://vinyl-mac.local/sonos/callback", "state1")
        assert url.startswith("https://api.sonos.com/login/v3/oauth?")

    def test_includes_client_id(self, client):
        url = client.get_auth_url("https://vinyl-mac.local/sonos/callback", "state1")
        assert "client_id=test-key" in url

    def test_includes_response_type_code(self, client):
        url = client.get_auth_url("https://vinyl-mac.local/sonos/callback", "state1")
        assert "response_type=code" in url

    def test_includes_scope(self, client):
        url = client.get_auth_url("https://vinyl-mac.local/sonos/callback", "state1")
        assert "scope=playback-control-all" in url

    def test_includes_state(self, client):
        url = client.get_auth_url("https://vinyl-mac.local/sonos/callback", "my-state")
        assert "state=my-state" in url

    def test_includes_redirect_uri(self, client):
        url = client.get_auth_url("https://vinyl-mac.local/sonos/callback", "s")
        assert "redirect_uri=" in url


class TestExchangeCode:
    def test_returns_access_refresh_expires(self, client):
        resp = make_response({"access_token": "acc", "refresh_token": "ref", "expires_in": 3600})
        with patch("urllib.request.urlopen", return_value=resp):
            access, refresh, expires = client.exchange_code(
                "code123", "https://vinyl-mac.local/sonos/callback"
            )
        assert access == "acc"
        assert refresh == "ref"
        assert expires == 3600

    def test_raises_sonos_auth_error_on_http_error(self, client):
        with patch("urllib.request.urlopen", side_effect=make_http_error(400, '{"error":"invalid_grant"}')):
            with pytest.raises(SonosAuthError, match="400"):
                client.exchange_code("bad-code", "https://vinyl-mac.local/sonos/callback")

    def test_uses_basic_auth_header(self, client):
        resp = make_response({"access_token": "a", "refresh_token": "r", "expires_in": 1})
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            client.exchange_code("c", "https://vinyl-mac.local/sonos/callback")
        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization").startswith("Basic ")

    def test_posts_to_token_url(self, client):
        resp = make_response({"access_token": "a", "refresh_token": "r", "expires_in": 1})
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            client.exchange_code("c", "https://vinyl-mac.local/sonos/callback")
        req = mock_open.call_args[0][0]
        assert "oauth/access" in req.full_url

    def test_handles_missing_refresh_token(self, client):
        resp = make_response({"access_token": "a", "expires_in": 1})
        with patch("urllib.request.urlopen", return_value=resp):
            access, refresh, expires = client.exchange_code("c", "https://x/cb")
        assert access == "a"
        assert refresh == ""


class TestRefreshAccessToken:
    def test_returns_new_access_token_and_expiry(self, client):
        resp = make_response({"access_token": "new-acc", "expires_in": 7200})
        with patch("urllib.request.urlopen", return_value=resp):
            access, expires = client.refresh_access_token("old-refresh")
        assert access == "new-acc"
        assert expires == 7200

    def test_raises_on_http_error(self, client):
        with patch("urllib.request.urlopen", side_effect=make_http_error(401)):
            with pytest.raises(SonosAuthError):
                client.refresh_access_token("bad-token")

    def test_uses_refresh_grant_type(self, client):
        resp = make_response({"access_token": "a", "expires_in": 1})
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            client.refresh_access_token("my-refresh")
        req = mock_open.call_args[0][0]
        assert b"grant_type=refresh_token" in req.data
        assert b"refresh_token=my-refresh" in req.data


class TestGetHouseholds:
    def test_returns_household_list(self, client):
        resp = make_response({"households": [{"id": "hh-123", "name": "Home"}]})
        with patch("urllib.request.urlopen", return_value=resp):
            households = client.get_households("valid-token")
        assert len(households) == 1
        assert households[0]["id"] == "hh-123"

    def test_returns_empty_list_when_none(self, client):
        resp = make_response({"households": []})
        with patch("urllib.request.urlopen", return_value=resp):
            result = client.get_households("valid-token")
        assert result == []

    def test_raises_sonos_auth_error_on_401(self, client):
        with patch("urllib.request.urlopen", side_effect=make_http_error(401)):
            with pytest.raises(SonosAuthError, match="Unauthorized"):
                client.get_households("bad-token")

    def test_uses_bearer_auth_header(self, client):
        resp = make_response({"households": []})
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            client.get_households("my-token")
        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer my-token"

    def test_raises_non_401_http_errors(self, client):
        with patch("urllib.request.urlopen", side_effect=make_http_error(500)):
            with pytest.raises(SonosAuthError, match="500"):
                client.get_households("token")
