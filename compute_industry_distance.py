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
WATER_GEOJSON = os.path.join(OUTPUT_DIR, "banten_coastal_kecamatan_water.geojson")


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


def compute_urban_influence_index(lat: float, lon: float) -> float:
    """Menghitung Indeks Pengaruh Urban (IPU) skala 0-100.
    
    Menggunakan IDW (Inverse Distance Weighting) ke pusat-pusat kota utama.
    Mencerminkan sebaran pemukiman padat dan limpasan limbah domestik perkotaan.
    
    Formula: IPU = (Σ weight_i × exp(-dist_i / decay_rate)) / max_theoretical × 100
    - decay_rate = URBAN_DECAY_RATE (15 km)
    """
    total_influence = 0.0
    for center in URBAN_CENTERS:
        dist = haversine(lat, lon, center["latitude"], center["longitude"])
        influence = center["weight"] * math.exp(-dist / URBAN_DECAY_RATE)
        total_influence += influence
        
    max_theoretical = sum(c["weight"] for c in URBAN_CENTERS)
    if max_theoretical == 0:
        return 0.0
        
    index = (total_influence / max_theoretical) * 100
    return round(min(100.0, index), 2)


def generate_terrestrial_explanation(name: str, stats: dict, is_beach: bool = False) -> str:
    """Menghasilkan penjelasan kelayakan lingkungan berbasis parameter darat secara dinamis."""
    kec_name = stats.get("Kecamatan", name) if is_beach else name
    
    # 1. Teks Kepadatan Penduduk & IPU
    density = stats.get("kepadatan_penduduk_kecamatan", 500.0)
    ipu = stats.get("indeks_pengaruh_urban", 0.0)
    
    demo_urban_text = f" Wilayah ini memiliki kepadatan penduduk **{density:,.0f} jiwa/km²**."
    if ipu >= 60:
        demo_urban_text += f" Indeks Pengaruh Urban bernilai **TINGGI** ({ipu:.2f}/100) akibat dekatnya dengan sprawl metropolitan/pusat kota utama."
    elif ipu >= 30:
        demo_urban_text += f" Indeks Pengaruh Urban bernilai **SEDANG** ({ipu:.2f}/100) dengan pengaruh limpasan domestik perkotaan sedang."
    else:
        demo_urban_text += f" Indeks Pengaruh Urban bernilai **RENDAH** ({ipu:.2f}/100) karena lokasinya relatif terpencil dari aglomerasi perkotaan utama."
        
    # 2. Teks Dampak Industri
    idi = stats.get("indeks_dampak_industri", 0.0)
    kategori = stats.get("kategori_dampak_industri", "RENDAH")
    industri = stats.get("industri_terdekat", "")
    tipe = stats.get("tipe_industri", "")
    jarak = stats.get("jarak_industri_km")
    n_radius = stats.get("jumlah_industri_radius_10km", 0)
    industri_relevan = stats.get("industri_relevan_terdekat")
    jarak_relevan = stats.get("jarak_industri_relevan_km")
    
    industry_text = ""
    if industri and jarak is not None:
        if idi >= 30:
            industry_text = (
                f" Indeks Dampak Industri di wilayah ini **{idi:.2f}/100** (kategori **{kategori}**) "
                f"dengan {n_radius} fasilitas industri dalam radius 10 km."
            )
            if industri_relevan and jarak_relevan:
                industry_text += f" Industri paling relevan terhadap pencemaran air adalah {industri_relevan} berjarak **{jarak_relevan:.2f} km**."
            industry_text += " Tekanan kumulatif industri terhadap kualitas perairan sangat signifikan."
        elif idi >= 15:
            industry_text = (
                f" Indeks Dampak Industri **{idi:.2f}/100** ({kategori}) dengan {n_radius} industri dalam radius 10 km. "
                f"Industri terdekat: {industri} ({tipe}) berjarak **{jarak:.2f} km**. "
                f"Pengaruh industri terhadap kualitas perairan bersifat moderat."
            )
        elif idi >= 5:
            industry_text = (
                f" Indeks Dampak Industri **{idi:.2f}/100** ({kategori}). "
                f"Industri terdekat adalah {industri} ({tipe}) berjarak **{jarak:.2f} km** "
                f"dengan dampak relatif rendah terhadap kualitas air."
            )
        else:
            industry_text = (
                f" Indeks Dampak Industri sangat rendah (**{idi:.2f}/100**). "
                f"Industri terdekat ({industri}) berjarak **{jarak:.2f} km** — "
                f"dampak industri terhadap kualitas air sangat minimal."
            )
            
    # 3. Gabungkan narasi kelayakan
    if is_beach:
        if idi >= 30 or ipu >= 60:
            intro = f"Kawasan pesisir di {name} ({kec_name}) dinilai memiliki **TEKANAN LINGKUNGAN TINGGI**. Hal ini dipengaruhi oleh tingginya aktivitas manusia perkotaan atau letaknya yang dekat dengan pusat industri."
        elif idi >= 15 or ipu >= 30:
            intro = f"Kawasan pesisir di {name} ({kec_name}) berada dalam kondisi kelayakan lingkungan **SEDANG**. Terdapat pengaruh antropogenik menengah dari pemukiman perkotaan sekitar atau aktivitas pelabuhan/industri regional."
        else:
            intro = f"Kawasan pesisir di {name} ({kec_name}) diklasifikasikan memiliki kelayakan lingkungan **SANGAT BAIK (Lestari)**. Wilayah pantai sangat bersih dari pencemaran darat karena kepadatan penduduk lokal sangat rendah dan jauh dari kawasan industri berat."
    else:
        if idi >= 30 or ipu >= 60:
            intro = f"Kawasan pesisir di Kecamatan {name} dinilai memiliki **TEKANAN LINGKUNGAN TINGGI**. Tingginya aktivitas industri dan/atau kepadatan pemukiman urban di wilayah ini memberikan kontribusi polutan antropogenik yang signifikan ke perairan pesisir."
        elif idi >= 15 or ipu >= 30:
            intro = f"Kawasan pesisir di Kecamatan {name} berada dalam kondisi kelayakan lingkungan **SEDANG**. Terdapat tekanan antropogenik menengah dari pemukiman domestik atau area industri regional."
        else:
            intro = f"Kawasan pesisir di Kecamatan {name} diklasifikasikan memiliki kelayakan lingkungan **SANGAT BAIK (Lestari)**. Kondisi alam sekitar terjaga dengan kepadatan penduduk yang minim serta jarak yang sangat jauh dari kawasan industri berat."
            
    return f"{intro}{demo_urban_text}{industry_text}"


