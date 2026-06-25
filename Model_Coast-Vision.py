# %% [markdown]
# # Pemetaan Dinamika Pantai dan Evaluasi Kesehatan Hutan Mangrove
# ### Analisis Spasial Komparatif 34 Provinsi Indonesia Berbasis openEO & Sentinel-2
#
# Notebook ini memfasilitasi pemrosesan terdistribusi berbasis cloud menggunakan **openEO API** untuk mengolah citra Sentinel-2 bebas awan secara nasional, dilanjutkan dengan analisis spasial lokal untuk:
# 1. Mendeteksi perubahan garis pantai (abrasi dan akresi) periode tahun 2017 vs 2026.
# 2. Mengklasifikasikan tingkat kesehatan hutan mangrove berbasis integrasi data Global Mangrove Watch (GMW) dan indeks NDVI.
# 3. Menyusun visualisasi analitik interaktif tingkat nasional dan provinsi.

# %% [markdown]
# ---
# ## 1. Setup Lingkungan Pemrosesan & Dependensi

# %%
# Install dependensi eksternal (jalankan jika belum terinstal pada environment saat ini)
# !pip install openeo rasterio rioxarray xarray geopandas shapely fiona folium scikit-learn matplotlib pandas numpy

# %% [markdown]
# ### Import Library
# Memuat modul-modul analisis geosains, visualisasi grafik, pemrosesan array, serta pustaka pendukung lainnya.

# %%
import openeo
import rasterio
import rasterio.mask
from rasterio.merge import merge
import xarray as xr
import geopandas as gpd
import rioxarray
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import json
import os
import folium
from datetime import datetime
import time
import random
import glob
import shutil
from sklearn.ensemble import RandomForestClassifier

