"""
Model_Water_Quality.py — Analisis Kualitas Air Pesisir Banten per Kecamatan

Menggunakan citra satelit Sentinel-2 (openEO CDSE) untuk mendeteksi:
- Kekeruhan air (NDTI - Turbidity)
- Konsentrasi Klorofil-a (NDCI - Chlorophyll-a)
- Total Suspended Solids (TSS) & CDOM proxy
- Klasifikasi status kualitas air (SEHAT, SEDANG, TIDAK SEHAT) per kecamatan pesisir Banten.
- Perbandingan temporal tahun 2017 vs 2026.
"""

import os
import sys
import glob
import shutil
import tempfile
import time
import json
import argparse
import joblib
from datetime import datetime

import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
import rioxarray
import folium
from folium import plugins
from shapely.geometry import mapping
from sklearn.ensemble import RandomForestClassifier

# ---------------------------------------------------------------------------
# Konstanta Konfigurasi
# ---------------------------------------------------------------------------
YEAR_T1 = 2017
YEAR_T2 = 2026

DRY_SEASON_START = 5  # Mei
DRY_SEASON_END = 10    # Oktober

SCALE_EXPORT = 30      # Resolusi analisis spasial (30m)
GADM_PATH = "data/gadm41_IDN.gpkg"
COMPOSITE_DIR = "data/composites"
OUTPUT_DIR = "output"

# Threshold Kualitas Air (Kondisi Fisik-Kimiawi Air Pesisir)
NDTI_TURBID_THRESHOLD = 0.05       # NDTI > 0.05 -> Sangat Keruh (Tidak Sehat)
NDCI_BLOOM_THRESHOLD = 0.08        # NDCI > 0.08 -> Blooming Alga (Tidak Sehat)
NDCI_LOW_THRESHOLD = -0.02         # NDCI <= -0.02 -> Sangat Jernih/Rendah Nutrisi
NDTI_CLEAR_THRESHOLD = -0.05       # NDTI <= -0.05 -> Sangat Jernih

# ---------------------------------------------------------------------------
# 1. Ekstraksi Spasial Kecamatan Pesisir Banten
# ---------------------------------------------------------------------------
def load_banten_coastal_kecamatans(gadm_path=GADM_PATH, buffer_meters=3000, min_water_area_ha=10.0, return_land_geom=False):
    """
    Memuat batas administrasi kecamatan GADM, menyaring wilayah Banten,
    dan menghitung poligon perairan pesisir untuk masing-masing kecamatan.
    
    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame kecamatan pesisir dengan kolom geometry berisi zona air laut.
    """
    print("\n[STEP 1] Mengekstrak data batas wilayah kecamatan pesisir Banten...")
    if not os.path.exists(gadm_path):
        raise FileNotFoundError(f"File GADM tidak ditemukan di {gadm_path}. Silakan unduh terlebih dahulu.")
        
    # Load ADM_3 (Kecamatan)
    t0 = time.time()
    gdf = gpd.read_file(gadm_path, layer="ADM_ADM_3")
    print(f"  GADM ADM_3 dimuat dalam {time.time() - t0:.1f}s")
    
    # Filter Banten dan tetangga terdekat (untuk memotong buffer daratan secara akurat)
    banten = gdf[gdf["NAME_1"] == "Banten"].copy()
    neighbors = gdf[gdf["NAME_1"].isin(["Banten", "Jawa Barat", "Jakarta Raya", "Dki Jakarta"])].copy()
    
    # Proyeksikan ke UTM 48S (EPSG:32748) untuk akurasi buffer dalam meter
    print("  Memproyeksikan batas wilayah ke UTM Zone 48S...")
    banten_utm = banten.to_crs(epsg=32748)
    neighbors_utm = neighbors.to_crs(epsg=32748)
    
    # Gabungkan seluruh daratan Banten dan tetangganya sebagai masker daratan
    print("  Membuat gabungan geometri darat (land mask)...")
    land_geom = neighbors_utm.union_all()
    
    coastal_rows = []
    
    print("  Menghitung zona laut pesisir per kecamatan...")
    for idx, row in banten_utm.iterrows():
        geom = row.geometry
        name_3 = row["NAME_3"]
        name_2 = row["NAME_2"]
        gid_3 = row["GID_3"]
        
        # Buffer keluar dari batas kecamatan sejauh 3 km
        buffered = geom.buffer(buffer_meters)
        
        # Kurangi daratan untuk menyisakan bagian laut saja
        water_zone = buffered.difference(land_geom)
        
        # Hitung luas zona laut dalam hektar
        water_area_ha = water_zone.area / 10000.0
        
        # Hanya masukkan kecamatan yang memiliki area laut pesisir signifikan
        if water_area_ha >= min_water_area_ha:
            # Simpan original land geometry dalam WKT atau objek shapely untuk visualisasi nanti
            coastal_rows.append({
                "GID_3": gid_3,
                "Kabupaten_Kota": name_2,
                "Kecamatan": name_3,
                "water_area_ha": water_area_ha,
                "land_geom": geom,       # Batas darat kecamatan (original)
                "geometry": water_zone   # Zona laut pesisir kecamatan (sebagai active geometry)
            })
            
    # Buat GeoDataFrame baru
    coastal_gdf = gpd.GeoDataFrame(coastal_rows, crs="EPSG:32748")
    
    # Kembalikan ke koordinat geografis (EPSG:4326) untuk analisis citra satelit
    coastal_gdf = coastal_gdf.to_crs(epsg=4326)
    
    # Pastikan land_geom juga dikonversi ke EPSG:4326
    coastal_gdf["land_geom"] = coastal_gdf["land_geom"].apply(lambda g: gpd.GeoSeries([g], crs="EPSG:32748").to_crs(epsg=4326).iloc[0])
    
    print(f"  Ditemukan {len(coastal_gdf)} kecamatan pesisir dari total {len(banten)} kecamatan di Banten.")
    if return_land_geom:
        return coastal_gdf, land_geom
    return coastal_gdf

