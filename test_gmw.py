import os
import glob
import rasterio

tile_dir = r"data/gmw_v3_2020_gtiff/gmw_v3_2020"
all_tifs = glob.glob(os.path.join(tile_dir, "*.tif"))
print(f"Total tiles: {len(all_tifs)}")

# Check metadata of one tile
test_tile = all_tifs[0]
print(f"\nMetadata for {os.path.basename(test_tile)}:")
with rasterio.open(test_tile) as src:
    print(src.meta)
    print(src.bounds)
