# Sonos API Research Notes

Investigation into how to search music services (Apple Music, Amazon Music)
via Sonos, for the purpose of replacing the iTunes Search API with something
that includes personal library and playlists.

---

## Background

The current implementation uses the iTunes Search API to find albums by name
and constructs Apple Music URIs for Sonos playback. This works for catalog
content but cannot access:

- Personal playlists
- Personal library / uploaded music
- Other linked services (Amazon Music, Spotify, etc.)

---

## Architecture: How Sonos Music Service Search Works

Sonos uses a SOAP-based protocol called **SMAPI** (Sonos Music API) to
communicate with music services. When you search Apple Music in the Sonos app,
the app makes a direct SOAP request to Apple Music's servers using credentials
stored on the Sonos speaker/household.

### SMAPI Request Format

```
POST https://sonos-music.apple.com/ws/SonosSoap
SOAPAction: "http://www.sonos.com/Services/1.1#search"
User-Agent: SonosApp/53 CFNetwork/3860.400.51 Darwin/25.3.0

<Envelope>
  <Header>
    <credentials xmlns="http://www.sonos.com/Services/1.1">
      <loginToken>
        <token>{access_token}</token>
        <key>{private_key}</key>
        <householdId>{household_id_with_oadevid_suffix}</householdId>
      </loginToken>
    </credentials>
    <context xmlns="http://www.sonos.com/Services/1.1">
      <timeZone>00:00</timeZone>
    </context>
  </Header>
  <Body>
    <search xmlns="http://www.sonos.com/Services/1.1">
      <id>all</id>
      <term>{search_term}</term>
      <index>0</index>
      <count>50</count>
    </search>
  </Body>
</Envelope>
```

### Key Credential Details

- **`token`**: Short-lived OAuth access token (~1 hour)
- **`key`**: Long-lived private/refresh key
- **`householdId`**: Must include OADevID suffix — format is
  `Sonos_{base_household_id}_{oa_dev_id}`, e.g. `Sonos_xxxxx_f7c0f087`.
  The base `speaker.household_id` from soco is missing this suffix and will
  cause `AuthTokenExpired` errors.
- **`deviceId`**: Deprecated in SMAPI spec. Do not send — causes errors.

### Search Response

- Only `<id>all</id>` works for Apple Music. Sending `id=albums`, `id=tracks`,
  etc. returns zero results.
- Results contain `mediaCollection` (album/artist/program) and `mediaMetadata`
  (track) items.
- Album IDs are in format `album:1440902935` — strip the prefix and the number
  matches the iTunes catalog ID exactly.

### Service Endpoints

| Service       | ID  | Auth Type  | SMAPI URL                                    |
|---------------|-----|------------|----------------------------------------------|
| Apple Music   | 204 | AppLink    | `https://sonos-music.apple.com/ws/SonosSoap` |
| Amazon Music  | 201 | DeviceLink | `https://sonos.amazonmusic.com/`             |
| Spotify       | 12  | AppLink    | varies                                       |

Full service list (including endpoints) available via UPnP:
```
POST http://{speaker_ip}:1400/MusicServices/Control
SOAPAction: "urn:schemas-upnp-org:service:MusicServices:1#ListAvailableServices"
```

---

## Authentication Flows

### AppLink (used by Apple Music, Spotify)

1. Client calls `getAppLink` on the music service SMAPI endpoint.
   Server returns `regUrl` (auth URL) and `linkCode`.
2. User visits `regUrl` in a browser/app and authorizes.
3. Client calls `getDeviceAuthToken(linkCode, linkDeviceId)`.
   Server returns `authToken` (token) and `privateKey` (key).

**Apple Music blocks `getAppLink` for unregistered apps.** Returns
`SOAP-ENV:Server` error 999. Only registered Sonos partner apps (like Sonify,
the official Sonos app) can initiate this flow. When called with proper device
credentials (see below), Apple Music returns an empty `callToAction` with
`appUrlEncrypt=true` — indicating the auth URL is encrypted and only
decryptable by a registered partner.