# ---------------------------------------------------------------------------
# 1b. Ekstraksi Spasial Pantai Pesisir Banten
# ---------------------------------------------------------------------------
def load_banten_coastal_beaches(land_geom_utm, buffer_meters=1000):
    """
    Memuat data pantai pesisir Banten, membuffer titiknya,
    dan memotong dengan land_geom_utm untuk menyisakan wilayah air saja.
    """
    print("\n[STEP 1b] Mengekstrak data batas wilayah pantai pesisir Banten...")
    
    beaches = [
        {"name": "Pantai Anyer", "Kecamatan": "Anyar", "Kabupaten_Kota": "Serang", "lat": -6.0465, "lon": 105.8850},
        {"name": "Pantai Carita", "Kecamatan": "Carita", "Kabupaten_Kota": "Pandeglang", "lat": -6.1305, "lon": 105.8427},
        {"name": "Pantai Tanjung Lesung", "Kecamatan": "Panimbang", "Kabupaten_Kota": "Pandeglang", "lat": -6.4785, "lon": 105.6565},
        {"name": "Pantai Sawarna", "Kecamatan": "Bayah", "Kabupaten_Kota": "Lebak", "lat": -6.9930, "lon": 106.3180},
        {"name": "Pantai Bagedur", "Kecamatan": "Malingping", "Kabupaten_Kota": "Lebak", "lat": -6.9038, "lon": 106.0125},
        {"name": "Pantai Karang Bolong", "Kecamatan": "Cinangka", "Kabupaten_Kota": "Serang", "lat": -6.1082, "lon": 105.8569},
        {"name": "Pantai Ciputih", "Kecamatan": "Sumur", "Kabupaten_Kota": "Pandeglang", "lat": -6.6575, "lon": 105.5180},
        {"name": "Pantai Pulau Umang", "Kecamatan": "Sumur", "Kabupaten_Kota": "Pandeglang", "lat": -6.6715, "lon": 105.5875},
        {"name": "Pantai Sambolo", "Kecamatan": "Anyar", "Kabupaten_Kota": "Serang", "lat": -6.0712, "lon": 105.8812},
        {"name": "Pantai Pasir Putih Sirih", "Kecamatan": "Anyar", "Kabupaten_Kota": "Serang", "lat": -6.0825, "lon": 105.8805},
        {"name": "Pantai Marbella", "Kecamatan": "Anyar", "Kabupaten_Kota": "Serang", "lat": -6.0620, "lon": 105.8825},
        {"name": "Pantai Florida Indah", "Kecamatan": "Cinangka", "Kabupaten_Kota": "Serang", "lat": -6.1345, "lon": 105.8670},
        {"name": "Pantai Jambu", "Kecamatan": "Cinangka", "Kabupaten_Kota": "Serang", "lat": -6.1158, "lon": 105.8640},
        {"name": "Pantai Lontar", "Kecamatan": "Pontang", "Kabupaten_Kota": "Serang", "lat": -6.0102, "lon": 106.2730},
        {"name": "Pantai Tanjung Pasir", "Kecamatan": "Teluknaga", "Kabupaten_Kota": "Tangerang", "lat": -6.0150, "lon": 106.6850},
        {"name": "Pantai Tanjung Kait", "Kecamatan": "Mauk", "Kabupaten_Kota": "Tangerang", "lat": -6.0195, "lon": 106.4520},
        {"name": "Pantai Binuangeun", "Kecamatan": "Wanasalam", "Kabupaten_Kota": "Lebak", "lat": -6.8290, "lon": 105.9030},
        {"name": "Pantai Karang Taraje", "Kecamatan": "Bayah", "Kabupaten_Kota": "Lebak", "lat": -6.9912, "lon": 106.3312},
        {"name": "Pantai Sangiang", "Kecamatan": "Anyar", "Kabupaten_Kota": "Serang", "lat": -5.9535, "lon": 105.8565},
        {"name": "Pantai Pasir Putih Florida", "Kecamatan": "Cinangka", "Kabupaten_Kota": "Serang", "lat": -6.1265, "lon": 105.8645}
    ]
    
    from shapely.geometry import Point
    df = pd.DataFrame(beaches)
    geometry = [Point(xy) for xy in zip(df['lon'], df['lat'])]
    beaches_gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    
    # Proyeksikan ke UTM 48S
    beaches_utm = beaches_gdf.to_crs(epsg=32748)
    
    coastal_beaches = []
    for idx, row in beaches_utm.iterrows():
        point_geom = row.geometry
        name = row["name"]
        kec = row["Kecamatan"]
        kab = row["Kabupaten_Kota"]
        lat = row["lat"]
        lon = row["lon"]
        
        # Buffer 1 km
        buffered = point_geom.buffer(buffer_meters)
        
        # Kurangkan daratan
        water_zone = buffered.difference(land_geom_utm)
        
        if not water_zone.is_empty:
            coastal_beaches.append({
                "Pantai": name,
                "Kecamatan": kec,
                "Kabupaten_Kota": kab,
                "latitude": lat,
                "longitude": lon,
                "geometry": water_zone
            })
            
    coastal_beaches_gdf = gpd.GeoDataFrame(coastal_beaches, crs="EPSG:32748")
    coastal_beaches_gdf = coastal_beaches_gdf.to_crs(epsg=4326)
    
    print(f"  Ditemukan {len(coastal_beaches_gdf)} lokasi pantai pesisir Banten yang siap dianalisis.")
    return coastal_beaches_gdf

def generate_beach_explanation(beach_name, kec_name, status, ndti, ndci):
    if status == "SEHAT":
        return f"Kualitas air di {beach_name} ({kec_name}) tergolong **SEHAT** (Bersih). Kondisi perairan pantai sangat bersih dengan kekeruhan rendah (NDTI: {ndti:.4f}) and klorofil-a (NDCI: {ndci:.4f}) yang normal, menjadikannya sangat aman dan nyaman untuk kegiatan pariwisata atau berenang."
    elif status == "SEDANG":
        return f"Kualitas air di {beach_name} ({kec_name}) berada dalam kondisi **SEDANG**. Perairan pantai cukup bersih namun tingkat kekeruhan (NDTI: {ndti:.4f}) atau klorofil-a (NDCI: {ndci:.4f}) menunjukkan nilai ambang batas wajar. Pengunjung dihimbau tetap menjaga kebersihan pantai sekitar."
    else: # TIDAK SEHAT
        reasons = []
        if ndti > 0.05:
            reasons.append(f"tingginya kekeruhan air (NDTI: {ndti:.4f}) akibat limpasan sedimen darat")
        if ndci > 0.08:
            reasons.append(f"kadar klorofil-a yang tinggi (NDCI: {ndci:.4f}) yang menandakan penumpukan nutrien/blooming alga")
        reason_str = " dan ".join(reasons) if reasons else "penurunan baku mutu air laut pesisir"
        return f"Kualitas air di {beach_name} ({kec_name}) tergolong **TIDAK SEHAT** (Tercemar). Analisis menunjukkan {reason_str}. Disarankan untuk membatasi aktivitas kontak langsung seperti berenang di sekitar perairan pantai ini."

# ---------------------------------------------------------------------------
# 2. openEO — Download Composite Sentinel-2 dengan Band B05 (Red Edge)
# ---------------------------------------------------------------------------
def get_sentinel2_water_composite_job(connection, bbox, year, scale_export=SCALE_EXPORT):
    """
    Membuat datacube composite Sentinel-2 bebas awan dengan band tambahan B05
    di server openEO untuk parameter kualitas air.
    """
    start_date = f"{year}-{DRY_SEASON_START:02d}-01"
    end_date   = f"{year}-{DRY_SEASON_END:02d}-31"

    extent = {
        "west": bbox[0], "south": bbox[1],
        "east": bbox[2], "north": bbox[3],
        "crs": "EPSG:4326",
    }

    # Memuat koleksi Sentinel-2 L2A dengan menyertakan B05 (Red Edge 1)
    cube = connection.load_collection(
        "SENTINEL2_L2A",
        spatial_extent=extent,
        temporal_extent=[start_date, end_date],
        bands=["B02", "B03", "B04", "B05", "B08", "B11", "SCL"],
    )

    # Cloud masking berdasarkan band SCL
    scl = cube.band("SCL")
    cloud_mask = ~(
        (scl == 1) | (scl == 3) | (scl == 8) |
        (scl == 9) | (scl == 10) | (scl == 11)
    )
    masked_cube = cube.mask(cloud_mask)

    res_deg = scale_export / 111320.0
    resampled = masked_cube.resample_spatial(
        resolution=res_deg, projection=4326, method="bilinear",
    )

    # Reduksi temporal dengan median reducer untuk composite bebas awan
    composite = resampled.reduce_dimension(reducer="median", dimension="t")
    
    # Filter bands untuk output GeoTIFF (menyimpan band spektral utama)
    return composite.filter_bands(["B02", "B03", "B04", "B05", "B08", "B11"])


def download_banten_composite(connection, bbox, year, output_path, scale_export=SCALE_EXPORT):
    """Mengunduh composite GeoTIFF Banten dengan openEO batch job."""
    if os.path.exists(output_path):
        print(f"  Composite untuk tahun {year} sudah tersedia di: {output_path}")
        return

    print(f"  Mengajukan batch job openEO untuk composite Banten tahun {year}...")
    cube = get_sentinel2_water_composite_job(connection, bbox, year, scale_export)
    cube = cube.save_result("GTiff")

    job = cube.create_job(title=f"banten_water_quality_{year}")
    job.start_and_wait()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        job.download_results(tmpdir)
        downloaded = glob.glob(os.path.join(tmpdir, "*.tif"))
        if downloaded:
            shutil.move(downloaded[0], output_path)
            print(f"  Composite berhasil disimpan ke: {output_path}")
        else:
            raise RuntimeError("Gagal mengunduh file TIFF hasil analisis dari openEO.")

# ---------------------------------------------------------------------------
# 3. Pengolahan Data Raster & Indeks Spektral Kualitas Air
# ---------------------------------------------------------------------------
def load_composite_as_dataset(tif_path):
    """
    Membaca GeoTIFF composite dan memetakan nama band berdasarkan jenis file.
    """
    raw = rioxarray.open_rasterio(tif_path)
    
    # Cek apakah ini file baru hasil download dengan B05 atau file lama
    filename = os.path.basename(tif_path)
    if "Water" in filename:
        band_names = ["B02", "B03", "B04", "B05", "B08", "B11"]
        print(f"  Memuat composite air pesisir (dengan B05 Red-Edge): {filename}")
    else:
        # File lama dari Model_Earth.ipynb (tidak ada B05, band 4 adalah B08)
        band_names = ["B02", "B03", "B04", "B08", "B11", "B12"]
        print(f"  Memuat composite standar (tanpa B05 Red-Edge, menggunakan fallback): {filename}")
        
    ds = xr.Dataset({
        name: raw.sel(band=i + 1).drop_vars("band")
        for i, name in enumerate(band_names)
    })
    ds = ds.rio.write_crs("EPSG:4326")
    return ds


