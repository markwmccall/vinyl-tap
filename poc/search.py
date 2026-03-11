import requests
import xml.etree.ElementTree as ET

# Configuration
SPEAKER_IP = "10.0.0.47"
SERVICE_ID = "65031" # Apple Music
SEARCH_TERM = "Blinding Lights"
SEARCH_TYPE = "track" # Can be 'track', 'album', or 'playlist'

# SMAPI Endpoint for Apple Music
ENDPOINT = "https://sonos-music.apple.com/ws/SonosSoap"

def search_apple_music(term, search_type="track"):
    # The SOAP envelope Sonos uses for searching
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="http://www.sonos.com/Services/1.1">
      <soap:Header>
        <ns:credentials>
          <ns:deviceId>00-11-22-33-44-55:1</ns:deviceId>
          <ns:deviceProvider>Sonos</ns:deviceProvider>
        </ns:credentials>
      </soap:Header>
      <soap:Body>
        <ns:search>
          <ns:id>{search_type}</ns:id>
          <ns:term>{term}</ns:term>
          <ns:index>0</ns:index>
          <ns:count>10</ns:count>
        </ns:search>
      </soap:Body>
    </soap:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": '"http://www.sonos.com/Services/1.1#search"'
    }

    try:
        response = requests.post(ENDPOINT, data=soap_body, headers=headers)
        response.raise_for_status()
        
        # Parse the XML response
        root = ET.fromstring(response.content)
        # Handle namespaces
        ns = {'ns': 'http://www.sonos.com/Services/1.1'}
        
        results = []
        for item in root.findall(".//ns:mediaMetadata", ns):
            results.append({
                "title": item.find("ns:title", ns).text,
                "id": item.find("ns:id", ns).text,
                "artist": item.find(".//ns:artist", ns).text if item.find(".//ns:artist", ns) is not None else "N/A"
            })
        
        return results

    except Exception as e:
        return f"Error: {e}"

# Run search
print(f"Searching for '{SEARCH_TERM}' on Apple Music...")
results = search_apple_music(SEARCH_TERM, SEARCH_TYPE)

if isinstance(results, list):
    print(f"{'Title':<30} | {'Artist':<20} | {'ID (for NFC tag)'}")
    print("-" * 80)
    for r in results:
        print(f"{r['title'][:30]:<30} | {r['artist'][:20]:<20} | {r['id']}")
else:
    print(results)