print("Libraries successfully imported.")
print(f"Execution timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# %% [markdown]
# ### Koneksi dan Autentikasi openEO
# Menghubungkan sesi kerja ke server Copernicus Data Space Ecosystem (CDSE) openEO menggunakan alur autentikasi OIDC Device Code.

# %%
print("Connecting to Copernicus Data Space Ecosystem (openEO)...")
connection = openeo.connect('https://openeo.dataspace.copernicus.eu')
print("Authenticating (OIDC Device Code Flow)...")
connection.authenticate_oidc()
print("Authentication successful. openEO session initialized.")

# %% [markdown]
# ---
# ## 2. Konfigurasi Parameter Analisis

# %% [markdown]
# ### Inisialisasi Parameter Kajian
# Mendefinisikan parameter waktu, ambang indeks spektral, batas elevasi, dan skala pemrosesan grid.

# %%
# Parameter Temporal
YEAR_T1 = 2017          # Tahun dasar (baseline)
YEAR_T2 = 2026          # Tahun pembanding (terkini)
YEAR_MANGROVE = 2026    # Tahun analisis kesehatan mangrove

# Parameter Musiman (target musim kemarau untuk reduksi tutupan awan)
DRY_SEASON_START = 5    # Mei
DRY_SEASON_END = 10     # Oktober

# Kriteria Toleransi Tutupan Awan per Scene (%)
MAX_CLOUD_PERCENT = 30

# Ambang Batas Indeks Spektral
MNDWI_THRESHOLD = 0.0   # MNDWI > 0 diklasifikasikan sebagai badan air

# Klasifikasi Tingkat Kesehatan Mangrove (Kriteria Kepmen LH No. 201/2004)
NDVI_RUSAK = 0.33       # NDVI <= 0.33 menandakan kondisi rusak/jarang
NDVI_SEDANG = 0.43      # 0.33 < NDVI <= 0.43 menandakan kondisi sedang

# Filter Elevasi Pesisir
ELEVATION_MAX = 30      # Maksimum elevasi dari permukaan laut (meter)

# Resolusi Grid (meter)
SCALE_ANALYSIS = 10     # Resolusi analisis native Sentinel-2
SCALE_EXPORT = 30       # Resolusi ekspor composite (optimalisasi ukuran file)

print("Configuration loaded:")
print(f"  Shoreline baseline: {YEAR_T1} -> comparison: {YEAR_T2}")
print(f"  Mangrove target year: {YEAR_MANGROVE}")
print(f"  Export scale (resolution): {SCALE_EXPORT}m")

# %% [markdown]
# ---
# ## 3. Data Batas Wilayah Administrasi

# %% [markdown]
# ### Memuat Batas Provinsi GADM
# Memuat geopackage batas provinsi Indonesia hasil ekstraksi dataset GADM v4.1.

# %%
gadm_path = 'data/gadm41_IDN.gpkg'
if not os.path.exists(gadm_path):
    print("Error: GADM boundary file not found in 'data/gadm41_IDN.gpkg'. Running data_downloader.py first is recommended.")
else:
    provinces = gpd.read_file(gadm_path, layer='ADM_ADM_1')
    # Standardisasi nama wilayah untuk kompatibilitas data historis
    provinces['NAME_1'] = provinces['NAME_1'].replace({
        'Jakarta Raya': 'Dki Jakarta',
        'Yogyakarta': 'Daerah Istimewa Yogyakarta'
    })
    province_names = sorted(provinces['NAME_1'].unique().tolist())
    print(f"Total provinces loaded: {len(province_names)}")
    print("\nProvinces list:")
    for i, name in enumerate(province_names, 1):
        print(f"  {i:2d}. {name}")

# %% [markdown]
# ### Peta Wilayah Administrasi Provinsi
# Peta interaktif sebaran wilayah administrasi provinsi di Indonesia.

# %%
m = folium.Map(location=[-2.5, 118], zoom_start=5, control_scale=True)

# Penyederhanaan geometri wilayah untuk visualisasi web yang responsif
provinces_simplified = provinces.copy()
provinces_simplified['geometry'] = provinces['geometry'].simplify(0.02)

folium.GeoJson(
    provinces_simplified,
    style_function=lambda x: {
        'fillColor': '#00BCD4',
        'color': '#00BCD4',
        'weight': 1.5,
        'fillOpacity': 0.1
    },
    tooltip=folium.GeoJsonTooltip(fields=['NAME_1'], aliases=['Provinsi:'])
).add_to(m)

m

# %% [markdown]
# ---
# ## 4. Pra-pemrosesan Data & Cloud Masking
#
# ### Scene Classification Layer (SCL) Masking
# Proses reduksi awan dilakukan secara cloud-native di backend openEO menggunakan Scene Classification Layer (SCL) yang didistribusikan bersama produk Sentinel-2 L2A.
#
# Piksel-piksel yang terdeteksi sebagai awan tebal, awan tipis, bayangan awan, atau piksel rusak (kelas SCL: 1, 3, 8, 9, 10, 11) di-mask dan diabaikan dari perhitungan statistik composite.

# %% [markdown]
# ### Perhitungan Indeks Spektral Lokal
# Fungsi lokal untuk memproses indeks NDVI, NDWI, MNDWI, EVI, SAVI, dan CMRI secara efisien menggunakan `xarray`.

# %%
def add_spectral_indices(ds):
    """
    Menghitung indeks spektral dan menambahkan variabel baru ke dalam xarray Dataset.
    """
    blue = ds['B02']
    green = ds['B03']
    red = ds['B04']
    nir = ds['B08']
    swir1 = ds['B11']
    swir2 = ds['B12']
    
    # Normalized Difference Vegetation Index (NDVI)
    ndvi = (nir - red) / (nir + red + 1e-10)
    
    # Normalized Difference Water Index (NDWI)
    ndwi = (green - nir) / (green + nir + 1e-10)
    
    # Modified Normalized Difference Water Index (MNDWI)
    mndwi = (green - swir1) / (green + swir1 + 1e-10)
    
    # Enhanced Vegetation Index (EVI)
    evi = 2.5 * (nir - red) / (nir + 6.0 * red - 7.5 * blue + 1.0 + 1e-10)
    
    # Soil Adjusted Vegetation Index (SAVI)
    savi = 1.5 * (nir - red) / (nir + red + 0.5 + 1e-10)
    
    # Combined Mangrove Recognition Index (CMRI)
    cmri = ndvi - ndwi
    
    ds['NDVI'] = ndvi
    ds['NDWI'] = ndwi
    ds['MNDWI'] = mndwi
    ds['EVI'] = evi
    ds['SAVI'] = savi
    ds['CMRI'] = cmri
    
    return ds

# %% [markdown]
# ### Pembuatan Composite Sentinel-2 Menggunakan openEO
# Fungsi pembangun job openEO untuk memproses filter awan, reprojeksi koordinat, resampling, penggabungan temporal menggunakan nilai tengah (median), serta pengunduhan file raster GeoTIFF.

# %%
def get_sentinel2_composite_job(connection, bbox, year, scale_export=SCALE_EXPORT):
    """
    Membuat workflow data cube composite Sentinel-2 bebas awan di server openEO.
    """
    start_date = f'{year}-{DRY_SEASON_START:02d}-01'
    end_date = f'{year}-{DRY_SEASON_END:02d}-31'
    
    extent = {
        'west': bbox[0],
        'south': bbox[1],
        'east': bbox[2],
        'north': bbox[3],
        'crs': 'EPSG:4326'
    }
    
    cube = connection.load_collection(
        'SENTINEL2_L2A',
        spatial_extent=extent,
        temporal_extent=[start_date, end_date],
        bands=['B02', 'B03', 'B04', 'B08', 'B11', 'B12', 'SCL']
    )
    
    scl = cube.band('SCL')
    mask = ~((scl == 1) | (scl == 3) | (scl == 8) | (scl == 9) | (scl == 10) | (scl == 11))
    masked_cube = cube.mask(mask)
    
    # Resample spasial sebelum reduksi temporal untuk efisiensi beban komputasi server
    res_deg = scale_export / 111320.0
    resampled = masked_cube.resample_spatial(resolution=res_deg, projection=4326, method='bilinear')
    
    # Reduksi temporal menggunakan nilai median
    composite = resampled.reduce_dimension(reducer='median', dimension='t')
    output_cube = composite.filter_bands(['B02', 'B03', 'B04', 'B08', 'B11', 'B12'])
    
    return output_cube

def get_composite_with_fallback(connection, bbox, year, output_path, scale_export=SCALE_EXPORT):
    """
    Menjalankan openEO batch job untuk memproses composite citra dan mengunduh hasilnya.
    """
    if os.path.exists(output_path):
        print(f"Composite file already exists: {output_path}")
        return
        
    print(f"Submitting openEO batch job for composite {year}...")
    cube = get_sentinel2_composite_job(connection, bbox, year, scale_export)
    cube = cube.save_result('GTiff')
    
    job = cube.create_job(title=f'composite_{year}')
    job.start_and_wait()
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        job.download_results(tmpdir)
        downloaded = glob.glob(os.path.join(tmpdir, '*.tif'))
        if downloaded:
            shutil.move(downloaded[0], output_path)
            print(f"Composite downloaded and saved: {output_path}")
        else:
            raise RuntimeError("Failed to retrieve TIFF result from openEO service.")

# %% [markdown]
# ---
# ## 5. Analisis Perubahan Garis Pantai (Abrasi & Akresi)

# %% [markdown]
# ### Deteksi Badan Air & Dinamika Pesisir
# Fungsi klasifikasi air/darat menggunakan threshold MNDWI dan perhitungan statistik luasan perubahan pantai.

# %%
def classify_water_land(ds, threshold=MNDWI_THRESHOLD):
    """MNDWI > threshold diklasifikasikan sebagai air (True), sisanya sebagai darat (False)."""
    return (ds['MNDWI'] > threshold).values

def detect_shoreline_change(water_t1, water_t2):
    """
    Menganalisis perbedaan grid air.
     1 = Abrasi (darat berubah menjadi air)
    -1 = Akresi (air berubah menjadi darat)
     0 = Stabil
    """
    return water_t2.astype(int) - water_t1.astype(int)

def compute_shoreline_stats(change, pixel_area_ha):
    abrasi_ha = np.sum(change == 1) * pixel_area_ha
    akresi_ha = np.sum(change == -1) * pixel_area_ha
    stabil_ha = np.sum(change == 0) * pixel_area_ha
    return {
        'abrasi_ha': float(abrasi_ha),
        'akresi_ha': float(akresi_ha),
        'stabil_ha': float(stabil_ha)
    }

# %% [markdown]
# ---
# ## 6. Analisis Ekosistem Hutan Mangrove

# %% [markdown]
# ### Identifikasi & Penilaian Kesehatan Mangrove
# Fungsi spasial untuk memuat raster spasial Global Mangrove Watch (GMW) v3 lokal, melakukan masking area mangrove, dan klasifikasi NDVI.

# %%
def get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    """
    Mengidentifikasi nama file tile GMW v3 yang beririsan dengan bounding box analisis.
    """
    lon_start = int(np.floor(min_lon))
    lon_end = int(np.floor(max_lon))
    lat_start = int(np.floor(min_lat))
    lat_end = int(np.floor(max_lat))
    
    tiles = []
    for lon in range(lon_start, lon_end + 1):
        for lat_cell in range(lat_start, lat_end + 1):
            top_lat = lat_cell + 1
            if top_lat > 0:
                lat_str = f'N{top_lat:02d}'
            elif top_lat == 0:
                lat_str = 'N00'
            else:
                lat_str = f'S{abs(top_lat):02d}'
                
            if lon >= 0:
                lon_str = f'E{lon:03d}'
            else:
                lon_str = f'W{abs(lon):03d}'
                
            tile_name = f'GMW_{lat_str}{lon_str}_2020_v3.tif'
            tiles.append(tile_name)
    return tiles

def load_mangrove_mask_rioxarray(bbox, province_geom, tile_dir, target_ds):
    """
    Membuat masker biner hutan mangrove berdasarkan data raster Global Mangrove Watch v3.
    """
    tile_names = get_tiles_for_bbox(*bbox)
    tile_paths = [os.path.join(tile_dir, t) for t in tile_names if os.path.exists(os.path.join(tile_dir, t))]
    
    if not tile_paths:
        return np.zeros(target_ds.rio.shape, dtype=bool)
        
    srcs = [rioxarray.open_rasterio(p) for p in tile_paths]
    if len(srcs) == 1:
        gmw = srcs[0]
    else:
        from rioxarray.merge import merge_arrays
        gmw = merge_arrays(srcs)
        
    try:
        cropped = gmw.rio.clip([province_geom], crs='EPSG:4326', all_touched=True)
        matched = cropped.rio.reproject_match(target_ds)
        mask = matched.values[0] == 1
    except Exception as e:
        print(f"Warning: GMW clip failed ({e}). Returning empty mask.")
        mask = np.zeros(target_ds.rio.shape, dtype=bool)
        
    return mask

def classify_mangrove_health_threshold(ds, mangrove_mask):
    """
    Mengklasifikasikan kesehatan mangrove berdasarkan NDVI (pedoman Kepmen LH 201/2004).
    """
    ndvi = ds['NDVI'].values
    health = np.zeros_like(ndvi, dtype=np.uint8)
    
    health[ndvi <= NDVI_RUSAK] = 1                              # Rusak
    health[(ndvi > NDVI_RUSAK) & (ndvi <= NDVI_SEDANG)] = 2    # Sedang
    health[ndvi > NDVI_SEDANG] = 3                              # Sehat
    health[~mangrove_mask] = 0                                  # Non-mangrove
    return health

def compute_mangrove_stats(health, pixel_area_ha):
    results = {}
    for kelas, label in [(1, 'rusak'), (2, 'sedang'), (3, 'sehat')]:
        results[f'mangrove_{label}_ha'] = float(np.sum(health == kelas) * pixel_area_ha)
    results['mangrove_total_ha'] = float(np.sum(health > 0) * pixel_area_ha)
    return results

def classify_mangrove_health_rf(ds, mangrove_mask):
    """
    Klasifikasi kesehatan mangrove alternatif menggunakan algoritme Random Forest lokal.
    """
    class_bands = ['NDVI', 'NDWI', 'MNDWI', 'EVI', 'SAVI', 'CMRI',
                   'B02', 'B03', 'B04', 'B08', 'B11', 'B12']
    
    features_list = []
    for band in class_bands:
        features_list.append(ds[band].values[mangrove_mask])
        
    X = np.stack(features_list, axis=1)
    valid_mask = ~np.isnan(X).any(axis=1)
    X = X[valid_mask]
    
    ndvi_values = ds['NDVI'].values[mangrove_mask][valid_mask]
    y = np.zeros_like(ndvi_values, dtype=int)
    y[ndvi_values <= NDVI_RUSAK] = 1
    y[(ndvi_values > NDVI_RUSAK) & (ndvi_values <= NDVI_SEDANG)] = 2
    y[ndvi_values > NDVI_SEDANG] = 3
    
    if len(X) == 0:
        raise ValueError("No valid mangrove pixels found for Random Forest training.")
        
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
    
    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42)
    rf.fit(X_train, y_train)
    
    y_pred = rf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    kappa = cohen_kappa_score(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred)
    
    all_pixels_features = []
    for band in class_bands:
        all_pixels_features.append(ds[band].values)
        
    stacked_all = np.stack(all_pixels_features, axis=-1)
    y_dim, x_dim, n_feats = stacked_all.shape
    flat_all = stacked_all.reshape(-1, n_feats)
    flat_mangrove_mask = mangrove_mask.reshape(-1)
    valid_flat_mask = flat_mangrove_mask & (~np.isnan(flat_all).any(axis=1))
    
    predicted_flat = np.zeros(y_dim * x_dim, dtype=np.uint8)
    if np.sum(valid_flat_mask) > 0:
        predicted_flat[valid_flat_mask] = rf.predict(flat_all[valid_flat_mask])
        
    predicted_health = predicted_flat.reshape(y_dim, x_dim)
    
    metrics = {
        'overall_accuracy': float(acc),
        'kappa': float(kappa),
        'confusion_matrix': cm.tolist()
    }
    return predicted_health, metrics

