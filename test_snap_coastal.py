import json
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import nearest_points

print("Loading GADM data...")
gdf = gpd.read_file("data/gadm41_IDN.gpkg", layer="ADM_ADM_3")
banten = gdf[gdf["NAME_1"] == "Banten"].to_crs("EPSG:4326")

# Combined coastline / land boundary
banten_land = banten.union_all()
banten_boundary = banten_land.boundary

with open("output/banten_water_quality_beach.json", "r", encoding="utf-8") as f:
    beaches = json.load(f)

# Special overrides for specific beaches that are islands or specific known POIs
# Island beaches or specific POIs where GADM boundary might differ:
# Pantai Sangiang: Sangiang Island (-5.9535, 105.8565 - wait, Sangiang is an island in Sunda Strait!)
# Pantai Pulau Umang: Umang Island (-6.64065, 105.58436 - island in Sumur!)
# Pantai Pulau Merak Kecil: (-5.9388, 105.9948 - island!)
# Pantai Pulau Merak Besar: (-5.9308, 105.9868 - island!)
ISLAND_BEACHES = {
    "Pantai Sangiang": (-5.9535, 105.8565),
    "Pantai Pulau Umang": (-6.64065, 105.58436),
    "Pantai Pulau Merak Kecil": (-5.9388, 105.9948),
    "Pantai Pulau Merak Besar": (-5.9308, 105.9868),
    "Pantai Pulau Cangkir": (-6.0025, 106.4190), # Pulau Cangkir island/peninsula tip
}

# Known exact POI adjustments:
# Pantai Ciputih: Sumur coast near Resort (-6.6660, 105.5170)
# Pantai Anyer: -6.0465, 105.8850 -> snapped
# Pantai Carita: -6.1305, 105.8427 -> snapped
# Pantai Batu Hideung: -6.5185, 105.6310 -> snapped
# Pantai Lalassa: -6.4832, 105.6442 -> snapped
# Pantai Cipenyu: -6.4915, 105.6415 -> snapped
# Pantai Tanjung Burung: -6.0020, 106.6540 -> snapped
# Pantai Dadap: -6.0520, 106.7025 -> snapped

snapped_coords = {}

print("\nSnapping all beaches to exact coastline:")
print("-" * 80)
for name, item in beaches.items():
    if name in ISLAND_BEACHES:
        new_lat, new_lon = ISLAND_BEACHES[name]
        print(f"[ISLAND] {name:28s} -> lat: {new_lat:9.5f}, lon: {new_lon:9.5f}")
    else:
        orig_lat = item.get("latitude")
        orig_lon = item.get("longitude")
        pt = Point(orig_lon, orig_lat)
        
        # Find nearest point on Banten main coastline
        nearest_pt = nearest_points(banten_boundary, pt)[0]
        new_lon = round(nearest_pt.x, 5)
        new_lat = round(nearest_pt.y, 5)
        
        # Calculate shift
        shift_km = pt.distance(nearest_pt) * 111.0
        print(f"[COAST]  {name:28s} -> lat: {new_lat:9.5f}, lon: {new_lon:9.5f} (shifted {shift_km:5.2f} km)")
        
    snapped_coords[name] = (new_lat, new_lon)

print("-" * 80)
