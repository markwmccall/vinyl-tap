import soco
from soco.events import event_listener

def on_service_update(event):
    # This triggers when the user adds/updates a service in the official app
    if 'Accounts' in event.variables:
        print("Detected Account Update!")
        print(event.variables['Accounts'])

device = soco.discovery.any_soco()
# Subscribe to the System Properties (where account changes live)
sub = device.systemProperties.subscribe()
sub.callback = on_service_update

print("Listening for you to add Apple Music in the official Sonos app...")
# Keep the script running
import time
while True:
    time.sleep(1)