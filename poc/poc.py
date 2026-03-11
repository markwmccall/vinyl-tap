import requests
import xml.dom.minidom # For pretty printing the output

# The credentials you harvested
TOKEN = "AgGjuuzxvs5Fu0eD9DajtYQm53KcE+m4fIGXZzEHzzAK2WGPvOFpAFNcsZh3ZW0TudEgfFGVsBCdESu0iYxeGj0x78Hmwze2LOe6nXEOjm1ZXIrKGKA5LwDlDsDH8iyGv5KE/G5VeKgEsbdoK1QQQ8feGc5DdOOIwtaufELC0ydHu+f2eL8="
KEY = "1770586134897"
HHID = "Sonos_q83BVuX1yolDA6Bg1DbwdTfETv_f7c0f087"

def apple_music_search(query):
    url = "https://sonos-music.apple.com/ws/SonosSoap"
    
    # We use the exact structure from your capture
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="http://www.sonos.com/Services/1.1">
      <s:Header>
        <ns:credentials>
          <ns:loginToken>
            <ns:token>{TOKEN}</ns:token>
            <ns:key>{KEY}</ns:key>
            <ns:householdId>{HHID}</ns:householdId>
          </ns:loginToken>
        </ns:credentials>
        <ns:context>
          <ns:timeZone>00:00</ns:timeZone>
        </ns:context>
      </s:Header>
      <s:Body>
        <ns:search>
          <ns:id>all</ns:id>
          <ns:term>{query}</ns:term>
          <ns:index>0</ns:index>
          <ns:count>50</ns:count>
        </ns:search>
      </s:Body>
    </s:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": '"http://www.sonos.com/Services/1.1#search"',
        "User-Agent": "Sonos/71.1-35240 (build 35240; iOS 17.4.1)"
    }

    print(f"Searching Apple Music for: {query}...")
    response = requests.post(url, data=soap_body, headers=headers)
    
    if response.status_code == 200:
        # Pretty print the XML response
        dom = xml.dom.minidom.parseString(response.text)
        print(dom.toprettyxml())
    else:
        print(f"Error {response.status_code}:")
        print(response.text)

if __name__ == "__main__":
    apple_music_search("Radiohead")