# %% [markdown]
# ---
# ## 7. Alur Utama Pemrosesan per Provinsi

# %% [markdown]
# ### Pipeline Integrasi Provinsi
# Fungsi agregator untuk merangkum proses analisis spasial garis pantai dan mangrove pada suatu provinsi.

# %%
def analyze_province(connection, province_feature, gadm_path, tile_dir, year_t1=YEAR_T1, year_t2=YEAR_T2, scale_export=SCALE_EXPORT):
    geom = province_feature.geometry
    province_name = province_feature.NAME_1 if hasattr(province_feature, 'NAME_1') else province_feature['NAME_1']
    bbox = geom.bounds
    
    safe_name = province_name.replace(' ', '_').replace("'", "")
    os.makedirs('data/composites', exist_ok=True)
    composite_path_t1 = f'data/composites/{safe_name}_{year_t1}.tif'
    composite_path_t2 = f'data/composites/{safe_name}_{year_t2}.tif'
    
    get_composite_with_fallback(connection, bbox, year_t1, composite_path_t1, scale_export)
    get_composite_with_fallback(connection, bbox, year_t2, composite_path_t2, scale_export)
    
    ds_t1_raw = rioxarray.open_rasterio(composite_path_t1)
    ds_t2_raw = rioxarray.open_rasterio(composite_path_t2)
    
    band_names = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']
    ds_t1 = xr.Dataset({name: ds_t1_raw.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})
    ds_t2 = xr.Dataset({name: ds_t2_raw.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})
    
    ds_t1 = ds_t1.rio.write_crs('EPSG:4326')
    ds_t2 = ds_t2.rio.write_crs('EPSG:4326')
    
    ds_t1 = add_spectral_indices(ds_t1)
    ds_t2 = add_spectral_indices(ds_t2)
    
    water_t1 = classify_water_land(ds_t1)
    water_t2 = classify_water_land(ds_t2)
    change = detect_shoreline_change(water_t1, water_t2)
    
    res_x = abs(ds_t2.rio.transform()[0])
    res_y = abs(ds_t2.rio.transform()[4])
    res_x_m = res_x * 111320.0
    res_y_m = res_y * 111320.0
    pixel_area_ha = (res_x_m * res_y_m) / 10000.0
    
    shore_stats = compute_shoreline_stats(change, pixel_area_ha)
    
    mangrove_mask = load_mangrove_mask_rioxarray(bbox, geom, tile_dir, ds_t2['NDVI'])
    health = classify_mangrove_health_threshold(ds_t2, mangrove_mask)
    mangrove_stats = compute_mangrove_stats(health, pixel_area_ha)
    
    mangrove_ndvi = ds_t2['NDVI'].values[mangrove_mask]
    mean_ndvi = float(np.mean(mangrove_ndvi)) if len(mangrove_ndvi) > 0 else 0.0
    
    results = {
        'province_name': province_name,
        'year_t1': year_t1,
        'year_t2': year_t2,
        'abrasi_ha': shore_stats['abrasi_ha'],
        'akresi_ha': shore_stats['akresi_ha'],
        'stabil_ha': shore_stats['stabil_ha'],
        'mangrove_total_ha': mangrove_stats['mangrove_total_ha'],
        'mangrove_sehat_ha': mangrove_stats['mangrove_sehat_ha'],
        'mangrove_sedang_ha': mangrove_stats['mangrove_sedang_ha'],
        'mangrove_rusak_ha': mangrove_stats['mangrove_rusak_ha'],
        'mangrove_mean_ndvi': mean_ndvi
    }
    return results