def add_industry_fields(data: dict, lat: float, lon: float, kecamatan_name: str = "", is_beach: bool = False) -> dict:
    """Menambahkan semua field dampak industri, kepadatan penduduk, dan pengaruh urban ke data."""
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

    # --- Metrik Baru: Demografi & Urban ---
    # Kepadatan Penduduk
    kec_key = kecamatan_name or data.get("Kecamatan", "")
    density = DISTRICT_POPULATION_DENSITY.get(kec_key, 500.0)
    data["kepadatan_penduduk_kecamatan"] = density
    
    # Indeks Pengaruh Urban
    ipu = compute_urban_influence_index(lat, lon)
    data["indeks_pengaruh_urban"] = ipu
    
    # Penjelasan Kualitas Kelayakan Terestrial
    data["penjelasan_kualitas"] = generate_terrestrial_explanation(data.get("Pantai", kecamatan_name), data, is_beach=is_beach)
    
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
            add_industry_fields(stats, lat, lon, kecamatan_name=kec_name, is_beach=False)
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
            stats["Pantai"] = beach_name
            add_industry_fields(stats, lat, lon, kecamatan_name=stats.get("Kecamatan", ""), is_beach=True)
            
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
        "industri_terdekat", "tipe_industri", "jarak_industri_km",
        "industri_terdekat_2", "tipe_industri_2", "jarak_industri_2_km",
        "industri_terdekat_3", "tipe_industri_3", "jarak_industri_3_km",
        "industri_relevan_terdekat", "tipe_industri_relevan", "jarak_industri_relevan_km", "relevansi_industri",
        "jumlah_industri_radius_10km", "kepadatan_industri", "total_relevansi_radius",
        "indeks_dampak_industri", "kategori_dampak_industri",
        "kepadatan_penduduk_kecamatan", "indeks_pengaruh_urban",
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
        "industri_terdekat", "tipe_industri", "jarak_industri_km",
        "industri_terdekat_2", "tipe_industri_2", "jarak_industri_2_km",
        "industri_terdekat_3", "tipe_industri_3", "jarak_industri_3_km",
        "industri_relevan_terdekat", "tipe_industri_relevan", "jarak_industri_relevan_km", "relevansi_industri",
        "jumlah_industri_radius_10km", "kepadatan_industri", "total_relevansi_radius",
        "indeks_dampak_industri", "kategori_dampak_industri",
        "kepadatan_penduduk_kecamatan", "indeks_pengaruh_urban",
        "penjelasan_kualitas"
    ]
    
    with open(BEACH_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for beach_name, stats in beach_data.items():
            row = dict(stats)
            row["Pantai"] = beach_name
            writer.writerow(row)


def _extract_water_boundary_points(geojson_path: str) -> list[tuple[float, float]]:
    """Mengekstrak semua titik batas dari polygon air di GeoJSON pesisir.

    Mengembalikan list of (lat, lon) yang merepresentasikan garis pantai.
    """
    if not os.path.exists(geojson_path):
        print(f"  WARNING: Water GeoJSON tidak ditemukan: {geojson_path}")
        return []

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    points: list[tuple[float, float]] = []
    for feature in data.get("features", []):
        geom = feature.get("geometry", {})
        geom_type = geom.get("type", "")
        coords = geom.get("coordinates", [])

        if geom_type == "Polygon":
            for ring in coords:
                for lon, lat, *_ in ring:
                    points.append((lat, lon))
        elif geom_type == "MultiPolygon":
            for polygon in coords:
                for ring in polygon:
                    for lon, lat, *_ in ring:
                        points.append((lat, lon))
    return points


def compute_distance_to_coast(lat: float, lon: float,
                              coastline_points: list[tuple[float, float]]) -> float:
    """Menghitung jarak minimum (km) dari suatu titik ke garis pantai terdekat.

    Menggunakan Haversine terhadap semua titik batas polygon air pesisir.
    """
    if not coastline_points:
        return 0.0

    min_dist = float("inf")
    for clat, clon in coastline_points:
        d = haversine(lat, lon, clat, clon)
        if d < min_dist:
            min_dist = d
    return round(min_dist, 2)


def compute_risk_score(distance_to_coast_km: float, relevance: float) -> float:
    """Menghitung skor risiko industri (0-100) terhadap pesisir.

    Formula menggabungkan dua faktor:
    1. Proximity — semakin dekat ke pantai, semakin berbahaya.
       Industri <= 1 km mendapat proximity = 1.0 (maksimal).
       Di luar 1 km, proximity turun secara eksponensial (half-life ~8 km).
    2. Relevansi polusi — bobot tipe industri (0.0-1.0).

    risk_score = relevance × proximity × 100, di-cap pada 100.
    """
    if distance_to_coast_km <= 1.0:
        proximity = 1.0
    else:
        proximity = math.exp(-0.0866 * (distance_to_coast_km - 1.0))  # ~50% at 8 km

    risk = relevance * proximity * 100.0
    return round(min(100.0, max(0.0, risk)), 1)


def save_industries_json():
    """Menyimpan daftar industri ke JSON terpisah untuk referensi API.

    Menambahkan field: industry_id, relevansi, distance_to_coast_km, risk_score.
    """
    # Ekstrak titik batas air (garis pantai)
    coastline_pts = _extract_water_boundary_points(WATER_GEOJSON)
    print(f"\n  -> Coastline points extracted: {len(coastline_pts)}")

    enriched = []
    for idx, industry in enumerate(INDUSTRIES, start=1):
        rel = INDUSTRY_RELEVANCE.get(industry["tipe"], 0.3)
        dist_coast = compute_distance_to_coast(
            industry["latitude"], industry["longitude"], coastline_pts
        )
        risk = compute_risk_score(dist_coast, rel)

        enriched.append({
            "industry_id": f"IND{idx:03d}",
            "nama": industry["nama"],
            "tipe": industry["tipe"],
            "latitude": industry["latitude"],
            "longitude": industry["longitude"],
            "relevansi": rel,
            "distance_to_coast_km": dist_coast,
            "risk_score": risk,
        })
        print(f"    {enriched[-1]['industry_id']}  {industry['nama']:<42s}  "
              f"coast={dist_coast:6.2f} km  risk={risk:5.1f}")

    with open(INDUSTRIES_JSON, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
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
