import geopandas as gpd
import fiona

gpkg_path = "data/gadm41_IDN.gpkg"
# List layers
layers = fiona.listlayers(gpkg_path)
print("Layers in geopackage:", layers)

# Read level 1 (provinces)
# In GADM 4.1 gpkg, the layer names are usually 'ADM_ADM_1' or 'IDN_1' or similar.
# Let's find layer that matches level 1
lvl1_layer = [l for l in layers if '1' in l]
print("Matching level 1 layers:", lvl1_layer)

if lvl1_layer:
    gdf = gpd.read_file(gpkg_path, layer=lvl1_layer[0])
    print(f"Columns: {gdf.columns.tolist()}")
    print(f"Total features: {len(gdf)}")
    print(f"First few provinces: {gdf['NAME_1'].head(10).tolist()}")
