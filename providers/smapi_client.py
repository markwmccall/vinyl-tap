"""Sonos SMAPI (Music API) SOAP client.

Handles authenticated SOAP calls to any Sonos music service endpoint.
Used by providers that support SMAPI search/browse (Apple Music, Amazon Music, etc.).

Credentials format:
  token  — short-lived access token (refreshed via refreshAuthToken)
  key    — long-lived private key (rotated on each refresh)
  household_id — full Sonos household ID with OADevID suffix
                  e.g. "Sonos_xxxxx_f7c0f087"
"""
from __future__ import annotations

import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SONOS = "http://www.sonos.com/Services/1.1"

_NAMESPACES = {"s": NS_SOAP, "ns": NS_SONOS}


def _build_envelope(header_xml: str, body_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{NS_SOAP}" xmlns:ns="{NS_SONOS}">'
        f"<s:Header>{header_xml}</s:Header>"
        f"<s:Body>{body_xml}</s:Body>"
        "</s:Envelope>"
    )


def _credentials_header(token: str, key: str, household_id: str) -> str:
    return (
        "<ns:credentials>"
        "<ns:loginToken>"
        f"<ns:token>{token}</ns:token>"
        f"<ns:key>{key}</ns:key>"
        f"<ns:householdId>{household_id}</ns:householdId>"
        "</ns:loginToken>"
        "</ns:credentials>"
        "<ns:context><ns:timeZone>00:00</ns:timeZone></ns:context>"
    )


def _device_credentials_header(
    device_id: str, household_id: str, device_provider: str = "Sonos"
) -> str:
    return (
        "<ns:credentials>"
        f"<ns:deviceId>{device_id}</ns:deviceId>"
        f"<ns:deviceProvider>{device_provider}</ns:deviceProvider>"
        f"<ns:householdId>{household_id}</ns:householdId>"
        "</ns:credentials>"
    )


class SmapiError(Exception):
    """SMAPI SOAP fault."""

    def __init__(self, fault_string: str, error_code: Optional[str] = None):
        self.fault_string = fault_string
        self.error_code = error_code
        super().__init__(f"SMAPI error {error_code}: {fault_string}")


class AuthTokenExpired(SmapiError):
    """Raised when the SMAPI endpoint returns an AuthTokenExpired fault."""
    pass


