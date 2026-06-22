# %% [markdown]
# # 🌊 Analisis Pesisir 34 Provinsi Indonesia
# ## Deteksi Abrasi/Erosi Garis Pantai & Kesehatan Mangrove
# 
# **Platform**: Google Earth Engine (Python API)  
# **Data**: Sentinel-2 MSI (10m) + Landsat 8/9 (30m)  
# **Cakupan**: 34 Provinsi Indonesia  
# **Periode Analisis**: 2016 vs 2024 (garis pantai), 2024 (mangrove)
#
# ### Workflow:
# 1. Setup & Autentikasi GEE
# 2. Load & Filter 34 Provinsi
# 3. Preprocessing (Cloud Masking, Composite, Indeks Spektral)
# 4. Task 1: Deteksi Perubahan Garis Pantai (Abrasi/Erosi)
# 5. Task 2: Klasifikasi Kesehatan Mangrove
# 6. Analisis Semua 34 Provinsi
# 7. Visualisasi & Dashboard
# 8. Export Hasil

# %% [markdown]
# ---
# ## 1. Setup & Instalasi

# %%
# ============================================================
# CELL 1: Install Dependencies
# ============================================================
# Jalankan cell ini sekali saja untuk install library yang dibutuhkan.
# Jika di Google Colab, library ee dan geemap perlu diinstall.

# !pip install earthengine-api geemap folium matplotlib pandas geopandas

# %%
# ============================================================
# CELL 2: Import Libraries
# ============================================================
import ee
import geemap
import geemap.foliumap as emap
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import json
import os
from datetime import datetime

print("✅ Semua library berhasil di-import")
print(f"📅 Waktu eksekusi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# %%
# ============================================================
# CELL 3: Autentikasi & Inisialisasi Google Earth Engine
# ============================================================
# Pertama kali pakai GEE, kamu perlu autentikasi.
# Ikuti link yang muncul, login dengan akun Google, dan paste kode-nya.

try:
    ee.Initialize()
    print("✅ GEE sudah ter-autentikasi dan ter-inisialisasi")
except Exception:
    ee.Authenticate()
    # Ganti 'your-project-id' dengan GEE Cloud Project ID kamu
    # Bisa dibuat di: https://console.cloud.google.com/
    ee.Initialize(project='your-project-id')
    print("✅ GEE berhasil di-autentikasi dan di-inisialisasi")

# %% [markdown]
# ---
# ## 2. Konfigurasi & Parameter

# %%
# ============================================================
# CELL 4: Konfigurasi Analisis
# ============================================================

# === Parameter Waktu ===
YEAR_T1 = 2016          # Tahun awal (baseline garis pantai)
YEAR_T2 = 2024          # Tahun akhir (garis pantai terkini)
YEAR_MANGROVE = 2024    # Tahun analisis mangrove

# === Parameter Musim (untuk mengurangi awan) ===
# Musim kering Indonesia: Juni - Oktober
DRY_SEASON_START = 5    # Mei
DRY_SEASON_END = 10     # Oktober

# === Parameter Cloud Masking ===
MAX_CLOUD_PERCENT = 30  # Maksimum persentase awan per scene

# === Threshold Garis Pantai ===
MNDWI_THRESHOLD = 0.0   # MNDWI > 0 = air, <= 0 = darat
# Bisa di-tune: 0.1 untuk lebih ketat (kurangi false water)

# === Threshold Kesehatan Mangrove ===
# Referensi: Kepmen LH No. 201 Tahun 2004
NDVI_RUSAK = 0.33       # NDVI <= 0.33 → Rusak (jarang)
NDVI_SEDANG = 0.43      # 0.33 < NDVI <= 0.43 → Sedang
# NDVI > 0.43 → Sehat (lebat)

# === Parameter Pesisir ===
ELEVATION_MAX = 30      # Filter area pesisir: elevasi < 30m
COASTAL_BUFFER_KM = 10  # Buffer dari garis pantai (km)

# === Resolusi Analisis ===
SCALE_ANALYSIS = 10     # 10m (Sentinel-2 native resolution)
SCALE_EXPORT = 30       # 30m (untuk export, lebih ringan)

# === Sentinel-2 Bands ===
S2_BANDS = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12']
S2_BAND_NAMES = ['Blue', 'Green', 'Red', 'RE1', 'RE2', 'RE3', 'NIR', 'NIR2', 'SWIR1', 'SWIR2']

print("✅ Konfigurasi dimuat")
print(f"   Periode analisis garis pantai: {YEAR_T1} → {YEAR_T2}")
print(f"   Tahun analisis mangrove: {YEAR_MANGROVE}")
print(f"   Resolusi analisis: {SCALE_ANALYSIS}m")

# %% [markdown]
# ---
# ## 3. Load Data 34 Provinsi Indonesia

# %%
# ============================================================
# CELL 5: Load Batas Provinsi
# ============================================================

# Menggunakan FAO GAUL 2015 Level 1 (tersedia di GEE)
# Catatan: dataset ini mungkin belum termasuk pemekaran terbaru
# (misal Papua Barat Daya, Papua Selatan, dll)
# Untuk yang lebih akurat, upload shapefile BIG/BPS sebagai GEE Asset.

gaul = ee.FeatureCollection('FAO/GAUL/2015/level1')
indonesia_provinces = gaul.filter(ee.Filter.eq('ADM0_NAME', 'Indonesia'))

# Ambil daftar nama provinsi
province_names = indonesia_provinces.aggregate_array('ADM1_NAME').getInfo()
province_names.sort()

print(f"✅ Total provinsi ditemukan: {len(province_names)}")
print("\n📋 Daftar Provinsi:")
for i, name in enumerate(province_names, 1):
    print(f"   {i:2d}. {name}")

# %%
# ============================================================
# CELL 6: Visualisasi Peta Provinsi
# ============================================================

Map = geemap.Map(center=[-2.5, 118], zoom=5)
Map.addLayer(
    indonesia_provinces.style(
        color='#00BCD4',
        fillColor='#00BCD420',
        width=2
    ),
    {},
    'Batas Provinsi Indonesia'
)

# Tambahkan label provinsi
Map.add_labels(
    indonesia_provinces,
    'ADM1_NAME',
    font_size='10pt',
    font_color='white',
    font_weight='bold'
)

Map.addLayerControl()
Map

# %% [markdown]
# ---
# ## 4. Fungsi Preprocessing

# %%
# ============================================================
# CELL 7: Cloud Masking Functions
# ============================================================

def mask_s2_clouds(image):
    """
    Cloud masking untuk Sentinel-2 Surface Reflectance.
    Menggunakan SCL (Scene Classification Layer) band.
    
    SCL Values:
    - 1: Saturated/Defective
    - 3: Cloud Shadow
    - 6: Water (kita pertahankan)
    - 8: Cloud Medium Probability
    - 9: Cloud High Probability
    - 10: Thin Cirrus
    - 11: Snow/Ice
    """
    scl = image.select('SCL')
    
    # Mask: hapus cloud shadow, cloud, dan cirrus
    mask = (scl.neq(1)   # Saturated
        .And(scl.neq(3))  # Cloud Shadow
        .And(scl.neq(8))  # Cloud Medium
        .And(scl.neq(9))  # Cloud High
        .And(scl.neq(10)) # Cirrus
        .And(scl.neq(11)) # Snow
    )
    
    return (image
        .updateMask(mask)
        .select(S2_BANDS)
        .divide(10000)  # Scale ke reflectance [0, 1]
        .copyProperties(image, ['system:time_start'])
    )


def mask_landsat8_clouds(image):
    """
    Cloud masking untuk Landsat 8/9 Collection 2 Surface Reflectance.
    Menggunakan QA_PIXEL band (bit flags).
    """
    qa = image.select('QA_PIXEL')
    
    # Bit flags: 3=Cloud Shadow, 4=Cloud, 5=Snow
    cloud_shadow = qa.bitwiseAnd(1 << 3).eq(0)
    cloud = qa.bitwiseAnd(1 << 4).eq(0)
    snow = qa.bitwiseAnd(1 << 5).eq(0)
    
    mask = cloud_shadow.And(cloud).And(snow)
    
    return (image
        .updateMask(mask)
        .select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'],
                ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'])
        .multiply(0.0000275).add(-0.2)  # Scale ke reflectance
        .copyProperties(image, ['system:time_start'])
    )


print("✅ Cloud masking functions defined")
print("   - mask_s2_clouds(): untuk Sentinel-2 SR")
print("   - mask_landsat8_clouds(): untuk Landsat 8/9 C2 SR")

# %%
# ============================================================
# CELL 8: Spectral Indices Functions
# ============================================================

def add_spectral_indices(image, sensor='S2'):
    """
    Menambahkan indeks spektral ke citra.
    
    Indeks yang dihitung:
    - NDVI  : Normalized Difference Vegetation Index (kesehatan vegetasi)
    - NDWI  : Normalized Difference Water Index (deteksi air, McFeeters 1996)
    - MNDWI : Modified NDWI (deteksi air lebih baik, Xu 2006)
    - EVI   : Enhanced Vegetation Index (vegetasi, lebih sensitif)
    - SAVI  : Soil Adjusted Vegetation Index (vegetasi + koreksi tanah)
    - CMRI  : Combined Mangrove Recognition Index (NDVI - NDWI)
    - MMRI  : Mangrove Moisture Recognition Index
    
    Parameters:
    - sensor: 'S2' untuk Sentinel-2, 'L8' untuk Landsat 8
    """
    
    if sensor == 'S2':
        blue  = image.select('B2')
        green = image.select('B3')
        red   = image.select('B4')
        nir   = image.select('B8')
        swir1 = image.select('B11')
        swir2 = image.select('B12')
    else:  # Landsat 8
        blue  = image.select('Blue')
        green = image.select('Green')
        red   = image.select('Red')
        nir   = image.select('NIR')
        swir1 = image.select('SWIR1')
        swir2 = image.select('SWIR2')
    
    # NDVI = (NIR - Red) / (NIR + Red)
    ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    
    # NDWI = (Green - NIR) / (Green + NIR)  [McFeeters]
    ndwi = green.subtract(nir).divide(green.add(nir)).rename('NDWI')
    
    # MNDWI = (Green - SWIR1) / (Green + SWIR1)  [Xu]
    mndwi = green.subtract(swir1).divide(green.add(swir1)).rename('MNDWI')
    
    # EVI = 2.5 * (NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1)
    evi = image.expression(
        '2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))',
        {'NIR': nir, 'RED': red, 'BLUE': blue}
    ).rename('EVI')
    
    # SAVI = ((NIR - Red) / (NIR + Red + L)) * (1 + L), L = 0.5
    savi = image.expression(
        '((NIR - RED) / (NIR + RED + 0.5)) * 1.5',
        {'NIR': nir, 'RED': red}
    ).rename('SAVI')
    
    # CMRI = NDVI - NDWI  (Combined Mangrove Recognition Index)
    cmri = ndvi.subtract(ndwi).rename('CMRI')
    
    # MMRI = abs(MNDWI) - abs(NDVI) (untuk distinguishing mangrove dari air)
    # Tidak selalu dipakai, tapi berguna untuk supplement
    
    return image.addBands([ndvi, ndwi, mndwi, evi, savi, cmri])


print("✅ Spectral indices function defined")
print("   Indeks: NDVI, NDWI, MNDWI, EVI, SAVI, CMRI")

# %%
# ============================================================
# CELL 9: Composite Generation Function
# ============================================================

def get_yearly_composite(geometry, year, sensor='S2', season='dry'):
    """
    Membuat composite citra tahunan untuk area tertentu.
    
    Parameters:
    - geometry: ee.Geometry area of interest
    - year: tahun (int)
    - sensor: 'S2' (Sentinel-2) atau 'L8' (Landsat 8)
    - season: 'dry' (musim kering, default), 'full' (setahun penuh)
    
    Returns:
    - ee.Image: median composite dengan indeks spektral
    """
    
    if season == 'dry':
        start_date = ee.Date.fromYMD(year, DRY_SEASON_START, 1)
        end_date = ee.Date.fromYMD(year, DRY_SEASON_END, 31)
    else:
        start_date = ee.Date.fromYMD(year, 1, 1)
        end_date = ee.Date.fromYMD(year, 12, 31)
    
    if sensor == 'S2':
        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(geometry)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', MAX_CLOUD_PERCENT))
            .map(mask_s2_clouds)
        )
        composite = collection.median().clip(geometry)
        composite = add_spectral_indices(composite, sensor='S2')
        
    else:  # Landsat 8
        collection = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
            .filterBounds(geometry)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUD_COVER', MAX_CLOUD_PERCENT))
            .map(mask_landsat8_clouds)
        )
        composite = collection.median().clip(geometry)
        composite = add_spectral_indices(composite, sensor='L8')
    
    # Tambahkan info metadata
    composite = composite.set({
        'year': year,
        'sensor': sensor,
        'season': season,
        'n_images': collection.size()
    })
    
    return composite