# %% [markdown]
# ### Konfigurasi Provinsi Analisis
# Menentukan daftar wilayah provinsi yang akan diproses.

# %%
# Daftar provinsi yang dianalisis. Gunakan ['all'] untuk memproses seluruh wilayah.
test_provinces = ['Bali']

if 'all' in test_provinces or not test_provinces:
    provinces_to_process = provinces
else:
    provinces_to_process = provinces[provinces['NAME_1'].isin(test_provinces)]
    
print(f"Selected {len(provinces_to_process)} province(s) for analysis: {test_provinces}")

# %% [markdown]
# ### Loop Eksekusi Pipeline
# Menjalankan iterasi pipeline analisis di setiap provinsi dan menyusun hasilnya dalam format DataFrame.

# %%
rows = []
tile_dir = 'data/gmw_v3_2020_gtiff/gmw_v3_2020'

for i, prov in enumerate(provinces_to_process.itertuples()):
    print(f"[{i+1}/{len(provinces_to_process)}] Processing {prov.NAME_1}...")
    try:
        start_time = time.time()
        res = analyze_province(connection, prov, gadm_path, tile_dir, YEAR_T1, YEAR_T2)
        
        pct_sehat = (res['mangrove_sehat_ha'] / res['mangrove_total_ha'] * 100) if res['mangrove_total_ha'] > 0 else 0
        pct_sedang = (res['mangrove_sedang_ha'] / res['mangrove_total_ha'] * 100) if res['mangrove_total_ha'] > 0 else 0
        pct_rusak = (res['mangrove_rusak_ha'] / res['mangrove_total_ha'] * 100) if res['mangrove_total_ha'] > 0 else 0
        
        if res['abrasi_ha'] > res['akresi_ha'] * 1.2:
            status_pantai = 'ABRASI'
        elif res['akresi_ha'] > res['abrasi_ha'] * 1.2:
            status_pantai = 'AKRESI'
        else:
            status_pantai = 'STABIL'
            
        if pct_sehat >= 60:
            status_mangrove = 'SEHAT'
        elif pct_rusak >= 40:
            status_mangrove = 'RUSAK'
        else:
            status_mangrove = 'SEDANG'
            
        rows.append({
            'Provinsi': res['province_name'],
            'Abrasi (ha)': round(res['abrasi_ha'], 2),
            'Akresi (ha)': round(res['akresi_ha'], 2),
            'Net Change (ha)': round(res['akresi_ha'] - res['abrasi_ha'], 2),
            'Status Pantai': status_pantai,
            'Mangrove Total (ha)': round(res['mangrove_total_ha'], 2),
            'Mangrove Sehat (ha)': round(res['mangrove_sehat_ha'], 2),
            'Mangrove Sedang (ha)': round(res['mangrove_sedang_ha'], 2),
            'Mangrove Rusak (ha)': round(res['mangrove_rusak_ha'], 2),
            '% Sehat': round(pct_sehat, 1),
            '% Sedang': round(pct_sedang, 1),
            '% Rusak': round(pct_rusak, 1),
            'Mean NDVI': round(res['mangrove_mean_ndvi'], 4),
            'Status Mangrove': status_mangrove
        })
        print(f"  Successfully processed {prov.NAME_1} in {time.time() - start_time:.1f}s")
    except Exception as e:
        print(f"  Error processing {prov.NAME_1}: {e}")