def calculate_water_quality_indices(ds):
    """
    Menghitung indeks kualitas air pesisir:
    - NDWI / MNDWI (Deteksi Air)
    - NDTI (Kekeruhan/Turbidity)
    - NDCI (Klorofil-a / Alga)
    - TSS Proxy (Total Suspended Solids)
    - CDOM Proxy (Organic Matter)
    """
    blue  = ds["B02"]
    green = ds["B03"]
    red   = ds["B04"]
    eps   = 1e-10

    # 1. MNDWI / NDWI untuk water masking
    if "B11" in ds:
        swir1 = ds["B11"]
        ds["MNDWI"] = (green - swir1) / (green + swir1 + eps)
    else:
        nir = ds["B08"]
        ds["MNDWI"] = (green - nir) / (green + nir + eps)

    # 2. NDTI (Normalized Difference Turbidity Index) -> Kekeruhan
    ds["NDTI"] = (green - red) / (green + red + eps)

    # 3. NDCI (Normalized Difference Chlorophyll Index) -> Klorofil-a
    if "B05" in ds:
        red_edge = ds["B05"]
        ds["NDCI"] = (red_edge - red) / (red_edge + red + eps)
    else:
        # Fallback jika B05 tidak ada: gunakan Normalized Difference Green-Blue
        ds["NDCI"] = (green - blue) / (green + blue + eps)

    # 4. TSS Proxy (Total Suspended Solids)
    ds["TSS"] = red / (green + eps)

    # 5. CDOM Proxy
    ds["CDOM"] = green / (blue + eps)

    return ds


def classify_water_pixels_threshold(ds):
    """
    Mengklasifikasikan kualitas air piksel demi piksel menggunakan threshold:
    0 = Daratan/Bukan air
    1 = TIDAK SEHAT (Sangat Keruh)
    2 = TIDAK SEHAT (Blooming Alga / Eutrofik)
    3 = SEDANG (Rendah Nutrisi / Sangat Jernih)
    4 = SEHAT (Kondisi Optimum)
    5 = SEDANG (Kondisi Sedang/Lainnya)
    """
    mndwi = ds["MNDWI"].values
    ndti  = ds["NDTI"].values
    ndci  = ds["NDCI"].values
    
    # Definisikan masker air (MNDWI > 0.0)
    water_mask = (mndwi > 0.0) & (~np.isnan(mndwi))
    
    # Array hasil klasifikasi
    classes = np.zeros_like(mndwi, dtype=np.uint8)
    
    # 1. Kekeruhan Tinggi (Turbid / Tidak Sehat)
    turbid_mask = water_mask & (ndti > NDTI_TURBID_THRESHOLD)
    classes[turbid_mask] = 1
    
    # 2. Blooming Alga (Eutrofik / Tidak Sehat)
    bloom_mask = water_mask & (ndci > NDCI_BLOOM_THRESHOLD) & (classes == 0)
    classes[bloom_mask] = 2
    
    # 3. Rendah Nutrisi (Sangat Jernih / Sedang)
    clear_low_nut_mask = water_mask & (ndci <= NDCI_LOW_THRESHOLD) & (ndti <= NDTI_CLEAR_THRESHOLD) & (classes == 0)
    classes[clear_low_nut_mask] = 3
    
    # 4. Kondisi Optimum (Sehat)
    optimum_mask = (
        water_mask & 
        (ndti > NDTI_CLEAR_THRESHOLD) & (ndti <= NDTI_TURBID_THRESHOLD) &
        (ndci > NDCI_LOW_THRESHOLD) & (ndci <= NDCI_BLOOM_THRESHOLD) &
        (classes == 0)
    )
    classes[optimum_mask] = 4
    
    # 5. Sedang (Kondisi Sedang / Lainnya)
    sedang_mask = water_mask & (classes == 0)
    classes[sedang_mask] = 5
    
    return classes


# ---------------------------------------------------------------------------
# 4. Supervised Random Forest Classifier untuk Klasifikasi Kualitas Air
# ---------------------------------------------------------------------------
def train_water_quality_rf(ds, threshold_classes):
    """
    Melatih model Random Forest menggunakan hasil klasifikasi threshold
    sebagai training data untuk merapikan klasifikasi spasial.
    """
    # Filter hanya untuk piksel air (kelas > 0)
    water_mask = threshold_classes > 0
    
    features_bands = ["NDVI" if "NDVI" in ds else "B08", "B02", "B03", "B04", "NDTI", "NDCI", "TSS", "CDOM"]
    # Filter bands yang benar-benar ada di dataset
    features_bands = [f for f in features_bands if f in ds]
    
    features_list = [ds[band].values[water_mask] for band in features_bands]
    X = np.stack(features_list, axis=1)
    
    y = threshold_classes[water_mask]
    
    # Buang NaN
    valid = ~np.isnan(X).any(axis=1)
    X = X[valid]
    y = y[valid]
    
    if len(X) < 100:
        print("  Warning: Piksel air terlalu sedikit untuk melatih Random Forest. Menggunakan klasifikasi threshold.")
        return None
        
    print(f"  Melatih model Random Forest pada {len(X)} sampel piksel air...")
    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42)
    rf.fit(X, y)
    
    # Prediksi seluruh grid air
    all_features = [ds[band].values for band in features_bands]
    stacked = np.stack(all_features, axis=-1)
    y_dim, x_dim, n_feats = stacked.shape
    flat_all = stacked.reshape(-1, n_feats)
    flat_water_mask = water_mask.reshape(-1)
    
    valid_flat = flat_water_mask & (~np.isnan(flat_all).any(axis=1))
    
    predicted_flat = np.zeros(y_dim * x_dim, dtype=np.uint8)
    if np.sum(valid_flat) > 0:
        predicted_flat[valid_flat] = rf.predict(flat_all[valid_flat])
        
    predicted_classes = predicted_flat.reshape(y_dim, x_dim)
    return predicted_classes

# ---------------------------------------------------------------------------
# 5. Pipeline Utama Analisis per Kecamatan
# ---------------------------------------------------------------------------
def compute_pixel_area_ha(ds):
    """Menghitung luas area satu piksel dalam hektar."""
    res_x = abs(ds.rio.transform()[0])
    res_y = abs(ds.rio.transform()[4])
    # Konversi derajat ke meter (pendekatan ekuator/Banten: 1 derajat ~ 111.32 km)
    return (res_x * 111320.0) * (res_y * 111320.0) / 10000.0


