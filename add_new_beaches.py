"""
add_new_beaches.py — Menambahkan 25 pantai baru ke dataset Banten

Menambahkan data dasar pantai (koordinat, kecamatan, kode_adm4, slug, dll).
Field industri akan dihitung oleh compute_industry_distance.py.
"""

import json
import math
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
BEACH_JSON = os.path.join(OUTPUT_DIR, "banten_water_quality_beach.json")
GEOJSON_PATH = os.path.join(OUTPUT_DIR, "banten_coastal_beaches.geojson")

# ---------------------------------------------------------------------------
# 25 Pantai Baru
# ---------------------------------------------------------------------------

NEW_BEACHES = [
    # === PANDEGLANG (7) ===
    {
        "Pantai": "Pantai Batu Hideung",
        "Kecamatan": "Panimbang",
        "Kabupaten_Kota": "Pandeglang",
        "desa": "Tanjungjaya",
        "kode_adm4": "36.01.06.2012",
        "latitude": -6.8131,
        "longitude": 105.6500,
    },
    {
        "Pantai": "Pantai Lalassa",
        "Kecamatan": "Panimbang",
        "Kabupaten_Kota": "Pandeglang",
        "desa": "Tanjungjaya",
        "kode_adm4": "36.01.06.2012",
        "latitude": -6.8072,
        "longitude": 105.6417,
    },
    {
        "Pantai": "Pantai Cipenyu",
        "Kecamatan": "Panimbang",
        "Kabupaten_Kota": "Pandeglang",
        "desa": "Tanjungjaya",
        "kode_adm4": "36.01.06.2012",
        "latitude": -6.8000,
        "longitude": 105.6350,
    },
    {
        "Pantai": "Pantai Pandan Carita",
        "Kecamatan": "Carita",
        "Kabupaten_Kota": "Pandeglang",
        "desa": "Sukajadi",
        "kode_adm4": "36.01.28.2007",
        "latitude": -6.1250,
        "longitude": 105.8380,
    },
    {
        "Pantai": "Pantai Labuan",
        "Kecamatan": "Labuan",
        "Kabupaten_Kota": "Pandeglang",
        "desa": "Teluk",
        "kode_adm4": "36.01.12.2010",
        "latitude": -6.3720,
        "longitude": 105.8100,
    },
    {
        "Pantai": "Pantai Teluk Lada",
        "Kecamatan": "Sobang",
        "Kabupaten_Kota": "Pandeglang",
        "desa": "Teluklada",
        "kode_adm4": "36.01.35.2002",
        "latitude": -6.5290,
        "longitude": 105.8170,
    },
    {
        "Pantai": "Pantai Ujung Kulon",
        "Kecamatan": "Sumur",
        "Kabupaten_Kota": "Pandeglang",
        "desa": "Tamanjaya",
        "kode_adm4": "36.01.01.2006",
        "latitude": -6.7100,
        "longitude": 105.3350,
    },
    # === LEBAK (8) ===
    {
        "Pantai": "Pantai Ciantir",
        "Kecamatan": "Bayah",
        "Kabupaten_Kota": "Lebak",
        "desa": "Sawarna",
        "kode_adm4": "36.02.03.2002",
        "latitude": -6.9800,
        "longitude": 106.2900,
    },
    {
        "Pantai": "Pantai Legon Pari",
        "Kecamatan": "Bayah",
        "Kabupaten_Kota": "Lebak",
        "desa": "Sawarna",
        "kode_adm4": "36.02.03.2002",
        "latitude": -6.9670,
        "longitude": 106.2960,
    },
    {
        "Pantai": "Pantai Pulo Manuk",
        "Kecamatan": "Bayah",
        "Kabupaten_Kota": "Lebak",
        "desa": "Sawarna",
        "kode_adm4": "36.02.03.2002",
        "latitude": -6.9890,
        "longitude": 106.3050,
    },
    {
        "Pantai": "Pantai Goa Langir",
        "Kecamatan": "Bayah",
        "Kabupaten_Kota": "Lebak",
        "desa": "Sawarna",
        "kode_adm4": "36.02.03.2002",
        "latitude": -6.9880,
        "longitude": 106.3150,
    },
    {
        "Pantai": "Pantai Cibobos",
        "Kecamatan": "Cihara",
        "Kabupaten_Kota": "Lebak",
        "desa": "Karangkamulyan",
        "kode_adm4": "36.02.26.2008",
        "latitude": -6.8900,
        "longitude": 106.1050,
    },
    {
        "Pantai": "Pantai Citarate",
        "Kecamatan": "Cilograng",
        "Kabupaten_Kota": "Lebak",
        "desa": "Cibareno",
        "kode_adm4": "36.02.20.2002",
        "latitude": -6.9650,
        "longitude": 106.3800,
    },
    {
        "Pantai": "Pantai Cibareno",
        "Kecamatan": "Cilograng",
        "Kabupaten_Kota": "Lebak",
        "desa": "Cibareno",
        "kode_adm4": "36.02.20.2002",
        "latitude": -6.9550,
        "longitude": 106.3900,
    },
    {
        "Pantai": "Pantai Panggarangan",
        "Kecamatan": "Panggarangan",
        "Kabupaten_Kota": "Lebak",
        "desa": "Panggarangan",
        "kode_adm4": "36.02.02.2002",
        "latitude": -6.8500,
        "longitude": 106.1700,
    },
    # === SERANG (5) ===
    {
        "Pantai": "Pantai Marina",
        "Kecamatan": "Cinangka",
        "Kabupaten_Kota": "Serang",
        "desa": "Karangsuraga",
        "kode_adm4": "36.04.31.2005",
        "latitude": -6.1454,
        "longitude": 105.8530,
    },
    {
        "Pantai": "Pantai Batu Saung",
        "Kecamatan": "Cinangka",
        "Kabupaten_Kota": "Serang",
        "desa": "Cinangka",
        "kode_adm4": "36.04.31.2001",
        "latitude": -6.1258,
        "longitude": 105.8383,
    },
    {
        "Pantai": "Pantai Karang Pamulang",
        "Kecamatan": "Bojonegara",
        "Kabupaten_Kota": "Serang",
        "desa": "Bojonegara",
        "kode_adm4": "36.04.07.2001",
        "latitude": -6.0120,
        "longitude": 105.9650,
    },
    {
        "Pantai": "Pantai Pontang",
        "Kecamatan": "Pontang",
        "Kabupaten_Kota": "Serang",
        "desa": "Pontang",
        "kode_adm4": "36.04.12.2001",
        "latitude": -5.9850,
        "longitude": 106.2100,
    },
    {
        "Pantai": "Pantai Tanara",
        "Kecamatan": "Tanara",
        "Kabupaten_Kota": "Serang",
        "desa": "Tanara",
        "kode_adm4": "36.04.14.2001",
        "latitude": -5.9750,
        "longitude": 106.2500,
    },
    # === TANGERANG (3) ===
    {
        "Pantai": "Pantai Tanjung Burung",
        "Kecamatan": "Teluknaga",
        "Kabupaten_Kota": "Tangerang",
        "desa": "Tanjung Burung",
        "kode_adm4": "36.03.13.2012",
        "latitude": -6.0670,
        "longitude": 106.6670,
    },
    {
        "Pantai": "Pantai Dadap",
        "Kecamatan": "Kosambi",
        "Kabupaten_Kota": "Tangerang",
        "desa": "Dadap",
        "kode_adm4": "36.03.14.1010",
        "latitude": -6.0870,
        "longitude": 106.7030,
    },
    {
        "Pantai": "Pantai Pakuhaji",
        "Kecamatan": "Pakuhaji",
        "Kabupaten_Kota": "Tangerang",
        "desa": "Pakuhaji",
        "kode_adm4": "36.03.15.1001",
        "latitude": -6.0350,
        "longitude": 106.5600,
    },
    # === CILEGON (2) ===
    {
        "Pantai": "Pantai Pulorida",
        "Kecamatan": "Pulomerak",
        "Kabupaten_Kota": "Cilegon",
        "desa": "Tamansari",
        "kode_adm4": "36.72.03.1001",
        "latitude": -5.9320,
        "longitude": 105.9850,
    },
    {
        "Pantai": "Pantai Pulau Merak Kecil",
        "Kecamatan": "Pulomerak",
        "Kabupaten_Kota": "Cilegon",
        "desa": "Mekarsari",
        "kode_adm4": "36.72.03.1003",
        "latitude": -5.9417,
        "longitude": 105.9970,
    },
]


