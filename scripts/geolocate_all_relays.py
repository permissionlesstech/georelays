#!/usr/bin/env python3
"""
Geolocate All Discovered Relays

This script reads:
1. nostr_relays.csv - The already geolocated BitChat-capable relays
2. relay_discovery_results.json - The list of ALL functioning relays discovered

It geolocates the remaining non-BitChat relays and outputs a unified CSV:
'all_relays_geo.csv' with columns: Relay URL,Latitude,Longitude,IsBitChat (1 or 0).
This avoids redundant geolocating of the BitChat relays.
"""

import os
import sys
import csv
import json
import asyncio
import re

# Add root folder to path to import relays_geo_lookup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from relays_geo_lookup import GeoIPDatabase, resolve_and_locate, clean_url, DB_FILENAME
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

def strip_protocol(url):
    """Standardizes URLs by removing ws:// or wss:// prefix."""
    return re.sub(r'^wss?://', '', url).strip()

async def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root_dir)

    bitchat_csv_path = "nostr_relays.csv"
    results_json_path = "relay_discovery_results.json"
    output_csv_path = "all_relays_geo.csv"

    if not os.path.exists(bitchat_csv_path):
        print(f"Error: {bitchat_csv_path} does not exist. Run the pipeline first.")
        sys.exit(1)
    if not os.path.exists(results_json_path):
        print(f"Error: {results_json_path} does not exist.")
        sys.exit(1)

    # 1. Read already geolocated BitChat relays
    bitchat_relays = {}
    with open(bitchat_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) >= 3:
                url, lat, lon = row[0].strip(), row[1].strip(), row[2].strip()
                # Store mapped by both raw URL and stripped protocol URL for matching robustness
                bitchat_relays[strip_protocol(url)] = (url, lat, lon)

    print(f"Loaded {len(bitchat_relays)} geolocated BitChat relays.")

    # 2. Read all functioning relays from discovery JSON
    with open(results_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        all_functioning = data.get("functioning_relays", [])

    print(f"Loaded {len(all_functioning)} total functioning relays from discovery results.")

    # 3. Filter out those that are NOT geolocated BitChat relays
    non_bitchat_to_locate = []
    for raw_url in all_functioning:
        stripped = strip_protocol(raw_url)
        if stripped not in bitchat_relays:
            non_bitchat_to_locate.append(raw_url)

    print(f"Identified {len(non_bitchat_to_locate)} non-BitChat relays requiring geolocation.")

    # 4. Geolocate the non-BitChat relays asynchronously
    success_records = []
    if non_bitchat_to_locate:
        db = GeoIPDatabase(DB_FILENAME)
        db.ensure_db_exists()
        db.load()

        print(f"Geolocating {len(non_bitchat_to_locate)} relays...")
        tasks = [resolve_and_locate(url, url, db) for url in non_bitchat_to_locate]
        results = await asyncio.gather(*tasks)

        for res in results:
            if res:
                url, lat, lon = res
                success_records.append((url, lat, lon))
        print(f"Successfully geolocated {len(success_records)}/{len(non_bitchat_to_locate)} non-BitChat relays.")

    # 5. Write unified CSV output
    total_written = 0
    with open(output_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Relay URL", "Latitude", "Longitude", "IsBitChat"])

        # Write BitChat relays (IsBitChat = 1)
        for stripped_url, (url, lat, lon) in bitchat_relays.items():
            # Keep protocol-stripped for consistency if that's how it is in the CSV
            writer.writerow([url, lat, lon, "1"])
            total_written += 1

        # Write geolocated non-BitChat relays (IsBitChat = 0)
        for url, lat, lon in success_records:
            # Strip protocol to match the other CSV format
            clean_r = strip_protocol(url)
            writer.writerow([clean_r, lat, lon, "0"])
            total_written += 1

    print(f"Unified database written to {output_csv_path} (Total of {total_written} geolocated relays).")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