### DeviceLink (used by Amazon Music, TIDAL)

1. Client generates a random `linkCode` (UUID).
2. Client calls `getDeviceAuthToken(linkCode, linkDeviceId)`.
   Server returns `NOT_LINKED_RETRY` fault with `regUrl`.
3. User visits `regUrl` and authorizes.
4. Client polls `getDeviceAuthToken(linkCode, linkDeviceId)` until
   server returns `authToken` and `privateKey`.

Amazon Music DeviceLink requires the householdId to match a registered
household (the Amazon account must be linked to Sonos already).

---

## Local UPnP API (port 1400)

### What is accessible

**SystemProperties service** — `http://{ip}:1400/SystemProperties/Control`

| Action              | Purpose                                         |
|---------------------|-------------------------------------------------|
| `GetString`         | Read stored string variables                    |
| `SetString`         | Write string variables                          |
| `GetWebCode`        | Get web auth code for account linking           |
| `AddOAuthAccountX`  | Store OAuth credentials for a music service     |
| `RefreshAccountCredentialsX` | Update stored credentials              |
| `ReplaceAccountX`   | Replace account credentials                     |
| `RemoveAccount`     | Remove a linked account                         |

**Getting Device ID:**
```
GetString(VariableName="R_TrialZPSerial")
→ Returns e.g. "48-A6-B8-6B-2B-90:2"
```
Note: `R_TrialZPSerialNum` (wrong) returns error 800. `R_TrialZPSerial` (correct) works.

**Credentials are write-only.** There is no `GetCredentials` or `GetToken`
action. The speaker stores OAuth tokens for music services (put there by the
Sonos app via `AddOAuthAccountX`) but deliberately does not expose them to
third-party apps. This is intentional — confirmed by the svrooij.io
documentation: *"Sonos locked down communication with most service, by no
longer allowing access to the needed access tokens."*

**MusicServices service** — `http://{ip}:1400/MusicServices/Control`

| Action                   | Purpose                              |
|--------------------------|--------------------------------------|
| `ListAvailableServices`  | Returns XML of all music services    |
| `GetSessionId`           | Session auth only (not AppLink/DeviceLink) |
| `UpdateAvailableServices`| Refresh service list                 |

**ContentDirectory service** does not provide access to music service search
or browsing. ObjectID prefixes like `MS:204` return error 701 (no such object).
ContentDirectory only exposes local library (`A:`), favorites (`FV:2`),
playlists (`SQ:`), radio (`R:`), and shares (`S:`).

### What is NOT accessible via local UPnP

- Music service tokens / credentials
- Apple Music or Amazon Music catalog search
- Any music service content browsing (ContentDirectory is local-only)

---

## OADevID and householdId Construction

The OADevID suffix on the householdId is service-account-specific and
embedded in the music service UDN. It can be extracted from Sonos Favorites
(`FV:2` ContentDirectory browse), which is already implemented in
`sonos_controller.py` via `_lookup_apple_music_udn()`.

UDN format: `SA_RINCON52231_X_#Svc52231-{oadevid}-Token`

The full SMAPI householdId is: `{speaker.household_id}_{oadevid}`

---

## Tools

### `smapi_probe.py`

Diagnostic script for probing SMAPI search. Run on the Pi with the venv active:

```bash
# Test search (requires valid token in soco token store)
python3 smapi_probe.py --ip 10.0.0.x --sn 3 --query "Rumours"

# Run AppLink auth flow interactively
python3 smapi_probe.py --ip 10.0.0.x --auth
```

### mitmproxy

Used to capture SMAPI traffic from Sonify (iOS app):

```bash
pip install mitmproxy
mitmweb --listen-port 8080 \
  --ignore-hosts "10\.0\.0\.\d+" \
  --ignore-hosts "192\.168\.\d+\.\d+"
```