def analyze_kecamatan_water_quality(ds, geom, pixel_area_ha):
    """
    Melakukan ekstraksi, klasifikasi, dan perhitungan statistik kualitas air
    untuk geometri kecamatan tertentu.
    """
    try:
        # Potong raster dataset sesuai poligon air kecamatan pesisir
        clipped_ds = ds.rio.clip([geom], crs="EPSG:4326", all_touched=True)
    except Exception as e:
        # Jika tidak bersinggungan secara spasial
        return None
        
    # Hitung indeks
    clipped_ds = calculate_water_quality_indices(clipped_ds)
    
    # Deteksi air dan buat threshold classes
    threshold_classes = classify_water_pixels_threshold(clipped_ds)
    
    # Jalankan Random Forest untuk memperhalus (jika piksel mencukupi)
    final_classes = train_water_quality_rf(clipped_ds, threshold_classes)
    if final_classes is None:
        final_classes = threshold_classes
        
    # Kumpulkan statistik
    # Kelas: 1=Keruh (Tidak Sehat), 2=Algae (Tidak Sehat), 3=Clear/Low (Sedang), 4=Optimum (Sehat), 5=Sedang/Lainnya
    total_water_pixels = np.sum(final_classes > 0)
    
    if total_water_pixels == 0:
        return None
        
    unhealthy_pixels = np.sum((final_classes == 1) | (final_classes == 2))
    healthy_pixels = np.sum(final_classes == 4)
    moderate_pixels = np.sum((final_classes == 3) | (final_classes == 5))
    
    water_area_ha = float(total_water_pixels * pixel_area_ha)
    healthy_ha = float(healthy_pixels * pixel_area_ha)
    moderate_ha = float(moderate_pixels * pixel_area_ha)
    unhealthy_ha = float(unhealthy_pixels * pixel_area_ha)
    
    pct_healthy = (healthy_ha / water_area_ha * 100) if water_area_ha > 0 else 0
    pct_moderate = (moderate_ha / water_area_ha * 100) if water_area_ha > 0 else 0
    pct_unhealthy = (unhealthy_ha / water_area_ha * 100) if water_area_ha > 0 else 0
    
    # Rata-rata nilai indeks pada piksel air
    water_mask = final_classes > 0
    mean_ndti = float(np.nanmean(clipped_ds["NDTI"].values[water_mask]))
    mean_ndci = float(np.nanmean(clipped_ds["NDCI"].values[water_mask]))
    mean_tss = float(np.nanmean(clipped_ds["TSS"].values[water_mask]))
    mean_cdom = float(np.nanmean(clipped_ds["CDOM"].values[water_mask]))
    
    # Tentukan status kualitas air kecamatan
    # SEHAT jika area sehat > 50%
    # TIDAK SEHAT jika area tidak sehat > 30%
    if pct_healthy > 50.0:
        status = "SEHAT"
    elif pct_unhealthy > 30.0:
        status = "TIDAK SEHAT"
    else:
        status = "SEDANG"
        
    return {
        "water_area_ha": round(water_area_ha, 2),
        "healthy_ha": round(healthy_ha, 2),
        "moderate_ha": round(moderate_ha, 2),
        "unhealthy_ha": round(unhealthy_ha, 2),
        "pct_healthy": round(pct_healthy, 1),
        "pct_moderate": round(pct_moderate, 1),
        "pct_unhealthy": round(pct_unhealthy, 1),
        "mean_ndti": round(mean_ndti, 4),
        "mean_ndci": round(mean_ndci, 4),
        "mean_tss": round(mean_tss, 4),
        "mean_cdom": round(mean_cdom, 4),
        "status": status
    }

# ---------------------------------------------------------------------------
# 6. Pembuatan Peta Visualisasi Interaktif Folium
# ---------------------------------------------------------------------------
def create_folium_visualization(coastal_gdf, results_df, output_path, beaches_gdf=None, beaches_results_df=None):
    """
    Membuat peta interaktif Folium yang memvisualisasikan data kualitas air pesisir Banten.
    """
    print("\n[STEP 5] Membuat peta interaktif Folium...")
    
    # Gabungkan data spasial dengan hasil analisis 2026
    merged_gdf = coastal_gdf.merge(results_df, on=["Kabupaten_Kota", "Kecamatan"], how="inner")
    
    # Hitung koordinat tengah Banten
    centroid = merged_gdf.union_all().centroid
    map_center = [centroid.y, centroid.x]
    
    m = folium.Map(location=map_center, zoom_start=10, tiles="cartodbpositron")
    
    # Tambahkan fullscreen control & layer control
    plugins.Fullscreen(position="topright", title="Fullscreen", title_cancel="Exit").add_to(m)
    
    # Pemetaan Warna berdasarkan Status Kualitas Air
    color_map = {
        "SEHAT": "#2ecc71",      # Hijau
        "SEDANG": "#f1c40f",     # Kuning
        "TIDAK SEHAT": "#e74c3c"  # Merah
    }
    
    # 1. Layer Batas Darat Kecamatan (Light Grey)
    land_layer = folium.FeatureGroup(name="Darat Kecamatan (Administratif)", show=True)
    for idx, row in merged_gdf.iterrows():
        # Buat geojson untuk batas darat
        geojson_land = mapping(row["land_geom"])
        
        popup_html = f"""
        <div style='font-family: Arial; font-size: 12px; width: 200px;'>
            <b>Kecamatan:</b> {row['Kecamatan']}<br/>
            <b>Kabupaten/Kota:</b> {row['Kabupaten_Kota']}<br/>
        </div>
        """
        
        folium.GeoJson(
            geojson_land,
            style_function=lambda x: {
                "fillColor": "#bdc3c7",
                "color": "#7f8c8d",
                "weight": 1.0,
                "fillOpacity": 0.15
            },
            highlight_function=lambda x: {
                "fillOpacity": 0.35,
                "weight": 1.5
            },
            tooltip=f"{row['Kecamatan']}, {row['Kabupaten_Kota']}"
        ).add_to(land_layer)
    land_layer.add_to(m)
    
    # 2. Layer Zona Air Pesisir (Warna Hijau/Kuning/Merah)
    water_layer = folium.FeatureGroup(name="Kualitas Air Pesisir (3 km dari Pantai)", show=True)
    for idx, row in merged_gdf.iterrows():
        geojson_water = mapping(row["geometry"])
        status_2026 = row["Status_Kualitas_2026"]
        color = color_map.get(status_2026, "#7f8c8d")
        
        tooltip_text = f"Kecamatan {row['Kecamatan']} ({status_2026})"
        
        popup_html = f"""
        <div style='font-family: Arial, sans-serif; font-size: 13px; width: 300px; padding: 5px;'>
            <h4 style='margin: 0 0 5px 0; color: #2c3e50;'>Kecamatan {row['Kecamatan']}</h4>
            <span style='font-size: 11px; color: #7f8c8d;'>{row['Kabupaten_Kota']}</span>
            <hr style='margin: 8px 0;'/>
            <b>Luas Zona Air:</b> {row['Luas_Air_2026_Ha']:.1f} Ha<br/>
            <b>Status Kualitas (2026):</b> 
            <span style='color: {color}; font-weight: bold;'>{status_2026}</span><br/>
            <b>Perubahan (2017 -> 2026):</b> 
            <span style='font-weight: bold;'>{row['Tren_Kualitas']}</span><br/>
            <hr style='margin: 8px 0;'/>
            <div style='font-size: 11px; line-height: 1.4; background-color: #f8f9fa; padding: 6px; border-left: 3px solid #3498db; margin: 5px 0;'>
                <b>Analisis Kondisi:</b><br/>{row.get('penjelasan_kualitas', 'Tidak ada data penjelasan.')}
            </div>
            <hr style='margin: 8px 0;'/>
            <table style='width: 100%; font-size: 12px;'>
                <tr style='background: #f8f9fa;'>
                    <td>🟢 <b>Sehat:</b></td>
                    <td style='text-align: right;'>{row['Pct_Sehat_2026']:.1f}% ({row['Sehat_2026_Ha']:.1f} Ha)</td>
                </tr>
                <tr>
                    <td>🟡 <b>Sedang:</b></td>
                    <td style='text-align: right;'>{row['Pct_Sedang_2026']:.1f}% ({row['Sedang_2026_Ha']:.1f} Ha)</td>
                </tr>
                <tr style='background: #f8f9fa;'>
                    <td>🔴 <b>Tidak Sehat:</b></td>
                    <td style='text-align: right;'>{row['Pct_TidakSehat_2026']:.1f}% ({row['TidakSehat_2026_Ha']:.1f} Ha)</td>
                </tr>
            </table>
            <hr style='margin: 8px 0;'/>
            <div style='font-size: 11px;'>
                <b>Mean NDTI (Turbidity):</b> {row['Mean_NDTI_2026']:.4f}<br/>
                <b>Mean NDCI (Chlorophyll):</b> {row['Mean_NDCI_2026']:.4f}<br/>
                <b>Mean TSS Proxy:</b> {row['Mean_TSS_2026']:.4f}
            </div>
        </div>
        """
        
        folium.GeoJson(
            geojson_water,
            style_function=lambda x, col=color: {
                "fillColor": col,
                "color": col,
                "weight": 1.5,
                "fillOpacity": 0.55
            },
            highlight_function=lambda x, col=color: {
                "fillOpacity": 0.85,
                "weight": 2.5
            },
            tooltip=tooltip_text
        ).add_child(folium.Popup(popup_html)).add_to(water_layer)
        
    water_layer.add_to(m)

    # 3. Layer Pantai Banten (Circle Markers & Buffer Polygons)
    if beaches_gdf is not None and beaches_results_df is not None:
        beach_layer = folium.FeatureGroup(name="Kualitas Air Pantai Banten (1 km)", show=True)
        merged_beaches = beaches_gdf.merge(beaches_results_df, on=["Pantai", "Kecamatan", "Kabupaten_Kota", "latitude", "longitude"], how="inner")
        
        for idx, row in merged_beaches.iterrows():
            geojson_beach_water = mapping(row["geometry"])
            status = row["Status_Kualitas_2026"]
            color = color_map.get(status, "#7f8c8d")
            
            tooltip_text = f"{row['Pantai']} ({status})"
            
            popup_html = f"""
            <div style='font-family: Arial, sans-serif; font-size: 13px; width: 300px; padding: 5px;'>
                <h4 style='margin: 0 0 5px 0; color: #2c3e50;'>{row['Pantai']}</h4>
                <span style='font-size: 11px; color: #7f8c8d;'>Kecamatan {row['Kecamatan']}, {row['Kabupaten_Kota']}</span>
                <hr style='margin: 8px 0;'/>
                <b>Status Kualitas (2026):</b> 
                <span style='color: {color}; font-weight: bold;'>{status}</span><br/>
                <b>Perubahan (2017 -> 2026):</b> 
                <span style='font-weight: bold;'>{row['Tren_Kualitas']}</span><br/>
                <hr style='margin: 8px 0;'/>
                <div style='font-size: 11px; line-height: 1.4; background-color: #f8f9fa; padding: 6px; border-left: 3px solid #3498db; margin: 5px 0;'>
                    <b>Analisis Kondisi:</b><br/>{row.get('penjelasan_kualitas', 'Tidak ada data penjelasan.')}
                </div>
                <hr style='margin: 8px 0;'/>
                <table style='width: 100%; font-size: 12px;'>
                    <tr style='background: #f8f9fa;'>
                        <td>🟢 <b>Sehat:</b></td>
                        <td style='text-align: right;'>{row['Pct_Sehat_2026']:.1f}%</td>
                    </tr>
                    <tr>
                        <td>🟡 <b>Sedang:</b></td>
                        <td style='text-align: right;'>{row['Pct_Sedang_2026']:.1f}%</td>
                    </tr>
                    <tr style='background: #f8f9fa;'>
                        <td>🔴 <b>Tidak Sehat:</b></td>
                        <td style='text-align: right;'>{row['Pct_TidakSehat_2026']:.1f}%</td>
                    </tr>
                </table>
                <hr style='margin: 8px 0;'/>
                <div style='font-size: 11px;'>
                    <b>Mean NDTI (Turbidity):</b> {row['Mean_NDTI_2026']:.4f}<br/>
                    <b>Mean NDCI (Chlorophyll):</b> {row['Mean_NDCI_2026']:.4f}<br/>
                    <b>Mean TSS Proxy:</b> {row['Mean_TSS_2026']:.4f}
                </div>
            </div>
            """
            
            # Map Marker untuk Pantai
            marker_color = "green" if status == "SEHAT" else "orange" if status == "SEDANG" else "red"
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                icon=folium.Icon(color=marker_color, icon="info-sign"),
                tooltip=row["Pantai"],
                popup=folium.Popup(popup_html, max_width=320)
            ).add_to(beach_layer)
            
            # Poligon Buffer Air Pantai
            folium.GeoJson(
                geojson_beach_water,
                style_function=lambda x, col=color: {
                    "fillColor": col,
                    "color": col,
                    "weight": 1.0,
                    "fillOpacity": 0.35
                },
                highlight_function=lambda x, col=color: {
                    "fillOpacity": 0.65,
                    "weight": 2.0
                },
                tooltip=tooltip_text
            ).add_child(folium.Popup(popup_html)).add_to(beach_layer)
            
        beach_layer.add_to(m)
    
    # Tambahkan Legenda Peta (HTML Control)
    legend_html = """
     <div style="position: fixed; 
                 bottom: 50px; left: 50px; width: 220px; height: 160px; 
                 border:2px solid grey; z-index:9999; font-size:12px;
                 background-color:white;
                 opacity: 0.9;
                 padding: 10px;
                 border-radius: 5px;
                 font-family: Arial, sans-serif;">
     <h4 style="margin:0 0 8px 0; font-size:13px; color:#2c3e50;">Kualitas Air Pesisir</h4>
     <div style="margin-bottom: 5px;"><i style="background:#2ecc71; width:28px; height:12px; float:left; margin-right:8px; opacity:0.7; border-radius: 2px;"></i>🟢 <b>SEHAT</b> (>50% Sehat)</div>
     <div style="margin-bottom: 5px;"><i style="background:#f1c40f; width:28px; height:12px; float:left; margin-right:8px; opacity:0.7; border-radius: 2px;"></i>🟡 <b>SEDANG</b> (Kondisi Sedang)</div>
     <div style="margin-bottom: 8px;"><i style="background:#e74c3c; width:28px; height:12px; float:left; margin-right:8px; opacity:0.7; border-radius: 2px;"></i>🔴 <b>TIDAK SEHAT</b> (>30% Unhealthy)</div>
     <hr style="margin: 5px 0;"/>
     <span style="font-size:10px; color:#7f8c8d;">Banten per Kecamatan (Sentinel-2)</span>
     </div>
     """
    m.get_root().html.add_child(folium.Element(legend_html))
    
    folium.LayerControl(position="topright").add_to(m)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    m.save(output_path)
    print(f"  Peta interaktif disimpan ke: {output_path}")