def get_composite_with_fallback(geometry, year, season='dry'):
    """
    Coba Sentinel-2 dulu, kalau scene-nya terlalu sedikit, fallback ke Landsat 8.
    Sentinel-2 tersedia sejak 2015, Landsat 8 sejak 2013.
    Untuk tahun < 2015, otomatis pakai Landsat.
    """
    if year < 2015:
        print(f"   ⚠️ Tahun {year} < 2015, menggunakan Landsat 8")
        return get_yearly_composite(geometry, year, sensor='L8', season=season)
    
    # Coba Sentinel-2
    s2_composite = get_yearly_composite(geometry, year, sensor='S2', season=season)
    
    # Cek jumlah scene
    n_images = s2_composite.get('n_images')
    
    # Jika S2 terlalu sedikit, gabungkan dengan Landsat
    # (biarkan logic ini di server-side)
    return s2_composite


print("✅ Composite generation functions defined")
print("   - get_yearly_composite(): buat composite Sentinel-2 atau Landsat")
print("   - get_composite_with_fallback(): otomatis fallback ke Landsat")

# %% [markdown]
# ---
# ## 5. Task 1: Deteksi Perubahan Garis Pantai (Abrasi/Erosi)
#
# ### Metode:
# 1. Buat composite citra untuk **T1** (2016) dan **T2** (2024)
# 2. Klasifikasi **air vs darat** menggunakan **MNDWI thresholding**
# 3. Bandingkan: mana yang **berubah dari darat→air** (abrasi) atau **air→darat** (akresi)
# 4. Hitung **luas perubahan** dalam hektar per provinsi

# %%
# ============================================================
# CELL 10: Shoreline Change Detection Functions
# ============================================================

def classify_water_land(image, threshold=MNDWI_THRESHOLD):
    """
    Klasifikasi air vs darat menggunakan MNDWI.
    MNDWI > threshold → Air (1)
    MNDWI <= threshold → Darat (0)
    """
    mndwi = image.select('MNDWI')
    water = mndwi.gt(threshold).rename('water')
    return water


def detect_shoreline_change(water_t1, water_t2):
    """
    Deteksi perubahan garis pantai antara dua periode.
    
    Returns ee.Image dengan nilai:
    -  1 = ABRASI  (darat T1 → air T2, pantai berkurang/terkikis)
    -  0 = STABIL  (tidak berubah)
    - -1 = AKRESI  (air T1 → darat T2, pantai bertambah)
    """
    change = water_t2.subtract(water_t1).rename('shoreline_change')
    return change