df = pd.DataFrame(rows)
if not df.empty:
    df = df.sort_values('Provinsi').reset_index(drop=True)
print(f"\nProcessing complete. Loaded data for {len(df)} province(s).")
df

# %% [markdown]
# ---
# ## 8. Analisis & Visualisasi Hasil

# %% [markdown]
# ### Ringkasan Hasil Analisis Nasional
# Mengekstrak deskripsi statistik akumulatif dinamika garis pantai dan parameter ekologi mangrove tingkat nasional.

# %%
if not df.empty:
    print("=" * 60)
    print("NATIONAL SUMMARY - INDONESIAN SHORELINE & MANGROVE ANALYSIS")
    print(f"Shoreline Period: {YEAR_T1} -> {YEAR_T2}")
    print(f"Mangrove Year:    {YEAR_MANGROVE}")
    print("=" * 60)
    
    print(f"\nSHORELINE DYNAMICS:")
    print(f"  Total Abrasion  : {df['Abrasi (ha)'].sum():,.1f} ha")
    print(f"  Total Accretion  : {df['Akresi (ha)'].sum():,.1f} ha")
    print(f"  Net Change      : {df['Net Change (ha)'].sum():,.1f} ha")
    print(f"  Provinces with dominant Abrasion: {(df['Status Pantai'] == 'ABRASI').sum()}")
    print(f"  Provinces with dominant Accretion: {(df['Status Pantai'] == 'AKRESI').sum()}")
    print(f"  Stable Provinces:                 {(df['Status Pantai'] == 'STABIL').sum()}")
    
    print(f"\nMANGROVE ECOLOGY:")
    print(f"  Total Mangrove Area: {df['Mangrove Total (ha)'].sum():,.1f} ha")
    print(f"  Healthy Mangroves:   {df['Mangrove Sehat (ha)'].sum():,.1f} ha")
    print(f"  Moderate Mangroves:  {df['Mangrove Sedang (ha)'].sum():,.1f} ha")
    print(f"  Damaged Mangroves:   {df['Mangrove Rusak (ha)'].sum():,.1f} ha")
    print(f"  National Mean NDVI:  {df['Mean NDVI'].mean():.4f}")