Configure iPhone WiFi proxy to `{mac_ip}:8080`. Install mitmproxy cert on
iPhone for HTTPS inspection. The `--ignore-hosts` flags are required to allow
the Sonos app to discover speakers via local network.

---

## Why soco's AppLink Flow Fails

`soco`'s `MusicService.soap_client.begin_authentication()` calls `getAppLink`
on the music service. For Apple Music this returns SOAP-ENV:Server error 999
because soco is not a registered Sonos partner app and Apple Music's server
rejects the request server-side.

Additionally, soco uses `speaker.household_id` directly as the householdId,
which is missing the `_{oadevid}` suffix. Even with a valid token injected into
soco's token store, searches fail with `AuthTokenExpired` due to this mismatch.

---

## Sonos S2 Change (May 2024): SMAPI Now Requires Public HTTPS

**Breaking change for local Pi deployments.** As of the S2 app update (May 2024),
Sonos routes SMAPI traffic through its cloud infrastructure, which means:

- SMAPI services must be exposed to the internet with a valid HTTPS certificate
- Local-only SMAPI implementations (LAN only, no port forwarding) no longer work on S2
- S1 devices are unaffected

This fundamentally changes the viability of running a custom SMAPI service on a Pi
behind a home NAT. Workarounds include Cloudflare Tunnel, ngrok, or a VPS reverse
proxy — but all require the Pi's SMAPI endpoint to be publicly reachable.

---

## Recommended Path Forward: Sonos Control API