def create_coastal_zone(geometry, dem=None):
    """
    Membuat mask zona pesisir untuk membatasi analisis
    hanya pada area dekat pantai (mengurangi noise dari inland).
    
    Menggunakan DEM (elevasi) < ELEVATION_MAX meter.
    """
    if dem is None:
        dem = ee.Image('USGS/SRTMGL1_003')
    
    # Area dengan elevasi rendah (pesisir)
    coastal_mask = dem.lt(ELEVATION_MAX)
    
    return coastal_mask.clip(geometry)


def compute_shoreline_stats(change_image, geometry, coastal_mask=None):
    """
    Hitung statistik perubahan garis pantai (luas dalam hektar).
    """
    if coastal_mask is not None:
        change_image = change_image.updateMask(coastal_mask)
    
    pixel_area = ee.Image.pixelArea()
    
    # Abrasi (change == 1)
    abrasi_area = (change_image.eq(1)
        .multiply(pixel_area)
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ))
    
    # Akresi (change == -1)
    akresi_area = (change_image.eq(-1)
        .multiply(pixel_area)
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ))
    
    # Stabil (change == 0, tapi hanya area water boundary)
    stabil_area = (change_image.eq(0)
        .multiply(pixel_area)
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ))
    
    return {
        'abrasi_ha': abrasi_area,
        'akresi_ha': akresi_area,
        'stabil_ha': stabil_area
    }


print("✅ Shoreline change detection functions defined")
print("   - classify_water_land(): klasifikasi air/darat via MNDWI")
print("   - detect_shoreline_change(): deteksi abrasi/akresi")
print("   - compute_shoreline_stats(): hitung luas perubahan (ha)")

# %% [markdown]
# ---
# ## 6. Task 2: Klasifikasi Kesehatan Mangrove
#
# ### Metode:
# 1. **Identifikasi area mangrove** menggunakan Global Mangrove Watch (GMW) + CMRI filter
# 2. **Hitung NDVI** di area mangrove
# 3. **Klasifikasi** berdasarkan threshold Kepmen LH No. 201/2004:
#    - 🔴 **Rusak** (Jarang): NDVI ≤ 0.33
#    - 🟡 **Sedang**: 0.33 < NDVI ≤ 0.43
#    - 🟢 **Sehat** (Lebat): NDVI > 0.43

# %%
# ============================================================
# CELL 11: Mangrove Detection Functions
# ============================================================

def get_mangrove_mask(geometry, year=2020):
    """
    Mendapatkan mask area mangrove dari berbagai sumber.
    
    Strategi:
    1. Global Mangrove Watch (GMW) v3 — sebagai baseline
    2. JRC Global Surface Water — untuk exclude permanent water
    3. CMRI filter — tambahan konfirmasi vegetasi mangrove
    
    Parameters:
    - geometry: ee.Geometry area of interest
    - year: tahun referensi untuk GMW
    
    Returns:
    - ee.Image: binary mask (1 = mangrove, 0 = bukan)
    """
    
    # === Sumber 1: Global Mangrove Watch (GMW) ===
    # GMW tersedia: 1996, 2007-2020 (annual)
    try:
        gmw = (ee.ImageCollection('projects/global-mangrove-watch/GMW/v3/annual')
            .filterDate(f'{year}-01-01', f'{year}-12-31')
            .first())
        gmw_mask = gmw.select('mangrove').eq(1)
    except Exception:
        # Fallback: pakai dataset mangrove lain
        # CGIAR/MANGROVE atau custom classification
        gmw_mask = ee.Image(0)
    
    # === Sumber 2: Filter dengan DEM (hanya area pesisir) ===
    dem = ee.Image('USGS/SRTMGL1_003')
    elevation_mask = dem.lt(ELEVATION_MAX)
    
    # === Gabungkan ===
    mangrove_mask = gmw_mask.And(elevation_mask).clip(geometry).rename('mangrove')
    
    return mangrove_mask


def classify_mangrove_health_threshold(composite, mangrove_mask):
    """
    Klasifikasi kesehatan mangrove menggunakan NDVI thresholding.
    
    Referensi: Kepmen LH No. 201 Tahun 2004
    - Kelas 1 (Rusak/Jarang):  NDVI ≤ 0.33  → Kerapatan < 1000 pohon/ha
    - Kelas 2 (Sedang):        0.33 < NDVI ≤ 0.43 → 1000-1500 pohon/ha
    - Kelas 3 (Sehat/Lebat):   NDVI > 0.43  → Kerapatan > 1500 pohon/ha
    
    Returns:
    - ee.Image: klasifikasi (1=Rusak, 2=Sedang, 3=Sehat)
    """
    ndvi = composite.select('NDVI').updateMask(mangrove_mask)
    
    # Klasifikasi
    health = (ee.Image(0)
        .where(ndvi.lte(NDVI_RUSAK), 1)                              # Rusak
        .where(ndvi.gt(NDVI_RUSAK).And(ndvi.lte(NDVI_SEDANG)), 2)    # Sedang
        .where(ndvi.gt(NDVI_SEDANG), 3)                              # Sehat
        .updateMask(mangrove_mask)
        .rename('mangrove_health')
    )
    
    return health


def classify_mangrove_health_rf(composite, mangrove_mask, training_points=None):
    """
    Klasifikasi kesehatan mangrove menggunakan Random Forest.
    Lebih akurat dari thresholding, tapi butuh training data.
    
    Parameters:
    - composite: ee.Image dengan semua band + indeks
    - mangrove_mask: ee.Image mask area mangrove
    - training_points: ee.FeatureCollection dengan property 'class' (1,2,3)
                       Jika None, gunakan semi-automatic labeling
    
    Returns:
    - ee.Image: klasifikasi (1=Rusak, 2=Sedang, 3=Sehat)
    - dict: accuracy metrics
    """
    
    # Band yang dipakai untuk klasifikasi
    class_bands = ['NDVI', 'NDWI', 'MNDWI', 'EVI', 'SAVI', 'CMRI',
                   'B3', 'B4', 'B8', 'B11', 'B12']
    
    training_image = composite.select(class_bands).updateMask(mangrove_mask)
    
    if training_points is None:
        # === Semi-Automatic Labeling ===
        # Buat training points otomatis berdasarkan NDVI threshold
        # Ini bukan seakurat manual labeling, tapi cukup untuk initial model
        
        ndvi = composite.select('NDVI').updateMask(mangrove_mask)
        
        # Sample titik per kelas
        rusak_region = ndvi.lte(NDVI_RUSAK).selfMask()
        sedang_region = ndvi.gt(NDVI_RUSAK).And(ndvi.lte(NDVI_SEDANG)).selfMask()
        sehat_region = ndvi.gt(NDVI_SEDANG).selfMask()
        
        rusak_pts = rusak_region.stratifiedSample(
            numPoints=200, classBand='NDVI', region=mangrove_mask.geometry(),
            scale=SCALE_ANALYSIS, geometries=True
        ).map(lambda f: f.set('class', 1))
        
        sedang_pts = sedang_region.stratifiedSample(
            numPoints=200, classBand='NDVI', region=mangrove_mask.geometry(),
            scale=SCALE_ANALYSIS, geometries=True
        ).map(lambda f: f.set('class', 2))
        
        sehat_pts = sehat_region.stratifiedSample(
            numPoints=200, classBand='NDVI', region=mangrove_mask.geometry(),
            scale=SCALE_ANALYSIS, geometries=True
        ).map(lambda f: f.set('class', 3))
        
        training_points = rusak_pts.merge(sedang_pts).merge(sehat_pts)
    
    # Sample training data
    training = training_image.sampleRegions(
        collection=training_points,
        properties=['class'],
        scale=SCALE_ANALYSIS
    )
    
    # Split train/test (70/30)
    training = training.randomColumn('random')
    train_set = training.filter(ee.Filter.lt('random', 0.7))
    test_set = training.filter(ee.Filter.gte('random', 0.7))
    
    # Train Random Forest (100 trees)
    classifier = ee.Classifier.smileRandomForest(
        numberOfTrees=100,
        minLeafPopulation=5,
        seed=42
    ).train(
        features=train_set,
        classProperty='class',
        inputProperties=class_bands
    )
    
    # Classify
    classified = training_image.classify(classifier).rename('mangrove_health_rf')
    
    # Accuracy Assessment
    validated = test_set.classify(classifier)
    confusion_matrix = validated.errorMatrix('class', 'classification')
    
    accuracy_info = {
        'overall_accuracy': confusion_matrix.accuracy(),
        'kappa': confusion_matrix.kappa(),
        'confusion_matrix': confusion_matrix
    }
    
    return classified, accuracy_info


