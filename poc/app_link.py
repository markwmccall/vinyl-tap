import soco
import requests
import uuid

def prove_app_link_spoofed():
    print("Searching for Sonos system...")
    device = soco.discovery.any_soco()
    if not device: return
    
    # Apple requires these specific IDs to authorize a link
    hhid = device.household_id
    sn = device.get_speaker_info()['serial_number']
    # Create a random unique ID for this session
    device_id = str(uuid.uuid4())

    # The official Apple Music Sonos Endpoint
    url = "https://sonos-music.apple.com/ws/SonosSoap"
    
    # This XML is the 'Magic'—it mimics the exact getAppLink request
    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
        <s:Header>
            <credentials xmlns="http://www.sonos.com/Services/1.1">
                <deviceId>{device_id}</deviceId>
                <deviceProvider>Sonos</deviceProvider>
                <householdId>{hhid}</householdId>
            </credentials>
        </s:Header>
        <s:Body>
            <getAppLink xmlns="http://www.sonos.com/Services/1.1" />
        </s:Body>
    </s:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": '"http://www.sonos.com/Services/1.1#getAppLink"',
        # Pretending to be a Sonos Controller (Crucial for Apple)
        "User-Agent": "Sonos/80.1-55240 (Moves)", 
        "X-Sonos-Household-Id": hhid
    }

    print(f"Sponsoring link with Move 2 (SN: {sn})...")
    
    try:
        response = requests.post(url, data=soap_body, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("\n✅ AUTO-MAGIC CONFIRMED!")
            # Extract the URL from the XML response
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.text)
            # Find the regUrl in the namespace
            ns = {'n': 'http://www.sonos.com/Services/1.1'}
            reg_url = root.find('.//n:regUrl', ns).text
            link_code = root.find('.//n:linkCode', ns).text
            
            print(f"URL: {reg_url}")
            print(f"Code: {link_code}")
        else:
            print(f"\n❌ Server rejected request (Status {response.status_code})")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    prove_app_link_spoofed()