# %% [markdown]
# ### Perbandingan 10 Provinsi Teratas (Abrasi vs Akresi)
# Grafik batang horizontal yang memetakan wilayah-wilayah dengan dinamika garis pantai tertinggi.

# %%
if not df.empty and len(df) >= 2:
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    fig.suptitle('Top 10 Provinces - Shoreline Change Dynamics', fontsize=16, fontweight='bold')
    
    # Top 10 Abrasi
    ax1 = axes[0]
    top_abrasi = df.nlargest(min(10, len(df)), 'Abrasi (ha)')
    colors_abrasi = plt.cm.Reds(np.linspace(0.4, 0.9, len(top_abrasi)))
    bars1 = ax1.barh(top_abrasi['Provinsi'], top_abrasi['Abrasi (ha)'], color=colors_abrasi)
    ax1.set_xlabel('Abrasion Area (ha)')
    ax1.set_title('Top 10 Largest Abrasion Areas')
    ax1.invert_yaxis()
    
    # Top 10 Akresi
    ax2 = axes[1]
    top_akresi = df.nlargest(min(10, len(df)), 'Akresi (ha)')
    colors_akresi = plt.cm.Greens(np.linspace(0.4, 0.9, len(top_akresi)))
    bars2 = ax2.barh(top_akresi['Provinsi'], top_akresi['Akresi (ha)'], color=colors_akresi)
    ax2.set_xlabel('Accretion Area (ha)')
    ax2.set_title('Top 10 Largest Accretion Areas')
    ax2.invert_yaxis()
    
    plt.tight_layout()
    plt.savefig('output/figures/top10_shoreline_change.png', dpi=150, bbox_inches='tight')
    plt.show()

# %% [markdown]
# ### Sebaran Luas Kesehatan Mangrove
# Grafik batang sebaran tingkat kesehatan mangrove pada wilayah terluas, disandingkan dengan komposisi rata-rata nasional.