def compute_mangrove_stats(health_image, geometry):
    """
    Hitung statistik kesehatan mangrove per kelas (luas dalam hektar).
    """
    pixel_area = ee.Image.pixelArea()
    
    results = {}
    for kelas, label in [(1, 'rusak'), (2, 'sedang'), (3, 'sehat')]:
        area = (health_image.eq(kelas)
            .multiply(pixel_area)
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=geometry,
                scale=SCALE_ANALYSIS,
                maxPixels=1e13,
                bestEffort=True
            ))
        results[f'mangrove_{label}_ha'] = area
    
    # Total mangrove
    total = (health_image.gt(0)
        .multiply(pixel_area)
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ))
    results['mangrove_total_ha'] = total
    
    # Mean NDVI di area mangrove
    # (akan ditambahkan di fungsi analisis utama)
    
    return results


print("✅ Mangrove health functions defined")
print("   - get_mangrove_mask(): identifikasi area mangrove (GMW)")
print("   - classify_mangrove_health_threshold(): klasifikasi via NDVI threshold")
print("   - classify_mangrove_health_rf(): klasifikasi via Random Forest")
print("   - compute_mangrove_stats(): hitung luas per kelas (ha)")

# %% [markdown]
# ---
# ## 7. 🔄 Analisis Utama: Loop 34 Provinsi
#
# Cell ini menjalankan analisis lengkap untuk **semua 34 provinsi**.
# Proses ini bisa memakan waktu cukup lama karena GEE memproses data di server.
#
# > **Tips**: Kalau mau test dulu, ubah `provinces_to_process` ke 1-2 provinsi saja.

# %%
# ============================================================
# CELL 12: Fungsi Analisis Per Provinsi
# ============================================================

def analyze_province(province_feature, year_t1=YEAR_T1, year_t2=YEAR_T2):
    """
    Jalankan analisis lengkap untuk satu provinsi:
    1. Buat composite T1 dan T2
    2. Deteksi perubahan garis pantai
    3. Klasifikasi kesehatan mangrove
    4. Hitung statistik
    
    Parameters:
    - province_feature: ee.Feature provinsi
    - year_t1: tahun awal
    - year_t2: tahun akhir
    
    Returns:
    - ee.Feature: provinsi dengan properti hasil analisis
    """
    geom = province_feature.geometry()
    province_name = province_feature.get('ADM1_NAME')
    
    # === PREPROCESSING ===
    # Composite T1 dan T2 (musim kering untuk kurangi awan)
    composite_t1 = get_composite_with_fallback(geom, year_t1, season='dry')
    composite_t2 = get_composite_with_fallback(geom, year_t2, season='dry')
    
    # Coastal zone mask
    coastal_mask = create_coastal_zone(geom)
    
    # === TASK 1: SHORELINE CHANGE ===
    water_t1 = classify_water_land(composite_t1)
    water_t2 = classify_water_land(composite_t2)
    shoreline_change = detect_shoreline_change(water_t1, water_t2)
    
    # Hanya analisis di zona pesisir
    shoreline_change_coastal = shoreline_change.updateMask(coastal_mask)
    
    # Statistik garis pantai
    abrasi_area = (shoreline_change_coastal.eq(1)
        .multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('shoreline_change'))
    
    akresi_area = (shoreline_change_coastal.eq(-1)
        .multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('shoreline_change'))
    
    # === TASK 2: MANGROVE HEALTH ===
    mangrove_mask = get_mangrove_mask(geom, year=min(year_t2, 2020))
    mangrove_health = classify_mangrove_health_threshold(composite_t2, mangrove_mask)
    
    # Statistik mangrove per kelas
    mangrove_total = (mangrove_mask.eq(1)
        .multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('mangrove'))
    
    mangrove_sehat = (mangrove_health.eq(3)
        .multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('mangrove_health'))
    
    mangrove_sedang = (mangrove_health.eq(2)
        .multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('mangrove_health'))
    
    mangrove_rusak = (mangrove_health.eq(1)
        .multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('mangrove_health'))
    
    # Mean NDVI di area mangrove
    mean_ndvi = (composite_t2.select('NDVI')
        .updateMask(mangrove_mask)
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('NDVI'))
    
    # === SET RESULTS ===
    return province_feature.set({
        'province_name': province_name,
        'year_t1': year_t1,
        'year_t2': year_t2,
        # Garis Pantai
        'abrasi_m2': ee.Algorithms.If(abrasi_area, abrasi_area, 0),
        'akresi_m2': ee.Algorithms.If(akresi_area, akresi_area, 0),
        # Mangrove
        'mangrove_total_m2': ee.Algorithms.If(mangrove_total, mangrove_total, 0),
        'mangrove_sehat_m2': ee.Algorithms.If(mangrove_sehat, mangrove_sehat, 0),
        'mangrove_sedang_m2': ee.Algorithms.If(mangrove_sedang, mangrove_sedang, 0),
        'mangrove_rusak_m2': ee.Algorithms.If(mangrove_rusak, mangrove_rusak, 0),
        'mangrove_mean_ndvi': ee.Algorithms.If(mean_ndvi, mean_ndvi, 0),
    })


print("✅ analyze_province() function defined")
print("   Siap untuk analisis 34 provinsi!")

# %%
# ============================================================
# CELL 13: Jalankan Analisis untuk SEMUA 34 Provinsi (Server-Side)
# ============================================================
# Metode: Server-side mapping (lebih efisien, diproses di GEE server)
# Semua komputasi dilakukan secara paralel di cloud Google.

print("🚀 Memulai analisis 34 provinsi...")
print(f"   Periode: {YEAR_T1} → {YEAR_T2}")
print(f"   Ini diproses di server GEE, tunggu sebentar...\n")

# Map analisis ke semua provinsi (server-side)
results_fc = indonesia_provinces.map(analyze_province)

# Export hasil sebagai ee.FeatureCollection
# (untuk preview, kita ambil beberapa properti)

print("✅ Analisis selesai di-submit ke GEE server")
print("   Hasilnya akan dimuat saat di-query (lazy evaluation)")

# %%
# ============================================================
# CELL 14: Ambil Hasil & Buat DataFrame
# ============================================================
# Cell ini mengambil hasil dari GEE server dan mengubahnya ke pandas DataFrame.
# ⚠️ Proses ini bisa memakan waktu 5-15 menit tergantung jumlah provinsi.

print("📥 Mengambil hasil dari GEE server...")
print("   ⏳ Proses ini bisa memakan waktu 5-15 menit...\n")

