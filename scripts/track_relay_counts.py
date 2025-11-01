#!/usr/bin/env python3
"""
Track Relay Count Changes

This script analyzes the git history of relay data files to track how 
the number of relay entries changes over time. It generates charts showing
the trend over the last 70 commits that modified the files (approximately 70 days).

Two charts are generated:
1. BitChat Relay Count - from nostr_relays.csv (relays supporting kind 20000)
2. Total Relay Count - from relay_discovery_results.json (all functioning relays)
"""

import os
import subprocess
import re
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np

# Function to get the count of BitChat relays in a specific commit
def get_relay_count(commit_hash):
    """
    Get the count of BitChat relay entries in the CSV file at a specific commit.
    
    Args:
        commit_hash: Git commit hash
        
    Returns:
        int: Number of relay entries (excluding header)
    """
    try:
        # Get the file content at this commit
        result = subprocess.run(
            ['git', 'show', f'{commit_hash}:nostr_relays.csv'],
            capture_output=True, text=True, check=True
        )
        
        # Count lines excluding header
        lines = result.stdout.strip().split('\n')
        # Subtract 1 for the header row
        return len(lines) - 1 if lines else 0
    except subprocess.CalledProcessError:
        # File might not exist in this commit
        return 0

# Function to get the count of total functioning relays in a specific commit
def get_total_relay_count(commit_hash):
    """
    Get the count of total functioning relays from the JSON file at a specific commit.
    
    Args:
        commit_hash: Git commit hash
        
    Returns:
        int: Number of functioning relays
    """
    try:
        # Get the file content at this commit
        result = subprocess.run(
            ['git', 'show', f'{commit_hash}:relay_discovery_results.json'],
            capture_output=True, text=True, check=True
        )
        
        # Parse JSON and get the count from functioning_relays array
        data = json.loads(result.stdout)
        return len(data.get('functioning_relays', []))
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        print(f"Error getting total relay count from commit {commit_hash}: {e}")
        return 0

# Function to extract date from commit message
def extract_date_from_commit(commit_hash):
    """
    Extract the date from a commit.
    
    Args:
        commit_hash: Git commit hash
        
    Returns:
        datetime: Commit date
    """
    try:
        result = subprocess.run(
            ['git', 'show', '-s', '--format=%ci', commit_hash],
            capture_output=True, text=True, check=True
        )
        commit_date = result.stdout.strip()
        return datetime.strptime(commit_date, '%Y-%m-%d %H:%M:%S %z')
    except Exception as e:
        print(f"Error extracting date from commit {commit_hash}: {e}")
        return None

def create_plot(data_frame, title, y_label, output_path):
    """
    Create and save a plot from the given data.
    
    Args:
        data_frame: DataFrame containing 'date' and 'count' columns
        title: Title for the plot
        y_label: Label for Y-axis
        output_path: Path to save the plot
    """
    if data_frame.empty:
        print(f"No data found to generate {title} chart")
        return
    
    plt.figure(figsize=(12, 6))
    plt.plot(data_frame['date'], data_frame['count'], marker='o', linestyle='-', linewidth=2)
    
    # Add title and labels
    plt.title(title, fontsize=16)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel(y_label, fontsize=12)
    
    # Format the x-axis to show dates nicely
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    
    # Add grid and rotate date labels
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(rotation=45)
    
    # Add data points annotation
    for i, row in data_frame.iterrows():
        plt.annotate(
            f"{row['count']}",
            (row['date'], row['count']),
            textcoords="offset points",
            xytext=(0, 10),
            ha='center'
        )
    
    # Add current count in the corner
    if not data_frame.empty:
        latest_count = data_frame['count'].iloc[-1]
        plt.annotate(
            f"Latest Count: {latest_count}",
            xy=(0.02, 0.96),
            xycoords='axes fraction',
            fontsize=12,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8)
        )
    
    # Adjust layout and save
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(output_path, dpi=300)
    
    # Close the figure to prevent memory leaks
    plt.close()
    
    # Return summary
    return len(data_frame), latest_count if not data_frame.empty else 'N/A'

def main():
    """
    Main function to track relay count changes and generate charts.
    """
    # Change to the root directory of the project if necessary
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    os.chdir(root_dir)
    
    # Ensure the assets directory exists
    os.makedirs('assets', exist_ok=True)
    
    # Get commits that modified the nostr_relays.csv file
    bitchat_result = subprocess.run(
        ['git', 'log', '--format=%H', '-n', '70', '--', 'nostr_relays.csv'],
        capture_output=True, text=True
    )
    bitchat_commit_hashes = bitchat_result.stdout.strip().split('\n')
    
    # Get commits that modified the relay_discovery_results.json file
    total_result = subprocess.run(
        ['git', 'log', '--format=%H', '-n', '70', '--', 'relay_discovery_results.json'],
        capture_output=True, text=True
    )
    total_commit_hashes = total_result.stdout.strip().split('\n')
    
    # Collect BitChat relay data
    bitchat_data = []
    for commit_hash in bitchat_commit_hashes:
        if not commit_hash:
            continue
        date = extract_date_from_commit(commit_hash)
        count = get_relay_count(commit_hash)
        if date and count > 0:  # Only add valid entries
            bitchat_data.append({
                'date': date,
                'commit': commit_hash,
                'count': count
            })
    
    # Collect total relay data
    total_data = []
    for commit_hash in total_commit_hashes:
        if not commit_hash:
            continue
        date = extract_date_from_commit(commit_hash)
        count = get_total_relay_count(commit_hash)
        if date and count > 0:  # Only add valid entries
            total_data.append({
                'date': date,
                'commit': commit_hash,
                'count': count
            })
    
    # Create DataFrames and sort by date
    bitchat_df = pd.DataFrame(bitchat_data).sort_values('date') if bitchat_data else pd.DataFrame()
    total_df = pd.DataFrame(total_data).sort_values('date') if total_data else pd.DataFrame()
    
    # Create and save plots
    bitchat_stats = create_plot(
        bitchat_df, 
        'BitChat-Compatible Relay Count Over Time', 
        'Number of BitChat Relays', 
        'assets/bitchat_relay_count_chart.png'
    )
    
    total_stats = create_plot(
        total_df, 
        'Total Functioning Relay Count Over Time', 
        'Number of Functioning Relays', 
        'assets/total_relay_count_chart.png'
    )
    
    # Print summary for log
    if bitchat_stats:
        print(f"Generated BitChat relay chart with {bitchat_stats[0]} data points")
        print(f"Latest BitChat relay count: {bitchat_stats[1]}")
    
    if total_stats:
        print(f"Generated total relay chart with {total_stats[0]} data points")
        print(f"Latest total relay count: {total_stats[1]}")

if __name__ == "__main__":
    main()
