import openeo
import rasterio
import rasterio.mask
import xarray as xr
import geopandas as gpd
import rioxarray
import pandas as pd
import numpy as np
import os
import glob
import shutil
import time
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier

# === Config ===
YEAR_T1 = 2017          # Baseline year
YEAR_T2 = 2026          # Compare year
DRY_SEASON_START = 5    # May
DRY_SEASON_END = 10     # October
MAX_CLOUD_PERCENT = 30
MNDWI_THRESHOLD = 0.0
NDVI_RUSAK = 0.33
NDVI_SEDANG = 0.43
SCALE_EXPORT = 30       # 30m resolution for download

def add_spectral_indices(ds):
    blue = ds['B02']
    green = ds['B03']
    red = ds['B04']
    nir = ds['B08']
    swir1 = ds['B11']
    swir2 = ds['B12']
    
    ndvi = (nir - red) / (nir + red + 1e-10)
    ndwi = (green - nir) / (green + nir + 1e-10)
    mndwi = (green - swir1) / (green + swir1 + 1e-10)
    evi = 2.5 * (nir - red) / (nir + 6.0 * red - 7.5 * blue + 1.0 + 1e-10)
    savi = 1.5 * (nir - red) / (nir + red + 0.5 + 1e-10)
    cmri = ndvi - ndwi
    
    ds['NDVI'] = ndvi
    ds['NDWI'] = ndwi
    ds['MNDWI'] = mndwi
    ds['EVI'] = evi
    ds['SAVI'] = savi
    ds['CMRI'] = cmri
    return ds

def get_sentinel2_composite_job(connection, bbox, year, scale_export=SCALE_EXPORT):
    start_date = f'{year}-{DRY_SEASON_START:02d}-01'
    end_date = f'{year}-{DRY_SEASON_END:02d}-31'
    
    extent = {
        'west': bbox[0],
        'south': bbox[1],
        'east': bbox[2],
        'north': bbox[3],
        'crs': 'EPSG:4326'
    }
    
    # Load collection
    cube = connection.load_collection(
        'SENTINEL2_L2A',
        spatial_extent=extent,
        temporal_extent=[start_date, end_date],
        bands=['B02', 'B03', 'B04', 'B08', 'B11', 'B12', 'SCL']
    )
    
    # Cloud masking via SCL (at native resolution)
    scl = cube.band('SCL')
    mask = ~((scl == 1) | (scl == 3) | (scl == 8) | (scl == 9) | (scl == 10) | (scl == 11))
    masked_cube = cube.mask(mask)
    
    # Resample spatial resolution of the masked cube to export resolution (in degrees) FIRST
    res_deg = scale_export / 111320.0
    resampled = masked_cube.resample_spatial(resolution=res_deg, projection=4326, method='bilinear')
    
    # Median composite on the resampled cube
    composite = resampled.reduce_dimension(reducer='median', dimension='t')
    
    # Filter bands to remove SCL
    output_cube = composite.filter_bands(['B02', 'B03', 'B04', 'B08', 'B11', 'B12'])
    return output_cube

def get_composite_with_fallback(connection, bbox, year, output_path, scale_export=SCALE_EXPORT):
    if os.path.exists(output_path):
        print(f'   [INFO] File composite sudah ada: {output_path}')
        return
        
    print(f'   [JOB] Mengirim batch job OpenEO untuk composite {year}...')
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
            print(f'   [SUCCESS] Composite diunduh: {output_path}')
        else:
            raise RuntimeError('Gagal mengunduh file GeoTIFF dari OpenEO')

def classify_water_land(ds, threshold=MNDWI_THRESHOLD):
    return (ds['MNDWI'] > threshold).values

def detect_shoreline_change(water_t1, water_t2):
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

def get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
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
    tile_names = get_tiles_for_bbox(*bbox)
    tile_paths = [os.path.join(tile_dir, t) for t in tile_names if os.path.exists(os.path.join(tile_dir, t)) ]
    
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
        print(f'      [WARNING] GMW clip warning: {e}, menggunakan mask kosong')
        mask = np.zeros(target_ds.rio.shape, dtype=bool)
    return mask

