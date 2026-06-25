import geopandas as gpd
import pandas as pd
import os
import time

def main():
    t0 = time.time()
    gpkg_path = "data/gadm41_IDN.gpkg"
    if not os.path.exists(gpkg_path):
        print(f"Error: {gpkg_path} not found.")
        return

    print("Loading GADM ADM_ADM_3 layer...")
    gdf = gpd.read_file(gpkg_path, layer="ADM_ADM_3")
    print(f"Loaded in {time.time() - t0:.1f}s")
    
    # Filter for Banten and neighbors
    banten = gdf[gdf["NAME_1"] == "Banten"].copy()
    neighbors = gdf[gdf["NAME_1"].isin(["Banten", "Jawa Barat", "Jakarta Raya", "Dki Jakarta"])].copy()
    print(f"Total kecamatan in Banten: {len(banten)}")
    print(f"Total features in neighbors: {len(neighbors)}")
    
    # Project to UTM 48S (EPSG:32748) for accurate buffering in meters
    print("Projecting to UTM 48S...")
    banten_utm = banten.to_crs(epsg=32748)
    neighbors_utm = neighbors.to_crs(epsg=32748)
    
    # Create a unified land geometry for Banten & neighbors
    print("Creating union of land geometry...")
    t_union = time.time()
    land_utm = neighbors_utm.union_all()
    print(f"Union created in {time.time() - t_union:.1f}s")
    
    coastal_kecamatans = []
    
    print("Determining coastal water zones for each kecamatan...")
    for idx, row in banten_utm.iterrows():
        geom = row.geometry
        name_3 = row["NAME_3"]
        name_2 = row["NAME_2"]
        
        # Buffer by 3000 meters (3 km)
        buffered = geom.buffer(3000)
        
        # Subtract the land to get the water zone
        water_zone = buffered.difference(land_utm)
        
        # If the water zone is not empty and has a significant area (e.g. > 10 ha or 100,000 m2)
        water_area_ha = water_zone.area / 10000.0
        
        if water_area_ha > 10.0: # more than 10 hectares of water
            coastal_kecamatans.append({
                "Kabupaten_Kota": name_2,
                "Kecamatan": name_3,
                "Water_Area_Ha": water_area_ha
            })
            
    df_coastal = pd.DataFrame(coastal_kecamatans)
    print(f"Total coastal kecamatans: {len(df_coastal)}")
    print(df_coastal.sort_values(by="Water_Area_Ha", ascending=False).head(20))
    print(f"Total script run time: {time.time() - t0:.1f}s")

if __name__ == "__main__":
    main()
