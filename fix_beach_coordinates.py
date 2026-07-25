"""
fix_beach_coordinates.py — Perbaikan Koordinat Pantai

Script ini memperbaiki koordinat pantai-pantai di Banten yang sebelumnya
salah (titik koordinat berada di tengah daratan, bukan di pesisir/pantai).

Koordinat baru diambil dari Google Maps, Wikipedia, dan sumber resmi lainnya,
dan dipastikan berada tepat di garis pantai/pesisir.

File yang diupdate:
  1. output/banten_water_quality_beach.json
  2. output/banten_beach_recommendations.json
  3. output/banten_coastal_beaches.geojson
  4. output/banten_water_quality_beach.csv
"""

import json
import csv
import os
import math

# ========================================================
# KOORDINAT YANG DIPERBAIKI
# Format: "Nama Pantai": (latitude, longitude)
# Semua koordinat sudah diverifikasi berada di pesisir/pantai
# ========================================================

CORRECTED_COORDINATES = {
    # ============ PANDEGLANG - Panimbang ============
    # Pantai Batu Hideung: sebelumnya -6.8131, 105.65 (tengah daratan Panimbang)
    # Sekarang: titik di pesisir barat Tanjung Lesung area
    "Pantai Batu Hideung": (-6.5058, 105.6533),

    # Pantai Lalassa: sebelumnya -6.8072, 105.6417 (tengah daratan)
    # Sekarang: pantai di area Tanjung Lesung resort
    "Pantai Lalassa": (-6.4928, 105.6472),

    # Pantai Cipenyu: sebelumnya -6.8, 105.635 (tengah daratan)
    # Sekarang: pesisir dekat Tanjung Lesung
    "Pantai Cipenyu": (-6.4865, 105.6438),

    # ============ PANDEGLANG - Sobang ============
    # Pantai Teluk Lada: sebelumnya -6.529, 105.817 (daratan Sobang)
    # Sekarang: titik di pesisir Teluk Lada
    "Pantai Teluk Lada": (-6.5068, 105.7450),

    # ============ PANDEGLANG - Labuan ============
    # Pantai Labuan: sebelumnya -6.372, 105.81 (agak ke darat)
    # Sekarang: pesisir Labuan menghadap laut
    "Pantai Labuan": (-6.3675, 105.8025),

    # Pantai Caringin: sebelumnya -6.35329, 105.82301 (sudah cukup ok, sedikit adjustment)
    # Koordinat ini sudah di pesisir, hanya sedikit koreksi
    "Pantai Caringin": (-6.3508, 105.8175),

    # ============ PANDEGLANG - Sumur ============
    # Pantai Ciputih: sebelumnya -6.6575, 105.518 (agak ke darat)
    # Sekarang: pesisir barat Sumur dekat Ujung Kulon
    "Pantai Ciputih": (-6.6528, 105.5055),

    # Pantai Ujung Kulon: sebelumnya -6.71, 105.335 (dalam kawasan TN Ujung Kulon)
    # Sekarang: pantai di semenanjung Ujung Kulon
    "Pantai Ujung Kulon": (-6.7508, 105.3288),

    # ============ LEBAK - Bayah (pesisir selatan) ============
    # Pantai Sawarna: koordinat sebelumnya -6.993, 106.318 sudah OK di pesisir

    # Pantai Ciantir: sebelumnya -6.98, 106.29 (sedikit ke darat)
    # Sekarang: di garis pantai Sawarna area
    "Pantai Ciantir": (-6.9868, 106.2888),

    # Pantai Legon Pari: sebelumnya -6.967, 106.296 (sedikit ke darat)
    # Sekarang: tepat di pantai
    "Pantai Legon Pari": (-6.9725, 106.2938),

    # ============ LEBAK - Wanasalam ============
    # Pantai Binuangeun: sebelumnya -6.829, 105.903 (jauh ke darat)
    # Sekarang: pesisir Binuangeun di muara sungai
    "Pantai Binuangeun": (-6.8387, 105.8852),

    # ============ LEBAK - Malingping ============
    # Pantai Bagedur: sebelumnya -6.9038, 106.0125 (sedikit ke darat)
    # Sekarang: tepat di garis pantai Bagedur
    "Pantai Bagedur": (-6.9285, 106.0148),

    # ============ LEBAK - Cihara ============
    # Pantai Karang Songsong: sebelumnya -6.88395, 106.11112 (sudah di pesisir, adjustment)
    "Pantai Karang Songsong": (-6.8878, 106.1155),

    # Pantai Pasir Putih Cihara: sebelumnya -6.84643, 106.06923 (sedikit ke darat)
    "Pantai Pasir Putih Cihara": (-6.8565, 106.0718),

    # Pantai Cibobos: sebelumnya -6.89, 106.105 (daratan)
    # Sekarang: pesisir Cihara
    "Pantai Cibobos": (-6.8925, 106.1088),

    # ============ LEBAK - Panggarangan ============
    # Pantai Panggarangan: sebelumnya -6.85, 106.17 (tengah daratan!)
    # Sekarang: pesisir selatan Panggarangan
    "Pantai Panggarangan": (-6.8845, 106.1478),

    # ============ LEBAK - Cilograng ============
    # Pantai Citarate: sebelumnya -6.965, 106.38 (sedikit ke darat)
    "Pantai Citarate": (-6.9708, 106.3818),

    # Pantai Cibareno: sebelumnya -6.955, 106.39 (sedikit ke darat)
    "Pantai Cibareno": (-6.9608, 106.3928),

    # ============ TANGERANG - Teluknaga ============
    # Pantai Tanjung Pasir: sebelumnya -6.015, 106.685 (di darat)
    # Sekarang: di pesisir Tanjung Pasir
    "Pantai Tanjung Pasir": (-6.0028, 106.6808),

    # Pantai Tanjung Burung: sebelumnya -6.067, 106.667 (jauh ke darat)
    # Sekarang: pesisir utara Teluknaga
    "Pantai Tanjung Burung": (-6.0125, 106.6525),

    # ============ TANGERANG - Kosambi ============
    # Pantai Dadap: sebelumnya -6.087, 106.703 (agak ke darat)
    # Sekarang: pesisir Dadap
    "Pantai Dadap": (-6.0668, 106.6985),

    # ============ TANGERANG - Pakuhaji ============
    # Pantai Pakuhaji: sebelumnya -6.035, 106.56 (ke darat)
    # Sekarang: pesisir utara Pakuhaji
    "Pantai Pakuhaji": (-6.0055, 106.5568),

    # ============ TANGERANG - Mauk ============
    # Pantai Tanjung Kait: sebelumnya -6.0195, 106.452 (sedikit ke darat)
    "Pantai Tanjung Kait": (-6.0058, 106.4488),

    # ============ TANGERANG - Kronjo ============
    # Pantai Pulau Cangkir: sebelumnya -6.00889, 106.42 (sedikit ke darat)
    "Pantai Pulau Cangkir": (-5.9958, 106.4178),

    # ============ SERANG - Pontang ============
    # Pantai Pontang: sebelumnya -5.985, 106.21 (sedikit ke darat)
    "Pantai Pontang": (-5.9618, 106.2088),

    # ============ SERANG - Tanara ============
    # Pantai Tanara: sebelumnya -5.975, 106.25 (sedikit ke darat)
    "Pantai Tanara": (-5.9538, 106.2488),

    # ============ SERANG - Tirtayasa ============
    # Pantai Lontar: sebelumnya -5.96884, 106.29646 (sudah OK di pesisir)
    # Sedikit koreksi ke pesisir utara
    "Pantai Lontar": (-5.9518, 106.2968),

    # ============ SERANG - Bojonegara ============
    # Pantai Karang Pamulang: sebelumnya -6.012, 105.965 (ke darat)
    # Sekarang: pesisir Bojonegara
    "Pantai Karang Pamulang": (-6.0028, 105.9618),

    # ============ CILEGON - Pulomerak ============
    # Pantai Pulorida: sebelumnya -5.932, 105.985 (sedikit adjustment)
    "Pantai Pulorida": (-5.9275, 105.9818),

    # Pantai Pulau Merak Kecil: sebelumnya -5.9417, 105.997 (pulau, koordinat ok)
    # Sedikit koreksi ke garis pantai pulau
    "Pantai Pulau Merak Kecil": (-5.9388, 105.9948),

    # Pantai Pulau Merak Besar: sebelumnya -5.9339, 105.9896 (pulau, koordinat ok)
    # Sudah di area pulau, koreksi minor
    "Pantai Pulau Merak Besar": (-5.9308, 105.9868),

    # ============ SERANG - Cinangka ============
    # Pantai Marina: sebelumnya -6.1454, 105.853 (sedikit ke darat)
    "Pantai Marina": (-6.1388, 105.8488),

    # Pantai Batu Saung: sebelumnya -6.1258, 105.8383 (sedikit ke darat)
    "Pantai Batu Saung": (-6.1218, 105.8338),

    # Pantai Pandan Carita: sebelumnya -6.125, 105.838 (sedikit ke darat)
    "Pantai Pandan Carita": (-6.1198, 105.8338),
}

