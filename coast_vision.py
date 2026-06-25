"""
coast_vision.py — Modul Analisis Geospasial Pesisir Indonesia

Berisi seluruh fungsi inti untuk:
- Perhitungan indeks spektral (NDVI, NDWI, MNDWI, EVI, SAVI, CMRI)
- Deteksi perubahan garis pantai (abrasi/akresi) berbasis MNDWI
- Klasifikasi kesehatan hutan mangrove (threshold NDVI & Random Forest)
- Pembuatan composite Sentinel-2 bebas awan via openEO
- Pipeline analisis per provinsi

Diekstrak dari Model_Earth.ipynb agar dapat digunakan oleh batch_process.py
dan api_server.py secara terpisah.
"""

import os
import glob
import shutil
import tempfile

import numpy as np
import xarray as xr
import geopandas as gpd
import rioxarray
from sklearn.ensemble import RandomForestClassifier


# ---------------------------------------------------------------------------
# Konstanta Konfigurasi
# ---------------------------------------------------------------------------

YEAR_T1 = 2017
YEAR_T2 = 2026
YEAR_MANGROVE = 2026

DRY_SEASON_START = 5
DRY_SEASON_END = 10

MAX_CLOUD_PERCENT = 30
MNDWI_THRESHOLD = 0.0

# Klasifikasi Kesehatan Mangrove (Kepmen LH No. 201/2004)
NDVI_RUSAK = 0.33
NDVI_SEDANG = 0.43

ELEVATION_MAX = 30
SCALE_ANALYSIS = 10
SCALE_EXPORT = 30

GADM_PATH = "data/gadm41_IDN.gpkg"
TILE_DIR = "data/gmw_v3_2020_gtiff/gmw_v3_2020"
COMPOSITE_DIR = "data/composites"


# ---------------------------------------------------------------------------
# Indeks Spektral
# ---------------------------------------------------------------------------

def add_spectral_indices(ds):
    """
    Menghitung 6 indeks spektral dan menambahkannya ke xarray Dataset.

    Parameter
    ---------
    ds : xr.Dataset
        Dataset dengan variabel band Sentinel-2 (B02..B12).

    Returns
    -------
    xr.Dataset
        Dataset yang sama, ditambah variabel NDVI, NDWI, MNDWI, EVI, SAVI, CMRI.
    """
    blue  = ds["B02"]
    green = ds["B03"]
    red   = ds["B04"]
    nir   = ds["B08"]
    swir1 = ds["B11"]
    # swir2 = ds["B12"]  # tersedia tapi tidak dipakai dalam indeks saat ini

    eps = 1e-10

    ds["NDVI"]  = (nir - red)   / (nir + red + eps)
    ds["NDWI"]  = (green - nir) / (green + nir + eps)
    ds["MNDWI"] = (green - swir1) / (green + swir1 + eps)
    ds["EVI"]   = 2.5 * (nir - red) / (nir + 6.0 * red - 7.5 * blue + 1.0 + eps)
    ds["SAVI"]  = 1.5 * (nir - red) / (nir + red + 0.5 + eps)
    ds["CMRI"]  = ds["NDVI"] - ds["NDWI"]

    return ds


# ---------------------------------------------------------------------------
# Deteksi Perubahan Garis Pantai
# ---------------------------------------------------------------------------

def classify_water_land(ds, threshold=MNDWI_THRESHOLD):
    """Klasifikasi piksel air (True) dan darat (False) berdasarkan MNDWI."""
    return (ds["MNDWI"] > threshold).values


def detect_shoreline_change(water_t1, water_t2):
    """
    Bandingkan dua grid klasifikasi air.
     1 = Abrasi  (darat -> air)
    -1 = Akresi  (air  -> darat)
     0 = Stabil
    """
    return water_t2.astype(int) - water_t1.astype(int)


def compute_shoreline_stats(change, pixel_area_ha):
    """Hitung luas abrasi, akresi, dan stabil dalam hektar."""
    return {
        "abrasi_ha": float(np.sum(change == 1) * pixel_area_ha),
        "akresi_ha": float(np.sum(change == -1) * pixel_area_ha),
        "stabil_ha": float(np.sum(change == 0) * pixel_area_ha),
    }


