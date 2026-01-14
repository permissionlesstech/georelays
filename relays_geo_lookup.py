#!/usr/bin/env python3
import sys
import os
import csv
import gzip
import urllib.request
import shutil
import socket
import struct
import bisect
import asyncio
import re
import argparse
from typing import List, Tuple, Optional, Dict

# Configuration
DB_URL = "https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/dbip-city/dbip-city-ipv4-num.csv.gz"
DB_FILENAME_GZ = "dbip-city-ipv4-num.csv.gz"
DB_FILENAME = "dbip-city-ipv4-num.csv"

class GeoIPDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.starts = []
        self.ends = []
        self.locations = []
        self.loaded = False

    def ensure_db_exists(self):
        """Downloads and extracts the database if it doesn't exist."""
        if os.path.exists(self.db_path):
            return

        print(f"Database not found at {self.db_path}. Downloading...")
        try:
            # Download
            urllib.request.urlretrieve(DB_URL, DB_FILENAME_GZ)
            
            # Extract
            print("Extracting database...")
            with gzip.open(DB_FILENAME_GZ, 'rb') as f_in:
                with open(self.db_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Cleanup gz
            os.remove(DB_FILENAME_GZ)
            print("Database ready.")
        except Exception as e:
            print(f"Error setting up database: {e}")
            sys.exit(1)

    def load(self):
        """Loads the CSV database into memory."""
        if not os.path.exists(self.db_path):
            self.ensure_db_exists()

        print("Loading GeoIP database into memory...")
        try:
            # The CSV format is expected to be: start_ip_int, end_ip_int, country, state, city, ..., lat, lon
            # Based on the bash script, lat is col 7 (index 7) and lon is col 8 (index 8) if split by comma?
            # Bash script:
            # start=f[0], end=f[1]
            # lat=f[7], lon=f[8] (indices are 0-based)
            
            self.starts = []
            self.ends = []
            self.locations = []
            
            with open(self.db_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or row[0].startswith('#'):
                        continue
                    if len(row) < 9: # We need at least up to index 8
                        continue
                        
                    try:
                        start_ip = int(row[0])
                        end_ip = int(row[1])
                        lat = row[7]
                        lon = row[8]
                        
                        if lat and lon:
                            self.starts.append(start_ip)
                            self.ends.append(end_ip)
                            self.locations.append((lat, lon))
                    except ValueError:
                        continue
                        
            self.loaded = True
            print(f"Loaded {len(self.starts)} IP ranges.")
        except Exception as e:
            print(f"Error loading database: {e}")
            sys.exit(1)

    def lookup(self, ip_str: str) -> Optional[Tuple[str, str]]:
        """Binary search for the IP."""
        try:
            # Convert IP to integer
            packed = socket.inet_aton(ip_str)
            ip_num = struct.unpack("!L", packed)[0]
        except socket.error:
            return None

        # Binary search
        # bisect_right returns an insertion point i, such that all e in a[:i] have e <= x
        # We want to find a range where start <= ip <= end
        # Since the list is sorted by start_ip, we find the first start_ip > ip_num, then check the previous range
        
        idx = bisect.bisect_right(self.starts, ip_num)
        
        if idx == 0:
            return None
            
        # Check the range at idx - 1
        matched_idx = idx - 1
        if self.starts[matched_idx] <= ip_num <= self.ends[matched_idx]:
            return self.locations[matched_idx]
            
        return None

def clean_url(url: str) -> str:
    """Extracts hostname from a Relay URL."""
    # Remove protocol
    url = re.sub(r'^wss?://', '', url)
    # Remove path and port
    url = url.split('/')[0]
    url = url.split(':')[0]
    return url

async def resolve_and_locate(url: str, raw_url: str, geo_db: GeoIPDatabase) -> Optional[Tuple[str, str, str]]:
    """Resolves URL and looks up Geo location."""
    hostname = clean_url(url)
    if not hostname:
        return None
        
    try:
        # Async DNS resolution
        loop = asyncio.get_running_loop()
        # getaddrinfo returns list of (family, type, proto, canonname, sockaddr)
        # sockaddr is (address, port) for IPv4
        infos = await loop.getaddrinfo(hostname, None, family=socket.AF_INET)
        
        if not infos:
            return None
            
        # Take the first IP
        ip = infos[0][4][0]
        
        # Geo Lookup
        loc = geo_db.lookup(ip)
        if loc:
            lat, lon = loc
            return (raw_url, lat, lon)
        else:
            # print(f"Geolocation failed for {hostname} ({ip})") # Optional verbose logging
            return None
            
    except Exception as e:
        # print(f"Resolution failed for {hostname}: {e}")
        return None

async def main():
    parser = argparse.ArgumentParser(description="Resolve Nostr relay URLs to Geo coordinates.")
    parser.add_argument("output_file", help="Path to output CSV file")
    parser.add_argument("--db", default=DB_FILENAME, help=f"Path to DB-IP CSV (default: {DB_FILENAME})")
    parser.add_argument("--input", help="Input file with relay URLs (one per line). Defaults to stdin if not provided.")
    
    # We parse args manually if we want to support the simple "$0 output.csv" usage 
    # while also supporting flags, but argparse handles it well.
    # If the user runs `script.py output.csv`, it matches the positional arg.
    
    args = parser.parse_args()
    
    # Setup DB
    db = GeoIPDatabase(args.db)
    db.ensure_db_exists()
    db.load()
    
    # Read URLs
    urls = []
    if args.input:
        if os.path.exists(args.input):
            with open(args.input, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
    else:
        # Read from stdin
        if not sys.stdin.isatty():
            urls = [line.strip() for line in sys.stdin if line.strip()]
    
    if not urls:
        print("No URLs provided via input file or stdin.")
        return

    print(f"Processing {len(urls)} relays...")
    
    # Process concurrently
    tasks = [resolve_and_locate(url, url, db) for url in urls]
    results = await asyncio.gather(*tasks)
    
    # Write Output
    success_count = 0
    with open(args.output_file, 'w', newline='') as f:
        # The bash script outputs: "Relay URL,Latitude,Longitude" header
        # And: url,lat,lon lines.
        # It creates the file fresh.
        writer = csv.writer(f)
        writer.writerow(["Relay URL", "Latitude", "Longitude"])
        
        for res in results:
            if res:
                url, lat, lon = res
                print(f"{url}: latitude={lat}, longitude={lon}")
                writer.writerow([url, lat, lon])
                success_count += 1
                
    print(f"Results written to {args.output_file}")
    print(f"Successfully resolved {success_count}/{len(urls)} relays.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
