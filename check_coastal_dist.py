import json
import geopandas as gpd
from shapely.geometry import Point

print("Loading GADM data...")
gdf = gpd.read_file("data/gadm41_IDN.gpkg", layer="ADM_ADM_3")
banten = gdf[gdf["NAME_1"] == "Banten"].to_crs("EPSG:4326")

# Combined coastline / land boundary
banten_land = banten.unary_union
banten_boundary = banten_land.boundary

with open("output/banten_water_quality_beach.json", "r", encoding="utf-8") as f:
    beaches = json.load(f)

print(f"\nChecking {len(beaches)} beaches against GADM Banten land boundary:")
print("-" * 85)
print(f"{'Nama Pantai':30s} | {'Latitude':9s} | {'Longitude':9s} | {'Inside Land?':12s} | {'Dist to Coast (km)':18s}")
print("-" * 85)

for name, item in beaches.items():
    lat = item.get("latitude")
    lon = item.get("longitude")
    pt = Point(lon, lat)
    is_inside = banten_land.contains(pt)
    
    # Distance in degrees approx to km (1 deg ~ 111 km)
    dist_deg = banten_boundary.distance(pt)
    dist_km = dist_deg * 111.0
    
    status = "INLAND" if is_inside else "IN SEA"
    print(f"{name:30s} | {lat:9.5f} | {lon:9.5f} | {status:12s} | {dist_km:18.3f}")