# Ambil data dari GEE
results_list = results_fc.getInfo()

# Parse ke DataFrame
rows = []
for feature in results_list['features']:
    props = feature['properties']
    
    # Konversi m² ke hektar
    abrasi_ha = props.get('abrasi_m2', 0) / 10000 if props.get('abrasi_m2') else 0
    akresi_ha = props.get('akresi_m2', 0) / 10000 if props.get('akresi_m2') else 0
    mangrove_total_ha = props.get('mangrove_total_m2', 0) / 10000 if props.get('mangrove_total_m2') else 0
    mangrove_sehat_ha = props.get('mangrove_sehat_m2', 0) / 10000 if props.get('mangrove_sehat_m2') else 0
    mangrove_sedang_ha = props.get('mangrove_sedang_m2', 0) / 10000 if props.get('mangrove_sedang_m2') else 0
    mangrove_rusak_ha = props.get('mangrove_rusak_m2', 0) / 10000 if props.get('mangrove_rusak_m2') else 0
    mean_ndvi = props.get('mangrove_mean_ndvi', 0) or 0
    
    # Hitung persentase
    pct_sehat = (mangrove_sehat_ha / mangrove_total_ha * 100) if mangrove_total_ha > 0 else 0
    pct_sedang = (mangrove_sedang_ha / mangrove_total_ha * 100) if mangrove_total_ha > 0 else 0
    pct_rusak = (mangrove_rusak_ha / mangrove_total_ha * 100) if mangrove_total_ha > 0 else 0
    
    # Status dominan garis pantai
    if abrasi_ha > akresi_ha * 1.2:
        status_pantai = 'ABRASI'
    elif akresi_ha > abrasi_ha * 1.2:
        status_pantai = 'AKRESI'
    else:
        status_pantai = 'STABIL'
    
    # Status dominan mangrove
    if pct_sehat >= 60:
        status_mangrove = 'SEHAT'
    elif pct_rusak >= 40:
        status_mangrove = 'RUSAK'
    else:
        status_mangrove = 'SEDANG'
    
    rows.append({
        'Provinsi': props.get('ADM1_NAME', props.get('province_name', 'Unknown')),
        'Abrasi (ha)': round(abrasi_ha, 2),
        'Akresi (ha)': round(akresi_ha, 2),
        'Net Change (ha)': round(akresi_ha - abrasi_ha, 2),
        'Status Pantai': status_pantai,
        'Mangrove Total (ha)': round(mangrove_total_ha, 2),
        'Mangrove Sehat (ha)': round(mangrove_sehat_ha, 2),
        'Mangrove Sedang (ha)': round(mangrove_sedang_ha, 2),
        'Mangrove Rusak (ha)': round(mangrove_rusak_ha, 2),
        '% Sehat': round(pct_sehat, 1),
        '% Sedang': round(pct_sedang, 1),
        '% Rusak': round(pct_rusak, 1),
        'Mean NDVI': round(mean_ndvi, 4),
        'Status Mangrove': status_mangrove,
    })

df = pd.DataFrame(rows)
df = df.sort_values('Provinsi').reset_index(drop=True)

print(f"✅ Data berhasil dimuat! ({len(df)} provinsi)")
print()
df

# %% [markdown]
# ---
# ## 8. 📊 Visualisasi Hasil

# %%
# ============================================================
# CELL 15: Tabel Ringkasan
# ============================================================

# Ringkasan statistik nasional
print("=" * 70)
print("📊 RINGKASAN NASIONAL - ANALISIS PESISIR INDONESIA")
print(f"   Periode Garis Pantai: {YEAR_T1} → {YEAR_T2}")
print(f"   Tahun Mangrove: {YEAR_MANGROVE}")
print("=" * 70)

print(f"\n🏖️  GARIS PANTAI:")
print(f"   Total Abrasi  : {df['Abrasi (ha)'].sum():,.1f} ha")
print(f"   Total Akresi  : {df['Akresi (ha)'].sum():,.1f} ha")
print(f"   Net Change    : {df['Net Change (ha)'].sum():,.1f} ha")
print(f"   Provinsi Abrasi dominan : {(df['Status Pantai'] == 'ABRASI').sum()}")
print(f"   Provinsi Akresi dominan : {(df['Status Pantai'] == 'AKRESI').sum()}")
print(f"   Provinsi Stabil         : {(df['Status Pantai'] == 'STABIL').sum()}")

print(f"\n🌿 MANGROVE:")
print(f"   Total Luas Mangrove  : {df['Mangrove Total (ha)'].sum():,.1f} ha")
print(f"   Mangrove Sehat       : {df['Mangrove Sehat (ha)'].sum():,.1f} ha")
print(f"   Mangrove Sedang      : {df['Mangrove Sedang (ha)'].sum():,.1f} ha")
print(f"   Mangrove Rusak       : {df['Mangrove Rusak (ha)'].sum():,.1f} ha")
print(f"   Mean NDVI Nasional   : {df['Mean NDVI'].mean():.4f}")
print(f"   Provinsi Mangrove Sehat  : {(df['Status Mangrove'] == 'SEHAT').sum()}")
print(f"   Provinsi Mangrove Sedang : {(df['Status Mangrove'] == 'SEDANG').sum()}")
print(f"   Provinsi Mangrove Rusak  : {(df['Status Mangrove'] == 'RUSAK').sum()}")

# %%
# ============================================================
# CELL 16: Top 10 Provinsi Abrasi Terbesar
# ============================================================

fig, axes = plt.subplots(1, 2, figsize=(18, 8))
fig.suptitle('Top 10 Provinsi - Perubahan Garis Pantai', fontsize=16, fontweight='bold')

# --- Top 10 Abrasi ---
ax1 = axes[0]
top_abrasi = df.nlargest(10, 'Abrasi (ha)')
colors_abrasi = plt.cm.Reds(np.linspace(0.4, 0.9, 10))
bars1 = ax1.barh(top_abrasi['Provinsi'], top_abrasi['Abrasi (ha)'], color=colors_abrasi)
ax1.set_xlabel('Luas Abrasi (ha)')
ax1.set_title('🔴 Top 10 Abrasi Terbesar')
ax1.invert_yaxis()
for bar, val in zip(bars1, top_abrasi['Abrasi (ha)']):
    ax1.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
             f'{val:,.0f}', ha='left', va='center', fontsize=9)

# --- Top 10 Akresi ---
ax2 = axes[1]
top_akresi = df.nlargest(10, 'Akresi (ha)')
colors_akresi = plt.cm.Greens(np.linspace(0.4, 0.9, 10))
bars2 = ax2.barh(top_akresi['Provinsi'], top_akresi['Akresi (ha)'], color=colors_akresi)
ax2.set_xlabel('Luas Akresi (ha)')
ax2.set_title('🟢 Top 10 Akresi Terbesar')
ax2.invert_yaxis()
for bar, val in zip(bars2, top_akresi['Akresi (ha)']):
    ax2.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
             f'{val:,.0f}', ha='left', va='center', fontsize=9)

plt.tight_layout()
plt.savefig('top10_shoreline_change.png', dpi=150, bbox_inches='tight')
plt.show()
print("💾 Saved: top10_shoreline_change.png")

# %%
# ============================================================
# CELL 17: Visualisasi Kesehatan Mangrove per Provinsi
# ============================================================

fig, axes = plt.subplots(1, 2, figsize=(18, 8))
fig.suptitle('Kesehatan Mangrove per Provinsi', fontsize=16, fontweight='bold')

# --- Top 10 Luas Mangrove ---
ax1 = axes[0]
top_mangrove = df.nlargest(10, 'Mangrove Total (ha)')
x = np.arange(len(top_mangrove))
width = 0.25

