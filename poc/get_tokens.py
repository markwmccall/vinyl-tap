import soco
import xml.etree.ElementTree as ET

def get_apple_tokens():
    print("Searching for your Move 2...")
    device = soco.discovery.any_soco()
    if not device:
        print("No speakers found.")
        return

    print(f"Connected to {device.player_name}. Querying system accounts...")
    
    # 1. Get the list of all music service accounts on the system
    try:
        response = device.systemProperties.GetDeviceProperties([('VariableName', 'Settings')])
        # The 'Settings' variable contains an XML block of all accounts
        settings_xml = response['Settings']
        
        # 2. Parse the settings XML
        root = ET.fromstring(settings_xml)
        
        # 3. Look for Apple Music (Service ID 204)
        found_apple = False
        for account in root.findall('.//Account'):
            service_id = account.get('Type')
            # 204 is the hardcoded ID for Apple Music
            if service_id == "204":
                found_apple = True
                account_id = account.find('ID').text if account.find('ID') is not None else "Unknown"
                username = account.find('Username').text if account.find('Username') is not None else "Unknown"
                
                print("\n--- FOUND APPLE MUSIC ACCOUNT ---")
                print(f"Account ID: {account_id}")
                print(f"Username:   {username}")
                print("-" * 33)
                print("Checking for usable Token/Key...")
                
                # Check for the validation string (Key)
                key = account.find('Key').text if account.find('Key') is not None else None
                if key:
                    print(f"Private Key: {key}")
                else:
                    print("Key is hidden/masked in this firmware version.")

        if not found_apple:
            print("No Apple Music account found on this Sonos system.")

    except Exception as e:
        print(f"Error extracting accounts: {e}")

if __name__ == "__main__":
    get_apple_tokens()