def generate_slug(name: str) -> str:
    """Generate URL-friendly slug from beach name."""
    slug = name.lower().strip()
    slug = "".join(c if c.isalnum() or c in " -" else "" for c in slug)
    slug = slug.replace(" ", "-").replace("--", "-")
    return slug


def generate_circle_polygon(lat: float, lon: float, radius_km: float = 1.0, n_points: int = 17):
    """Generate a circular polygon (GeoJSON coordinates) around a center point.
    
    This matches the approach used for existing beaches in the GeoJSON.
    """
    R = 6371.0  # Earth radius km
    coords = []
    for i in range(n_points):
        angle = 2 * math.pi * i / (n_points - 1) if n_points > 1 else 0
        dlat = (radius_km / R) * math.cos(angle)
        dlon = (radius_km / (R * math.cos(math.radians(lat)))) * math.sin(angle)
        new_lat = lat + math.degrees(dlat)
        new_lon = lon + math.degrees(dlon)
        coords.append([round(new_lon, 12), round(new_lat, 12)])
    # Close the ring
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return [coords]


def add_beaches_to_json():
    """Add new beaches to the main beach JSON file."""
    print(f"Membaca: {BEACH_JSON}")
    with open(BEACH_JSON, "r", encoding="utf-8") as f:
        beach_data = json.load(f)

    existing_count = len(beach_data)
    print(f"  -> {existing_count} pantai existing")

    added = 0
    for beach in NEW_BEACHES:
        name = beach["Pantai"]
        if name in beach_data:
            print(f"  SKIP: {name} sudah ada")
            continue

        slug = generate_slug(name)
        entry = {
            "Kecamatan": beach["Kecamatan"],
            "Kabupaten_Kota": beach["Kabupaten_Kota"],
            "url_gambar": "",
            "latitude": beach["latitude"],
            "longitude": beach["longitude"],
            "slug": slug,
            "Pantai": name,
            "desa": beach["desa"],
            "kode_adm4": beach["kode_adm4"],
        }
        beach_data[name] = entry
        added += 1
        print(f"  ADDED: {name} ({beach['Kecamatan']}, {beach['Kabupaten_Kota']})")

    # Save
    with open(BEACH_JSON, "w", encoding="utf-8") as f:
        json.dump(beach_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n  -> {added} pantai ditambahkan (total: {len(beach_data)})")
    print(f"  -> Disimpan ke: {BEACH_JSON}")
    return beach_data


def add_beaches_to_geojson():
    """Add new beaches to the GeoJSON file with circular polygon geometry."""
    print(f"\nMembaca GeoJSON: {GEOJSON_PATH}")
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        geojson = json.load(f)

    existing_names = {f["properties"]["Pantai"] for f in geojson["features"]}
    existing_count = len(geojson["features"])
    print(f"  -> {existing_count} features existing")

    added = 0
    for beach in NEW_BEACHES:
        name = beach["Pantai"]
        if name in existing_names:
            print(f"  SKIP GeoJSON: {name}")
            continue

        coords = generate_circle_polygon(beach["latitude"], beach["longitude"], radius_km=1.0)
        feature = {
            "type": "Feature",
            "properties": {
                "Pantai": name,
                "Kecamatan": beach["Kecamatan"],
                "Kabupaten_Kota": beach["Kabupaten_Kota"],
                "latitude": beach["latitude"],
                "longitude": beach["longitude"],
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": coords,
            },
        }
        geojson["features"].append(feature)
        added += 1
        print(f"  ADDED GeoJSON: {name}")

    # Save
    with open(GEOJSON_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)

    print(f"\n  -> {added} features ditambahkan (total: {len(geojson['features'])})")
    print(f"  -> Disimpan ke: {GEOJSON_PATH}")


if __name__ == "__main__":
    print("=" * 60)
    print("MENAMBAHKAN 25 PANTAI BARU KE DATASET BANTEN")
    print("=" * 60)
    
    add_beaches_to_json()
    add_beaches_to_geojson()
    
    print("\n" + "=" * 60)
    print("SELESAI! Jalankan compute_industry_distance.py untuk menghitung metrik.")
    print("=" * 60)
