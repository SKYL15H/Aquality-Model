import os
import openeo

def main():
    print("Connecting to OpenEO...")
    connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
    
    # Authenticate (this will prompt the device code flow)
    print("Authenticating...")
    connection.authenticate_oidc()
    
    print("Creating data cube for tiny Bali bbox...")
    # Bbox around Denpasar/Sanur beach area
    bbox = {
        "west": 115.22,
        "south": -8.68,
        "east": 115.27,
        "north": -8.63,
        "crs": "EPSG:4326"
    }
    
    cube = connection.load_collection(
        "SENTINEL2_L2A",
        spatial_extent=bbox,
        temporal_extent=["2023-07-01", "2023-08-31"],
        bands=["B02", "B03", "B04", "B08", "B11", "B12", "SCL"]
    )
    
    # Apply cloud masking using SCL (exclude classes 1, 3, 8, 9, 10, 11)
    scl = cube.band("SCL")
    mask = ~((scl == 1) | (scl == 3) | (scl == 8) | (scl == 9) | (scl == 10) | (scl == 11))
    masked_cube = cube.mask(mask)
    
    # Median composite
    composite = masked_cube.reduce_dimension(reducer="median", dimension="t")
    
    # Resample to 30m resolution for fast download
    resampled = composite.resample_spatial(resolution=30.0, projection=4326, method="bilinear")
    
    # We only want spectral bands (remove SCL from output)
    output_cube = resampled.filter_bands(["B02", "B03", "B04", "B08", "B11", "B12"])
    
    # Save as GeoTIFF
    output_cube = output_cube.save_result("GTiff")
    
    print("Downloading result synchronously...")
    dest = "data/bali_tiny_test.tif"
    output_cube.download(dest)
    print(f"Success! Downloaded to {dest}")
    
    # Check downloaded file metadata
    import rasterio
    with rasterio.open(dest) as src:
        print("\nDownloaded File Metadata:")
        print(src.meta)
        print("Bands:", src.indexes)

if __name__ == "__main__":
    main()
