import soco
from soco.music_services import MusicService
from soco.music_services.accounts import Account

def browse_my_playlists():
    print("Searching for your Move 2...")
    device = soco.discovery.any_soco()
    if not device:
        print("No speakers found.")
        return

    print(f"Connected to {device.player_name}. Fetching Apple Music account...")
    
    try:
        # 1. Get all Apple Music accounts linked to this speaker
        # 204 is the service ID for Apple Music
        apple_accounts = Account.get_accounts_for_service('204')
        
        if not apple_accounts:
            print("No Apple Music account found on this system.")
            return
            
        # Use the first account found
        my_account = apple_accounts[0]
        print(f"Using account: {my_account.username}")

        # 2. Initialize the service WITH your account
        # This is the "Magic" that unlocks your private library
        apple_music = MusicService('Apple Music', account=my_account)

        print("Browsing your Apple Music library...")
        
        # 3. Find the Library node
        root_items = apple_music.browse()
        library_folder = next((item for item in root_items if 'Library' in item.title), None)
        
        if library_folder:
            # 4. Find the Playlists node
            library_items = apple_music.browse(library_folder)
            playlist_folder = next((item for item in library_items if 'Playlists' in item.title), None)
            
            if playlist_folder:
                print("\n✅ YOUR PLAYLISTS:")
                print("-" * 30)
                my_playlists = apple_music.browse(playlist_folder)
                for pl in my_playlists:
                    print(f" - {pl.title}")
                    # pl.item_id is what you'll eventually save to your NFC tags
            else:
                print("Found Library, but no Playlists folder.")
        else:
            print("Could not find the 'Library' node. Try 'My Music'?")
            
    except Exception as e:
        print(f"❌ Browse failed: {e}")

if __name__ == "__main__":
    browse_my_playlists()