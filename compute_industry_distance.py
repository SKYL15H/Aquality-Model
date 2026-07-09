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
# Relevansi Tipe Industri terhadap Kualitas Air Pesisir
# Skor 0.0 - 1.0: semakin tinggi = semakin berdampak terhadap pencemaran air
# ---------------------------------------------------------------------------

INDUSTRY_RELEVANCE = {
    # Tinggi — limbah cair/kimia langsung ke laut
    "Petrokimia": 1.0,
    "Kimia": 1.0,
    "Baja/Logam": 0.9,
    "Pulp & Paper": 0.9,
    # Sedang — polusi termal/sedimen
    "Pembangkit Listrik": 0.7,
    "Energi": 0.7,
    "Semen": 0.6,
    # Rendah — polusi fisik/logistik
    "Pelabuhan": 0.5,
    "Pelabuhan/Logistik": 0.5,
    "Perikanan": 0.3,
}

# Threshold relevansi minimum agar dianggap "relevan" terhadap kualitas air
MIN_RELEVANCE_THRESHOLD = 0.5

# Radius default (km) untuk menghitung kepadatan industri
DENSITY_RADIUS_KM = 10.0

# Decay rate (km) untuk perhitungan Indeks Dampak Industri (IDI)
# Pada jarak = decay_rate, dampak turun ke ~37% dari dampak maksimal
IDI_DECAY_RATE = 10.0

# ---------------------------------------------------------------------------
# Data Kepadatan Penduduk & Aktivitas Manusia Banten (BPS Banten)
# ---------------------------------------------------------------------------

# Kepadatan Penduduk per Kecamatan (jiwa/km2)
DISTRICT_POPULATION_DENSITY = {
    # Tangerang Kab (Sangat Padat / Urban Sprawl)
    "Kosambi": 3200.0,
    "Teluknaga": 2800.0,
    "Sukadiri": 2100.0,
    "Pakuhaji": 1900.0,
    "Mauk": 1500.0,
    "Kemiri": 1200.0,
    "Kronjo": 1100.0,
    "Mekarbaru": 1000.0,
    # Cilegon (Padat / Industri)
    "Jombang": 4500.0,
    "Cibeber": 2500.0,
    "Citangkil": 2200.0,
    "Pulomerak": 1800.0,
    "Ciwandan": 1100.0,
    "Grogol": 1300.0,
    # Serang Kota & Kab (Sedang)
    "Kramatwatu": 1400.0,
    "Bojonegara": 950.0,
    "Anyar": 800.0,
    "Kasemen": 1200.0,
    "Puloampel": 900.0,
    "Pontang": 750.0,
    "Tirtayasa": 600.0,
    "Tanara": 650.0,
    "Cinangka": 450.0,
    # Pandeglang (Rendah - Sedang)
    "Labuan": 1600.0,
    "Jiput": 700.0,
    "Carita": 550.0,
    "Pagelaran": 600.0,
    "Sukaresmi": 450.0,
    "Patia": 350.0,
    "Panimbang": 300.0,
    "Cigeulis": 200.0,
    "Sobang": 180.0,
    "Cimanggu": 150.0,
    "Cibitung": 120.0,
    "Sumur": 90.0,
    # Lebak (Sangat Rendah / Terpencil)
    "Malingping": 700.0,
    "Wanasalam": 400.0,
    "Bayah": 350.0,
    "Panggarangan": 200.0,
    "Cihara": 180.0,
    "Cilograng": 150.0,
}

# Pusat Kota Utama & Metropolitan Area (Urban Centers)
# Weight: skala 0.0 - 1.0 (bobot/ukuran aktivitas perkotaan)
URBAN_CENTERS = [
    {"nama": "Metropolitan Tangerang/Jakarta", "latitude": -6.1783, "longitude": 106.6319, "weight": 1.0},
    {"nama": "Kota Serang", "latitude": -6.1149, "longitude": 106.1502, "weight": 0.8},
    {"nama": "Kota Cilegon", "latitude": -6.0174, "longitude": 106.0182, "weight": 0.7},
    {"nama": "Rangkasbitung", "latitude": -6.3533, "longitude": 106.2483, "weight": 0.5},
    {"nama": "Pandeglang Kota", "latitude": -6.3084, "longitude": 105.8394, "weight": 0.5},
    {"nama": "Labuan", "latitude": -6.3784, "longitude": 105.8267, "weight": 0.4},
]

# Jarak peluruhan (km) pengaruh polusi domestik perkotaan
URBAN_DECAY_RATE = 15.0

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