# ---------------------------------------------------------------------------
# Mangrove — Tile Lookup & Masking
# ---------------------------------------------------------------------------

def get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    """Menentukan nama file tile GMW v3 yang beririsan dengan bounding box."""
    lon_start = int(np.floor(min_lon))
    lon_end   = int(np.floor(max_lon))
    lat_start = int(np.floor(min_lat))
    lat_end   = int(np.floor(max_lat))

    tiles = []
    for lon in range(lon_start, lon_end + 1):
        for lat_cell in range(lat_start, lat_end + 1):
            top_lat = lat_cell + 1
            if top_lat > 0:
                lat_str = f"N{top_lat:02d}"
            elif top_lat == 0:
                lat_str = "N00"
            else:
                lat_str = f"S{abs(top_lat):02d}"

            lon_str = f"E{lon:03d}" if lon >= 0 else f"W{abs(lon):03d}"
            tiles.append(f"GMW_{lat_str}{lon_str}_2020_v3.tif")
    return tiles


def load_mangrove_mask_rioxarray(bbox, province_geom, tile_dir, target_ds):
    """
    Membuat masker biner hutan mangrove dari tile GMW v3 lokal.
    Otomatis mencocokkan CRS, resolusi, dan grid piksel target.
    """
    tile_names = get_tiles_for_bbox(*bbox)
    tile_paths = [
        os.path.join(tile_dir, t) for t in tile_names
        if os.path.exists(os.path.join(tile_dir, t))
    ]

    if not tile_paths:
        return np.zeros(target_ds.rio.shape, dtype=bool)

    srcs = [rioxarray.open_rasterio(p) for p in tile_paths]
    if len(srcs) == 1:
        gmw = srcs[0]
    else:
        from rioxarray.merge import merge_arrays
        gmw = merge_arrays(srcs)

    try:
        cropped = gmw.rio.clip([province_geom], crs="EPSG:4326", all_touched=True)
        matched = cropped.rio.reproject_match(target_ds)
        mask = matched.values[0] == 1
    except Exception as exc:
        print(f"Warning: GMW clip failed ({exc}). Returning empty mask.")
        mask = np.zeros(target_ds.rio.shape, dtype=bool)

    return mask


# ---------------------------------------------------------------------------
# Mangrove — Klasifikasi Kesehatan
# ---------------------------------------------------------------------------

def classify_mangrove_health_threshold(ds, mangrove_mask):
    """
    Klasifikasi kesehatan mangrove berbasis threshold NDVI.
    0 = non-mangrove, 1 = rusak, 2 = sedang, 3 = sehat
    """
    ndvi = ds["NDVI"].values
    health = np.zeros_like(ndvi, dtype=np.uint8)

    health[ndvi <= NDVI_RUSAK] = 1
    health[(ndvi > NDVI_RUSAK) & (ndvi <= NDVI_SEDANG)] = 2
    health[ndvi > NDVI_SEDANG] = 3
    health[~mangrove_mask] = 0
    return health


def compute_mangrove_stats(health, pixel_area_ha):
    """Hitung luas mangrove per kelas kesehatan dalam hektar."""
    results = {}
    for kelas, label in [(1, "rusak"), (2, "sedang"), (3, "sehat")]:
        results[f"mangrove_{label}_ha"] = float(np.sum(health == kelas) * pixel_area_ha)
    results["mangrove_total_ha"] = float(np.sum(health > 0) * pixel_area_ha)
    return results


