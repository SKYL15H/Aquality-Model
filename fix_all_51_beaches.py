"""
fix_all_51_beaches.py — Perbaikan Akurat 51 Koordinat Pantai Banten

Script ini memperbaiki koordinat persis untuk ke-51 pantai di Banten
agar tepat berada di garis pantai/pesisir (pertemuan darat dan laut) pada peta.

Fokus Khusus Perbaikan:
1. Pantai Ciputih: Dipindahkan dari tengah laut (lat: -6.6528, lon: 105.5055)
   ke garis pantai Kertamukti Sumur (lat: -6.6585, lon: 105.5255).
2. Pantai Batu Hideung: Dipindahkan dari tengah daratan Panimbang
   ke pesisir barat Tanjungjaya (lat: -6.5185, lon: 105.6310).
3. Pantai Lalassa: Dipindahkan dari tengah daratan
   ke pesisir pantai LaLassa Tanjung Lesung (lat: -6.4832, lon: 105.6442).
4. Pantai Cipenyu: Dipindahkan dari tengah daratan
   ke pesisir barat Tanjungjaya (lat: -6.4915, lon: 105.6415).
5. Pantai Tanjung Burung: Dipindahkan dari tengah daratan Cengklong
   ke pesisir muara Cisadane Teluknaga (lat: -5.9965, lon: 106.6560).
6. Pantai Dadap: Dipindahkan dari tengah daratan Jatimulya
   ke pesisir pantai Dadap Kosambi (lat: -6.0505, lon: 106.7025).
7. Pantai Bagedur: Dipindahkan ke pesisir selatan Malingping (lat: -6.9038, lon: 106.0125).
"""

import json
import csv
import os
import math
import subprocess

# Kamus 51 pantai dengan koordinat pesisir yang presisi
EXACT_BEACH_COORDINATES = {
    # Anyer & Cinangka (Serang)
    "Pantai Anyer": (-6.0520, 105.8900),
    "Pantai Sambolo": (-6.0712, 105.8835),
    "Pantai Pasir Putih Sirih": (-6.0825, 105.8825),
    "Pantai Marbella": (-6.0620, 105.8845),
    "Pantai Karang Bolong": (-6.1082, 105.8650),
    "Pantai Jambu": (-6.1158, 105.8665),
    "Pantai Pasir Putih Florida": (-6.1265, 105.8645),
    "Pantai Florida Indah": (-6.1345, 105.8625),
    "Pantai Batu Saung": (-6.1258, 105.8450),
    "Pantai Marina": (-6.1454, 105.8500),
    "Pantai Sangiang": (-5.9535, 105.8565),

    # Carita & Labuan (Pandeglang)
    "Pantai Carita": (-6.1305, 105.8525),
    "Pantai Pandan Carita": (-6.1250, 105.8450),
    "Pantai Caringin": (-6.3533, 105.8150),
    "Pantai Labuan": (-6.3720, 105.8050),

    # Panimbang & Tanjung Lesung (Pandeglang)
    "Pantai Tanjung Lesung": (-6.4785, 105.6565),
    "Pantai Lalassa": (-6.4832, 105.6442),
    "Pantai Cipenyu": (-6.4915, 105.6415),
    "Pantai Batu Hideung": (-6.5185, 105.6310),
    "Pantai Teluk Lada": (-6.5068, 105.7450),

    # Sumur & Ujung Kulon (Pandeglang)
    "Pantai Ciputih": (-6.6585, 105.5255),
    "Pantai Pulau Umang": (-6.64065, 105.58436),
    "Pantai Ujung Kulon": (-6.7508, 105.3288),

    # Lebak Selatan (Malingping, Wanasalam, Cihara, Panggarangan, Bayah, Cilograng)
    "Pantai Binuangeun": (-6.8387, 105.8852),
    "Pantai Bagedur": (-6.9038, 106.0125),
    "Pantai Pasir Putih Cihara": (-6.8464, 106.0692),
    "Pantai Cibobos": (-6.8840, 106.1110),
    "Pantai Karang Songsong": (-6.88395, 106.11112),
    "Pantai Panggarangan": (-6.8785, 106.1478),
    "Pantai Sawarna": (-6.9930, 106.3180),
    "Pantai Ciantir": (-6.9868, 106.2888),
    "Pantai Legon Pari": (-6.9725, 106.2938),
    "Pantai Pulo Manuk": (-6.9890, 106.3050),
    "Pantai Goa Langir": (-6.9880, 106.3150),
    "Pantai Karang Taraje": (-6.9912, 106.3312),
    "Pantai Tanjung Layar": (-6.9943, 106.3072),
    "Pantai Citarate": (-6.9878, 106.3821),
    "Pantai Cibareno": (-6.9789, 106.3972),

    # Serang Utara (Pontang, Tanara, Tirtayasa, Bojonegara)
    "Pantai Pontang": (-5.9618, 106.2088),
    "Pantai Tanara": (-5.9538, 106.2488),
    "Pantai Lontar": (-5.9688, 106.2965),
    "Pantai Karang Pamulang": (-6.0028, 105.9618),

    # Cilegon (Pulomerak)
    "Pantai Pulorida": (-5.9275, 105.9818),
    "Pantai Pulau Merak Kecil": (-5.9388, 105.9948),
    "Pantai Pulau Merak Besar": (-5.9308, 105.9868),

    # Tangerang (Pakuhaji, Mauk, Kronjo, Teluknaga, Kosambi)
    "Pantai Pakuhaji": (-5.9968, 106.5650),
    "Pantai Tanjung Kait": (-6.0058, 106.4488),
    "Pantai Pulau Cangkir": (-6.0025, 106.4190),
    "Pantai Tanjung Pasir": (-6.0028, 106.6808),
    "Pantai Tanjung Burung": (-5.9965, 106.6560),
    "Pantai Dadap": (-6.0505, 106.7025),
}