def get_dampak_category_by_index(index: float) -> str:
    """Menentukan kategori dampak industri berdasarkan Indeks Dampak Industri (IDI).
    
    IDI 0-100: semakin tinggi = semakin terdampak industri.
    5 level kategori untuk granularitas lebih baik.
    """
    if index >= 50:
        return "SANGAT TINGGI"
    elif index >= 30:
        return "TINGGI"
    elif index >= 15:
        return "SEDANG"
    elif index >= 5:
        return "RENDAH"
    else:
        return "SANGAT RENDAH"


def get_dampak_category(distance_km: float) -> str:
    """Menentukan kategori dampak industri berdasarkan jarak (legacy, backward-compat)."""
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
        relevance = INDUSTRY_RELEVANCE.get(industry["tipe"], 0.3)
        distances.append({
            "nama": industry["nama"],
            "tipe": industry["tipe"],
            "jarak_km": dist,
            "relevansi": relevance,
            "lat": industry["latitude"],
            "lon": industry["longitude"]
        })
    distances.sort(key=lambda x: x["jarak_km"])
    return distances[:top_n]


def find_nearest_relevant_industry(lat: float, lon: float) -> dict | None:
    """Menemukan industri terdekat yang RELEVAN terhadap pencemaran air.
    
    Hanya industri dengan skor relevansi >= MIN_RELEVANCE_THRESHOLD yang dianggap relevan.
    Ini mengecualikan industri berdampak rendah seperti pelabuhan perikanan.
    """
    best = None
    best_dist = float("inf")
    
    for industry in INDUSTRIES:
        relevance = INDUSTRY_RELEVANCE.get(industry["tipe"], 0.3)
        if relevance < MIN_RELEVANCE_THRESHOLD:
            continue
        dist = haversine(lat, lon, industry["latitude"], industry["longitude"])
        if dist < best_dist:
            best_dist = dist
            best = {
                "nama": industry["nama"],
                "tipe": industry["tipe"],
                "jarak_km": dist,
                "relevansi": relevance,
            }
    return best


def count_industries_in_radius(lat: float, lon: float, radius_km: float = DENSITY_RADIUS_KM) -> dict:
    """Menghitung jumlah dan kepadatan industri dalam radius tertentu dari titik koordinat.
    
    Returns:
        dict dengan keys:
        - jumlah: total industri dalam radius
        - total_relevansi: jumlah skor relevansi industri dalam radius
        - kepadatan: jumlah industri per km² (area lingkaran π×r²)
        - daftar: list nama industri dalam radius
    """
    count = 0
    total_relevance = 0.0
    names = []
    
    for industry in INDUSTRIES:
        dist = haversine(lat, lon, industry["latitude"], industry["longitude"])
        if dist <= radius_km:
            relevance = INDUSTRY_RELEVANCE.get(industry["tipe"], 0.3)
            count += 1
            total_relevance += relevance
            names.append(industry["nama"])
    
    area_km2 = math.pi * radius_km ** 2
    density = round(count / area_km2, 4) if area_km2 > 0 else 0.0
    
    return {
        "jumlah": count,
        "total_relevansi": round(total_relevance, 2),
        "kepadatan": density,
        "daftar": names,
    }


def compute_industry_impact_index(lat: float, lon: float) -> float:
    """Menghitung Indeks Dampak Industri (IDI) skala 0-100.
    
    Menggunakan Inverse Distance Weighting (IDW) dengan bobot relevansi industri.
    Memperhitungkan SEMUA industri sekaligus, bukan hanya yang terdekat.
    
    Formula: IDI = (Σ relevance_i × exp(-dist_i / decay_rate)) / max_theoretical × 100
    
    - decay_rate = IDI_DECAY_RATE km (pada jarak ini dampak turun ke ~37%)
    - Industri dekat + relevan = kontribusi besar
    - Industri jauh + tidak relevan = kontribusi kecil
    """
    total_impact = 0.0
    
    for industry in INDUSTRIES:
        dist = haversine(lat, lon, industry["latitude"], industry["longitude"])
        relevance = INDUSTRY_RELEVANCE.get(industry["tipe"], 0.3)
        impact = relevance * math.exp(-dist / IDI_DECAY_RATE)
        total_impact += impact
    
    # Normalisasi: max theoretical = semua industri di jarak 0
    max_theoretical = sum(INDUSTRY_RELEVANCE.get(i["tipe"], 0.3) for i in INDUSTRIES)
    if max_theoretical == 0:
        return 0.0
    
    index = (total_impact / max_theoretical) * 100
    return round(min(100.0, index), 2)


