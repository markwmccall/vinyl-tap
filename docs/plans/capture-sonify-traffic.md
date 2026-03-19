# Plan: Capture Sonify Network Traffic with Proxyman

## Goal

Determine how Sonify obtains Apple Music credentials (token + key) for SMAPI
requests to `sonos-music.apple.com` — specifically whether tokens come from the
Sonos Control API (cloud), the local Sonos speaker WebSocket API, or via AppLink.

## What to Look For

| Traffic type | What it means |
|---|---|
| `ws://10.0.0.x:1400/websocket/api` with token-shaped response | Tokens come from local speaker |
| `api.sonos.com` → returns token/key pair | Tokens come from Sonos Control API (cloud) |
| `sonos-music.apple.com` `getAppLink` / `getDeviceAuthToken` | Sonify does its own AppLink flow |
| `sonos-music.apple.com` search with credentials already in headers | Tokens arrived from somewhere else first |

The sequence matters: what happens *before* the first call to
`sonos-music.apple.com`?

---

## Prerequisites

- Mac with Proxyman installed (https://proxyman.io — free tier is sufficient)
- iPhone on the same WiFi network as the Mac and Sonos speaker
- Sonify installed on iPhone (will be deleted and reinstalled during the steps)
- Apple ID / App Store access to reinstall Sonify

---

## Step 1: Verify Proxyman iOS Helper is Available

1. Open Proxyman on the Mac.
2. From the menu bar: **Certificate → Install Certificate on iOS → Physical
   Device**.
3. Confirm the Proxyman iOS Setup Guide appears — it will show the URL to
   navigate to on the iPhone. Keep this window open for Step 3.

---

## Step 2: Delete Sonify from iPhone

1. On the iPhone, press and hold the Sonify app icon.
2. Tap **Remove App → Delete App → Delete**.
3. Open **Settings → [Your Name] → iCloud → Show All Apps**.
4. Check if Sonify appears in the list.
   - If it does: toggle it **off** and choose **Delete from iCloud** to prevent
     token restoration on reinstall.
   - If it does not appear: proceed — iCloud is not backing up Sonify data.

---

## Step 3: Install Proxyman Certificate on iPhone

1. On iPhone, open Safari and navigate to the address shown in Proxyman's setup
   guide (typically `proxy.man/ssl`). iPhone must be on the same WiFi network
   as the Mac.
2. Tap **Allow** when prompted to download a configuration profile.
3. On iPhone: **Settings → General → VPN & Device Management** → find the
   Proxyman profile → tap **Install** → enter passcode → tap **Install** again.
4. On iPhone: **Settings → General → About → Certificate Trust Settings** →
   enable full trust for the Proxyman certificate.

---

## Step 4: Configure iPhone to Route Traffic Through Proxyman

1. In Proxyman on Mac: note the IP address and port shown at the top of the
   window (e.g., `192.168.x.x:9090`).
2. On iPhone: **Settings → WiFi** → tap the **(i)** next to your current
   network → scroll to **HTTP Proxy → Configure Proxy → Manual**.
3. Enter:
   - **Server**: the Mac's IP from Proxyman
   - **Port**: `9090`
   - **Authentication**: off
4. Tap **Save**.

> **Note on local traffic**: iOS does not route connections to local RFC-1918
> addresses (10.x.x.x, 192.168.x.x) through the proxy by default. Traffic to
> any Sonos speaker on the local network will go direct. To capture local speaker
> traffic, run Wireshark on the Mac in parallel (see Step 5 — optional).

---

## Step 5 (Optional): Capture Local Sonos Speaker Traffic with Wireshark

If you want to see traffic between the iPhone and any Sonos speaker on the
local network:

1. Install Wireshark on Mac if not already installed.
2. Open Wireshark → select your WiFi interface (e.g., `en0`).
3. Set the filter for port 1400 traffic to/from all speakers on the network,
   since Sonify may communicate with any of them:
   - **Display filter** (bar at top of packet list, after capture starts):
     `tcp.port == 1400`
   - **Capture filter** (in capture options dialog, before starting):
     `tcp port 1400`
4. Start capture before Step 7.

WebSocket connections to the speaker appear as HTTP Upgrade requests on port
1400. The payload is JSON (not encrypted — no cert needed).

---

## Step 6: Start Proxyman Capture

1. Clear any prior requests: **File → Clear** (⌘K).
2. Click the **Record** button (or press ⌘R) to start capturing.
3. Leave the filter bar empty — capture everything unfiltered. You will search
   for specific domains in Step 9 after the capture is complete.

---

## Step 7: Reinstall and Launch Sonify Fresh

1. Temporarily disable the proxy on iPhone: **Settings → WiFi → (i) →
   HTTP Proxy → Off**. The App Store uses certificate pinning and will not
   work through the proxy.
2. On iPhone, open the App Store and reinstall Sonify.
3. **Do not launch Sonify yet.**
4. Re-enable the proxy: **Settings → WiFi → (i) → HTTP Proxy → Manual**
   (same Server/Port as Step 4).
5. Confirm Proxyman is recording and Wireshark (if used) is capturing.
4. Launch Sonify.
5. Allow it to fully complete its initial load — wait for the home screen to
   appear and the speaker/household to be detected.
6. Do **not** tap anything yet.

---

## Step 8: Trigger a Search

1. In Sonify, perform a simple search — e.g., search for "Rumours".
2. Let results load fully.
3. Note any Apple Music results that appear (these require a valid SMAPI token).

---

## Step 9: Stop Capture and Analyze

1. Stop Proxyman recording (⌘R).
2. Stop Wireshark capture if running.

### In Proxyman — look for, in chronological order:

1. Any calls to `signon.service.sonos.com` or `api.sonos.com` — these are
   Sonos account / Control API calls
2. Any calls to `sonos-music.apple.com` — look at the SOAP request headers for
   the `<loginToken>` block containing `<token>` and `<key>`
3. The `SOAPAction` of the first Apple Music call — is it `getAppLink`,
   `getDeviceAuthToken`, or `search`?

### In Wireshark — look for:

1. WebSocket upgrade to `10.0.0.47:1400/websocket/api`
2. Any JSON message body that contains fields resembling `token`, `key`,
   `authToken`, `accessToken`, or `credential`

---

## Step 10: Document Findings

Update `tools/SONOS_API_RESEARCH.md` with:
- Which API provided the token (Sonos cloud, local speaker, or AppLink)
- The exact request/response structure observed
- Whether the credential format matches what `smapi_client.py` already sends

---

## Step 11: Restore iPhone Proxy Settings

1. On iPhone: **Settings → WiFi → (i)** next to network → **HTTP Proxy → Off**.
2. This step is easy to forget — Proxyman will stop capturing but your phone
   will lose internet access if the Mac proxy is turned off while still
   configured on the phone.
