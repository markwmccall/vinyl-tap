import soco
import xml.etree.ElementTree as ET

def find_every_hidden_account():
    device = soco.discovery.any_soco()
    print(f"Deep-scanning {device.player_name} for all service credentials...")

    try:
        # Ask the speaker for its raw internal account XML
        response = device.systemProperties.GetDeviceProperties([('VariableName', 'Settings')])
        raw_xml = response['Settings']
        
        # Parse the XML block
        root = ET.fromstring(raw_xml)
        
        print(f"\n{'Service Name':<20} | {'Type ID':<10} | {'Account ID'}")
        print("-" * 60)
        
        # Iterate through every 'Account' node in the speaker's memory
        for acc in root.findall('.//Account'):
            service_type = acc.get('Type')
            username = acc.find('Username').text if acc.find('Username') is not None else "N/A"
            
            # Map common IDs if unknown (for your reference)
            names = {
                '204': 'Apple Music',
                '38411': 'Amazon Music',
                '51463': 'SiriusXM',
                '166': 'Pocket Casts',
                '65031': 'Apple Music (Custom)'
            }
            name = names.get(service_type, "Unknown Service")
            
            print(f"{name:<20} | {service_type:<10} | {username}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_every_hidden_account()