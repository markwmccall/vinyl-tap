import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

SONOS_AUTH_URL = "https://api.sonos.com/login/v3/oauth"
SONOS_TOKEN_URL = "https://api.sonos.com/login/v3/oauth/access"
SONOS_API_BASE = "https://api.sonos.com/control/api/v1"
SONOS_SCOPE = "playback-control-all"


class SonosAuthError(Exception):
    pass


class SonosControlClient:
    """Client for the Sonos Control API (OAuth 2.0 authorization code flow).

    Each environment has its own client_key + client_secret pair registered in
    the Sonos developer portal, with a matching redirect URI:
      - Pi:  vinyl-emulator-key  / https://vinyl-pi.local/sonos/callback
      - Dev: vinyl-emulator-dev-key / https://vinyl-mac.local/sonos/callback

    client_key is used as client_id in the authorize URL and as the Basic auth
    username for token exchange. client_secret is the Basic auth password.
    """

    def __init__(self, client_key: str, client_secret: str):
        self._client_key = client_key
        creds = f"{client_key}:{client_secret}".encode()
        self._basic_auth = base64.b64encode(creds).decode()

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        """Return the Sonos authorization URL to redirect the user to."""
        params = urllib.parse.urlencode({
            "client_id": self._client_key,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SONOS_SCOPE,
            "state": state,
        })
        return f"{SONOS_AUTH_URL}?{params}"

    def exchange_code(self, code: str, redirect_uri: str) -> Tuple[str, str, int]:
        """Exchange an authorization code for tokens.

        Returns:
            (access_token, refresh_token, expires_in_seconds)
        """
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }).encode()
        return self._token_request(data)

    def refresh_access_token(self, refresh_token: str) -> Tuple[str, int]:
        """Refresh an expired access token.

        Returns:
            (new_access_token, expires_in_seconds)
        """
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }).encode()
        access_token, _, expires_in = self._token_request(data)
        return access_token, expires_in

    def get_households(self, access_token: str) -> List[Dict]:
        """Return the list of Sonos households for the authenticated user."""
        body = self._api_get("/households", access_token)
        return body.get("households", [])

    # --- internal ---

    def _token_request(self, data: bytes) -> Tuple[str, str, int]:
        log.debug("Token request to %s body=%s", SONOS_TOKEN_URL, data.decode())
        req = urllib.request.Request(
            SONOS_TOKEN_URL,
            data=data,
            headers={
                "Authorization": f"Basic {self._basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raw = b""
            try:
                raw = e.read()
            except Exception:
                pass
            raise SonosAuthError(
                f"Token request failed ({e.code}): {raw.decode(errors='replace')}"
            )
        return (
            body["access_token"],
            body.get("refresh_token", ""),
            int(body.get("expires_in", 3600)),
        )

    def _api_get(self, path: str, access_token: str) -> Dict:
        req = urllib.request.Request(
            f"{SONOS_API_BASE}{path}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raw = b""
            try:
                raw = e.read()
            except Exception:
                pass
            log.debug("API GET %s failed (%s): %s", path, e.code, raw.decode(errors="replace"))
            if e.code == 401:
                raise SonosAuthError("Unauthorized — access token expired or invalid")
            raise SonosAuthError(f"API GET {path} failed ({e.code}): {raw.decode(errors='replace')}")
