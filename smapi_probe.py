#!/usr/bin/env python3
"""
Diagnostic script: probe Sonos SMAPI search for Apple Music.

Run on the Pi (with the venv active or soco installed):
    python3 smapi_probe.py --ip 10.0.0.x --sn 3

Results are dumped as JSON so we can see what SMAPI returns vs.
what the iTunes Search API returns, and whether personal library
items show up.
"""
import argparse
import json
import sys

try:
    import soco
    from soco.music_services import MusicService
except ImportError:
    sys.exit("soco not installed. Run: pip install soco")


def probe(speaker_ip, sn, query):
    print(f"\n--- Connecting to speaker at {speaker_ip} ---")
    speaker = soco.SoCo(speaker_ip)
    print(f"    Speaker: {speaker.player_name}")

    print("\n--- Available music services ---")
    services = MusicService.get_all_music_services_names()
    apple_names = [s for s in services if "apple" in s.lower()]
    print(f"    Apple-related: {apple_names}")
    print(f"    (total services: {len(services)})")

    if not apple_names:
        sys.exit("No Apple Music service found on this speaker.")

    service_name = apple_names[0]
    print(f"\n--- Using service: '{service_name}' ---")

    # Find the linked account for Apple Music on this speaker
    try:
        from soco.music_services import MusicServiceAccount
        all_accounts = MusicServiceAccount.get_accounts()
        print(f"    All accounts: {list(all_accounts.keys())}")
        account = all_accounts.get(service_name)
        print(f"    Account for '{service_name}': {account}")
    except Exception as e:
        account = None
        print(f"    (could not get accounts: {e})")

    svc = MusicService(service_name, account=account)

    # Show service info
    try:
        print(f"    Service ID: {svc.service_id}")
        print(f"    Account: {svc.account}")
    except Exception as e:
        print(f"    (could not read service metadata: {e})")

    # --- Search albums ---
    print(f"\n--- Searching albums for: '{query}' ---")
    try:
        results = svc.search("albums", term=query)
        items = list(results)
        print(f"    {len(items)} result(s)")
        for i, item in enumerate(items[:5]):
            print(f"\n    [{i}] type={type(item).__name__}")
            # Dump all attributes
            attrs = {k: v for k, v in vars(item).items() if not k.startswith("_")}
            print(json.dumps(attrs, default=str, indent=6))
    except Exception as e:
        print(f"    Album search failed: {e}")

    # --- Search tracks ---
    print(f"\n--- Searching tracks for: '{query}' ---")
    try:
        results = svc.search("tracks", term=query)
        items = list(results)
        print(f"    {len(items)} result(s)")
        for i, item in enumerate(items[:3]):
            print(f"\n    [{i}] type={type(item).__name__}")
            attrs = {k: v for k, v in vars(item).items() if not k.startswith("_")}
            print(json.dumps(attrs, default=str, indent=6))
    except Exception as e:
        print(f"    Track search failed: {e}")

    # --- Search playlists ---
    print(f"\n--- Searching playlists for: '{query}' ---")
    try:
        results = svc.search("playlists", term=query)
        items = list(results)
        print(f"    {len(items)} result(s)")
        for i, item in enumerate(items[:3]):
            print(f"\n    [{i}] type={type(item).__name__}")
            attrs = {k: v for k, v in vars(item).items() if not k.startswith("_")}
            print(json.dumps(attrs, default=str, indent=6))
    except Exception as e:
        print(f"    Playlist search failed: {e}")

    # --- Browse personal library root ---
    print(f"\n--- Browsing personal library root ---")
    try:
        results = svc.get_metadata("library")
        items = list(results)
        print(f"    {len(items)} item(s)")
        for i, item in enumerate(items[:5]):
            print(f"\n    [{i}] type={type(item).__name__}")
            attrs = {k: v for k, v in vars(item).items() if not k.startswith("_")}
            print(json.dumps(attrs, default=str, indent=6))
    except Exception as e:
        print(f"    Library browse failed: {e}")

    print("\n--- Done ---\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Sonos SMAPI Apple Music search")
    parser.add_argument("--ip", required=True, help="Sonos speaker IP address")
    parser.add_argument("--sn", default="3", help="Apple Music sn value from config")
    parser.add_argument("--query", default="Pyromania", help="Search term to test with")
    args = parser.parse_args()
    probe(args.ip, args.sn, args.query)
