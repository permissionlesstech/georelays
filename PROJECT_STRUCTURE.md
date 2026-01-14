# Project Organization

This project is organized as follows:

## Core Files
- `nostr_relay_discovery.py` - Python script for discovering functioning Nostr relays
- `filter_bitchat_relays.sh` - Shell script to filter relays for BitChat capability
- `relays_geo_lookup.py` - Python script to geolocate relay servers
- `nostr_relays.csv` - The main output file with relay URLs and geolocation data

## Directories
- `/assets` - Contains generated images and other static resources
  - `relay_count_chart.png` - Chart showing relay count history
- `/scripts` - Utility scripts for analysis and visualization
  - `track_relay_counts.py` - Script for analyzing relay count changes
- `/.github/workflows` - GitHub Actions workflow definitions
  - `update-relay-data.yml` - Workflow that updates relay data daily
  - `relay-count-tracker.yml` - Workflow that tracks relay count changes

## GitHub Workflows
The project uses two automated workflows:
1. `update-relay-data.yml` - Runs daily at 6:00 AM UTC to update the relay data
2. `relay-count-tracker.yml` - Runs after the update workflow to track and visualize changes
