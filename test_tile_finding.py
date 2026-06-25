import os
import numpy as np

def get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    lon_start = int(np.floor(min_lon))
    lon_end = int(np.floor(max_lon))
    
    lat_start = int(np.floor(min_lat))
    lat_end = int(np.floor(max_lat))
    
    tiles = []
    for lon in range(lon_start, lon_end + 1):
        for lat_cell in range(lat_start, lat_end + 1):
            # For each 1-degree cell, the top-left latitude is lat_cell + 1
            top_lat = lat_cell + 1
            
            # Format top_lat
            if top_lat > 0:
                lat_str = f"N{top_lat:02d}"
            elif top_lat == 0:
                lat_str = "N00"
            else:
                lat_str = f"S{abs(top_lat):02d}"
                
            # Format lon
            if lon >= 0:
                lon_str = f"E{lon:03d}"
            else:
                lon_str = f"W{abs(lon):03d}"
                
            tile_name = f"GMW_{lat_str}{lon_str}_2020_v3.tif"
            tiles.append(tile_name)
    return tiles

# Test for Bali bounding box: Lon [114.4, 115.7], Lat [-8.9, -8.0]
bali_tiles = get_tiles_for_bbox(114.4, -8.9, 115.7, -8.0)
print("Bali Tiles:")
for t in bali_tiles:
    path = os.path.join("data/gmw_v3_2020_gtiff/gmw_v3_2020", t)
    exists = os.path.exists(path)
    print(f"  {t} - exists: {exists}")