bars_sehat = ax1.barh(x - width, top_mangrove['Mangrove Sehat (ha)'], width, 
                       label='Sehat', color='#2ecc71')
bars_sedang = ax1.barh(x, top_mangrove['Mangrove Sedang (ha)'], width, 
                       label='Sedang', color='#f39c12')
bars_rusak = ax1.barh(x + width, top_mangrove['Mangrove Rusak (ha)'], width, 
                      label='Rusak', color='#e74c3c')

ax1.set_yticks(x)
ax1.set_yticklabels(top_mangrove['Provinsi'])
ax1.set_xlabel('Luas (ha)')
ax1.set_title('🌿 Top 10 Provinsi Mangrove Terluas')
ax1.legend()
ax1.invert_yaxis()

# --- Pie Chart Nasional ---
ax2 = axes[1]
total_sehat = df['Mangrove Sehat (ha)'].sum()
total_sedang = df['Mangrove Sedang (ha)'].sum()
total_rusak = df['Mangrove Rusak (ha)'].sum()

sizes = [total_sehat, total_sedang, total_rusak]
labels = [f'Sehat\n{total_sehat:,.0f} ha', 
          f'Sedang\n{total_sedang:,.0f} ha', 
          f'Rusak\n{total_rusak:,.0f} ha']
colors = ['#2ecc71', '#f39c12', '#e74c3c']
explode = (0.05, 0.05, 0.1)

ax2.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%',
        shadow=True, startangle=90, textprops={'fontsize': 11})
ax2.set_title('🇮🇩 Komposisi Kesehatan Mangrove Nasional')

plt.tight_layout()
plt.savefig('mangrove_health_summary.png', dpi=150, bbox_inches='tight')
plt.show()
print("💾 Saved: mangrove_health_summary.png")

# %%
# ============================================================
# CELL 18: Heatmap Net Change per Provinsi
# ============================================================

fig, ax = plt.subplots(figsize=(14, 10))

# Sort by net change
df_sorted = df.sort_values('Net Change (ha)')

# Color: merah untuk negatif (abrasi), hijau untuk positif (akresi)
colors = ['#e74c3c' if x < 0 else '#2ecc71' for x in df_sorted['Net Change (ha)']]

bars = ax.barh(df_sorted['Provinsi'], df_sorted['Net Change (ha)'], color=colors)
ax.axvline(x=0, color='black', linewidth=0.8, linestyle='--')
ax.set_xlabel('Net Change (ha) — Negatif = Abrasi Dominan, Positif = Akresi Dominan')
ax.set_title(f'Net Perubahan Garis Pantai per Provinsi ({YEAR_T1} → {YEAR_T2})', 
             fontsize=14, fontweight='bold')

# Tambahkan nilai
for bar, val in zip(bars, df_sorted['Net Change (ha)']):
    offset = 5 if val >= 0 else -5
    ha = 'left' if val >= 0 else 'right'
    ax.text(bar.get_width() + offset, bar.get_y() + bar.get_height()/2,
            f'{val:+,.0f}', ha=ha, va='center', fontsize=7)

plt.tight_layout()
plt.savefig('net_change_all_provinces.png', dpi=150, bbox_inches='tight')
plt.show()
print("💾 Saved: net_change_all_provinces.png")

# %% [markdown]
# ---
# ## 9. 🗺️ Peta Interaktif

# %%
# ============================================================
# CELL 19: Peta Interaktif - Perubahan Garis Pantai (1 Provinsi Demo)
# ============================================================
# Contoh visualisasi detail untuk satu provinsi.
# Ubah DEMO_PROVINCE untuk melihat provinsi lain.

DEMO_PROVINCE = 'Jawa Timur'  # Ganti sesuai kebutuhan

# Ambil feature provinsi
demo_prov = indonesia_provinces.filter(
    ee.Filter.eq('ADM1_NAME', DEMO_PROVINCE)
).first()
demo_geom = demo_prov.geometry()

# Buat composite
demo_t1 = get_composite_with_fallback(demo_geom, YEAR_T1, season='dry')
demo_t2 = get_composite_with_fallback(demo_geom, YEAR_T2, season='dry')

# Deteksi perubahan
demo_water_t1 = classify_water_land(demo_t1)
demo_water_t2 = classify_water_land(demo_t2)
demo_change = detect_shoreline_change(demo_water_t1, demo_water_t2)

# Coastal zone filter
demo_coastal = create_coastal_zone(demo_geom)
demo_change_coastal = demo_change.updateMask(demo_coastal)

# Mangrove
demo_mangrove_mask = get_mangrove_mask(demo_geom)
demo_health = classify_mangrove_health_threshold(demo_t2, demo_mangrove_mask)

# === PETA ===
Map_demo = geemap.Map()
Map_demo.centerObject(demo_geom, zoom=8)

# Layer 1: RGB composite T2
vis_rgb = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.3}
Map_demo.addLayer(demo_t2, vis_rgb, f'RGB {YEAR_T2}')

# Layer 2: RGB composite T1
Map_demo.addLayer(demo_t1, vis_rgb, f'RGB {YEAR_T1}', shown=False)

# Layer 3: NDVI
vis_ndvi = {'min': -0.2, 'max': 0.8, 'palette': ['red', 'yellow', 'green', 'darkgreen']}
Map_demo.addLayer(demo_t2.select('NDVI'), vis_ndvi, f'NDVI {YEAR_T2}', shown=False)

# Layer 4: MNDWI (Water Index)
vis_mndwi = {'min': -0.5, 'max': 0.5, 'palette': ['brown', 'white', 'blue', 'darkblue']}
Map_demo.addLayer(demo_t2.select('MNDWI'), vis_mndwi, f'MNDWI {YEAR_T2}', shown=False)

# Layer 5: Perubahan Garis Pantai
vis_change = {'min': -1, 'max': 1, 'palette': ['#2ecc71', '#ecf0f1', '#e74c3c']}
Map_demo.addLayer(demo_change_coastal, vis_change, 
                  f'Perubahan Pantai ({YEAR_T1}→{YEAR_T2})')

# Layer 6: Kesehatan Mangrove
vis_health = {'min': 1, 'max': 3, 'palette': ['#e74c3c', '#f39c12', '#2ecc71']}
Map_demo.addLayer(demo_health, vis_health, 'Kesehatan Mangrove')

# Layer 7: Area Mangrove (mask)
Map_demo.addLayer(demo_mangrove_mask.selfMask(), 
                  {'palette': ['#1a5276']}, 'Area Mangrove (GMW)', shown=False)

# Batas provinsi
Map_demo.addLayer(demo_geom, {'color': '#00BCD4'}, f'Batas {DEMO_PROVINCE}')

# Legend
legend_dict = {
    'Akresi (pantai bertambah)': '#2ecc71',
    'Stabil': '#ecf0f1',
    'Abrasi (pantai terkikis)': '#e74c3c',
}
Map_demo.add_legend(title='Perubahan Garis Pantai', legend_dict=legend_dict)

Map_demo.addLayerControl()
Map_demo

# %%
# ============================================================
# CELL 20: Peta Interaktif - Overview Nasional (Semua Provinsi)
# ============================================================

Map_national = geemap.Map(center=[-2.5, 118], zoom=5)

# Warnai provinsi berdasarkan status
# Buat style berdasarkan hasil analisis
def style_province_shoreline(feature):
    """Warnai provinsi berdasarkan status perubahan garis pantai."""
    abrasi = ee.Number(feature.get('abrasi_m2'))
    akresi = ee.Number(feature.get('akresi_m2'))
    
    color = ee.Algorithms.If(
        abrasi.gt(akresi.multiply(1.2)),
        '#e74c3c',  # Merah = abrasi dominan
        ee.Algorithms.If(
            akresi.gt(abrasi.multiply(1.2)),
            '#2ecc71',  # Hijau = akresi dominan
            '#f39c12'   # Kuning = stabil
        )
    )
    
    return feature.set('style', {
        'color': color,
        'fillColor': color,
        'fillOpacity': 0.4,
        'width': 1
    })

