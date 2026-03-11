#!/usr/bin/env python3
"""Probe Sonos speaker for SMAPI credentials and test search capabilities."""

import requests
import xml.etree.ElementTree as ET
import xml.dom.minidom
import sys

SPEAKER_IP = "10.0.0.47"
BASE = f"http://{SPEAKER_IP}:1400"

# Known service info from ListAvailableServices dump
SERVICES = {
    "apple": {
        "name": "Apple Music",
        "sid": "204",
        "uri": "https://sonos-music.apple.com/ws/SonosSoap",
        "auth": "AppLink",
    },
    "amazon": {
        "name": "Amazon Music",
        "sid": "201",
        "uri": "https://sonos.amazonmusic.com/",
        "auth": "DeviceLink",
    },
    "spotify": {
        "name": "Spotify",
        "sid": "12",
        "uri": "https://spotify-v5.ws.sonos.com/smapi",
        "auth": "AppLink",
    },
}

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SONOS = "http://www.sonos.com/Services/1.1"


def soap_call(url, service_type, action, body_xml, timeout=10):
    """Make a SOAP call and return the response text."""
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="{NS_SOAP}" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
      <s:Body>{body_xml}</s:Body>
    </s:Envelope>"""
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{service_type}#{action}"',
    }
    try:
        r = requests.post(url, data=envelope, headers=headers, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def pretty(xml_text):
    """Pretty print XML, truncated."""
    try:
        dom = xml.dom.minidom.parseString(xml_text)
        pretty = dom.toprettyxml(indent="  ")
        lines = pretty.split("\n")
        if len(lines) > 60:
            return "\n".join(lines[:60]) + f"\n... ({len(lines) - 60} more lines)"
        return pretty
    except Exception:
        return xml_text[:2000]


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ── 1. Get Household ID ──────────────────────────────────────────────
section("1. DeviceProperties → GetHouseholdID")
status, text = soap_call(
    f"{BASE}/DeviceProperties/Control",
    "urn:schemas-upnp-org:service:DeviceProperties:1",
    "GetHouseholdID",
    '<u:GetHouseholdID xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1"/>',
)
print(f"Status: {status}")
hhid = None
if status == 200:
    root = ET.fromstring(text)
    for elem in root.iter():
        if "CurrentHouseholdID" in elem.tag:
            hhid = elem.text
            break
    print(f"HouseholdID: {hhid}")
else:
    print(pretty(text))


# ── 2. Get Device Serial (R_TrialZPSerial) ──────────────────────────
section("2. SystemProperties → GetString (R_TrialZPSerial)")
status, text = soap_call(
    f"{BASE}/SystemProperties/Control",
    "urn:schemas-upnp-org:service:SystemProperties:1",
    "GetString",
    """<u:GetString xmlns:u="urn:schemas-upnp-org:service:SystemProperties:1">
         <VariableName>R_TrialZPSerial</VariableName>
       </u:GetString>""",
)
print(f"Status: {status}")
device_id = None
if status == 200:
    root = ET.fromstring(text)
    for elem in root.iter():
        if "StringValue" in elem.tag:
            device_id = elem.text
            break
    print(f"DeviceId (R_TrialZPSerial): {device_id}")
else:
    print(pretty(text))


# ── 3. Probe SystemProperties for account/credential keys ───────────
section("3. SystemProperties → probe known keys")
probe_keys = [
    "R_TrialZPSerial",
    "CustomerID",
    "ThirdPartyMediaServersX",
    "OAuthLink_204",    # speculative: Apple Music OAuth
    "OAuthLink_201",    # speculative: Amazon OAuth
]
for key in probe_keys:
    status, text = soap_call(
        f"{BASE}/SystemProperties/Control",
        "urn:schemas-upnp-org:service:SystemProperties:1",
        "GetString",
        f"""<u:GetString xmlns:u="urn:schemas-upnp-org:service:SystemProperties:1">
              <VariableName>{key}</VariableName>
            </u:GetString>""",
    )
    if status == 200:
        root = ET.fromstring(text)
        val = None
        for elem in root.iter():
            if "StringValue" in elem.tag:
                val = elem.text
                break
        # Truncate long values
        if val and len(val) > 200:
            val = val[:200] + "..."
        print(f"  {key}: {val}")
    else:
        # Extract error code
        try:
            root = ET.fromstring(text)
            err = None
            for elem in root.iter():
                if "errorCode" in elem.tag:
                    err = elem.text
            print(f"  {key}: ERROR {err}")
        except Exception:
            print(f"  {key}: HTTP {status}")


# ── 4. Try GetSessionId for each service ─────────────────────────────
section("4. MusicServices → GetSessionId")
for svc_key, svc in SERVICES.items():
    print(f"\n  --- {svc['name']} (sid={svc['sid']}) ---")
    status, text = soap_call(
        f"{BASE}/MusicServices/Control",
        "urn:schemas-upnp-org:service:MusicServices:1",
        "GetSessionId",
        f"""<u:GetSessionId xmlns:u="urn:schemas-upnp-org:service:MusicServices:1">
              <ServiceId>{svc['sid']}</ServiceId>
              <Username></Username>
            </u:GetSessionId>""",
    )
    print(f"  Status: {status}")
    if status == 200:
        root = ET.fromstring(text)
        for elem in root.iter():
            if "SessionId" in elem.tag:
                print(f"  SessionId: {elem.text}")
    else:
        try:
            root = ET.fromstring(text)
            for elem in root.iter():
                if "errorCode" in elem.tag:
                    print(f"  ErrorCode: {elem.text}")
                if "errorDescription" in elem.tag:
                    print(f"  ErrorDesc: {elem.text}")
        except Exception:
            print(f"  Response: {text[:500]}")


# ── 5. Try getAppLink for Apple Music ────────────────────────────────
section("5. Apple Music SMAPI → getAppLink")
if hhid:
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="{NS_SOAP}" xmlns:ns="{NS_SONOS}">
      <s:Header>
        <ns:credentials>
          <ns:deviceId>{device_id or 'unknown'}</ns:deviceId>
          <ns:deviceProvider>Sonos</ns:deviceProvider>
          <ns:householdId>{hhid}</ns:householdId>
        </ns:credentials>
      </s:Header>
      <s:Body>
        <ns:getAppLink/>
      </s:Body>
    </s:Envelope>"""
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{NS_SONOS}#getAppLink"',
        "User-Agent": "Linux UPnP/1.0 Sonos/80.1-55240",
    }
    try:
        r = requests.post(SERVICES["apple"]["uri"], data=soap_body, headers=headers, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            ns = {"n": NS_SONOS}
            reg_url = root.find(".//n:regUrl", ns)
            link_code = root.find(".//n:linkCode", ns)
            if reg_url is not None:
                print(f"  regUrl: {reg_url.text}")
                print(f"  linkCode: {link_code.text if link_code is not None else 'N/A'}")
            else:
                print(pretty(r.text))
        else:
            print(pretty(r.text))
    except Exception as e:
        print(f"Error: {e}")
else:
    print("Skipped — no HouseholdID")


# ── 6. Try getAppLink for Amazon Music (DeviceLink) ─────────────────
section("6. Amazon Music SMAPI → getDeviceLinkCode")
if hhid:
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="{NS_SOAP}" xmlns:ns="{NS_SONOS}">
      <s:Header>
        <ns:credentials>
          <ns:deviceId>{device_id or 'unknown'}</ns:deviceId>
          <ns:deviceProvider>Sonos</ns:deviceProvider>
          <ns:householdId>{hhid}</ns:householdId>
        </ns:credentials>
      </s:Header>
      <s:Body>
        <ns:getDeviceLinkCode/>
      </s:Body>
    </s:Envelope>"""
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{NS_SONOS}#getDeviceLinkCode"',
        "User-Agent": "Linux UPnP/1.0 Sonos/80.1-55240",
    }
    try:
        r = requests.post(SERVICES["amazon"]["uri"], data=soap_body, headers=headers, timeout=10)
        print(f"Status: {r.status_code}")
        print(pretty(r.text))
    except Exception as e:
        print(f"Error: {e}")
else:
    print("Skipped — no HouseholdID")


# ── 7. Test search with existing poc.py credentials ──────────────────
section("7. Apple Music SMAPI → search (using poc.py credentials)")
# Credentials from poc.py (may be expired)
TOKEN = "AgGjuuzxvs5Fu0eD9DajtYQm53KcE+m4fIGXZzEHzzAK2WGPvOFpAFNcsZh3ZW0TudEgfFGVsBCdESu0iYxeGj0x78Hmwze2LOe6nXEOjm1ZXIrKGKA5LwDlDsDH8iyGv5KE/G5VeKgEsbdoK1QQQ8feGc5DdOOIwtaufELC0ydHu+f2eL8="
KEY = "1770586134897"
STORED_HHID = "Sonos_q83BVuX1yolDA6Bg1DbwdTfETv_f7c0f087"

soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="{NS_SOAP}" xmlns:ns="{NS_SONOS}">
  <s:Header>
    <ns:credentials>
      <ns:loginToken>
        <ns:token>{TOKEN}</ns:token>
        <ns:key>{KEY}</ns:key>
        <ns:householdId>{STORED_HHID}</ns:householdId>
      </ns:loginToken>
    </ns:credentials>
  </s:Header>
  <s:Body>
    <ns:search>
      <ns:id>album</ns:id>
      <ns:term>Radiohead</ns:term>
      <ns:index>0</ns:index>
      <ns:count>5</ns:count>
    </ns:search>
  </s:Body>
</s:Envelope>"""
headers = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": f'"{NS_SONOS}#search"',
    "User-Agent": "Linux UPnP/1.0 Sonos/80.1-55240",
}
try:
    r = requests.post(SERVICES["apple"]["uri"], data=soap_body, headers=headers, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        # Check if we got actual results or an auth error
        root = ET.fromstring(r.text)
        ns = {"n": NS_SONOS}
        items = root.findall(".//n:mediaCollection", ns) + root.findall(".//n:mediaMetadata", ns)
        if items:
            print(f"  Got {len(items)} results!")
            for item in items[:5]:
                title = item.find("n:title", ns)
                artist = item.find(".//n:artist", ns)
                item_id = item.find("n:id", ns)
                print(f"  - {title.text if title is not None else '?'}"
                      f" | {artist.text if artist is not None else '?'}"
                      f" | id={item_id.text if item_id is not None else '?'}")
        else:
            print(pretty(r.text))
    else:
        # Check for specific SMAPI errors
        try:
            root = ET.fromstring(r.text)
            for elem in root.iter():
                if "ExceptionInfo" in str(elem.tag) or "faultstring" in str(elem.tag):
                    print(f"  {elem.tag}: {elem.text}")
                if "SonosError" in str(elem.tag):
                    print(f"  SonosError: {elem.text}")
        except Exception:
            pass
        print(pretty(r.text))
except Exception as e:
    print(f"Error: {e}")


# ── 8. ContentDirectory browse with service prefix ───────────────────
section("8. ContentDirectory → Browse with service prefixes")
prefixes_to_try = [
    ("FV:2", "Sonos Favorites (known working)"),
    ("SQ:", "Sonos Playlists"),
    ("MS:204", "Apple Music (speculative)"),
    ("MS:201", "Amazon Music (speculative)"),
    ("SEARCH:204:album:Radiohead", "Apple Music search (speculative)"),
]
for prefix, desc in prefixes_to_try:
    status, text = soap_call(
        f"{BASE}/MediaServer/ContentDirectory/Control",
        "urn:schemas-upnp-org:service:ContentDirectory:1",
        "Browse",
        f"""<u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
              <ObjectID>{prefix}</ObjectID>
              <BrowseFlag>BrowseDirectChildren</BrowseFlag>
              <Filter>*</Filter>
              <StartingIndex>0</StartingIndex>
              <RequestedCount>5</RequestedCount>
              <SortCriteria></SortCriteria>
            </u:Browse>""",
    )
    result_count = "?"
    if status == 200:
        root = ET.fromstring(text)
        for elem in root.iter():
            if "NumberReturned" in elem.tag:
                result_count = elem.text
        print(f"  {prefix:<40} → {result_count} results  ({desc})")
    else:
        err_code = "?"
        try:
            root = ET.fromstring(text)
            for elem in root.iter():
                if "errorCode" in elem.tag:
                    err_code = elem.text
        except Exception:
            pass
        print(f"  {prefix:<40} → ERROR {err_code}  ({desc})")

print("\n" + "="*70)
print("  Done.")
print("="*70)
