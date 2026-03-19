# Plan: Static Analysis of Sonify IPA

## Goal

Extract the Sonify iOS app binary and search it for:
1. Partner credentials used to identify Sonify as a registered Sonos/Apple Music
   partner when calling `getAppLink`
2. The SOAP header format it sends for AppLink calls
3. Where/how it stores the resulting token (Keychain service name and key)

## Tools Needed

- **iMazing** (free tier) — extracts IPA from a connected iPhone without jailbreak
- Built-in macOS tools: `unzip`, `strings`, `file`, `nm`
- Optional: **Hopper Disassembler** (free trial) or **Ghidra** (free) for deeper
  analysis if `strings` is inconclusive

---

## Step 1: Install iMazing on Mac

1. Download iMazing from https://imazing.com — free tier is sufficient
2. Install and launch it

---

## Step 2: Extract the Sonify IPA

1. Connect iPhone to Mac via USB
2. In iMazing, select your iPhone in the left sidebar
3. Click **Apps** in the top navigation
4. Find **Sonify** in the app list
5. Right-click Sonify → **Export .IPA**
6. Save to a working directory, e.g. `~/Desktop/sonify-analysis/`

---

## Step 3: Unzip the IPA

An IPA is a zip archive. In Terminal:

```bash
cd ~/Desktop/sonify-analysis
unzip Sonify.ipa -d Sonify_extracted
```

The app binary will be at:
```
Sonify_extracted/Payload/Sonify.app/Sonify
```

Verify it:
```bash
file Sonify_extracted/Payload/Sonify.app/Sonify
```
Expected output: `Mach-O 64-bit executable arm64` (or a fat binary with arm64)

---

## Step 4: Quick Strings Pass

Run `strings` to dump all readable text from the binary and filter for
auth-related terms:

```bash
strings Sonify_extracted/Payload/Sonify.app/Sonify | grep -i -E \
  "applink|getAppLink|getDeviceAuthToken|partnerKey|clientId|deviceId|\
sonos-music|loginToken|privateKey|credential|keychain|SecItem" \
  | sort | uniq
```

Also search for Sonos registration identifiers:
```bash
strings Sonify_extracted/Payload/Sonify.app/Sonify | grep -i -E \
  "partner|registration|apiKey|secret|SonosApp|household"
```

And Apple Music specific terms:
```bash
strings Sonify_extracted/Payload/Sonify.app/Sonify | grep -i -E \
  "apple.com|musickit|music-user-token|204|sid=204"
```

---

## Step 5: Symbol Dump

List all class/method names in the binary (works for Objective-C; Swift symbols
are mangled but still useful):

```bash
nm Sonify_extracted/Payload/Sonify.app/Sonify | grep -i -E \
  "applink|auth|token|credential|sonos|apple|partner" \
  | c++filt
```

For Swift-specific demangling:
```bash
nm Sonify_extracted/Payload/Sonify.app/Sonify \
  | xcrun swift-demangle \
  | grep -i -E "applink|auth|token|credential|sonos|apple|partner"
```

---

## Step 6: Search the App Bundle

The binary isn't the only place credentials could live. Check the app bundle:

```bash
# List all files in the bundle
find Sonify_extracted/Payload/Sonify.app -type f | sort

# Search all plist files for interesting keys
find Sonify_extracted/Payload/Sonify.app -name "*.plist" \
  -exec plutil -convert xml1 -o - {} \; \
  | grep -i -E "token|key|partner|sonos|apple|auth|client"

# Check Info.plist specifically
plutil -p Sonify_extracted/Payload/Sonify.app/Info.plist
```

---

## Step 7: Deeper Analysis with Hopper (if needed)

If `strings` and `nm` are inconclusive, use Hopper Disassembler to search for
the AppLink call site:

1. Open Hopper → **File → Read Executable to Disassemble**
2. Select `Sonify_extracted/Payload/Sonify.app/Sonify`
3. Let it analyze (takes a few minutes)
4. Use **Navigate → Go to Address / Symbol** to search for `getAppLink`
5. Look at the surrounding code to identify what headers/credentials are
   constructed before the SOAP call

---

## What We're Looking For

| Finding | What it means |
|---|---|
| Hardcoded `clientId` / `partnerKey` string | Partner credential — use this in our `getAppLink` call |
| Keychain service name for token storage | Confirms iCloud Keychain is the storage mechanism |
| `getAppLink` SOAP header construction | Shows exactly what fields Apple Music requires |
| `appUrlEncrypt=true` handling code | Confirms whether Sonify decrypts the auth URL or delegates to Sonos |

---

## Expected Outcomes

**Best case**: A hardcoded partner key or client ID in the binary that Sonify
passes to `sonos-music.apple.com` to identify itself. We can use this in our
own `getAppLink` call.

**Likely case**: The credentials are not hardcoded but loaded from a
configuration or derived at runtime — `strings` will be inconclusive and we
will need to proceed to Option 2 (live AppLink capture) or Option 3 (Frida).

**Also valuable regardless**: Identifying the Keychain service name and key
that Sonify uses to store the token — this would confirm exactly how tokens
persist across reinstalls.
