# Georelays Scripts

This directory contains utility scripts for the Georelays project:

## track_relay_counts.py

This script analyzes the git history of the `nostr_relays.csv` file to track how the number of relay entries changes over time. 

### Features:
- Retrieves the last 30 commits that modified the relay CSV file
- Counts the number of relay entries in each commit
- Creates a time series chart showing the trend of relay counts
- Saves the chart as `assets/relay_count_chart.png`

### Usage:
```
python scripts/track_relay_counts.py
```

### Dependencies:
- pandas
- matplotlib
- numpy

This script is automatically run by the GitHub workflow after each update to the relay data.
