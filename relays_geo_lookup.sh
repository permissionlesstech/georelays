#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 output.csv"
    exit 1
fi

output_file="$1"

sudo mkdir -p /var/www/ip-location-api
sudo wget -q -O /var/www/ip-location-api/ip-location-api https://github.com/paul-norman/ip-location-api/releases/latest/download/ip-location-api-linux-x64.bin 
sudo chmod +x /var/www/ip-location-api/ip-location-api

sudo nano /var/www/ip-location-api/.env
sudo echo "
SERVER_HOST=127.0.0.1
SERVER_PORT=8081

API_KEY=

COUNTRY=
CITY=dbip-city
ASN=

UPDATE_TIME=01:30

DB_TYPE=sqlite
DB_USER=$PWD/db_ip.sqlite
DB_SCHEMA=
" > /var/www/ip-location-api/.env

sudo /var/www/ip-location-api/ip-location-api > /dev/null &
ip_location_pid=$!

sleep 30

echo "Relay URL,Latitude,Longitude" > "$output_file"

while IFS= read -r url; do

    a_records=$(dig +short "$url" A)

    if [[ -n "$a_records" ]]; then
        
    	for ip in $a_records; do
			echo "Attempting geo-location lookup for $url -> $ip"
			
			
			location_data=""
			retries=3
			attempt=0

			while [[ -z "$location_data" && $attempt -lt $retries ]]; do
				location_data=$(curl -s -k "http://localhost/ip/$ip")
				#echo "location data: $(echo $location_data | jq)"
				attempt=$((attempt + 1))
				sleep 1
			done
			
			latitude=$(echo "$location_data" | jq -r '.loc' | cut -d',' -f1)
			longitude=$(echo "$location_data" | jq -r '.loc' | cut -d',' -f2)

			if [[ -n "$latitude" && -n "$longitude" && $latitude != "null" && $longitude != "null" ]]; then
				echo "$url: latitude=$latitude, longitude=$longitude"
				echo "$url,$latitude,$longitude" >> "$output_file"
				break
			else
				echo "geolocation failed for $url"
				continue
			fi
		done
    else
        echo "geolocation failed for $url"
    fi
done

echo "Results written to $output_file"

