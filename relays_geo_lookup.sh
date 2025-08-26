#!/bin/bash

set -uo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 output.csv"
    exit 1
fi

output_file="$1"

wget -O dbip-city-ipv4-num.csv.gz https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/dbip-city/dbip-city-ipv4-num.csv.gz
gzip -fd dbip-city-ipv4-num.csv.gz
CSV_FILE="dbip-city-ipv4-num.csv"

declare -a start_arr
declare -a end_arr
declare -a gps_arr

# Convert dotted IPv4 to numeric (unsigned 32-bit)
# Usage: ip_to_num "1.2.3.4"
ip_to_num() {
  local ip="$1"
  IFS='.' read -r a b c d <<< "$ip"
  for part in "$a" "$b" "$c" "$d"; do
    if ! [[ "$part" =~ ^[0-9]+$ ]] || (( part < 0 || part > 255 )); then
      return 1
    fi
  done
  printf '%u' "$(( (a * 16777216) + (b * 65536) + (c * 256) + d ))"
}

# Load CSV and populate arrays
load_csv() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "CSV not found: $file" >&2
    return 2
  fi

  local line
  local IFS_old="$IFS"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    IFS=',' read -r -a f <<< "$line"
    IFS="$IFS_old"
    [[ ${#f[@]} -lt 2 ]] && continue
    local s="${f[0]}" e="${f[1]}"
    local lat="" lon=""
    [[ ${#f[@]} -ge 8 ]] && lat="${f[7]}"
    [[ ${#f[@]} -ge 9 ]] && lon="${f[8]}"
    s="${s//[[:space:]]/}" e="${e//[[:space:]]/}"
    lat="${lat//[[:space:]]/}" lon="${lon//[[:space:]]/}"
    start_arr+=("$s")
    end_arr+=("$e")
    if [[ -n "$lat" && -n "$lon" ]]; then
      gps_arr+=("${lat},${lon}")
    else
      gps_arr+=("")
    fi
  done < "$file"
}

# Binary search. Now accepts dotted IP, converts it, then searches.
# Usage: lookup_ip "1.2.3.4"
# Prints "lat,lon" if found, else returns 1.
lookup_ip() {
  local ip="$1"
  local num
  num="$(ip_to_num "$ip")" || return 2

  local lo=0
  local hi=$(( ${#start_arr[@]} - 1 ))
  if (( hi < 0 )); then return 1; fi
  if (( num < start_arr[0] || num > end_arr[hi] )); then return 1; fi

  while (( lo <= hi )); do
    local mid=$(( (lo + hi) / 2 ))
    local s="${start_arr[mid]}"
    local e="${end_arr[mid]}"
    if (( num < s )); then
      hi=$(( mid - 1 ))
    elif (( num > e )); then
      lo=$(( mid + 1 ))
    else
      local gps="${gps_arr[mid]}"
      if [[ -n "$gps" ]]; then
        printf '%s\n' "$gps"
        return 0
      else
        return 1
      fi
    fi
  done

  return 1
}

echo "Loading database into memory..."
load_csv $CSV_FILE

echo "Relay URL,Latitude,Longitude" > "$output_file"

while IFS= read -r url; do

    a_records=$(dig +short "$url" A 2>/dev/null)

    if [[ -n "$a_records" ]]; then
    	for ip in $a_records; do
        echo "Attempting geo-location lookup for $url -> $ip"
        
        location_data=$(lookup_ip "$ip" 2>/dev/null || true)
        
        if [[ -z "$location_data" ]]; then
          echo "geolocation failed for $ip"
          continue
        fi
        
        latitude=$(printf '%s' "$location_data" | cut -d',' -f1)
        longitude=$(printf '%s' "$location_data" | cut -d',' -f2)

        if [[ -n "$latitude" && -n "$longitude" ]]; then
          echo "$url: latitude=$latitude, longitude=$longitude"
          echo "$url,$latitude,$longitude" >> "$output_file"
          break
        else
          echo "can't extract latidude or longitude for $ip"
          continue
        fi
		  done
    else
        echo "geolocation failed for $url"
    fi
done

echo "Results written to $output_file"