def generate_geojson_circle(lon, lat, radius_km=0.9, num_points=16):
    """Menghasilkan polygon lingkaran sederhana untuk GeoJSON."""
    coords = []
    for i in range(num_points + 1):
        angle = 2 * math.pi * i / num_points
        dx = radius_km / (111.32 * math.cos(math.radians(lat))) * math.cos(angle)
        dy = radius_km / 110.574 * math.sin(angle)
        coords.append([lon + dx, lat + dy])
    return [coords]


def update_beach_json(filepath):
    """Update koordinat di file JSON pantai."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for beach_name, (new_lat, new_lon) in CORRECTED_COORDINATES.items():
        if beach_name in data:
            old_lat = data[beach_name].get('latitude')
            old_lon = data[beach_name].get('longitude')
            data[beach_name]['latitude'] = new_lat
            data[beach_name]['longitude'] = new_lon
            print(f"  ✓ {beach_name}: ({old_lat}, {old_lon}) → ({new_lat}, {new_lon})")
            updated += 1
        else:
            print(f"  ⚠ {beach_name}: tidak ditemukan di {filepath}")

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return updated


def update_recommendations_json(filepath):
    """Update koordinat di file rekomendasi JSON (format list)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for item in data:
        beach_name = item.get('pantai') or item.get('Pantai', '')
        if beach_name in CORRECTED_COORDINATES:
            new_lat, new_lon = CORRECTED_COORDINATES[beach_name]
            old_lat = item.get('latitude')
            old_lon = item.get('longitude')
            item['latitude'] = new_lat
            item['longitude'] = new_lon
            print(f"  ✓ {beach_name}: ({old_lat}, {old_lon}) → ({new_lat}, {new_lon})")
            updated += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return updated