def generate_geojson_circle(lon, lat, radius_km=0.9, num_points=16):
    coords = []
    for i in range(num_points + 1):
        angle = 2 * math.pi * i / num_points
        dx = radius_km / (111.32 * math.cos(math.radians(lat))) * math.cos(angle)
        dy = radius_km / 110.574 * math.sin(angle)
        coords.append([lon + dx, lat + dy])
    return [coords]


def update_beach_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for beach_name, (new_lat, new_lon) in EXACT_BEACH_COORDINATES.items():
        if beach_name in data:
            data[beach_name]['latitude'] = new_lat
            data[beach_name]['longitude'] = new_lon
            updated += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return updated


def update_recommendations_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for item in data:
        beach_name = item.get('pantai') or item.get('Pantai', '')
        if beach_name in EXACT_BEACH_COORDINATES:
            new_lat, new_lon = EXACT_BEACH_COORDINATES[beach_name]
            item['latitude'] = new_lat
            item['longitude'] = new_lon
            updated += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return updated


def update_geojson(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        beach_name = props.get('Pantai', '')
        if beach_name in EXACT_BEACH_COORDINATES:
            new_lat, new_lon = EXACT_BEACH_COORDINATES[beach_name]
            props['latitude'] = new_lat
            props['longitude'] = new_lon
            feature['geometry'] = {
                'type': 'Polygon',
                'coordinates': generate_geojson_circle(new_lon, new_lat)
            }
            updated += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

    return updated


def update_csv(filepath):
    if not os.path.exists(filepath):
        return 0

    rows = []
    fieldnames = None
    updated = 0

    with open(filepath, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            beach_name = row.get('Pantai', '')
            if beach_name in EXACT_BEACH_COORDINATES:
                new_lat, new_lon = EXACT_BEACH_COORDINATES[beach_name]
                row['latitude'] = str(new_lat)
                row['longitude'] = str(new_lon)
                updated += 1
            rows.append(row)

    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return updated


def main():
    print("=" * 60)
    print("MEMPERBAIKI 51 KOORDINAT PANTAI BANTEN (V3 FINAL)")
    print("=" * 60)

    n1 = update_beach_json('output/banten_water_quality_beach.json')
    print(f"✓ banten_water_quality_beach.json ({n1} pantai)")

    n2 = update_recommendations_json('output/banten_beach_recommendations.json')
    print(f"✓ banten_beach_recommendations.json ({n2} pantai)")

    n3 = update_geojson('output/banten_coastal_beaches.geojson')
    print(f"✓ banten_coastal_beaches.geojson ({n3} pantai)")

    n4 = update_csv('output/banten_water_quality_beach.csv')
    print(f"✓ banten_water_quality_beach.csv ({n4} pantai)")

    print("\nRegenerating Folium HTML maps...")
    subprocess.run(["python", "generate_maps.py"], check=True)

    print("=" * 60)
    print("SUKSES! Semua 51 pantai kini memiliki koordinat pesisir yang presisi.")
    print("=" * 60)


if __name__ == '__main__':
    main()
