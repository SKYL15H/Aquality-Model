import json
import math
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
BEACH_JSON = os.path.join(OUTPUT_DIR, "banten_water_quality_beach.json")
GEOJSON_PATH = os.path.join(OUTPUT_DIR, "banten_coastal_beaches.geojson")

BEACH = {
    "Pantai": "Pantai Pulau Merak Besar",
    "Kecamatan": "Pulomerak",
    "Kabupaten_Kota": "Cilegon",
    "desa": "Tamansari",
    "kode_adm4": "36.72.03.1001",
    "latitude": -5.9339,
    "longitude": 105.9896,
}

def generate_slug(name):
    slug = name.lower().strip()
    slug = "".join(c if c.isalnum() or c in " -" else "" for c in slug)
    return slug.replace(" ", "-").replace("--", "-")

def generate_circle_polygon(lat, lon, radius_km=1.0, n_points=17):
    R = 6371.0
    coords = []
    for i in range(n_points):
        angle = 2 * math.pi * i / (n_points - 1) if n_points > 1 else 0
        dlat = (radius_km / R) * math.cos(angle)
        dlon = (radius_km / (R * math.cos(math.radians(lat)))) * math.sin(angle)
        new_lat = lat + math.degrees(dlat)
        new_lon = lon + math.degrees(dlon)
        coords.append([round(new_lon, 12), round(new_lat, 12)])
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return [coords]

# --- JSON ---
with open(BEACH_JSON, "r", encoding="utf-8") as f:
    beach_data = json.load(f)

name = BEACH["Pantai"]
if name in beach_data:
    print(f"SKIP: {name} sudah ada di JSON")
else:
    beach_data[name] = {
        "Kecamatan": BEACH["Kecamatan"],
        "Kabupaten_Kota": BEACH["Kabupaten_Kota"],
        "url_gambar": "",
        "latitude": BEACH["latitude"],
        "longitude": BEACH["longitude"],
        "slug": generate_slug(name),
        "Pantai": name,
        "desa": BEACH["desa"],
        "kode_adm4": BEACH["kode_adm4"],
    }
    with open(BEACH_JSON, "w", encoding="utf-8") as f:
        json.dump(beach_data, f, indent=2, ensure_ascii=False)
    print(f"ADDED JSON: {name} (total: {len(beach_data)})")

# --- GeoJSON ---
with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
    geojson = json.load(f)

existing_names = {feat["properties"]["Pantai"] for feat in geojson["features"]}
if name in existing_names:
    print(f"SKIP: {name} sudah ada di GeoJSON")
else:
    coords = generate_circle_polygon(BEACH["latitude"], BEACH["longitude"])
    geojson["features"].append({
        "type": "Feature",
        "properties": {
            "Pantai": name,
            "Kecamatan": BEACH["Kecamatan"],
            "Kabupaten_Kota": BEACH["Kabupaten_Kota"],
            "latitude": BEACH["latitude"],
            "longitude": BEACH["longitude"],
        },
        "geometry": {"type": "Polygon", "coordinates": coords},
    })
    with open(GEOJSON_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)
    print(f"ADDED GeoJSON: {name} (total: {len(geojson['features'])})")