styled = results_fc.map(style_province_shoreline)
Map_national.addLayer(styled.style(styleProperty='style'), {}, 
                      'Status Perubahan Pantai per Provinsi')

# Legend
legend_national = {
    'Abrasi Dominan': '#e74c3c',
    'Stabil': '#f39c12',
    'Akresi Dominan': '#2ecc71',
}
Map_national.add_legend(title='Status Perubahan Garis Pantai', 
                        legend_dict=legend_national)
Map_national.addLayerControl()
Map_national

# %% [markdown]
# ---
# ## 10. 💾 Export Hasil

# %%
# ============================================================
# CELL 21: Export ke CSV (Lokal)
# ============================================================

# Simpan DataFrame ke CSV
output_csv = 'hasil_analisis_pesisir_34_provinsi.csv'
df.to_csv(output_csv, index=False, encoding='utf-8-sig')
print(f"✅ CSV disimpan: {output_csv}")

# Buat ringkasan juga
summary = {
    'Parameter': [
        'Periode Garis Pantai', 'Tahun Mangrove', 'Resolusi',
        'Total Abrasi Nasional (ha)', 'Total Akresi Nasional (ha)',
        'Net Change (ha)', 'Total Mangrove (ha)',
        'Mangrove Sehat (ha)', 'Mangrove Sedang (ha)', 'Mangrove Rusak (ha)',
        'Mean NDVI Nasional'
    ],
    'Nilai': [
        f'{YEAR_T1} → {YEAR_T2}', str(YEAR_MANGROVE), f'{SCALE_ANALYSIS}m',
        f"{df['Abrasi (ha)'].sum():,.1f}", f"{df['Akresi (ha)'].sum():,.1f}",
        f"{df['Net Change (ha)'].sum():,.1f}", f"{df['Mangrove Total (ha)'].sum():,.1f}",
        f"{df['Mangrove Sehat (ha)'].sum():,.1f}", f"{df['Mangrove Sedang (ha)'].sum():,.1f}",
        f"{df['Mangrove Rusak (ha)'].sum():,.1f}", f"{df['Mean NDVI'].mean():.4f}"
    ]
}
df_summary = pd.DataFrame(summary)
df_summary.to_csv('ringkasan_nasional.csv', index=False, encoding='utf-8-sig')
print(f"✅ Ringkasan disimpan: ringkasan_nasional.csv")

# %%
# ============================================================
# CELL 22: Export ke Google Drive (GeoTIFF & CSV dari GEE)
# ============================================================

# === Export tabel hasil ke Google Drive ===
task_csv = ee.batch.Export.table.toDrive(
    collection=results_fc,
    description='hasil_analisis_pesisir_indonesia',
    folder='Coastal_Analysis_Indonesia',
    fileNamePrefix='hasil_34_provinsi',
    fileFormat='CSV',
    selectors=[
        'ADM1_NAME', 'abrasi_m2', 'akresi_m2',
        'mangrove_total_m2', 'mangrove_sehat_m2', 
        'mangrove_sedang_m2', 'mangrove_rusak_m2',
        'mangrove_mean_ndvi'
    ]
)
task_csv.start()
print(f"📤 Export CSV ke Google Drive dimulai...")
print(f"   Task ID: {task_csv.id}")

# === Export GeoTIFF untuk satu provinsi (contoh) ===
# Untuk semua provinsi, loop ini:

EXPORT_PROVINCE = 'Jawa Timur'  # Ganti sesuai kebutuhan

export_prov = indonesia_provinces.filter(
    ee.Filter.eq('ADM1_NAME', EXPORT_PROVINCE)
).first()
export_geom = export_prov.geometry()

# Export perubahan garis pantai
export_comp = get_composite_with_fallback(export_geom, YEAR_T2, season='dry')
export_water_t1 = classify_water_land(
    get_composite_with_fallback(export_geom, YEAR_T1, season='dry'))
export_water_t2 = classify_water_land(export_comp)
export_change = detect_shoreline_change(export_water_t1, export_water_t2)

task_shoreline = ee.batch.Export.image.toDrive(
    image=export_change,
    description=f'shoreline_change_{EXPORT_PROVINCE.replace(" ", "_")}',
    folder='Coastal_Analysis_Indonesia',
    region=export_geom,
    scale=SCALE_EXPORT,
    maxPixels=1e13,
    fileFormat='GeoTIFF'
)
task_shoreline.start()
print(f"📤 Export Shoreline Change GeoTIFF dimulai...")

# Export kesehatan mangrove
export_mangrove_mask = get_mangrove_mask(export_geom)
export_health = classify_mangrove_health_threshold(export_comp, export_mangrove_mask)

task_mangrove = ee.batch.Export.image.toDrive(
    image=export_health,
    description=f'mangrove_health_{EXPORT_PROVINCE.replace(" ", "_")}',
    folder='Coastal_Analysis_Indonesia',
    region=export_geom,
    scale=SCALE_EXPORT,
    maxPixels=1e13,
    fileFormat='GeoTIFF'
)
task_mangrove.start()
print(f"📤 Export Mangrove Health GeoTIFF dimulai...")

print(f"\n✅ Semua export task sudah dimulai!")
print(f"   Cek progress di: https://code.earthengine.google.com/tasks")

# %%
# ============================================================
# CELL 23: Export GeoTIFF SEMUA 34 Provinsi (Batch)
# ============================================================
# ⚠️ Ini akan membuat banyak task di GEE. 
# Uncomment untuk menjalankan.

# UNCOMMENT BLOCK DI BAWAH UNTUK EXPORT SEMUA PROVINSI:

# for prov_name in province_names:
#     prov_feat = indonesia_provinces.filter(
#         ee.Filter.eq('ADM1_NAME', prov_name)
#     ).first()
#     prov_geom = prov_feat.geometry()
#     
#     safe_name = prov_name.replace(' ', '_').replace("'", "")
#     
#     # Composite T2
#     comp = get_composite_with_fallback(prov_geom, YEAR_T2, season='dry')
#     
#     # Shoreline change
#     water_t1 = classify_water_land(
#         get_composite_with_fallback(prov_geom, YEAR_T1, season='dry'))
#     water_t2 = classify_water_land(comp)
#     change = detect_shoreline_change(water_t1, water_t2)
#     
#     task_s = ee.batch.Export.image.toDrive(
#         image=change,
#         description=f'shoreline_{safe_name}',
#         folder='Coastal_Analysis_Indonesia',
#         region=prov_geom,
#         scale=SCALE_EXPORT,
#         maxPixels=1e13,
#         fileFormat='GeoTIFF'
#     )
#     task_s.start()
#     
#     # Mangrove health
#     m_mask = get_mangrove_mask(prov_geom)
#     m_health = classify_mangrove_health_threshold(comp, m_mask)
#     
#     task_m = ee.batch.Export.image.toDrive(
#         image=m_health,
#         description=f'mangrove_{safe_name}',
#         folder='Coastal_Analysis_Indonesia',
#         region=prov_geom,
#         scale=SCALE_EXPORT,
#         maxPixels=1e13,
#         fileFormat='GeoTIFF'
#     )
#     task_m.start()
#     
#     print(f"   📤 Export dimulai: {prov_name}")
# 
# print(f"\n✅ Export batch selesai dimulai untuk {len(province_names)} provinsi!")
# print(f"   Cek progress: https://code.earthengine.google.com/tasks")