# %%
if not df.empty:
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    fig.suptitle('Mangrove Health Status by Province', fontsize=16, fontweight='bold')
    
    # Top 10 Mangrove
    ax1 = axes[0]
    top_mangrove = df.nlargest(min(10, len(df)), 'Mangrove Total (ha)')
    x = np.arange(len(top_mangrove))
    width = 0.25
    
    ax1.barh(x - width, top_mangrove['Mangrove Sehat (ha)'], width, label='Healthy', color='#2ecc71')
    ax1.barh(x, top_mangrove['Mangrove Sedang (ha)'], width, label='Moderate', color='#f39c12')
    ax1.barh(x + width, top_mangrove['Mangrove Rusak (ha)'], width, label='Damaged', color='#e74c3c')
    
    ax1.set_yticks(x)
    ax1.set_yticklabels(top_mangrove['Provinsi'])
    ax1.set_xlabel('Area (ha)')
    ax1.set_title('Top Provinces by Mangrove Coverage')
    ax1.legend()
    ax1.invert_yaxis()
    
    # Pie Chart
    ax2 = axes[1]
    total_sehat = df['Mangrove Sehat (ha)'].sum()
    total_sedang = df['Mangrove Sedang (ha)'].sum()
    total_rusak = df['Mangrove Rusak (ha)'].sum()
    
    sizes = [total_sehat, total_sedang, total_rusak]
    labels = [f'Healthy\n{total_sehat:,.0f} ha', f'Moderate\n{total_sedang:,.0f} ha', f'Damaged\n{total_rusak:,.0f} ha']
    colors = ['#2ecc71', '#f39c12', '#e74c3c']
    
    ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', shadow=True, startangle=90)
    ax2.set_title('National Mangrove Health Composition')
    
    plt.tight_layout()
    plt.savefig('output/figures/mangrove_health_summary.png', dpi=150, bbox_inches='tight')
    plt.show()

# %% [markdown]
# ### Perubahan Net Garis Pantai per Provinsi
# Grafik batang yang menunjukkan nilai net change per provinsi (akresi - abrasi).

# %%
if not df.empty:
    fig, ax = plt.subplots(figsize=(14, 8))
    df_sorted = df.sort_values('Net Change (ha)')
    colors = ['#e74c3c' if x < 0 else '#2ecc71' for x in df_sorted['Net Change (ha)']]
    
    bars = ax.barh(df_sorted['Provinsi'], df_sorted['Net Change (ha)'], color=colors)
    ax.axvline(x=0, color='black', linewidth=0.8, linestyle='--')
    ax.set_xlabel('Net Change (ha)')
    ax.set_title(f'Net Shoreline Change per Province ({YEAR_T1} -> {YEAR_T2})', fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig('output/figures/net_change_all_provinces.png', dpi=150, bbox_inches='tight')
    plt.show()

# %% [markdown]
# ---
# ## 9. Visualisasi Peta Spasial Interaktif

# %% [markdown]
# ### Overlay Citra Satelit & Batas Spasial Provinsi
# Menampilkan peta komposit RGB Sentinel-2 terpotong berdasar batas provinsi untuk verifikasi spasial.

# %%
DEMO_PROVINCE = 'Bali'
demo_prov = provinces[provinces['NAME_1'] == DEMO_PROVINCE].iloc[0]
geom = demo_prov.geometry
bbox = geom.bounds
safe_name = DEMO_PROVINCE.replace(' ', '_').replace("'", "")

composite_path = f'data/composites/{safe_name}_{YEAR_T2}.tif'
if os.path.exists(composite_path):
    ds = rioxarray.open_rasterio(composite_path)
    band_names = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']
    ds = xr.Dataset({name: ds.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})
    ds = ds.rio.write_crs('EPSG:4326')
    ds = add_spectral_indices(ds)
    
    center_lat = (bbox[1] + bbox[3]) / 2.0
    center_lon = (bbox[0] + bbox[2]) / 2.0
    
    m_demo = folium.Map(location=[center_lat, center_lon], zoom_start=9)
    
    # Normalisasi RGB linear (kontras 2%-98% clipping)
    rgb = np.stack([ds['B04'].values, ds['B03'].values, ds['B02'].values], axis=-1)
    p_min, p_max = np.percentile(rgb, (2, 98))
    rgb_norm = np.clip((rgb - p_min) / (p_max - p_min + 1e-10), 0, 1)
    
    from folium.raster_layers import ImageOverlay
    img_bounds = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]]
    
    ImageOverlay(
        image=rgb_norm,
        bounds=img_bounds,
        name=f'RGB {YEAR_T2}',
        opacity=0.9
    ).add_to(m_demo)
    
    # Batas Administrasi
    folium.GeoJson(
        geom,
        name=f'Batas {DEMO_PROVINCE}',
        style_function=lambda x: {'fillColor': 'none', 'color': '#00BCD4', 'weight': 3}
    ).add_to(m_demo)
    
    folium.LayerControl().add_to(m_demo)
    display(m_demo)
else:
    print(f"Warning: Composite file {composite_path} not found. Please run the analysis loop first.")

# %% [markdown]
# ### Peta Tematik Nasional (Status Pesisir)
# Dashboard spasial nasional folium yang menggambarkan kelas dominansi perubahan pesisir tiap provinsi.

