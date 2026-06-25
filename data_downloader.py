import os
import urllib.request
import zipfile
import ssl

def download_file(url, filepath):
    print(f"Downloading {url} to {filepath}...")
    # Bypass SSL verification if needed (sometimes geodata or zenodo has certificate issues on Windows)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    with urllib.request.urlopen(url, context=ctx) as response, open(filepath, 'wb') as out_file:
        data = response.read()
        out_file.write(data)
    print(f"Finished downloading {filepath}")

def main():
    os.makedirs('data', exist_ok=True)
    
    # 1. GADM Indonesia GeoPackage
    gadm_url = "https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_IDN.gpkg"
    gadm_dest = "data/gadm41_IDN.gpkg"
    if not os.path.exists(gadm_dest):
        try:
            download_file(gadm_url, gadm_dest)
        except Exception as e:
            print(f"Error downloading GADM from primary URL: {e}")
            print("Trying shapefile ZIP fallback...")
            # Fallback to shapefile ZIP if geopackage download fails
            gadm_zip_url = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_IDN_shp.zip"
            gadm_zip_dest = "data/gadm41_IDN_shp.zip"
            download_file(gadm_zip_url, gadm_zip_dest)
            print("Extracting GADM shapefiles...")
            with zipfile.ZipFile(gadm_zip_dest, 'r') as zip_ref:
                zip_ref.extractall("data/gadm41_IDN_shp")
            print("GADM shapefiles extracted to data/gadm41_IDN_shp/")
    else:
        print("GADM boundary file already exists.")

    # 2. Global Mangrove Watch 2020 GeoTIFF
    gmw_url = "https://zenodo.org/records/6894273/files/gmw_v3_2020_gtiff.zip?download=1"
    gmw_zip_dest = "data/gmw_v3_2020_gtiff.zip"
    gmw_extracted_dir = "data/gmw_v3_2020_gtiff"
    
    if not os.path.exists(gmw_zip_dest) and not os.path.exists(gmw_extracted_dir):
        try:
            download_file(gmw_url, gmw_zip_dest)
            print("Extracting GMW 2020 GeoTIFF zip...")
            with zipfile.ZipFile(gmw_zip_dest, 'r') as zip_ref:
                zip_ref.extractall(gmw_extracted_dir)
            print(f"GMW 2020 GeoTIFF extracted to {gmw_extracted_dir}/")
        except Exception as e:
            print(f"Error downloading or extracting GMW: {e}")
    else:
        print("GMW 2020 GeoTIFF already exists or is extracted.")

if __name__ == "__main__":
    main()
