# Plan: Apple Music Token Onboarding Research

## Problem Statement

New users of Vinyl Tap need an Apple Music SMAPI `loginToken` (token +
key + householdId) stored in `config.json` before the system can search Apple
Music or play content. Currently there is no onboarding path — the token was
obtained manually by the original developer and will not work for anyone else.

**The goal: a new user can obtain their Apple Music token through Vinyl Tap's
own web UI, with no developer tools, no proxy setup, no command
line, and no technical knowledge required.**

The user should experience something like:
> "Go to Settings → Link Apple Music → follow the prompt → done."

---

## What We Know

- Apple Music SMAPI uses a `loginToken` with three fields:
  - `token` — base64-encoded binary, obtained via AppLink auth flow
  - `key` — Unix timestamp in milliseconds (token expiry, ~1 year lifespan)
  - `householdId` — `Sonos_{household_id}_{oadevid}`, discoverable from speaker
- The `oadevid` is already extracted by `_lookup_apple_music_udn()` in
  `sonos_controller.py`
- The `household_id` is available from soco
- The only missing piece is obtaining the `token` + `key` pair

- Traffic capture (March 2026) shows Sonify calls `sonos-music.apple.com`
  directly with cached credentials — no Sonos Control API involved
- Token acquisition happens inside encrypted iCloud tunnels — not visible at
  the HTTP layer via standard proxy tools
- Tokens survive app delete/reinstall via iCloud Keychain
- `getAppLink` returns error 999 for unregistered apps — Apple Music only
  responds to registered Sonos partner apps

---

## Research Options

### Option 1: Static Analysis of Sonify IPA (Recommended First Step)

**Goal**: Identify what partner credentials Sonify sends when calling
`getAppLink` on `sonos-music.apple.com`, and how/where it stores the resulting
token.

**Why this matters**: `getAppLink` returns error 999 for unregistered callers.
Sonify IS registered. If we can find the credentials Sonify uses to identify
itself as a registered partner, we may be able to replicate that call and
implement a full AppLink flow in Vinyl Tap's web UI.

**Approach**:
1. Extract the Sonify `.ipa` from the Mac (iTunes/Finder stores downloaded
   IPAs, or use `ipatool` CLI to download from App Store)
2. Unzip the `.ipa` (it is a zip archive)
3. Run `class-dump` on the binary to extract Objective-C/Swift class and method
   headers
4. Search for strings related to: `getAppLink`, `AppLink`, `linkCode`,
   `privateKey`, `SonosApp`, `partnerKey`, `clientId`, `bundleId`
5. Identify the SOAP header fields Sonify sends in its `getAppLink` call — in
   particular any `deviceId`, `hardware`, `osVersion`, or similar fields that
   Apple Music uses to verify the caller is a registered partner

**What success looks like**: We find a hardcoded partner identifier or
registration token in the binary that Sonify passes to `sonos-music.apple.com`
to authenticate itself as a registered partner. We can then use that identifier
in our own `getAppLink` call.

**Risk**: Low. Read-only analysis of a binary. Nothing to break.

**Tools needed**: `class-dump` (free), `strings`, a text editor.

---

### Option 2: Capture the Official Sonos App's AppLink Flow

**Goal**: Watch the official Sonos app perform the Apple Music AppLink flow
from scratch, capturing the exact SMAPI request/response sequence including
`getAppLink` and `getDeviceAuthToken`.

**Why this matters**: The official Sonos app is definitely a registered partner
and definitely performs AppLink when you first add Apple Music. Capturing that
flow would show us exactly what a successful `getAppLink` exchange looks like,
including what credentials are sent and what the response contains.

**Approach**:
1. On a **second** Apple ID / Sonos household (not the primary one) — to avoid
   disrupting the working setup — set up Proxyman capture
2. In the Sonos app, go to **Settings → Services & Voice → + Add a Service →
   Apple Music**
3. Follow the Apple Music linking flow completely
4. Capture all traffic to `sonos-music.apple.com` during this flow

**Approach (using existing Sonos household)**:
1. Set up Proxyman capture (already done — certificate installed)
2. In the Sonos app: **Settings → Services & Voice → Apple Music → Remove**
3. Re-add Apple Music: **Settings → Services & Voice → + Add a Service →
   Apple Music** — follow the AppLink flow completely
4. Capture all traffic to `sonos-music.apple.com` during the flow
5. Update `config.json` with the new token from the capture

Note: re-linking issues a new token. The existing `config.json` token becomes
stale and must be updated. If the re-link succeeds (expected), there is no
lasting disruption.

**What success looks like**: We see a `getAppLink` SOAP request with full
headers, the response containing a `regUrl`, the redirect to Apple Music
authorization, and finally `getDeviceAuthToken` returning `authToken` + `key`.
We understand the complete flow end to end.

**Risk**: Low. Re-linking Apple Music on a working Sonos household is a
standard user operation. Temporarily without Apple Music only during the flow.

**Tools needed**: Proxyman (already set up).

---

### Option 3: Frida Dynamic Instrumentation

**Goal**: Hook into the Sonify app's runtime to intercept the token acquisition
before it is encrypted and stored in iCloud Keychain.

**Why this matters**: This would let us see inside the encrypted `gateway.icloud.com`
tunnels by intercepting the data before encryption — at the point where Sonify
calls the relevant API and receives the token back.

**Approach**:
1. Re-sign the Sonify IPA with a Frida gadget injected (using `frida-ios-dump`
   or `objection` toolchain)
2. Install the re-signed IPA on a developer-provisioned device
3. Hook the relevant SSL/network functions to capture decrypted payloads
4. Trigger Sonify's token acquisition flow (may require clearing Keychain
   entries first using `objection` Keychain dump/clear)

**What success looks like**: We see the raw HTTP request/response inside the
iCloud tunnel, revealing exactly what API Sonify calls and what it receives back
in exchange for the token.

**Risk**: Medium. Requires re-signing the app (Apple developer account). Does
not affect the production setup.

**Tools needed**: Xcode, `frida`, `objection`, Apple developer account.

---

## Recommended Sequence

1. **Start with Option 2** (capture Sonos app AppLink flow) — unlink and
   re-link Apple Music on the existing household with Proxyman running. This
   directly captures the live token acquisition sequence end-to-end and is
   the most direct path to understanding the full flow.

2. **If Option 2 is inconclusive** (e.g. the AppLink flow is also encrypted),
   try **Option 1** (static analysis of Sonify) to look for hardcoded partner
   credentials in the binary.

3. **If both are inconclusive**, escalate to **Option 3** (Frida) to intercept
   at the runtime level.

---

## End State: What We Are Building

Once the token acquisition mechanism is understood, the implementation will be
a **Settings page flow** in Vinyl Tap's web UI:

1. User navigates to **Settings → Link Apple Music**
2. App calls `getAppLink` on `sonos-music.apple.com` → receives `regUrl`
3. App displays a button: **"Authorize with Apple Music"** (opens `regUrl` in
   a new tab)
4. User authorizes in their browser (Apple ID sign-in)
5. App polls `getDeviceAuthToken` until it receives `authToken` + `key`
6. App stores `token`, `key`, and constructs `householdId` from the speaker
7. Settings page shows **"Apple Music linked ✓"**

The user never touches a config file, terminal, or proxy tool.