# %%
m_national = folium.Map(location=[-2.5, 118], zoom_start=5)

if not df.empty:
    provinces_merged = provinces.merge(df, left_on='NAME_1', right_on='Provinsi')
    provinces_merged_simplified = provinces_merged.copy()
    provinces_merged_simplified['geometry'] = provinces_merged['geometry'].simplify(0.02)
    
    def get_color(row):
        if row['Status Pantai'] == 'ABRASI':
            return '#e74c3c'  # Merah
        elif row['Status Pantai'] == 'AKRESI':
            return '#2ecc71'  # Hijau
        else:
            return '#f39c12'  # Stabil (Kuning)
            
    folium.GeoJson(
        provinces_merged_simplified,
        style_function=lambda x: {
            'fillColor': get_color(x['properties']),
            'color': get_color(x['properties']),
            'weight': 1.5,
            'fillOpacity': 0.4
        },
        tooltip=folium.GeoJsonTooltip(fields=['NAME_1', 'Status Pantai', 'Abrasi (ha)', 'Akresi (ha)'],
                                     aliases=['Provinsi:', 'Status Pantai:', 'Abrasi (ha):', 'Akresi (ha):'])
    ).add_to(m_national)

m_national

# %% [markdown]
# ---
# ## 10. Ekspor & Penyimpanan Hasil

# %% [markdown]
# ### Ekspor Hasil Statistik
# Menyimpan kompilasi data tabular luas abrasi, akresi, dan mangrove ke file CSV eksternal.

# %%
if not df.empty:
    os.makedirs('output', exist_ok=True)
    df.to_csv('output/hasil_analisis_pesisir_34_provinsi.csv', index=False, encoding='utf-8-sig')
    print("Results table saved to output/hasil_analisis_pesisir_34_provinsi.csv")

# %% [markdown]
# ### Penyimpanan Data Raster GIS
# Informasi penempatan berkas spasial hasil analisis.

# %%
print("Composite and output GeoTIFF files are stored under data/composites/")

# %% [markdown]
# ---
# ## 11. Klasifikasi Mangrove Berbasis Random Forest (Supervised)

# %% [markdown]
# ### Pelatihan & Evaluasi Klasifikasi Random Forest Lokal
# Sel opsional untuk melatih pengklasifikasi acak (Random Forest) guna menilai tingkat kesehatan mangrove dengan input seluruh band spektral.

# %%
RF_PROVINCE = 'Bali'
demo_prov = provinces[provinces['NAME_1'] == RF_PROVINCE].iloc[0]
geom = demo_prov.geometry
bbox = geom.bounds
safe_name = RF_PROVINCE.replace(' ', '_').replace("'", "")

composite_path = f'data/composites/{safe_name}_{YEAR_T2}.tif'
tile_dir = 'data/gmw_v3_2020_gtiff/gmw_v3_2020'

if os.path.exists(composite_path):
    print(f"Running Random Forest classification for {RF_PROVINCE}...")
    ds = rioxarray.open_rasterio(composite_path)
    band_names = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']
    ds = xr.Dataset({name: ds.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})
    ds = ds.rio.write_crs('EPSG:4326')
    ds = add_spectral_indices(ds)
    
    mangrove_mask = load_mangrove_mask_rioxarray(bbox, geom, tile_dir, ds['NDVI'])
    
    try:
        rf_result, rf_metrics = classify_mangrove_health_rf(ds, mangrove_mask)
        print(f"\nRandom Forest Accuracy Metrics:")
        print(f"  Overall Accuracy: {rf_metrics['overall_accuracy']:.2%}")
        print(f"  Kappa Coefficient: {rf_metrics['kappa']:.4f}")
        print("  Confusion Matrix:")
        print(f"  {rf_metrics['confusion_matrix']}")
        
        res_x = abs(ds.rio.transform()[0])
        res_y = abs(ds.rio.transform()[4])
        res_x_m = res_x * 111320.0
        res_y_m = res_y * 111320.0
        pixel_area_ha = (res_x_m * res_y_m) / 10000.0
        rf_stats = compute_mangrove_stats(rf_result, pixel_area_ha)
        print(f"\nMangrove Area Classification (Random Forest):")
        print(f"  Total Mangrove Area: {rf_stats['mangrove_total_ha']:.2f} ha")
        print(f"  Healthy:             {rf_stats['mangrove_sehat_ha']:.2f} ha")
        print(f"  Moderate:            {rf_stats['mangrove_sedang_ha']:.2f} ha")
        print(f"  Damaged:             {rf_stats['mangrove_rusak_ha']:.2f} ha")
    except Exception as e:
        print(f"  Error in RF classification: {e}")
else:
    print(f"Warning: Composite file {composite_path} not found. Please run the analysis loop first.")

# %%
print("=" * 50)
print("Notebook execution finished.")
print("=" * 50)