# ---------------------------------------------------------------------------
# 6b. Supervised Random Forest Classifier (Global Banten Model)
# ---------------------------------------------------------------------------
def train_global_rf_model(ds, combined_geom):
    """
    Melatih Model Random Forest global untuk kualitas air pesisir Banten
    menggunakan sampel piksel dari seluruh kecamatan pesisir.
    """
    print("\n[STEP 6] Melatih Model Random Forest Global untuk Kualitas Air Banten...")
    try:
        # Potong composite dengan batas laut gabungan seluruh Banten
        clipped_ds = ds.rio.clip([combined_geom], crs="EPSG:4326", all_touched=True)
    except Exception as e:
        print(f"  Error: Gagal memotong composite global ({e})")
        return None, None

    clipped_ds = calculate_water_quality_indices(clipped_ds)
    threshold_classes = classify_water_pixels_threshold(clipped_ds)

    water_mask = threshold_classes > 0
    features_bands = ["B02", "B03", "B04", "B08", "B11"]
    if "B05" in clipped_ds:
        features_bands.append("B05")
    features_bands.extend(["NDTI", "NDCI", "TSS", "CDOM"])

    features_bands = [f for f in features_bands if f in clipped_ds]
    print(f"  Fitur yang digunakan untuk Random Forest: {features_bands}")

    features_list = [clipped_ds[band].values[water_mask] for band in features_bands]
    X = np.stack(features_list, axis=1)
    y = threshold_classes[water_mask]

    # Bersihkan NaN
    valid = ~np.isnan(X).any(axis=1)
    X = X[valid]
    y = y[valid]

    print(f"  Total sampel piksel air global: {len(X)}")
    if len(X) < 1000:
        print("  Warning: Sampel terlalu sedikit untuk pelatihan model global.")
        return None, None

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix

    # Split 70% training, 30% testing
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    print("  Melatih model Random Forest Classifier (100 estimators, min_samples_leaf=5)...")
    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)

    y_pred = rf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    kappa = cohen_kappa_score(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred)

    importances = rf.feature_importances_.tolist()
    feat_imp = {band: round(imp, 4) for band, imp in zip(features_bands, importances)}

    print(f"  Akurasi Validasi Model: {acc:.2%}")
    print(f"  Koefisien Kappa        : {kappa:.4f}")
    print(f"  Confusion Matrix       :\n  {cm}")
    print(f"  Feature Importances    :\n  {feat_imp}")

    metrics = {
        "accuracy": round(float(acc), 4),
        "kappa": round(float(kappa), 4),
        "confusion_matrix": cm.tolist(),
        "feature_importances": feat_imp,
        "n_train_samples": int(len(X_train)),
        "n_test_samples": int(len(X_test)),
        "features_used": features_bands,
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    return rf, metrics

# ---------------------------------------------------------------------------
# 7. Fungsi Utama (Main Pipeline Execution)
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Analisis kualitas air pesisir Banten per kecamatan.")
    parser.add_argument("--skip-openeo", action="store_true", help="Skip download openEO, gunakan composite lokal.")
    parser.add_argument("--kecamatans", nargs="*", default=None, help="Pilih kecamatan tertentu untuk pengujian.")
    args = parser.parse_args()
    
    t_start = time.time()
    
    print("=" * 70)
    print("ANALISIS KUALITAS AIR PESISIR BANTEN PER KECAMATAN (SENTINEL-2)")
    print(f"Waktu Mulai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tahun Analisis: {YEAR_T1} vs {YEAR_T2}")
    print(f"Skip openEO: {args.skip_openeo}")
    print("=" * 70)
    
    # 1. Load data batas kecamatan pesisir Banten
    try:
        coastal_gdf, land_geom_utm = load_banten_coastal_kecamatans(return_land_geom=True)
    except Exception as exc:
        print(f"Error pada Step 1: {exc}")
        sys.exit(1)
        
    if args.kecamatans:
        selected_kec = [k for k in args.kecamatans]
        coastal_gdf = coastal_gdf[coastal_gdf["Kecamatan"].isin(selected_kec)].copy()
        print(f"  [TEST MODE] Memproses {len(coastal_gdf)} kecamatan pilihan saja: {selected_kec}")
        if len(coastal_gdf) == 0:
            print("  Error: Tidak ada kecamatan pilihan yang cocok dengan data pesisir.")
            sys.exit(1)
            
    # 2. Definisikan Bounding Box seluruh Banten (dalam EPSG:4326)
    # Gunakan geometri perairan pesisir gabungan untuk bbox yang pas
    combined_geom = coastal_gdf.union_all()
    bbox = combined_geom.bounds # [minx, miny, maxx, maxy]
    print(f"\n[STEP 2] Bounding Box perairan pesisir Banten: {bbox}")
    
    # 3. Hubungkan ke openEO jika tidak di-skip
    connection = None
    if not args.skip_openeo:
        try:
            import openeo
            print("\nConnecting to openEO CDSE...")
            connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
            connection.authenticate_oidc()
            print("  Koneksi openEO berhasil diautentikasi.")
        except Exception as exc:
            print(f"  Warning: Koneksi openEO gagal ({exc}). Menggunakan mode --skip-openeo.")
            args.skip_openeo = True
            
    # 4. Download composite air pesisir Banten (dengan B05)
    path_t1 = os.path.join(COMPOSITE_DIR, f"Banten_Water_{YEAR_T1}.tif")
    path_t2 = os.path.join(COMPOSITE_DIR, f"Banten_Water_{YEAR_T2}.tif")
    
    if not args.skip_openeo:
        try:
            print("\n[STEP 3] Mengunduh Composite Sentinel-2 via openEO...")
            download_banten_composite(connection, bbox, YEAR_T1, path_t1, SCALE_EXPORT)
            download_banten_composite(connection, bbox, YEAR_T2, path_t2, SCALE_EXPORT)
        except Exception as exc:
            print(f"  Error download openEO: {exc}")
            print("  Mencari berkas composite fallback lokal...")
            
    # Validasi keberadaan file composite
    # Jika file khusus air (Banten_Water_*.tif) tidak ada, cari file standar (Banten_*.tif)
    if not os.path.exists(path_t1):
        fallback_path = os.path.join(COMPOSITE_DIR, f"Banten_{YEAR_T1}.tif")
        if os.path.exists(fallback_path):
            path_t1 = fallback_path
        else:
            print(f"Error: Composite baseline {YEAR_T1} tidak ditemukan di {path_t1} atau {fallback_path}")
            sys.exit(1)
            
    if not os.path.exists(path_t2):
        fallback_path = os.path.join(COMPOSITE_DIR, f"Banten_{YEAR_T2}.tif")
        if os.path.exists(fallback_path):
            path_t2 = fallback_path
        else:
            print(f"Error: Composite comparison {YEAR_T2} tidak ditemukan di {path_t2} or {fallback_path}")
            sys.exit(1)
            
    # 5. Membaca data raster composite Banten ke dalam xarray
    print("\n[STEP 4] Memuat berkas composite ke xarray...")
    ds_t1 = load_composite_as_dataset(path_t1)
    ds_t2 = load_composite_as_dataset(path_t2)
    
    # Hitung luas satu piksel raster (hektar)
    pixel_area_ha = compute_pixel_area_ha(ds_t2)
    print(f"  Ukuran piksel raster: {pixel_area_ha:.4f} Hektar (~{pixel_area_ha * 10000:.1f} m2)")
    
    # 6. Looping analisis per kecamatan
    print("\n[STEP 5] Memproses analisis kualitas air per kecamatan...")
    
    DISTRICT_CONTEXTS = {
        "pulomerak": {
            "context": "kawasan Pelabuhan Penyeberangan Merak yang sangat aktif serta berdekatan dengan zona industri galangan kapal dan PLTU Suralaya",
            "sources": ["aktivitas kapal feri", "limpasan industri pesisir", "buangan termal/sedimen PLTU"]
        },
        "ciwandan": {
            "context": "wilayah Pelabuhan Logistik Ciwandan dan pusat industri berat (pabrik baja, kimia, dan semen) Cilegon",
            "sources": ["buangan limbah industri berat", "bongkar muat kapal curah", "limpasan drainase industri"]
        },
        "citangkil": {
            "context": "zona industri kimia dan petrokimia yang terhubung langsung dengan garis pantai industri Cilegon",
            "sources": ["residu polutan kimiawi", "limpasan limbah cair industri", "aktivitas transportasi logistik laut"]
        },
        "grogol": {
            "context": "wilayah pesisir utara Cilegon yang padat aktivitas manufaktur logam dan logistik pelabuhan",
            "sources": ["limpasan sedimentasi", "buangan domestik perkotaan", "debu industri pesisir"]
        },
        "cibeber": {
            "context": "daerah aliran sungai urban Cilegon yang membawa sisa buangan domestik perkotaan ke pesisir",
            "sources": ["limbah domestik rumah tangga", "sampah plastik", "limpasan air hujan kota"]
        },
        "jombang": {
            "context": "aliran drainase pusat kota Cilegon dengan kepadatan penduduk tinggi",
            "sources": ["buangan detergen domestik", "sanitasi perkotaan", "limbah komersial mikro"]
        },
        "kasemen": {
            "context": "wilayah Pelabuhan Perikanan Karangantu dan area budidaya tambak pesisir Serang yang sangat luas",
            "sources": ["sisa pakan tambak udang/ikan", "limbah organik domestik pesisir", "aktivitas pasar ikan Karangantu"]
        },
        "anyar": {
            "context": "kawasan pariwisata pantai utama Banten dengan kepadatan hotel, resort, dan rekreasi pesisir",
            "sources": ["limbah domestik perhotelan", "aktivitas wisatawan", "sedimen dari sungai sekitar"]
        },
        "cinangka": {
            "context": "zona wisata pantai berpasir dengan aktivitas rekreasi laut dan perhotelan intensif",
            "sources": ["aktivitas wisata air", "limbah cair domestik", "limpasan pertanian dari hulu"]
        },
        "bojonegara": {
            "context": "pusat industri galangan kapal, manufaktur lepas pantai, dan dermaga logistik swasta (jetty)",
            "sources": ["tumpahan minyak ringan/oli kapal", "sedimentasi akibat reklamasi/pengerukan", "buangan industri galangan"]
        },
        "kramatwatu": {
            "context": "zona peralihan muara sungai dan industri berat Bojonegara",
            "sources": ["limpasan muara sungai", "sedimentasi lumpur", "buangan pelabuhan sekitar"]
        },
        "pontang": {
            "context": "wilayah muara Sungai Ciujung dengan area tambak tradisional yang sangat dominan",
            "sources": ["limpasan pertanian hulu", "sisa pupuk tambak", "sedimentasi lumpur Sungai Ciujung"]
        },
        "tirtayasa": {
            "context": "daerah muara Ciujung bagian hilir dan hutan mangrove tersisa",
            "sources": ["nutrien pertanian", "sedimen lumpur tebal", "limbah cair tambak"]
        },
        "tanara": {
            "context": "hilir Sungai Cidurian dengan limpasan pertanian intensif",
            "sources": ["pupuk urea/pestisida pertanian", "sedimentasi lumpur", "limbah rumah tangga pedesaan"]
        },
        "carita": {
            "context": "kawasan wisata pantai rekreasi dan cagar alam pesisir",
            "sources": ["limbah domestik pariwisata", "aktivitas perahu wisata", "limpasan sungai kecil"]
        },
        "labuan": {
            "context": "zona Pelabuhan Perikanan Labuan dan PLTU Banten 2 Labuan",
            "sources": ["aktivitas kapal nelayan dan bahan bakar solar", "limpasan pemukiman nelayan padat", "limbah air hangat PLTU"]
        },
        "panimbang": {
            "context": "wilayah pesisir Teluk Lada yang dikembangkan sebagai KEK Pariwisata Tanjung Lesung",
            "sources": ["pembangunan infrastruktur wisata", "sedimentasi lumpur Teluk Lada", "limpasan pertanian hulu"]
        },
        "sumur": {
            "context": "wilayah penyangga Taman Nasional Ujung Kulon yang menghadap ke Selat Sunda",
            "sources": ["suspensi pasir alami", "limpasan sungai liar hutan hujan", "aktivitas nelayan tradisional"]
        },
        "bayah": {
            "context": "wilayah pesisir Samudra Hindia dengan pelabuhan khusus semen (jetty) dan pertambangan batubara/pasir di hulu",
            "sources": ["sedimentasi debu tambang/semen", "erosi alami tebing pantai", "limpasan lumpur sungai"]
        },
        "wanasalam": {
            "context": "pusat Pelabuhan Perikanan Binuangeun dengan aktivitas nelayan lepas pantai",
            "sources": ["limbah organik Tempat Pelelangan Ikan (TPI)", "buangan bahan bakar solar kapal", "limpasan tambak udang sekitar"]
        },
        "cihara": {
            "context": "pesisir selatan terbuka dengan karakteristik gelombang besar Samudra Hindia",
            "sources": ["abrasi tebing alami", "sedimentasi sungai lokal", "turbulensi pasir akibat ombak"]
        },
        "panggarangan": {
            "context": "pesisir terbuka dengan aktivitas tambang batu bara tradisional/pasir di hulu",
            "sources": ["limpasan sedimen tambang rakyat", "abrasi pantai alami", "buangan domestik sungai"]
        }
    }

    def generate_explanation(kec_name, status, ndti, ndci, kab_kota):
        name_lower = kec_name.lower()
        profile = DISTRICT_CONTEXTS.get(name_lower)
        if profile:
            context_text = f"Kecamatan {kec_name} merupakan {profile['context']}. "
            sources_text = f"Kondisi ini dipengaruhi oleh {', '.join(profile['sources'])}."
        else:
            context_text = f"Kecamatan {kec_name} terletak di wilayah pesisir {kab_kota}. "
            sources_text = "Kondisi ini dipengaruhi oleh aktivitas domestik dan limpasan permukaan sekitar perairan pesisir."

        if status == "TIDAK SEHAT":
            reason = f"Status Kualitas Air di {kec_name} diklasifikasikan sebagai **TIDAK SEHAT**. {context_text}"
            param_reasons = []
            if ndti > 0.05:
                param_reasons.append(f"tingkat kekeruhan air (NDTI: {ndti:.4f}) melebihi ambang batas aman 0.05 yang menandakan sedimentasi pantai yang tinggi")
            if ndci > 0.08:
                param_reasons.append(f"konsentrasi klorofil-a (NDCI: {ndci:.4f}) melampaui batas aman 0.08 yang mengindikasikan adanya blooming alga (eutrofikasi) akibat penumpukan zat hara/nutrien")
            if param_reasons:
                reason += "Hal ini terbukti secara ilmiah melalui analisis citra Sentinel-2 di mana " + " dan ".join(param_reasons) + ". "
            else:
                reason += "Hasil analisis menunjukkan akumulasi parameter fisik-kimiawi air (TSS/CDOM) melampaui baku mutu optimal. "
            reason += sources_text
        elif status == "SEDANG":
            reason = f"Kualitas air pesisir di {kec_name} berada dalam kondisi **SEDANG**. {context_text}Meskipun parameter kekeruhan (NDTI: {ndti:.4f}) dan klorofil-a (NDCI: {ndci:.4f}) masih berada dalam tingkat toleransi wajar, tetap diperlukan pengawasan karena adanya kontribusi polusi dari {', '.join(profile['sources']) if profile else 'aktivitas antropogenik lokal'}."
        else:
            reason = f"Kualitas air pesisir di {kec_name} diklasifikasikan sebagai **SEHAT** (Optimum). {context_text}Kondisi fisik perairan terpantau sangat bersih dengan kekeruhan rendah (NDTI: {ndti:.4f}) dan kadar klorofil-a (NDCI: {ndci:.4f}) yang seimbang, menunjukkan sirkulasi perairan yang baik serta minimnya dampak negatif dari {', '.join(profile['sources']) if profile else 'limbah domestik perkotaan'}."
        return reason

    results = []
    
    for i, row in enumerate(coastal_gdf.itertuples()):
        name_3 = row.Kecamatan
        name_2 = row.Kabupaten_Kota
        geom = row.geometry
        
        print(f"  [{i+1}/{len(coastal_gdf)}] Menganalisis Kecamatan {name_3} ({name_2})...")
        
        # Analisis tahun 2017 (Baseline)
        stats_t1 = analyze_kecamatan_water_quality(ds_t1, geom, pixel_area_ha)
        
        # Analisis tahun 2026 (Comparison)
        stats_t2 = analyze_kecamatan_water_quality(ds_t2, geom, pixel_area_ha)
        
        if stats_t2 is None:
            print(f"    Warning: Tidak ada piksel air valid ditemukan di Kecamatan {name_3}.")
            continue
            
        # Jika data 2017 kosong (misal awan tebal seluruhnya), pakai fallback data kosong
        if stats_t1 is None:
            stats_t1 = {
                "water_area_ha": 0.0, "healthy_ha": 0.0, "moderate_ha": 0.0, "unhealthy_ha": 0.0,
                "pct_healthy": 0.0, "pct_moderate": 0.0, "pct_unhealthy": 0.0,
                "mean_ndti": 0.0, "mean_ndci": 0.0, "mean_tss": 0.0, "mean_cdom": 0.0, "status": "N/A"
            }
            
        # Hitung Tren Perubahan Kualitas Air
        # Tren membaik jika persentase air sehat bertambah signifikan (>5%) atau tidak sehat berkurang
        diff_healthy = stats_t2["pct_healthy"] - stats_t1["pct_healthy"]
        diff_unhealthy = stats_t2["pct_unhealthy"] - stats_t1["pct_unhealthy"]
        
        if diff_healthy >= 5.0 and diff_unhealthy <= -5.0:
            tren = "MEMBAIK"
        elif diff_unhealthy >= 5.0:
            tren = "MEMBURUK"
        else:
            tren = "STABIL"
            
        explanation = generate_explanation(name_3, stats_t2["status"], stats_t2["mean_ndti"], stats_t2["mean_ndci"], name_2)
        results.append({
            "Kabupaten_Kota": name_2,
            "Kecamatan": name_3,
            # 2026 Data
            "Luas_Air_2026_Ha": stats_t2["water_area_ha"],
            "Sehat_2026_Ha": stats_t2["healthy_ha"],
            "Sedang_2026_Ha": stats_t2["moderate_ha"],
            "TidakSehat_2026_Ha": stats_t2["unhealthy_ha"],
            "Pct_Sehat_2026": stats_t2["pct_healthy"],
            "Pct_Sedang_2026": stats_t2["pct_moderate"],
            "Pct_TidakSehat_2026": stats_t2["pct_unhealthy"],
            "Mean_NDTI_2026": stats_t2["mean_ndti"],
            "Mean_NDCI_2026": stats_t2["mean_ndci"],
            "Mean_TSS_2026": stats_t2["mean_tss"],
            "Mean_CDOM_2026": stats_t2["mean_cdom"],
            "Status_Kualitas_2026": stats_t2["status"],
            # 2017 Data
            "Luas_Air_2017_Ha": stats_t1["water_area_ha"],
            "Sehat_2017_Ha": stats_t1["healthy_ha"],
            "Pct_Sehat_2017": stats_t1["pct_healthy"],
            "Mean_NDTI_2017": stats_t1["mean_ndti"],
            "Mean_NDCI_2017": stats_t1["mean_ndci"],
            "Status_Kualitas_2017": stats_t1["status"],
            # Comparison
            "Delta_Pct_Sehat": round(diff_healthy, 1),
            "Tren_Kualitas": tren,
            "penjelasan_kualitas": explanation
        })
        
    df_results = pd.DataFrame(results)
    
    # Melatih Model Random Forest Global untuk Kualitas Air Banten
    rf_model, rf_metrics = train_global_rf_model(ds_t2, combined_geom)
    
    # Simpan model jika berhasil dilatih
    if rf_model is not None:
        model_dir = os.path.join(OUTPUT_DIR, "model")
        os.makedirs(model_dir, exist_ok=True)
        
        model_path = os.path.join(model_dir, "water_quality_rf.joblib")
        joblib.dump(rf_model, model_path)
        print(f"  Model Random Forest global disimpan ke: {model_path}")
        
        meta_path = os.path.join(model_dir, "model_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(rf_metrics, f, indent=2, ensure_ascii=False)
        print(f"  Metadata model global disimpan ke: {meta_path}")

    # 8. Proses Analisis Pantai
    print("\n[STEP 6b] Memproses analisis kualitas air per pantai...")
    coastal_beaches_gdf = load_banten_coastal_beaches(land_geom_utm)
    
    beach_results = []
    for i, row in enumerate(coastal_beaches_gdf.itertuples()):
        beach_name = row.Pantai
        kec_name = row.Kecamatan
        kab_name = row.Kabupaten_Kota
        geom = row.geometry
        lat = row.latitude
        lon = row.longitude
        
        print(f"  [{i+1}/{len(coastal_beaches_gdf)}] Menganalisis Pantai {beach_name} ({kec_name}, {kab_name})...")
        
        # Analisis tahun 2017 (Baseline)
        stats_t1 = analyze_kecamatan_water_quality(ds_t1, geom, pixel_area_ha)
        
        # Analisis tahun 2026 (Comparison)
        stats_t2 = analyze_kecamatan_water_quality(ds_t2, geom, pixel_area_ha)
        
        if stats_t2 is None:
            print(f"    Warning: Tidak ada piksel air valid ditemukan di Pantai {beach_name}.")
            continue
            
        if stats_t1 is None:
            stats_t1 = {
                "water_area_ha": 0.0, "healthy_ha": 0.0, "moderate_ha": 0.0, "unhealthy_ha": 0.0,
                "pct_healthy": 0.0, "pct_moderate": 0.0, "pct_unhealthy": 0.0,
                "mean_ndti": 0.0, "mean_ndci": 0.0, "mean_tss": 0.0, "mean_cdom": 0.0, "status": "N/A"
            }
            
        diff_healthy = stats_t2["pct_healthy"] - stats_t1["pct_healthy"]
        diff_unhealthy = stats_t2["pct_unhealthy"] - stats_t1["pct_unhealthy"]
        
        if diff_healthy >= 5.0 and diff_unhealthy <= -5.0:
            tren = "MEMBAIK"
        elif diff_unhealthy >= 5.0:
            tren = "MEMBURUK"
        else:
            tren = "STABIL"
            
        explanation = generate_beach_explanation(beach_name, kec_name, stats_t2["status"], stats_t2["mean_ndti"], stats_t2["mean_ndci"])
        
        beach_results.append({
            "Pantai": beach_name,
            "Kecamatan": kec_name,
            "Kabupaten_Kota": kab_name,
            "latitude": lat,
            "longitude": lon,
            # 2026 Data
            "Luas_Air_2026_Ha": stats_t2["water_area_ha"],
            "Sehat_2026_Ha": stats_t2["healthy_ha"],
            "Sedang_2026_Ha": stats_t2["moderate_ha"],
            "TidakSehat_2026_Ha": stats_t2["unhealthy_ha"],
            "Pct_Sehat_2026": stats_t2["pct_healthy"],
            "Pct_Sedang_2026": stats_t2["pct_moderate"],
            "Pct_TidakSehat_2026": stats_t2["pct_unhealthy"],
            "Mean_NDTI_2026": stats_t2["mean_ndti"],
            "Mean_NDCI_2026": stats_t2["mean_ndci"],
            "Mean_TSS_2026": stats_t2["mean_tss"],
            "Mean_CDOM_2026": stats_t2["mean_cdom"],
            "Status_Kualitas_2026": stats_t2["status"],
            # 2017 Data
            "Luas_Air_2017_Ha": stats_t1["water_area_ha"],
            "Sehat_2017_Ha": stats_t1["healthy_ha"],
            "Pct_Sehat_2017": stats_t1["pct_healthy"],
            "Mean_NDTI_2017": stats_t1["mean_ndti"],
            "Mean_NDCI_2017": stats_t1["mean_ndci"],
            "Status_Kualitas_2017": stats_t1["status"],
            # Comparison
            "Delta_Pct_Sehat": round(diff_healthy, 1),
            "Tren_Kualitas": tren,
            "penjelasan_kualitas": explanation
        })
        
    df_beach_results = pd.DataFrame(beach_results)

    # 9. Ekspor Hasil
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Simpan CSV Kecamatan
    csv_path = os.path.join(OUTPUT_DIR, "banten_water_quality_kecamatan.csv")
    df_results.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n[STEP 7] Hasil statistik kecamatan disimpan ke CSV: {csv_path}")
    
    # Simpan JSON Kecamatan
    json_path = os.path.join(OUTPUT_DIR, "banten_water_quality_kecamatan.json")
    json_dict = df_results.set_index("Kecamatan").to_dict(orient="index")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_dict, f, indent=2, ensure_ascii=False)
    print(f"          Hasil statistik kecamatan disimpan ke JSON: {json_path}")
    
    # Simpan CSV Pantai
    beach_csv_path = os.path.join(OUTPUT_DIR, "banten_water_quality_beach.csv")
    df_beach_results.to_csv(beach_csv_path, index=False, encoding="utf-8-sig")
    print(f"          Hasil statistik pantai disimpan ke CSV: {beach_csv_path}")
    
    # Simpan JSON Pantai
    beach_json_path = os.path.join(OUTPUT_DIR, "banten_water_quality_beach.json")
    beach_json_dict = df_beach_results.set_index("Pantai").to_dict(orient="index")
    with open(beach_json_path, "w", encoding="utf-8") as f:
        json.dump(beach_json_dict, f, indent=2, ensure_ascii=False)
    print(f"          Hasil statistik pantai disimpan ke JSON: {beach_json_path}")
    
    # 10. Peta Folium
    html_path = os.path.join(OUTPUT_DIR, "banten_water_quality_map.html")
    create_folium_visualization(coastal_gdf, df_results, html_path, coastal_beaches_gdf, df_beach_results)
    
    # Ringkasan Eksekusi
    total_time = time.time() - t_start
    print("\n" + "=" * 70)
    print("PROSES ANALISIS KUALITAS AIR SELESAI!")
    print(f"Kecamatan diproses  : {len(df_results)}")
    print(f"Kecamatan Sehat     : {len(df_results[df_results['Status_Kualitas_2026'] == 'SEHAT'])}")
    print(f"Kecamatan Sedang    : {len(df_results[df_results['Status_Kualitas_2026'] == 'SEDANG'])}")
    print(f"Kecamatan Tidak Sehat: {len(df_results[df_results['Status_Kualitas_2026'] == 'TIDAK SEHAT'])}")
    print("-" * 40)
    print(f"Pantai diproses     : {len(df_beach_results)}")
    print(f"Pantai Sehat        : {len(df_beach_results[df_beach_results['Status_Kualitas_2026'] == 'SEHAT'])}")
    print(f"Pantai Sedang       : {len(df_beach_results[df_beach_results['Status_Kualitas_2026'] == 'SEDANG'])}")
    print(f"Pantai Tidak Sehat  : {len(df_beach_results[df_beach_results['Status_Kualitas_2026'] == 'TIDAK SEHAT'])}")
    print(f"Total Waktu Jalan   : {total_time:.1f} detik ({total_time / 60:.1f} menit)")
    print("=" * 70)

if __name__ == "__main__":
    main()
