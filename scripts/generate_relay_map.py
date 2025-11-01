#!/usr/bin/env python3
"""
Generate World Map of Nostr Relay Locations

This script reads the nostr_relays.csv file, which contains information about
BitChat-compatible Nostr relays, including their geographical coordinates.
It generates both an interactive HTML map and a static PNG image showing
the distribution of relays around the world.

The maps are saved in the assets directory.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import folium
from folium.plugins import MarkerCluster
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
import time

def create_interactive_map(df, output_path):
    """
    Create an interactive HTML map showing relay locations with clustering.
    
    Args:
        df: DataFrame containing relay data with Latitude and Longitude columns
        output_path: Path to save the HTML map
    """
    # Create map centered at (0, 0) with zoom level 2
    world_map = folium.Map(location=[0, 0], zoom_start=2, tiles='CartoDB positron')
    
    # Add marker cluster
    marker_cluster = MarkerCluster().add_to(world_map)
    
    # Add markers for each relay
    for idx, row in df.iterrows():
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=row['Relay URL'],
            icon=folium.Icon(color='blue', icon='signal', prefix='fa')
        ).add_to(marker_cluster)
    
    # Save map
    world_map.save(output_path)
    
    return len(df)

def create_static_map(df, output_path):
    """
    Create a static PNG map showing relay locations on a proper world map.
    
    Args:
        df: DataFrame containing relay data with Latitude and Longitude columns
        output_path: Path to save the PNG map
    """
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    
    plt.figure(figsize=(15, 10))
    
    # Create a map with a proper projection
    ax = plt.axes(projection=ccrs.PlateCarree())
    
    # Add map features
    ax.add_feature(cfeature.LAND, facecolor='#E5E5E5')
    ax.add_feature(cfeature.OCEAN, facecolor='#DDEEFF')
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor='#999999')
    ax.add_feature(cfeature.BORDERS, linewidth=0.3, edgecolor='#AAAAAA')
    ax.add_feature(cfeature.LAKES, facecolor='#DDEEFF', edgecolor='#999999', linewidth=0.5)
    ax.add_feature(cfeature.RIVERS, edgecolor='#99CCFF', linewidth=0.5)
    
    # Add grid
    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                      linewidth=0.5, color='gray', alpha=0.5, linestyle='--')
    gl.top_labels = False
    gl.right_labels = False
    
    # Set map limits
    ax.set_extent([-180, 180, -90, 90], crs=ccrs.PlateCarree())
    
    # Plot relay locations
    plt.scatter(
        df['Longitude'], 
        df['Latitude'],
        alpha=0.8,
        c='blue',
        s=30,
        edgecolor='white',
        linewidth=0.5,
        transform=ccrs.PlateCarree()
    )
    
    # Add title and labels
    plt.title('Global Distribution of BitChat-Compatible Nostr Relays', fontsize=16)
    
    # Add timestamp
    timestamp = time.strftime("%Y-%m-%d", time.localtime())
    plt.annotate(
        f'Generated: {timestamp} | Total Relays: {len(df)}',
        xy=(0.02, 0.02),
        xycoords='axes fraction',
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8)
    )
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return len(df)

def create_heatmap(df, output_path):
    """
    Create a heatmap visualization showing relay density across the world.
    
    Args:
        df: DataFrame containing relay data with Latitude and Longitude columns
        output_path: Path to save the PNG heatmap
    """
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import gaussian_filter
    
    plt.figure(figsize=(15, 10))
    
    # Create a map with a proper projection
    ax = plt.axes(projection=ccrs.PlateCarree())
    
    # Add map features
    ax.add_feature(cfeature.LAND, facecolor='#E5E5E5')
    ax.add_feature(cfeature.OCEAN, facecolor='#DDEEFF')
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor='#999999')
    ax.add_feature(cfeature.BORDERS, linewidth=0.3, edgecolor='#AAAAAA')
    
    # Add grid
    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                      linewidth=0.5, color='gray', alpha=0.5, linestyle='--')
    gl.top_labels = False
    gl.right_labels = False
    
    # Set map limits
    ax.set_extent([-180, 180, -90, 90], crs=ccrs.PlateCarree())
    
    # Create grid for heatmap
    x = np.linspace(-180, 180, 360)
    y = np.linspace(-90, 90, 180)
    
    # Count relays in each grid cell
    heatmap = np.zeros((len(y)-1, len(x)-1))
    
    for _, row in df.iterrows():
        lon_idx = np.searchsorted(x, row['Longitude']) - 1
        lat_idx = np.searchsorted(y, row['Latitude']) - 1
        
        if 0 <= lon_idx < len(x)-1 and 0 <= lat_idx < len(y)-1:
            heatmap[lat_idx, lon_idx] += 1
    
    # Apply Gaussian smoothing to heatmap
    heatmap = gaussian_filter(heatmap, sigma=3)
    
    # Create custom colormap (blue to white)
    colors = [(0, 0, 0.8, 0), (0, 0, 1, 0.7), (0.5, 0.5, 1, 0.8), (1, 1, 1, 0.9)]
    cmap = LinearSegmentedColormap.from_list('custom_blue', colors)
    
    # Plot heatmap
    plt.pcolormesh(x, y, heatmap, cmap=cmap, alpha=0.7, transform=ccrs.PlateCarree())
    
    # Add title
    plt.title('Global Heatmap of BitChat-Compatible Nostr Relays', fontsize=16)
    
    # Add timestamp and relay count
    timestamp = time.strftime("%Y-%m-%d", time.localtime())
    plt.annotate(
        f'Generated: {timestamp} | Total Relays: {len(df)}',
        xy=(0.02, 0.02),
        xycoords='axes fraction',
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8)
    )
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return len(df)

def main():
    """
    Main function to generate maps of relay locations.
    """
    # Change to the root directory of the project
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    os.chdir(root_dir)
    
    # Ensure the assets directory exists
    os.makedirs('assets', exist_ok=True)
    
    try:
        # Read the relay data
        df = pd.read_csv('nostr_relays.csv')
        
        # Filter out rows with missing or invalid coordinates
        df = df.dropna(subset=['Latitude', 'Longitude'])
        
        # Filter out invalid coordinates
        df = df[(df['Latitude'] >= -90) & (df['Latitude'] <= 90) & 
                (df['Longitude'] >= -180) & (df['Longitude'] <= 180)]
        
        # Generate maps
        # 1. Interactive HTML map
        relay_count_interactive = create_interactive_map(
            df,
            'assets/relay_locations_interactive.html'
        )
        
        # 2. Static PNG map
        try:
            relay_count_static = create_static_map(
                df,
                'assets/relay_locations_static.png'
            )
        except Exception as e:
            print(f"Error creating static map: {e}")
            relay_count_static = 0
        
        # 3. Heatmap
        try:
            from scipy.ndimage import gaussian_filter
            relay_count_heatmap = create_heatmap(
                df,
                'assets/relay_locations_heatmap.png'
            )
        except ImportError:
            print("Could not create heatmap: scipy not installed")
            relay_count_heatmap = 0
            
        # Print summary
        print(f"Generated interactive map with {relay_count_interactive} relays")
        if relay_count_static > 0:
            print(f"Generated static map with {relay_count_static} relays")
        if relay_count_heatmap > 0:
            print(f"Generated heatmap with {relay_count_heatmap} relays")
            
    except Exception as e:
        print(f"Error generating relay maps: {e}")

if __name__ == "__main__":
    main()