def classify_mangrove_health_rf(ds, mangrove_mask):
    """
    Klasifikasi kesehatan mangrove menggunakan Random Forest.

    Returns
    -------
    predicted_health : np.ndarray
        Grid klasifikasi kesehatan (0/1/2/3).
    metrics : dict
        Akurasi, kappa, dan confusion matrix.
    rf : RandomForestClassifier
        Model yang sudah di-train (agar bisa disimpan).
    """
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix

    class_bands = [
        "NDVI", "NDWI", "MNDWI", "EVI", "SAVI", "CMRI",
        "B02", "B03", "B04", "B08", "B11", "B12",
    ]

    features_list = [ds[band].values[mangrove_mask] for band in class_bands]
    X = np.stack(features_list, axis=1)
    valid_mask = ~np.isnan(X).any(axis=1)
    X = X[valid_mask]

    ndvi_values = ds["NDVI"].values[mangrove_mask][valid_mask]
    y = np.zeros_like(ndvi_values, dtype=int)
    y[ndvi_values <= NDVI_RUSAK] = 1
    y[(ndvi_values > NDVI_RUSAK) & (ndvi_values <= NDVI_SEDANG)] = 2
    y[ndvi_values > NDVI_SEDANG] = 3

    if len(X) == 0:
        raise ValueError("No valid mangrove pixels found for Random Forest training.")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y,
    )

    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42)
    rf.fit(X_train, y_train)

    y_pred = rf.predict(X_test)
    acc   = accuracy_score(y_test, y_pred)
    kappa = cohen_kappa_score(y_test, y_pred)
    cm    = confusion_matrix(y_test, y_pred)

    # Prediksi seluruh grid
    all_features = [ds[band].values for band in class_bands]
    stacked = np.stack(all_features, axis=-1)
    y_dim, x_dim, n_feats = stacked.shape
    flat_all = stacked.reshape(-1, n_feats)
    flat_mask = mangrove_mask.reshape(-1)
    valid_flat = flat_mask & (~np.isnan(flat_all).any(axis=1))

    predicted_flat = np.zeros(y_dim * x_dim, dtype=np.uint8)
    if np.sum(valid_flat) > 0:
        predicted_flat[valid_flat] = rf.predict(flat_all[valid_flat])

    predicted_health = predicted_flat.reshape(y_dim, x_dim)

    metrics = {
        "overall_accuracy": float(acc),
        "kappa": float(kappa),
        "confusion_matrix": cm.tolist(),
    }
    return predicted_health, metrics, rf


# ---------------------------------------------------------------------------
# OpenEO — Composite Sentinel-2
# ---------------------------------------------------------------------------

def get_sentinel2_composite_job(connection, bbox, year, scale_export=SCALE_EXPORT):
    """Membuat datacube composite Sentinel-2 bebas awan di server openEO."""
    start_date = f"{year}-{DRY_SEASON_START:02d}-01"
    end_date   = f"{year}-{DRY_SEASON_END:02d}-31"

    extent = {
        "west": bbox[0], "south": bbox[1],
        "east": bbox[2], "north": bbox[3],
        "crs": "EPSG:4326",
    }

    cube = connection.load_collection(
        "SENTINEL2_L2A",
        spatial_extent=extent,
        temporal_extent=[start_date, end_date],
        bands=["B02", "B03", "B04", "B08", "B11", "B12", "SCL"],
    )

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

    composite = resampled.reduce_dimension(reducer="median", dimension="t")
    return composite.filter_bands(["B02", "B03", "B04", "B08", "B11", "B12"])


def get_composite_with_fallback(connection, bbox, year, output_path,
                                scale_export=SCALE_EXPORT):
    """Download composite GeoTIFF dari openEO batch job."""
    if os.path.exists(output_path):
        print(f"  Composite already exists: {output_path}")
        return

    print(f"  Submitting openEO batch job for composite {year}...")
    cube = get_sentinel2_composite_job(connection, bbox, year, scale_export)
    cube = cube.save_result("GTiff")

    job = cube.create_job(title=f"composite_{year}")
    job.start_and_wait()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        job.download_results(tmpdir)
        downloaded = glob.glob(os.path.join(tmpdir, "*.tif"))
        if downloaded:
            shutil.move(downloaded[0], output_path)
            print(f"  Composite saved: {output_path}")
        else:
            raise RuntimeError("Failed to retrieve TIFF from openEO.")


# ---------------------------------------------------------------------------
# Utilitas — Load Raster ke xarray Dataset
# ---------------------------------------------------------------------------

BAND_NAMES = ["B02", "B03", "B04", "B08", "B11", "B12"]