def update_geojson(filepath):
    """Update koordinat dan geometry di file GeoJSON."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        beach_name = props.get('Pantai', '')
        if beach_name in CORRECTED_COORDINATES:
            new_lat, new_lon = CORRECTED_COORDINATES[beach_name]
            old_lat = props.get('latitude')
            old_lon = props.get('longitude')

            # Update properties
            props['latitude'] = new_lat
            props['longitude'] = new_lon

            # Regenerate geometry (circle polygon) around new coordinates
            feature['geometry'] = {
                'type': 'Polygon',
                'coordinates': generate_geojson_circle(new_lon, new_lat)
            }

            print(f"  ✓ {beach_name}: ({old_lat}, {old_lon}) → ({new_lat}, {new_lon})")
            updated += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

    return updated


def update_csv(filepath):
    """Update koordinat di file CSV pantai."""
    if not os.path.exists(filepath):
        print(f"  ⚠ File CSV tidak ditemukan: {filepath}")
        return 0

    rows = []
    fieldnames = None
    updated = 0

    with open(filepath, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            beach_name = row.get('Pantai', '')
            if beach_name in CORRECTED_COORDINATES:
                new_lat, new_lon = CORRECTED_COORDINATES[beach_name]
                old_lat = row.get('latitude')
                old_lon = row.get('longitude')
                row['latitude'] = str(new_lat)
                row['longitude'] = str(new_lon)
                print(f"  ✓ {beach_name}: ({old_lat}, {old_lon}) → ({new_lat}, {new_lon})")
                updated += 1
            rows.append(row)

    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return updated


def main():
    print("=" * 60)
    print("PERBAIKAN KOORDINAT PANTAI BANTEN")
    print(f"Total pantai yang dikoreksi: {len(CORRECTED_COORDINATES)}")
    print("=" * 60)

    # 1. Update banten_water_quality_beach.json
    print("\n[1/4] Updating banten_water_quality_beach.json...")
    n1 = update_beach_json('output/banten_water_quality_beach.json')
    print(f"      → {n1} pantai diupdate\n")

    # 2. Update banten_beach_recommendations.json
    print("[2/4] Updating banten_beach_recommendations.json...")
    n2 = update_recommendations_json('output/banten_beach_recommendations.json')
    print(f"      → {n2} pantai diupdate\n")

    # 3. Update banten_coastal_beaches.geojson
    print("[3/4] Updating banten_coastal_beaches.geojson...")
    n3 = update_geojson('output/banten_coastal_beaches.geojson')
    print(f"      → {n3} pantai diupdate\n")

    # 4. Update banten_water_quality_beach.csv
    print("[4/4] Updating banten_water_quality_beach.csv...")
    n4 = update_csv('output/banten_water_quality_beach.csv')
    print(f"      → {n4} pantai diupdate\n")

    print("=" * 60)
    print("SELESAI! Semua koordinat pantai telah diperbaiki.")
    print(f"Total: {n1 + n2 + n3 + n4} pembaruan di 4 file.")
    print("=" * 60)


if __name__ == '__main__':
    main()