Register at [developer.sonos.com](https://developer.sonos.com) as a **Control
Integration**. This provides:

1. OAuth flow via `api.sonos.com` — user authenticates with Sonos account once
2. `GET /households/{id}/musicServiceAccounts` — lists all linked services
3. Music service search proxied through Sonos — no direct SMAPI token handling
4. `POST /groups/{groupId}/playback:loadContent` — load search results

This is how Sonify and similar apps work. Sonos handles the music service
authentication internally using the household's stored credentials.

**Registration status (2024–2025):** The approval process is slow and opaque.
Developers have reported registrations remaining "under analysis" indefinitely.
There is no explicit hobby/individual tier. Registration was started but not
completed as of this writing.

### Once registered: next steps

1. **Prove out search** — the critical unknown is whether the Control API actually
   proxies music service search by name, or only plays content by a pre-known
   `musicObjectId`. The `playback:loadContent` endpoint accepts a `musicObjectId`
   but it's unclear if that requires a prior search call or a known catalog ID.

2. **If search is exposed:**
   - Implement OAuth flow in the web UI (Settings page, one-time Sonos account auth)
   - Store and refresh the Sonos access token in `config.json`
   - Replace/augment `apple_music.py` search with Control API calls
   - `playback:loadContent` replaces the manual DIDL/URI construction in
     `sonos_controller.py`

3. **If search is NOT exposed:**
   - The Control API may only handle playback control, not content discovery
   - Search would still require SMAPI, which requires a public HTTPS endpoint (S2)
   - Options: Cloudflare Tunnel or ngrok to expose the Pi's SMAPI endpoint

4. **Token management:**
   - Access tokens are short-lived; refresh tokens must be stored securely
   - Add token refresh logic to `app.py` (background thread or on-demand)

---

## Ruled Out: Apple MusicKit API

- Requires $99/year Apple Developer Program membership — not viable
- Only covers Apple Music; does not solve search for Amazon Music, Spotify, or other services
- Not a path forward for this project

---

## Music Assistant: How It Actually Works

[GitHub: music-assistant/server](https://github.com/music-assistant/server)

Music Assistant is the most complete open-source reference implementation for
multi-service music search + Sonos playback. Key findings from the source code:

### Architecture

- **Search**: Implemented entirely internally. MA authenticates directly with each
  music service and syncs their content into its own local database. Sonos is never
  involved in search.
- **Playback**: Uses `aiosonos` (a WebSocket-based library, NOT soco) to control
  Sonos speakers over the local network. Sonos is purely a playback device.
- **No SMAPI**: MA does not implement SMAPI at all, so the S2 public HTTPS
  requirement is irrelevant to its architecture.

### Spotify authentication (source: `providers/spotify/`)

Uses **OAuth 2.0 with PKCE**. The redirect URI is hardcoded to
`https://music-assistant.io/callback` — a central endpoint the MA team hosts.

Flow:
1. MA generates a PKCE pair and constructs the Spotify auth URL with
   `redirect_uri=https://music-assistant.io/callback` and
   `state={local_callback_url}` (the local MA server's callback URL)
2. User authorizes in browser; Spotify redirects to `music-assistant.io/callback`
3. That hosted page reads the `state` param and redirects again to the local MA
   server's `/callback/{session_id}` route
4. MA's `AuthenticationHelper` captures the auth code and exchanges it for tokens
5. Refresh token stored in encrypted config; auto-refreshed on demand

The `state` parameter double-redirect is the mechanism that bridges the public
redirect URI back to the local server.

### Apple Music authentication (source: `providers/apple_music/`)

Uses **MusicKit JS** in a popup window — not a simple cookie extraction.

Flow:
1. MA opens a popup serving a local HTML page (`musickit_wrapper.html`)
2. The page loads Apple's MusicKit JS library and calls `music.authorize()`
3. MusicKit handles the Apple ID sign-in flow internally (within the popup)
4. On success, MusicKit returns a `music-user-token`; the page POSTs it back to
   MA's local `/callback/{session_id}` route
5. MA stores the token in encrypted config

MA uses a **shared app/developer token** (a JWT rotated via GitHub Actions) so
users don't need an Apple Developer account. The `music-user-token` expires after
~180 days and requires manual re-auth.

### AuthenticationHelper (source: `helpers/auth.py`)

A generic context manager used by all OAuth flows:
- Registers a dynamic route at `/callback/{session_id}` on the local MA server
- Supports both GET (query params) and POST (JSON body) callbacks
- Waits with a configurable timeout (default 60s) for the browser to hit the route
- Returns the parsed params to the calling provider

This is what makes local OAuth work without a public redirect URI for Apple Music —
the callback goes directly to the local server because the MusicKit popup runs in
the user's browser on the same LAN.

### Sonos playback (source: `providers/sonos/`)

Uses `aiosonos` (WebSocket-based, not UPnP/soco):
- Discovers speakers via mDNS
- Playback via `client.player.group.play_cloud_queue()` or `play_stream_url()`
- MA acts as a cloud queue server; Sonos pulls the stream from MA's local HTTP server

### Provider plugin architecture

Each music service is a provider module implementing:
- `get_config_entries()` — declares config fields (credentials, options)
- `setup()` — initializes the provider instance
- `MusicProvider` base class — search, browse, library sync
- `SUPPORTED_FEATURES` set — declares what the provider can do

---

## Community Tools

| Tool | Description | Status |
|------|-------------|--------|
| [bonob](https://github.com/simojenki/bonob) | SMAPI proxy for Subsonic-compatible servers (Navidrome, Gonic) | Active; requires public HTTPS for S2 |
| [node-sonos-http-api](https://github.com/jishi/node-sonos-http-api) | HTTP API for Sonos automation; `/musicsearch/{service}/{type}/{term}` | Uses iTunes catalog, not personal library |
| [YouTubeSonos](https://github.com/robertdejong1/YouTubeSonos) | SMAPI implementation for YouTube Music | Shows SMAPI endpoint structure |

---

## References

- [sonos.svrooij.io](https://sonos.svrooij.io) — Unofficial UPnP API documentation
- [docs.sonos.com/docs/smapi](https://docs.sonos.com/docs/smapi) — Official SMAPI spec
- [developer.sonos.com](https://developer.sonos.com) — Sonos developer portal
- [Apple Music API](https://developer.apple.com/documentation/applemusicapi/) — MusicKit REST API reference
- [Apple MusicKit](https://developer.apple.com/musickit/) — MusicKit developer overview