def load_composite_as_dataset(tif_path):
    """Membaca file GeoTIFF composite dan mengembalikan xr.Dataset dengan band bernama."""
    raw = rioxarray.open_rasterio(tif_path)
    ds = xr.Dataset({
        name: raw.sel(band=i + 1).drop_vars("band")
        for i, name in enumerate(BAND_NAMES)
    })
    ds = ds.rio.write_crs("EPSG:4326")
    return add_spectral_indices(ds)


def compute_pixel_area_ha(ds):
    """Hitung luas satu piksel dalam hektar berdasarkan transform raster."""
    res_x = abs(ds.rio.transform()[0])
    res_y = abs(ds.rio.transform()[4])
    return (res_x * 111320.0) * (res_y * 111320.0) / 10000.0


# ---------------------------------------------------------------------------
# Pipeline Utama per Provinsi
# ---------------------------------------------------------------------------

def analyze_province(connection, province_feature, tile_dir=TILE_DIR,
                     year_t1=YEAR_T1, year_t2=YEAR_T2,
                     scale_export=SCALE_EXPORT):
    """
    Pipeline lengkap analisis pesisir untuk satu provinsi.

    Returns
    -------
    dict
        Statistik abrasi, akresi, dan kesehatan mangrove.
    """
    geom = province_feature.geometry
    province_name = (
        province_feature.NAME_1
        if hasattr(province_feature, "NAME_1")
        else province_feature["NAME_1"]
    )
    bbox = geom.bounds

    safe_name = province_name.replace(" ", "_").replace("'", "")
    os.makedirs(COMPOSITE_DIR, exist_ok=True)
    path_t1 = os.path.join(COMPOSITE_DIR, f"{safe_name}_{year_t1}.tif")
    path_t2 = os.path.join(COMPOSITE_DIR, f"{safe_name}_{year_t2}.tif")

    # Download composites jika belum ada
    get_composite_with_fallback(connection, bbox, year_t1, path_t1, scale_export)
    get_composite_with_fallback(connection, bbox, year_t2, path_t2, scale_export)

    # Load dan hitung indeks spektral
    ds_t1 = load_composite_as_dataset(path_t1)
    ds_t2 = load_composite_as_dataset(path_t2)

    # Deteksi perubahan garis pantai
    water_t1 = classify_water_land(ds_t1)
    water_t2 = classify_water_land(ds_t2)
    change = detect_shoreline_change(water_t1, water_t2)

    pixel_area_ha = compute_pixel_area_ha(ds_t2)
    shore_stats = compute_shoreline_stats(change, pixel_area_ha)

    # Analisis mangrove
    mangrove_mask = load_mangrove_mask_rioxarray(bbox, geom, tile_dir, ds_t2["NDVI"])
    health = classify_mangrove_health_threshold(ds_t2, mangrove_mask)
    mangrove_stats = compute_mangrove_stats(health, pixel_area_ha)

    mangrove_ndvi = ds_t2["NDVI"].values[mangrove_mask]
    mean_ndvi = float(np.mean(mangrove_ndvi)) if len(mangrove_ndvi) > 0 else 0.0

    return {
        "province_name": province_name,
        "year_t1": year_t1,
        "year_t2": year_t2,
        "abrasi_ha": shore_stats["abrasi_ha"],
        "akresi_ha": shore_stats["akresi_ha"],
        "stabil_ha": shore_stats["stabil_ha"],
        "mangrove_total_ha": mangrove_stats["mangrove_total_ha"],
        "mangrove_sehat_ha": mangrove_stats["mangrove_sehat_ha"],
        "mangrove_sedang_ha": mangrove_stats["mangrove_sedang_ha"],
        "mangrove_rusak_ha": mangrove_stats["mangrove_rusak_ha"],
        "mangrove_mean_ndvi": mean_ndvi,
    }


# ---------------------------------------------------------------------------
# Utilitas — Load Provinsi GADM
# ---------------------------------------------------------------------------

def load_provinces(gadm_path=GADM_PATH):
    """Membaca GeoDataFrame provinsi dari file GADM GeoPackage."""
    gdf = gpd.read_file(gadm_path, layer="ADM_ADM_1")
    gdf["NAME_1"] = gdf["NAME_1"].replace({
        "Jakarta Raya": "Dki Jakarta",
        "Yogyakarta": "Daerah Istimewa Yogyakarta",
    })
    return gdf