class SmapiClient:
    """Authenticated SMAPI SOAP client for a specific music service.

    Args:
        endpoint: SMAPI SOAP endpoint URL (e.g. "https://sonos-music.apple.com/ws/SonosSoap")
        token: OAuth access token
        key: Private/refresh key
        household_id: Full Sonos household ID with OADevID suffix
    """

    def __init__(self, endpoint: str, token: str, key: str, household_id: str):
        self.endpoint = endpoint
        self.token = token
        self.key = key
        self.household_id = household_id

    def _call(self, action: str, body_xml: str, timeout: int = 10) -> ET.Element:
        """Make an authenticated SMAPI SOAP call and return the parsed Body element."""
        header = _credentials_header(self.token, self.key, self.household_id)
        envelope = _build_envelope(header, body_xml)
        req = urllib.request.Request(
            self.endpoint,
            data=envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{NS_SONOS}#{action}"',
                "User-Agent": "Linux UPnP/1.0 Sonos/80.1-55240",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                root = ET.fromstring(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self._raise_soap_fault(body)
            raise SmapiError(f"HTTP {e.code}", str(e.code))

        # Check for SOAP faults in 200 responses
        fault = root.find(".//s:Fault", _NAMESPACES)
        if fault is not None:
            self._raise_from_fault(fault)

        body = root.find("s:Body", _NAMESPACES)
        return body

    def _raise_soap_fault(self, response_text: str) -> None:
        """Parse a SOAP fault from error response body and raise."""
        try:
            root = ET.fromstring(response_text)
        except ET.ParseError:
            raise SmapiError(response_text[:200])
        self._raise_from_fault_root(root)

    def _raise_from_fault(self, fault_elem: ET.Element) -> None:
        faultstring = ""
        error_code = None
        fs = fault_elem.find("faultstring")
        if fs is not None:
            faultstring = fs.text or ""
        for elem in fault_elem.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "ErrorCode" or tag == "errorCode":
                error_code = elem.text
            if tag == "SonosError":
                error_code = elem.text
        if error_code == "SOAP-ENV:Client-AuthTokenExpired":
            raise AuthTokenExpired(faultstring, error_code)
        raise SmapiError(faultstring, error_code)

    def _raise_from_fault_root(self, root: ET.Element) -> None:
        fault = root.find(".//{%s}Fault" % NS_SOAP)
        if fault is not None:
            self._raise_from_fault(fault)
        # Try to find error info anywhere in the response
        faultstring = ""
        error_code = None
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "faultstring" and elem.text:
                faultstring = elem.text
            if tag in ("ErrorCode", "errorCode", "SonosError") and elem.text:
                error_code = elem.text
        if faultstring or error_code:
            if error_code == "SOAP-ENV:Client-AuthTokenExpired":
                raise AuthTokenExpired(faultstring, error_code)
            raise SmapiError(faultstring, error_code)
        raise SmapiError("Unknown SOAP fault")

    def search(
        self, term: str, search_id: str = "all", index: int = 0, count: int = 50
    ) -> Tuple[List[Dict], int]:
        """Search the music service.

        Args:
            term: Search query
            search_id: Search category ("all", "album", "track", etc.)
                       Apple Music only supports "all".
            index: Starting result index (for pagination)
            count: Max results to return

        Returns:
            (results, total) where results is a list of dicts with keys:
              id, title, item_type ("collection"|"track"), artist, album_art_uri
        """
        body = (
            "<ns:search>"
            f"<ns:id>{search_id}</ns:id>"
            f"<ns:term>{_xml_escape(term)}</ns:term>"
            f"<ns:index>{index}</ns:index>"
            f"<ns:count>{count}</ns:count>"
            "</ns:search>"
        )
        resp_body = self._call("search", body)
        return self._parse_search_response(resp_body)

    def get_metadata(
        self, item_id: str, index: int = 0, count: int = 100
    ) -> Tuple[List[Dict], int]:
        """Browse/get children of an item (album tracks, playlist tracks, etc.).

        Args:
            item_id: SMAPI item ID (e.g. "album:1440902935")
            index: Starting index
            count: Max items

        Returns:
            (items, total)
        """
        body = (
            "<ns:getMetadata>"
            f"<ns:id>{_xml_escape(item_id)}</ns:id>"
            f"<ns:index>{index}</ns:index>"
            f"<ns:count>{count}</ns:count>"
            "</ns:getMetadata>"
        )
        resp_body = self._call("getMetadata", body)
        return self._parse_search_response(resp_body)

    def get_media_metadata(self, item_id: str) -> Optional[Dict]:
        """Get metadata for a single item.

        Returns dict with id, title, item_type, artist, album, album_art_uri, track_id, etc.
        """
        body = (
            "<ns:getMediaMetadata>"
            f"<ns:id>{_xml_escape(item_id)}</ns:id>"
            "</ns:getMediaMetadata>"
        )
        resp_body = self._call("getMediaMetadata", body)
        # Response is a single mediaMetadata or mediaCollection element
        for child in resp_body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("getMediaMetadataResponse",):
                for item in child:
                    return self._parse_item(item)
        return None

    def refresh_auth_token(self) -> Tuple[str, str]:
        """Call refreshAuthToken to get a new token/key pair.

        Updates self.token and self.key in-place and returns (new_token, new_key).
        """
        body = "<ns:refreshAuthToken/>"
        resp_body = self._call("refreshAuthToken", body)

        new_token = None
        new_key = None
        for elem in resp_body.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "authToken" and elem.text:
                new_token = elem.text
            if tag == "privateKey" and elem.text:
                new_key = elem.text

        if new_token and new_key:
            self.token = new_token
            self.key = new_key
            log.info("SMAPI token refreshed successfully")
            return new_token, new_key

        raise SmapiError("refreshAuthToken returned no credentials")

    def _parse_search_response(self, body: ET.Element) -> Tuple[List[Dict], int]:
        """Parse search or getMetadata response body into items list."""
        items = []
        total = 0

        for elem in body.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "total" and elem.text:
                try:
                    total = int(elem.text)
                except ValueError:
                    pass
            if tag in ("mediaCollection", "mediaMetadata"):
                item = self._parse_item(elem)
                if item:
                    items.append(item)

        if not total:
            total = len(items)
        return items, total

    def _parse_item(self, elem: ET.Element) -> Optional[Dict]:
        """Parse a mediaCollection or mediaMetadata element into a dict."""
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        item_type = "collection" if tag == "mediaCollection" else "track"

        item = {"item_type": item_type}

        for child in elem.iter():
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child.text is None:
                continue
            if child_tag == "id":
                item["id"] = child.text
            elif child_tag == "title":
                item["title"] = child.text
            elif child_tag == "artist":
                item["artist"] = child.text
            elif child_tag == "albumArtURI":
                item["album_art_uri"] = child.text
            elif child_tag == "album":
                item["album"] = child.text
            elif child_tag == "itemType":
                item["item_type"] = child.text

        return item if "id" in item else None


def _xml_escape(text: str) -> str:
    """Escape text for inclusion in XML elements."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