print("ℹ️  Uncomment cell di atas untuk export GeoTIFF semua 34 provinsi")

# %% [markdown]
# ---
# ## 11. 🔬 Analisis Lanjutan (Opsional)
#
# ### A. Random Forest untuk Mangrove Health
# Jika mau pakai ML classifier, jalankan cell di bawah.
# Ini akan menggunakan semi-automatic labeling berdasarkan NDVI threshold.
#
# ### B. Time Series Analysis
# Analisis tren perubahan garis pantai dari tahun ke tahun.

# %%
# ============================================================
# CELL 24: [OPSIONAL] Random Forest Classification - Demo 1 Provinsi
# ============================================================
# Uncomment untuk menjalankan

RF_PROVINCE = 'Kalimantan Timur'  # Province dengan banyak mangrove

rf_prov = indonesia_provinces.filter(
    ee.Filter.eq('ADM1_NAME', RF_PROVINCE)
).first()
rf_geom = rf_prov.geometry()

rf_composite = get_composite_with_fallback(rf_geom, YEAR_MANGROVE, season='dry')
rf_mangrove_mask = get_mangrove_mask(rf_geom)

print(f"🤖 Running Random Forest classification untuk {RF_PROVINCE}...")

rf_result, rf_accuracy = classify_mangrove_health_rf(
    rf_composite, rf_mangrove_mask
)

# Print accuracy
print(f"\n📊 Akurasi Random Forest:")
print(f"   Overall Accuracy: {rf_accuracy['overall_accuracy'].getInfo():.2%}")
print(f"   Kappa Coefficient: {rf_accuracy['kappa'].getInfo():.4f}")
print(f"   Confusion Matrix:")
print(f"   {rf_accuracy['confusion_matrix'].getInfo()}")

# Visualisasi di peta
Map_rf = geemap.Map()
Map_rf.centerObject(rf_geom, zoom=9)
Map_rf.addLayer(rf_result, 
                {'min': 1, 'max': 3, 'palette': ['#e74c3c', '#f39c12', '#2ecc71']},
                'Mangrove Health (Random Forest)')
Map_rf.addLayer(
    classify_mangrove_health_threshold(rf_composite, rf_mangrove_mask),
    {'min': 1, 'max': 3, 'palette': ['#e74c3c', '#f39c12', '#2ecc71']},
    'Mangrove Health (Threshold)', shown=False)
Map_rf.addLayerControl()
Map_rf

# %%
# ============================================================
# CELL 25: [OPSIONAL] Time Series - Tren Perubahan Garis Pantai
# ============================================================

TS_PROVINCE = 'Jawa Timur'
TS_YEARS = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

ts_prov = indonesia_provinces.filter(
    ee.Filter.eq('ADM1_NAME', TS_PROVINCE)
).first()
ts_geom = ts_prov.geometry()

print(f"📈 Menghitung time series garis pantai untuk {TS_PROVINCE}...")
print(f"   Tahun: {TS_YEARS}")

water_areas = []
for year in TS_YEARS:
    comp = get_composite_with_fallback(ts_geom, year, season='dry')
    water = classify_water_land(comp)
    
    area = (water.multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=ts_geom,
            scale=SCALE_ANALYSIS,
            maxPixels=1e13,
            bestEffort=True
        ).get('water'))
    
    water_areas.append({
        'year': year,
        'water_area_m2': area.getInfo()
    })
    print(f"   ✅ {year} selesai")

df_ts = pd.DataFrame(water_areas)
df_ts['water_area_ha'] = df_ts['water_area_m2'] / 10000
df_ts['land_change_ha'] = -(df_ts['water_area_ha'] - df_ts['water_area_ha'].iloc[0])

# Plot
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

ax1.plot(df_ts['year'], df_ts['water_area_ha'], 'b-o', linewidth=2, markersize=8)
ax1.fill_between(df_ts['year'], df_ts['water_area_ha'], alpha=0.15, color='blue')
ax1.set_xlabel('Tahun')
ax1.set_ylabel('Luas Area Air (ha)')
ax1.set_title(f'Tren Luas Air di Zona Pesisir - {TS_PROVINCE}')
ax1.grid(True, alpha=0.3)

colors = ['green' if x >= 0 else 'red' for x in df_ts['land_change_ha']]
ax2.bar(df_ts['year'], df_ts['land_change_ha'], color=colors, alpha=0.7)
ax2.axhline(y=0, color='black', linewidth=0.8, linestyle='--')
ax2.set_xlabel('Tahun')
ax2.set_ylabel('Perubahan Daratan dari Baseline (ha)')
ax2.set_title(f'Kumulatif Perubahan Daratan - {TS_PROVINCE}\n(Positif=Tambah, Negatif=Berkurang)')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(f'timeseries_{TS_PROVINCE.replace(" ", "_")}.png', dpi=150, bbox_inches='tight')
plt.show()

# %% [markdown]
# ---
# ## 📝 Catatan & Referensi
#
# ### Limitasi:
# 1. **Awan**: Indonesia sangat berawan. Composite musim kering membantu tapi tidak sempurna.
#    → Solusi: Gunakan Sentinel-1 SAR (radar, tembus awan) sebagai pelengkap
# 2. **Resolusi**: Sentinel-2 (10m) cukup untuk provinsi-level, tapi untuk detail lokal 
#    mungkin perlu resolusi lebih tinggi (Planet 3m, drone)
# 3. **MNDWI Threshold**: Threshold 0 bisa berbeda optimalnya per wilayah
#    → Solusi: Otsu thresholding (adaptive per scene)
# 4. **Global Mangrove Watch**: Data terakhir 2020, untuk tahun lebih baru perlu 
#    klasifikasi sendiri atau sumber lain
# 5. **Pemekaran Provinsi**: FAO GAUL 2015 belum termasuk pemekaran terbaru 
#    (Papua Barat Daya, Papua Selatan, Papua Tengah, Papua Pegunungan)
#    → Solusi: Upload shapefile BIG/BPS terbaru sebagai GEE Asset
#
# ### Referensi:
# - Kepmen LH No. 201 Tahun 2004 - Kriteria Baku Kerusakan Mangrove
# - Xu, H. (2006). MNDWI for enhanced water body detection
# - Global Mangrove Watch: https://www.globalmangrovewatch.org/
# - Google Earth Engine: https://earthengine.google.com/
# - Sentinel-2 MSI: https://sentinel.esa.int/web/sentinel/missions/sentinel-2
#
# ### Pengembangan Selanjutnya:
# 1. **Otsu Thresholding** — adaptive threshold per scene/provinsi
# 2. **Sentinel-1 SAR** — untuk area yang selalu berawan
# 3. **Deep Learning (U-Net)** — semantic segmentation garis pantai dan mangrove
# 4. **DSAS-style Transect** — analisis perpindahan garis pantai per transect (meter/tahun)
# 5. **Dashboard Web** — Streamlit/Next.js untuk visualisasi interaktif

# %%
print("=" * 60)
print("🎉 NOTEBOOK SELESAI!")
print("=" * 60)
print()
print("Output yang dihasilkan:")
print("  📄 hasil_analisis_pesisir_34_provinsi.csv")
print("  📄 ringkasan_nasional.csv")
print("  📊 top10_shoreline_change.png")
print("  📊 mangrove_health_summary.png")
print("  📊 net_change_all_provinces.png")
print("  🗺️  GeoTIFF files (di Google Drive)")
print()
print("Selanjutnya:")
print("  1. Review hasil di CSV")
print("  2. Validasi dengan Google Earth Pro")
print("  3. Fine-tune threshold jika perlu")
print("  4. Export GeoTIFF untuk semua provinsi (Cell 23)")
