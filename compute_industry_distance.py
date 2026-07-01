"""
compute_industry_distance.py — Kalkulasi Jarak Industri/Pabrik ke Pesisir

Menghitung jarak Haversine dari setiap kecamatan pesisir dan pantai di Banten
ke industri/pabrik terdekat. Mengupdate file JSON dan CSV output.

Usage:
    python compute_industry_distance.py
"""

import json
import math
import csv
import os

# ---------------------------------------------------------------------------
# Data Industri/Pabrik Besar di Banten
# ---------------------------------------------------------------------------

INDUSTRIES = [
    {
        "nama": "PT Krakatau Steel",
        "tipe": "Baja/Logam",
        "latitude": -6.0048,
        "longitude": 106.0148
    },
    {
        "nama": "PT Chandra Asri Petrochemical",
        "tipe": "Petrokimia",
        "latitude": -6.0200,
        "longitude": 106.0050
    },
    {
        "nama": "PT Asahimas Chemical",
        "tipe": "Kimia",
        "latitude": -6.0120,
        "longitude": 106.0200
    },
    {
        "nama": "PLTU Suralaya",
        "tipe": "Pembangkit Listrik",
        "latitude": -5.9320,
        "longitude": 105.9440
    },
    {
        "nama": "PT Indah Kiat Pulp & Paper (Merak)",
        "tipe": "Pulp & Paper",
        "latitude": -5.9550,
        "longitude": 106.0000
    },
    {
        "nama": "PT Indonesia Power Suralaya",
        "tipe": "Energi",
        "latitude": -5.9350,
        "longitude": 105.9460
    },
    {
        "nama": "PT Banten Energy",
        "tipe": "Energi",
        "latitude": -6.0450,
        "longitude": 105.9750
    },
    {
        "nama": "Pelabuhan Merak",
        "tipe": "Pelabuhan",
        "latitude": -5.9350,
        "longitude": 106.0000
    },
    {
        "nama": "PT Lotte Chemical Indonesia",
        "tipe": "Kimia",
        "latitude": -6.0380,
        "longitude": 106.0100
    },
    {
        "nama": "PLTU Labuan (Banten 2)",
        "tipe": "Pembangkit Listrik",
        "latitude": -6.3660,
        "longitude": 105.8180
    },
    {
        "nama": "PT Indocement Tunggal Prakarsa (Bayah)",
        "tipe": "Semen",
        "latitude": -6.9500,
        "longitude": 106.2600
    },
    {
        "nama": "Pelabuhan Ciwandan",
        "tipe": "Pelabuhan/Logistik",
        "latitude": -6.0350,
        "longitude": 105.9600
    },
    {
        "nama": "PT Sulfindo Adiusaha",
        "tipe": "Kimia",
        "latitude": -6.0150,
        "longitude": 106.0080
    },
    {
        "nama": "Pelabuhan Perikanan Karangantu",
        "tipe": "Perikanan",
        "latitude": -6.0310,
        "longitude": 106.1700
    }
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

KECAMATAN_GEOJSON = os.path.join(OUTPUT_DIR, "banten_coastal_kecamatan_land.geojson")
KECAMATAN_JSON = os.path.join(OUTPUT_DIR, "banten_water_quality_kecamatan.json")
KECAMATAN_CSV = os.path.join(OUTPUT_DIR, "banten_water_quality_kecamatan.csv")
BEACH_JSON = os.path.join(OUTPUT_DIR, "banten_water_quality_beach.json")
BEACH_CSV = os.path.join(OUTPUT_DIR, "banten_water_quality_beach.csv")
INDUSTRIES_JSON = os.path.join(OUTPUT_DIR, "banten_industries.json")


# ---------------------------------------------------------------------------
# Haversine Formula
# ---------------------------------------------------------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Menghitung jarak antara dua titik koordinat (km) menggunakan Haversine formula."""
    R = 6371.0  # Radius bumi dalam km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return round(R * c, 2)


def get_dampak_category(distance_km: float) -> str:
    """Menentukan kategori dampak industri berdasarkan jarak."""
    if distance_km < 5:
        return "TINGGI"
    elif distance_km <= 15:
        return "SEDANG"
    else:
        return "RENDAH"


def find_nearest_industries(lat: float, lon: float, top_n: int = 3) -> list:
    """Menemukan N industri terdekat dari suatu koordinat."""
    distances = []
    for industry in INDUSTRIES:
        dist = haversine(lat, lon, industry["latitude"], industry["longitude"])
        distances.append({
            "nama": industry["nama"],
            "tipe": industry["tipe"],
            "jarak_km": dist,
            "lat": industry["latitude"],
            "lon": industry["longitude"]
        })
    distances.sort(key=lambda x: x["jarak_km"])
    return distances[:top_n]


def add_industry_fields(data: dict, lat: float, lon: float) -> dict:
    """Menambahkan field-field jarak industri ke dictionary data."""
    nearest = find_nearest_industries(lat, lon, top_n=3)
    
    if nearest:
        data["industri_terdekat"] = nearest[0]["nama"]
        data["tipe_industri"] = nearest[0]["tipe"]
        data["jarak_industri_km"] = nearest[0]["jarak_km"]
        data["kategori_dampak_industri"] = get_dampak_category(nearest[0]["jarak_km"])
    
    if len(nearest) >= 2:
        data["industri_terdekat_2"] = nearest[1]["nama"]
        data["tipe_industri_2"] = nearest[1]["tipe"]
        data["jarak_industri_2_km"] = nearest[1]["jarak_km"]
    
    if len(nearest) >= 3:
        data["industri_terdekat_3"] = nearest[2]["nama"]
        data["tipe_industri_3"] = nearest[2]["tipe"]
        data["jarak_industri_3_km"] = nearest[2]["jarak_km"]
    
    return data


# ---------------------------------------------------------------------------
# Centroid Calculation from GeoJSON Polygon
# ---------------------------------------------------------------------------

def compute_polygon_centroid(coordinates: list) -> tuple:
    """Menghitung centroid dari polygon coordinates (list of rings).
    Mengambil ring pertama (outer ring) saja.
    """
    ring = coordinates[0]
    n = len(ring)
    if n == 0:
        return (0, 0)
    
    sum_lat = sum(pt[1] for pt in ring)
    sum_lon = sum(pt[0] for pt in ring)
    return (sum_lat / n, sum_lon / n)


def compute_multipolygon_centroid(coordinates: list) -> tuple:
    """Menghitung centroid dari MultiPolygon (rata-rata centroid tiap polygon,
    weighted by jumlah titik di outer ring).
    """
    total_lat = 0.0
    total_lon = 0.0
    total_pts = 0
    
    for polygon_coords in coordinates:
        ring = polygon_coords[0]
        n = len(ring)
        total_lat += sum(pt[1] for pt in ring)
        total_lon += sum(pt[0] for pt in ring)
        total_pts += n
    
    if total_pts == 0:
        return (0, 0)
    return (total_lat / total_pts, total_lon / total_pts)


def get_kecamatan_centroids(geojson_path: str) -> dict:
    """Membaca GeoJSON kecamatan dan menghitung centroid setiap kecamatan."""
    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson = json.load(f)
    
    centroids = {}
    for feature in geojson["features"]:
        props = feature["properties"]
        kec_name = props.get("Kecamatan", "")
        geom_type = feature["geometry"]["type"]
        coords = feature["geometry"]["coordinates"]
        
        if geom_type == "Polygon":
            lat, lon = compute_polygon_centroid(coords)
        elif geom_type == "MultiPolygon":
            lat, lon = compute_multipolygon_centroid(coords)
        else:
            continue
        
        centroids[kec_name] = {"latitude": round(lat, 6), "longitude": round(lon, 6)}
    
    return centroids


# ---------------------------------------------------------------------------
# Main Processing
# ---------------------------------------------------------------------------

def process_kecamatan():
    """Memproses data kecamatan: menghitung jarak industri dan mengupdate JSON & CSV."""
    print("=" * 60)
    print("PROCESSING KECAMATAN DATA")
    print("=" * 60)
    
    # 1. Hitung centroid dari GeoJSON
    print(f"\nMembaca GeoJSON: {KECAMATAN_GEOJSON}")
    centroids = get_kecamatan_centroids(KECAMATAN_GEOJSON)
    print(f"  -> Ditemukan {len(centroids)} kecamatan dengan centroid")
    
    # 2. Baca data kualitas air kecamatan
    print(f"\nMembaca JSON: {KECAMATAN_JSON}")
    with open(KECAMATAN_JSON, "r", encoding="utf-8") as f:
        kec_data = json.load(f)
    print(f"  -> Ditemukan {len(kec_data)} kecamatan")
    
    # 3. Tambahkan field industri
    updated_count = 0
    for kec_name, stats in kec_data.items():
        centroid = centroids.get(kec_name)
        if centroid:
            lat, lon = centroid["latitude"], centroid["longitude"]
            # Tambahkan centroid ke data
            stats["centroid_latitude"] = lat
            stats["centroid_longitude"] = lon
            add_industry_fields(stats, lat, lon)
            updated_count += 1
            
            nearest = stats.get("industri_terdekat", "?")
            dist = stats.get("jarak_industri_km", "?")
            kategori = stats.get("kategori_dampak_industri", "?")
            print(f"  {kec_name}: {nearest} ({dist} km) -> Dampak {kategori}")
        else:
            print(f"  WARNING: Centroid tidak ditemukan untuk {kec_name}")
    
    print(f"\n  -> {updated_count}/{len(kec_data)} kecamatan terupdate")
    
    # 4. Simpan JSON
    with open(KECAMATAN_JSON, "w", encoding="utf-8") as f:
        json.dump(kec_data, f, indent=2, ensure_ascii=False)
    print(f"  -> JSON disimpan: {KECAMATAN_JSON}")
    
    # 5. Simpan CSV
    if os.path.exists(KECAMATAN_CSV):
        save_kecamatan_csv(kec_data)
        print(f"  -> CSV disimpan: {KECAMATAN_CSV}")
    
    return kec_data


def process_beaches():
    """Memproses data pantai: menghitung jarak industri dan mengupdate JSON & CSV."""
    print("\n" + "=" * 60)
    print("PROCESSING BEACH DATA")
    print("=" * 60)
    
    # 1. Baca data pantai
    print(f"\nMembaca JSON: {BEACH_JSON}")
    with open(BEACH_JSON, "r", encoding="utf-8") as f:
        beach_data = json.load(f)
    print(f"  -> Ditemukan {len(beach_data)} pantai")
    
    # 2. Tambahkan field industri
    for beach_name, stats in beach_data.items():
        lat = stats.get("latitude")
        lon = stats.get("longitude")
        
        if lat is not None and lon is not None:
            add_industry_fields(stats, lat, lon)
            
            nearest = stats.get("industri_terdekat", "?")
            dist = stats.get("jarak_industri_km", "?")
            kategori = stats.get("kategori_dampak_industri", "?")
            print(f"  {beach_name}: {nearest} ({dist} km) -> Dampak {kategori}")
        else:
            print(f"  WARNING: Koordinat tidak ditemukan untuk {beach_name}")
    
    # 3. Simpan JSON
    with open(BEACH_JSON, "w", encoding="utf-8") as f:
        json.dump(beach_data, f, indent=2, ensure_ascii=False)
    print(f"\n  -> JSON disimpan: {BEACH_JSON}")
    
    # 4. Simpan CSV
    if os.path.exists(BEACH_CSV):
        save_beach_csv(beach_data)
        print(f"  -> CSV disimpan: {BEACH_CSV}")
    
    return beach_data


def save_kecamatan_csv(kec_data: dict):
    """Menyimpan data kecamatan ke CSV dengan kolom baru."""
    fieldnames = [
        "Kabupaten_Kota", "Kecamatan",
        "centroid_latitude", "centroid_longitude",
        "Luas_Air_2026_Ha", "Sehat_2026_Ha", "Sedang_2026_Ha", "TidakSehat_2026_Ha",
        "Pct_Sehat_2026", "Pct_Sedang_2026", "Pct_TidakSehat_2026",
        "Mean_NDTI_2026", "Mean_NDCI_2026", "Mean_TSS_2026", "Mean_CDOM_2026",
        "Status_Kualitas_2026",
        "Luas_Air_2017_Ha", "Sehat_2017_Ha", "Pct_Sehat_2017",
        "Mean_NDTI_2017", "Mean_NDCI_2017", "Status_Kualitas_2017",
        "Delta_Pct_Sehat", "Tren_Kualitas",
        "industri_terdekat", "tipe_industri", "jarak_industri_km", "kategori_dampak_industri",
        "industri_terdekat_2", "tipe_industri_2", "jarak_industri_2_km",
        "industri_terdekat_3", "tipe_industri_3", "jarak_industri_3_km",
        "penjelasan_kualitas"
    ]
    
    with open(KECAMATAN_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for kec_name, stats in kec_data.items():
            row = dict(stats)
            row["Kecamatan"] = kec_name
            writer.writerow(row)


def save_beach_csv(beach_data: dict):
    """Menyimpan data pantai ke CSV dengan kolom baru."""
    fieldnames = [
        "Pantai", "Kecamatan", "Kabupaten_Kota",
        "latitude", "longitude",
        "Luas_Air_2026_Ha", "Sehat_2026_Ha", "Sedang_2026_Ha", "TidakSehat_2026_Ha",
        "Pct_Sehat_2026", "Pct_Sedang_2026", "Pct_TidakSehat_2026",
        "Mean_NDTI_2026", "Mean_NDCI_2026", "Mean_TSS_2026", "Mean_CDOM_2026",
        "Status_Kualitas_2026",
        "Luas_Air_2017_Ha", "Sehat_2017_Ha", "Pct_Sehat_2017",
        "Mean_NDTI_2017", "Mean_NDCI_2017", "Status_Kualitas_2017",
        "Delta_Pct_Sehat", "Tren_Kualitas",
        "industri_terdekat", "tipe_industri", "jarak_industri_km", "kategori_dampak_industri",
        "industri_terdekat_2", "tipe_industri_2", "jarak_industri_2_km",
        "industri_terdekat_3", "tipe_industri_3", "jarak_industri_3_km",
        "penjelasan_kualitas"
    ]
    
    with open(BEACH_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for beach_name, stats in beach_data.items():
            row = dict(stats)
            row["Pantai"] = beach_name
            writer.writerow(row)


def save_industries_json():
    """Menyimpan daftar industri ke JSON terpisah untuk referensi API."""
    with open(INDUSTRIES_JSON, "w", encoding="utf-8") as f:
        json.dump(INDUSTRIES, f, indent=2, ensure_ascii=False)
    print(f"\n  -> Daftar industri disimpan: {INDUSTRIES_JSON}")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("COMPUTE INDUSTRY DISTANCE — Coast-Vision Banten")
    print("=" * 60)
    
    # Verifikasi file input
    for path in [KECAMATAN_GEOJSON, KECAMATAN_JSON, BEACH_JSON]:
        if not os.path.exists(path):
            print(f"ERROR: File tidak ditemukan: {path}")
            exit(1)
    
    kec_data = process_kecamatan()
    beach_data = process_beaches()
    save_industries_json()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    kec_count = sum(1 for v in kec_data.values() if "industri_terdekat" in v)
    beach_count = sum(1 for v in beach_data.values() if "industri_terdekat" in v)
    print(f"  Kecamatan terupdate: {kec_count}")
    print(f"  Pantai terupdate   : {beach_count}")
    print(f"  Jumlah industri    : {len(INDUSTRIES)}")
    
    # Statistik kategori dampak
    for label, dataset in [("Kecamatan", kec_data), ("Pantai", beach_data)]:
        cats = {}
        for v in dataset.values():
            cat = v.get("kategori_dampak_industri", "N/A")
            cats[cat] = cats.get(cat, 0) + 1
        print(f"\n  Kategori Dampak Industri ({label}):")
        for cat in ["TINGGI", "SEDANG", "RENDAH"]:
            print(f"    {cat}: {cats.get(cat, 0)}")
    
    print("\nDone!")