def classify_mangrove_health_threshold(ds, mangrove_mask):
    ndvi = ds['NDVI'].values
    health = np.zeros_like(ndvi, dtype=np.uint8)
    health[ndvi <= NDVI_RUSAK] = 1
    health[(ndvi > NDVI_RUSAK) & (ndvi <= NDVI_SEDANG)] = 2
    health[ndvi > NDVI_SEDANG] = 3
    health[~mangrove_mask] = 0
    return health

def compute_mangrove_stats(health, pixel_area_ha):
    results = {}
    for kelas, label in [(1, 'rusak'), (2, 'sedang'), (3, 'sehat')]:
        results[f'mangrove_{label}_ha'] = float(np.sum(health == kelas) * pixel_area_ha)
    results['mangrove_total_ha'] = float(np.sum(health > 0) * pixel_area_ha)
    return results

def classify_mangrove_health_rf(ds, mangrove_mask):
    """
    Klasifikasi kesehatan mangrove menggunakan Random Forest secara lokal.
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
        raise ValueError("Tidak ada data mangrove yang valid untuk training RF.")
        
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

def main():
    print("Connecting to OpenEO...")
    connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
    print("Authenticating...")
    connection.authenticate_oidc()
    
    gadm_path = 'data/gadm41_IDN.gpkg'
    tile_dir = 'data/gmw_v3_2020_gtiff/gmw_v3_2020'
    
    print("Loading GADM boundaries...")
    provinces = gpd.read_file(gadm_path, layer='ADM_ADM_1')
    provinces['NAME_1'] = provinces['NAME_1'].replace({
        'Jakarta Raya': 'Dki Jakarta',
        'Yogyakarta': 'Daerah Istimewa Yogyakarta'
    })
    
    bali_feature = provinces[provinces['NAME_1'] == 'Bali'].iloc[0]
    print("Starting pipeline analysis for Bali...")
    start_time = time.time()
    results = analyze_province(connection, bali_feature, gadm_path, tile_dir, YEAR_T1, YEAR_T2)
    print("\nResults:")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print(f"Execution took {time.time() - start_time:.1f}s")
    
    # Run Random Forest Classification Test on Bali
    print("\n[RF] Running Random Forest classification on Bali...")
    composite_path = 'data/composites/Bali_2026.tif'
    if os.path.exists(composite_path):
        ds = rioxarray.open_rasterio(composite_path)
        band_names = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']
        ds = xr.Dataset({name: ds.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})
        ds = ds.rio.write_crs('EPSG:4326')
        ds = add_spectral_indices(ds)
        
        geom = bali_feature.geometry
        bbox = geom.bounds
        mangrove_mask = load_mangrove_mask_rioxarray(bbox, geom, tile_dir, ds['NDVI'])
        
        try:
            rf_result, rf_metrics = classify_mangrove_health_rf(ds, mangrove_mask)
            print(f"\n[METRICS] Akurasi Random Forest:")
            print(f"   Overall Accuracy: {rf_metrics['overall_accuracy']:.2%}")
            print(f"   Kappa Coefficient: {rf_metrics['kappa']:.4f}")
            print(f"   Confusion Matrix:")
            print(f"   {rf_metrics['confusion_matrix']}")
            
            res_x = abs(ds.rio.transform()[0])
            res_y = abs(ds.rio.transform()[4])
            res_x_m = res_x * 111320.0
            res_y_m = res_y * 111320.0
            pixel_area_ha = (res_x_m * res_y_m) / 10000.0
            rf_stats = compute_mangrove_stats(rf_result, pixel_area_ha)
            print(f"\n[RESULTS] Hasil Luas Mangrove (RF):")
            print(f"   Total Mangrove: {rf_stats['mangrove_total_ha']:.2f} ha")
            print(f"   Sehat         : {rf_stats['mangrove_sehat_ha']:.2f} ha")
            print(f"   Sedang        : {rf_stats['mangrove_sedang_ha']:.2f} ha")
            print(f"   Rusak         : {rf_stats['mangrove_rusak_ha']:.2f} ha")
        except Exception as e:
            print(f"   [ERROR] Gagal RF: {e}")
    else:
        print("   [WARNING] Composite 2026 Bali tidak ditemukan, lewati tes RF")

if __name__ == '__main__':
    main()