def add_industry_fields(data: dict, lat: float, lon: float) -> dict:
    """Menambahkan semua field dampak industri ke dictionary data.
    
    Metrik yang ditambahkan:
    1. Jarak ke industri terdekat (legacy) + 3 terdekat
    2. Jarak ke industri terdekat yang RELEVAN
    3. Kepadatan industri dalam radius
    4. Indeks Dampak Industri (IDI) komposit
    """
    # --- Metrik Legacy: 3 industri terdekat ---
    nearest = find_nearest_industries(lat, lon, top_n=3)
    
    if nearest:
        data["industri_terdekat"] = nearest[0]["nama"]
        data["tipe_industri"] = nearest[0]["tipe"]
        data["jarak_industri_km"] = nearest[0]["jarak_km"]
    
    if len(nearest) >= 2:
        data["industri_terdekat_2"] = nearest[1]["nama"]
        data["tipe_industri_2"] = nearest[1]["tipe"]
        data["jarak_industri_2_km"] = nearest[1]["jarak_km"]
    
    if len(nearest) >= 3:
        data["industri_terdekat_3"] = nearest[2]["nama"]
        data["tipe_industri_3"] = nearest[2]["tipe"]
        data["jarak_industri_3_km"] = nearest[2]["jarak_km"]
    
    # --- Metrik 1: Industri relevan terdekat ---
    relevant = find_nearest_relevant_industry(lat, lon)
    if relevant:
        data["industri_relevan_terdekat"] = relevant["nama"]
        data["tipe_industri_relevan"] = relevant["tipe"]
        data["jarak_industri_relevan_km"] = relevant["jarak_km"]
        data["relevansi_industri"] = relevant["relevansi"]
    
    # --- Metrik 2: Kepadatan industri dalam radius ---
    density_info = count_industries_in_radius(lat, lon, DENSITY_RADIUS_KM)
    data["jumlah_industri_radius_10km"] = density_info["jumlah"]
    data["kepadatan_industri"] = density_info["kepadatan"]
    data["total_relevansi_radius"] = density_info["total_relevansi"]
    data["daftar_industri_radius"] = density_info["daftar"]
    
    # --- Metrik 3: Indeks Dampak Industri (IDI) komposit ---
    idi = compute_industry_impact_index(lat, lon)
    data["indeks_dampak_industri"] = idi
    data["kategori_dampak_industri"] = get_dampak_category_by_index(idi)
    
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
        "industri_terdekat", "tipe_industri", "jarak_industri_km",
        "industri_terdekat_2", "tipe_industri_2", "jarak_industri_2_km",
        "industri_terdekat_3", "tipe_industri_3", "jarak_industri_3_km",
        "industri_relevan_terdekat", "tipe_industri_relevan", "jarak_industri_relevan_km", "relevansi_industri",
        "jumlah_industri_radius_10km", "kepadatan_industri", "total_relevansi_radius",
        "indeks_dampak_industri", "kategori_dampak_industri",
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
        "industri_terdekat", "tipe_industri", "jarak_industri_km",
        "industri_terdekat_2", "tipe_industri_2", "jarak_industri_2_km",
        "industri_terdekat_3", "tipe_industri_3", "jarak_industri_3_km",
        "industri_relevan_terdekat", "tipe_industri_relevan", "jarak_industri_relevan_km", "relevansi_industri",
        "jumlah_industri_radius_10km", "kepadatan_industri", "total_relevansi_radius",
        "indeks_dampak_industri", "kategori_dampak_industri",
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
    print("COMPUTE INDUSTRY DISTANCE —  Aquality Banten")
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
    
    # Statistik kategori dampak (5 level baru)
    for label, dataset in [("Kecamatan", kec_data), ("Pantai", beach_data)]:
        cats = {}
        idis = []
        for v in dataset.values():
            cat = v.get("kategori_dampak_industri", "N/A")
            cats[cat] = cats.get(cat, 0) + 1
            idi = v.get("indeks_dampak_industri", 0)
            idis.append(idi)
        print(f"\n  Kategori Dampak Industri ({label}):")
        for cat in ["SANGAT TINGGI", "TINGGI", "SEDANG", "RENDAH", "SANGAT RENDAH"]:
            print(f"    {cat}: {cats.get(cat, 0)}")
        if idis:
            print(f"  IDI range: {min(idis)} — {max(idis)} (mean: {sum(idis)/len(idis):.2f})")
    
    print("\nDone!")
