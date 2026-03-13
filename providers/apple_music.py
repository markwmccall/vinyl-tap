import html
import json
import logging
import re
import urllib.parse
import urllib.request
import xml.sax.saxutils as saxutils
from typing import Callable, Dict, List, Optional

from providers.base import MusicProvider

log = logging.getLogger(__name__)

APPLE_SMAPI_ENDPOINT = "https://sonos-music.apple.com/ws/SonosSoap"


def _upgrade_artwork_url(url):
    return url.replace("100x100bb", "600x600bb")


def _format_duration(ms):
    if not ms:
        return ""
    s = int(ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class AppleMusicProvider(MusicProvider):
    service_id = "apple"
    display_name = "Apple Music"
    sonos_sid = 204
    sonos_service_type = "52231"

    def __init__(self):
        self._smapi = None  # type: Optional[SmapiClient]
        self._on_token_refresh = None  # type: Optional[Callable]
        self._sonos_client = None
        self._sonos_access_token = None  # type: Optional[str]
        self._sonos_refresh_token = None  # type: Optional[str]
        self._sonos_household_id = None  # type: Optional[str]
        self._on_sonos_token_refresh = None  # type: Optional[Callable]

    @property
    def smapi_available(self) -> bool:
        return self._smapi is not None

    @property
    def sonos_available(self) -> bool:
        return self._sonos_client is not None and self._sonos_access_token is not None

    def configure_sonos(
        self,
        client,
        access_token: str,
        refresh_token: str,
        household_id: str,
        on_token_refresh: Optional[Callable] = None,
    ) -> None:
        """Configure Sonos Control API credentials for this provider.

        Args:
            client: SonosControlClient instance
            access_token: OAuth access token
            refresh_token: OAuth refresh token (for auto-refresh on expiry)
            household_id: Sonos household ID discovered after OAuth
            on_token_refresh: Optional callback(new_access_token, new_refresh_token)
                              called after a successful token refresh, to persist tokens.
        """
        self._sonos_client = client
        self._sonos_access_token = access_token
        self._sonos_refresh_token = refresh_token
        self._sonos_household_id = household_id
        self._on_sonos_token_refresh = on_token_refresh
        log.info("Apple Music Sonos Control API configured (household=%s)", household_id[:20] + "...")

    def configure_smapi(
        self,
        token: str,
        key: str,
        household_id: str,
        on_token_refresh: Optional[Callable] = None,
    ) -> None:
        """Configure SMAPI credentials for authenticated Apple Music access.

        Args:
            token: SMAPI OAuth access token
            key: SMAPI private/refresh key
            household_id: Full Sonos household ID with OADevID suffix
            on_token_refresh: Optional callback(new_token, new_key) called after
                              successful token refresh, to persist new credentials.
        """
        from providers.smapi_client import SmapiClient
        self._smapi = SmapiClient(APPLE_SMAPI_ENDPOINT, token, key, household_id)
        self._on_token_refresh = on_token_refresh
        log.info("Apple Music SMAPI configured (household=%s)", household_id[:20] + "...")

    def _smapi_search(self, query: str, retry: bool = True):
        """Run SMAPI search with auto-refresh on AuthTokenExpired."""
        from providers.smapi_client import AuthTokenExpired
        try:
            return self._smapi.search(query)
        except AuthTokenExpired:
            if not retry:
                raise
            log.info("SMAPI token expired, refreshing...")
            new_token, new_key = self._smapi.refresh_auth_token()
            if self._on_token_refresh:
                try:
                    self._on_token_refresh(new_token, new_key)
                except Exception as e:
                    log.warning("Failed to persist refreshed token: %s", e)
            return self._smapi_search(query, retry=False)

    def search_albums(self, query: str) -> List[Dict]:
        if self._smapi:
            try:
                return self._smapi_search_albums(query)
            except Exception as e:
                log.warning("SMAPI album search failed, falling back to iTunes: %s", e)
        return self._itunes_search_albums(query)

    def search_songs(self, query: str) -> List[Dict]:
        if self._smapi:
            try:
                return self._smapi_search_songs(query)
            except Exception as e:
                log.warning("SMAPI song search failed, falling back to iTunes: %s", e)
        return self._itunes_search_songs(query)

    def list_playlists(self) -> List[Dict]:
        """Return all personal playlists from the user's Apple Music library."""
        if not self._smapi:
            return []
        try:
            items, _ = self._smapi.get_metadata("libraryfolder:f.4", count=100)
            return [
                {
                    "id": item["id"].removeprefix("libraryplaylist:"),
                    "playlist_id": item["id"].removeprefix("libraryplaylist:"),
                    "title": item.get("title", ""),
                    "artwork_url": item.get("album_art_uri", ""),
                    "item_type": "playlist",
                }
                for item in items
                if item.get("item_type") == "playlist"
            ]
        except Exception as e:
            log.warning("list_playlists failed: %s", e)
            return []

    def search_playlists(self, query: str) -> List[Dict]:
        """Search personal playlists by name (client-side filter)."""
        q = query.lower()
        return [p for p in self.list_playlists() if q in p["title"].lower()]

    # --- SMAPI search implementations ---

    def _smapi_search_albums(self, query: str) -> List[Dict]:
        items, _ = self._smapi_search(query)
        results = []
        for item in items:
            if item.get("item_type") not in ("album", "collection"):
                continue
            album_id = item.get("id", "")
            # Strip "album:" prefix — the numeric ID matches iTunes catalog IDs
            if album_id.startswith("album:"):
                album_id = album_id[6:]
            results.append({
                "id": int(album_id) if album_id.isdigit() else album_id,
                "name": item.get("title", ""),
                "artist": item.get("artist", ""),
                "artwork_url": _upgrade_artwork_url(item.get("album_art_uri", "")),
            })
        return results

    def _smapi_search_songs(self, query: str) -> List[Dict]:
        items, _ = self._smapi_search(query)
        results = []
        for item in items:
            if item.get("item_type") != "track":
                continue
            track_id = item.get("id", "")
            for prefix in ("track:", "song:"):
                if track_id.startswith(prefix):
                    track_id = track_id[len(prefix):]
                    break
            # Skip non-numeric IDs — they cannot be looked up via the iTunes API
            if not track_id.isdigit():
                continue
            results.append({
                "id": int(track_id),
                "name": item.get("title", ""),
                "artist": item.get("artist", ""),
                "album": item.get("album", ""),
                "artwork_url": _upgrade_artwork_url(item.get("album_art_uri", "")),
            })
        return results

    # --- iTunes API implementations ---

    def _itunes_search_albums(self, query: str) -> List[Dict]:
        encoded = urllib.parse.quote(query)
        url = f"https://itunes.apple.com/search?term={encoded}&entity=album"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
        return [
            {
                "id": r["collectionId"],
                "name": r["collectionName"],
                "artist": r["artistName"],
                "artwork_url": _upgrade_artwork_url(r.get("artworkUrl100", "")),
            }
            for r in data["results"]
        ]

    def _itunes_search_songs(self, query: str) -> List[Dict]:
        encoded = urllib.parse.quote(query)
        url = f"https://itunes.apple.com/search?term={encoded}&entity=song"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
        return [
            {
                "id": r["trackId"],
                "name": r["trackName"],
                "artist": r["artistName"],
                "album": r["collectionName"],
                "artwork_url": _upgrade_artwork_url(r.get("artworkUrl100", "")),
            }
            for r in data["results"]
            if r.get("wrapperType") == "track"
        ]

    def get_album_tracks(self, album_id: str) -> List[Dict]:
        url = f"https://itunes.apple.com/lookup?id={album_id}&entity=song"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
        collection = next(
            (r for r in data["results"] if r.get("wrapperType") == "collection"), None
        )
        release_year = collection.get("releaseDate", "")[:4] if collection else ""
        copyright_line = collection.get("copyright", "") if collection else ""
        tracks = [r for r in data["results"] if r.get("wrapperType") == "track"]
        tracks.sort(key=lambda t: (t.get("discNumber", 1), t["trackNumber"]))
        return [
            {
                "track_id": t["trackId"],
                "name": t["trackName"],
                "track_number": t["trackNumber"],
                "artist": t["artistName"],
                "album": t["collectionName"],
                "album_id": t.get("collectionId"),
                "artwork_url": _upgrade_artwork_url(t.get("artworkUrl100", "")),
                "duration": _format_duration(t.get("trackTimeMillis")),
                "release_year": release_year,
                "copyright": copyright_line,
            }
            for t in tracks
        ]

    def get_track(self, track_id: str) -> List[Dict]:
        url = f"https://itunes.apple.com/lookup?id={track_id}"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
        tracks = [r for r in data["results"] if r.get("wrapperType") == "track"]
        if not tracks:
            return []
        t = tracks[0]
        return [
            {
                "track_id": t["trackId"],
                "name": t["trackName"],
                "track_number": t.get("trackNumber", 1),
                "artist": t["artistName"],
                "album": t["collectionName"],
                "album_id": t.get("collectionId"),
                "artwork_url": _upgrade_artwork_url(t.get("artworkUrl100", "")),
            }
        ]

    def build_playlist_uri(self, playlist_id: str, sn: int) -> str:
        """playlist_id is like 'p.PvVos1vxbV'"""
        return f"x-rincon-cpcontainer:1006206clibraryplaylist%3A{playlist_id}?sid=204&flags=8300&sn={sn}"

    def build_playlist_didl(self, playlist_id: str, title: str, udn: str) -> str:
        e = saxutils.escape
        item_id = f"1006206clibraryplaylist%3A{playlist_id}"
        return (
            '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"'
            ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
            ' xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"'
            ' xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            f'<item id="{item_id}" parentID="-1" restricted="true">'
            f'<dc:title>{e(title)}</dc:title>'
            '<upnp:class>object.container.playlistContainer</upnp:class>'
            f'<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{e(udn)}</desc>'
            '</item>'
            '</DIDL-Lite>'
        )

    def get_playlist_info(self, playlist_id: str) -> Optional[Dict]:
        """Return {'title': ..., 'artwork_url': ...} for a personal playlist ID like 'p.PvVos1vxbV'."""
        if not self._smapi:
            return None
        try:
            items, _ = self._smapi.get_metadata("libraryfolder:f.4", count=100)
            for item in items:
                if item.get("id") == f"libraryplaylist:{playlist_id}":
                    return {"title": item.get("title", ""), "artwork_url": item.get("album_art_uri", "")}
        except Exception:
            pass
        return None

    def build_track_uri(self, track_id: str, sn: int) -> str:
        return f"x-sonos-http:song%3a{track_id}.mp4?sid=204&flags=8232&sn={sn}"

    def build_track_didl(self, track: Dict, udn: str) -> str:
        """Build DIDL-Lite metadata matching the native Sonos app format.

        Uses the Sonos content-browser item ID format (10032028song%3a{track_id})
        so Sonos can resolve the SMAPI GetMediaMetadata call and populate the
        queue with full title/artist/album metadata from Apple Music.
        """
        e = saxutils.escape
        item_id = f"10032028song%3a{track['track_id']}"
        return (
            '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"'
            ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
            ' xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"'
            ' xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            f'<item id="{item_id}" parentID="{item_id}" restricted="true">'
            f'<dc:title>{e(track["name"])}</dc:title>'
            '<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
            f'<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{e(udn)}</desc>'
            '</item>'
            '</DIDL-Lite>'
        )

    def lookup_udn(self, speaker, sn: int) -> str:
        """Find the Apple Music account UDN for the given serial number by scanning
        Sonos favorites, which store the full authenticated account UDN in their
        DIDL metadata. Falls back to the bare service-type UDN if not found.
        """
        fallback = f"SA_RINCON{self.sonos_service_type}_"
        try:
            result = speaker.contentDirectory.Browse([
                ("ObjectID", "FV:2"),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 100),
                ("SortCriteria", ""),
            ])
            data = result.get("Result", "")
            for res_uri, resmd_raw in re.findall(
                r"<[^>]+:res[^>]*>([^<]*)</[^>]+:res>.*?<[^>]+:resMD>([^<]*)</[^>]+:resMD>",
                data,
                re.DOTALL,
            ):
                if f"sn={sn}" not in res_uri:
                    continue
                decoded = html.unescape(resmd_raw)
                m = re.search(
                    r"SA_RINCON" + self.sonos_service_type + r"[^<\"&\s]{0,80}", decoded
                )
                if m:
                    return m.group(0)
        except Exception:
            pass
        return fallback

    def detect_sn(self, speaker) -> Optional[str]:
        """Scan Sonos favorites for an Apple Music URI and extract the sn value.

        Returns the sn as a string, or None if not found (e.g., no Apple Music
        favorites saved in Sonos).
        """
        try:
            result = speaker.contentDirectory.Browse([
                ("ObjectID", "FV:2"),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 100),
                ("SortCriteria", ""),
            ])
            data = result.get("Result", "")
            for res_uri in re.findall(
                r"<(?:[^>]+:)?res[^>]*>([^<]*)</(?:[^>]+:)?res>", data
            ):
                uri = html.unescape(res_uri)
                if f"sid={self.sonos_sid}" not in uri:
                    continue
                m = re.search(r"[?&]sn=(\d+)", uri)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return None
