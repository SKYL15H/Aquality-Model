import os
import numpy as np
import geopandas as gpd
import rasterio
import rasterio.mask
from rasterio.merge import merge
import tempfile

def get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    lon_start = int(np.floor(min_lon))
    lon_end = int(np.floor(max_lon))
    lat_start = int(np.floor(min_lat))
    lat_end = int(np.floor(max_lat))
    
    tiles = []
    for lon in range(lon_start, lon_end + 1):
        for lat_cell in range(lat_start, lat_end + 1):
            top_lat = lat_cell + 1
            if top_lat > 0:
                lat_str = f"N{top_lat:02d}"
            elif top_lat == 0:
                lat_str = "N00"
            else:
                lat_str = f"S{abs(top_lat):02d}"
                
            if lon >= 0:
                lon_str = f"E{lon:03d}"
            else:
                lon_str = f"W{abs(lon):03d}"
                
            tile_name = f"GMW_{lat_str}{lon_str}_2020_v3.tif"
            tiles.append(tile_name)
    return tiles

def get_mangrove_mask(gadm_path, province_name, tile_dir):
    gdf = gpd.read_file(gadm_path, layer='ADM_ADM_1')
    prov = gdf[gdf['NAME_1'] == province_name]
    if prov.empty:
        raise ValueError(f"Province {province_name} not found in GADM")
    
    geom = prov.geometry.values[0]
    bbox = geom.bounds  # (minx, miny, maxx, maxy)
    
    tile_names = get_tiles_for_bbox(*bbox)
    tile_paths = []
    for t in tile_names:
        p = os.path.join(tile_dir, t)
        if os.path.exists(p):
            tile_paths.append(p)
            
    if not tile_paths:
        print("No mangrove tiles found for bbox")
        return None, None
        
    print(f"Loading and merging {len(tile_paths)} tiles: {[os.path.basename(p) for p in tile_paths]}")
    srcs = [rasterio.open(p) for p in tile_paths]
    
    # Merge tiles
    mosaic, out_trans = merge(srcs)
    
    # Copy metadata from the first source
    out_meta = srcs[0].meta.copy()
    out_meta.update({
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_trans
    })
    
    for s in srcs:
        s.close()
        
    # Crop to geometry
    # We can write mosaic to a temporary in-memory file or a temp file on disk to crop using rasterio.mask
    # In-memory file is faster and cleaner!
    from rasterio.io import MemoryFile
    with MemoryFile() as memfile:
        with memfile.open(**out_meta) as dataset:
            dataset.write(mosaic)
            # Crop
            out_image, out_transform = rasterio.mask.mask(dataset, [geom], crop=True)
            out_meta_cropped = dataset.meta.copy()
            out_meta_cropped.update({
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform
            })
            
    return out_image[0], out_meta_cropped

def main():
    gadm_path = "data/gadm41_IDN.gpkg"
    tile_dir = "data/gmw_v3_2020_gtiff/gmw_v3_2020"
    province = "Bali"
    
    mask, meta = get_mangrove_mask(gadm_path, province, tile_dir)
    if mask is not None:
        print(f"Mask cropped successfully for {province}!")
        print(f"Shape: {mask.shape}")
        print(f"Unique values in mask: {np.unique(mask)}")
        print(f"Total mangrove pixels (DN=1): {np.sum(mask == 1)}")
        pixel_area_ha = (25 * 25) / 10000.0  # GMW is ~25m resolution
        print(f"Estimated mangrove area: {np.sum(mask == 1) * pixel_area_ha:.2f} ha")
    else:
        print("Failed to crop mask")

if __name__ == "__main__":
    main()
