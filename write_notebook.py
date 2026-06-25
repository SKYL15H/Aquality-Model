import json
import os

# Define the cells list
cells = [
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# Pemetaan Dinamika Pantai dan Evaluasi Kesehatan Hutan Mangrove\n",
            "### Analisis Spasial Komparatif 34 Provinsi Indonesia Berbasis openEO & Sentinel-2\n",
            "\n",
            "Notebook ini memfasilitasi pemrosesan terdistribusi berbasis cloud menggunakan **openEO API** untuk mengolah citra Sentinel-2 bebas awan secara nasional, dilanjutkan dengan analisis spasial lokal untuk:\n",
            "1. Mendeteksi perubahan garis pantai (abrasi dan akresi) periode tahun 2017 vs 2026.\n",
            "2. Mengklasifikasikan tingkat kesehatan hutan mangrove berbasis integrasi data Global Mangrove Watch (GMW) dan indeks NDVI.\n",
            "3. Menyusun visualisasi analitik interaktif tingkat nasional dan provinsi."
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 1. Setup Lingkungan Pemrosesan & Dependensi"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Install dependensi eksternal (jalankan jika belum terinstal pada environment saat ini)\n",
            "# !pip install openeo rasterio rioxarray xarray geopandas shapely fiona folium scikit-learn matplotlib pandas numpy"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Import Library\n",
            "Memuat modul-modul analisis geosains, visualisasi grafik, pemrosesan array, serta pustaka pendukung lainnya."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "import openeo\n",
            "import rasterio\n",
            "import rasterio.mask\n",
            "from rasterio.merge import merge\n",
            "import xarray as xr\n",
            "import geopandas as gpd\n",
            "import rioxarray\n",
            "import pandas as pd\n",
            "import matplotlib.pyplot as plt\n",
            "import matplotlib.colors as mcolors\n",
            "import numpy as np\n",
            "import json\n",
            "import os\n",
            "import folium\n",
            "from datetime import datetime\n",
            "import time\n",
            "import random\n",
            "import glob\n",
            "import shutil\n",
            "from sklearn.ensemble import RandomForestClassifier\n",
            "\n",
            "print(\"Libraries successfully imported.\")\n",
            "print(f\"Execution timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Koneksi dan Autentikasi openEO\n",
            "Menghubungkan sesi kerja ke server Copernicus Data Space Ecosystem (CDSE) openEO menggunakan alur autentikasi OIDC Device Code."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "print(\"Connecting to Copernicus Data Space Ecosystem (openEO)...\")\n",
            "connection = openeo.connect('https://openeo.dataspace.copernicus.eu')\n",
            "print(\"Authenticating (OIDC Device Code Flow)...\")\n",
            "connection.authenticate_oidc()\n",
            "print(\"Authentication successful. openEO session initialized.\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 2. Konfigurasi Parameter Analisis"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Inisialisasi Parameter Kajian\n",
            "Mendefinisikan parameter waktu, ambang indeks spektral, batas elevasi, dan skala pemrosesan grid."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Parameter Temporal\n",
            "YEAR_T1 = 2017          # Tahun dasar (baseline)\n",
            "YEAR_T2 = 2026          # Tahun pembanding (terkini)\n",
            "YEAR_MANGROVE = 2026    # Tahun analisis kesehatan mangrove\n",
            "\n",
            "# Parameter Musiman (target musim kemarau untuk reduksi tutupan awan)\n",
            "DRY_SEASON_START = 5    # Mei\n",
            "DRY_SEASON_END = 10     # Oktober\n",
            "\n",
            "# Kriteria Toleransi Tutupan Awan per Scene (%)\n",
            "MAX_CLOUD_PERCENT = 30\n",
            "\n",
            "# Ambang Batas Indeks Spektral\n",
            "MNDWI_THRESHOLD = 0.0   # MNDWI > 0 diklasifikasikan sebagai badan air\n",
            "\n",
            "# Klasifikasi Tingkat Kesehatan Mangrove (Kriteria Kepmen LH No. 201/2004)\n",
            "NDVI_RUSAK = 0.33       # NDVI <= 0.33 menandakan kondisi rusak/jarang\n",
            "NDVI_SEDANG = 0.43      # 0.33 < NDVI <= 0.43 menandakan kondisi sedang\n",
            "\n",
            "# Filter Elevasi Pesisir\n",
            "ELEVATION_MAX = 30      # Maksimum elevasi dari permukaan laut (meter)\n",
            "\n",
            "# Resolusi Grid (meter)\n",
            "SCALE_ANALYSIS = 10     # Resolusi analisis native Sentinel-2\n",
            "SCALE_EXPORT = 30       # Resolusi ekspor composite (optimalisasi ukuran file)\n",
            "\n",
            "print(\"Configuration loaded:\")\n",
            "print(f\"  Shoreline baseline: {YEAR_T1} -> comparison: {YEAR_T2}\")\n",
            "print(f\"  Mangrove target year: {YEAR_MANGROVE}\")\n",
            "print(f\"  Export scale (resolution): {SCALE_EXPORT}m\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 3. Data Batas Wilayah Administrasi"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Memuat Batas Provinsi GADM\n",
            "Memuat geopackage batas provinsi Indonesia hasil ekstraksi dataset GADM v4.1."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "gadm_path = 'data/gadm41_IDN.gpkg'\n",
            "if not os.path.exists(gadm_path):\n",
            "    print(\"Error: GADM boundary file not found in 'data/gadm41_IDN.gpkg'. Running data_downloader.py first is recommended.\")\n",
            "else:\n",
            "    provinces = gpd.read_file(gadm_path, layer='ADM_ADM_1')\n",
            "    # Standardisasi nama wilayah untuk kompatibilitas data historis\n",
            "    provinces['NAME_1'] = provinces['NAME_1'].replace({\n",
            "        'Jakarta Raya': 'Dki Jakarta',\n",
            "        'Yogyakarta': 'Daerah Istimewa Yogyakarta'\n",
            "    })\n",
            "    province_names = sorted(provinces['NAME_1'].unique().tolist())\n",
            "    print(f\"Total provinces loaded: {len(province_names)}\")\n",
            "    print(\"\\nProvinces list:\")\n",
            "    for i, name in enumerate(province_names, 1):\n",
            "        print(f\"  {i:2d}. {name}\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Peta Wilayah Administrasi Provinsi\n",
            "Peta interaktif sebaran wilayah administrasi provinsi di Indonesia."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "m = folium.Map(location=[-2.5, 118], zoom_start=5, control_scale=True)\n",
            "\n",
            "# Penyederhanaan geometri wilayah untuk visualisasi web yang responsif\n",
            "provinces_simplified = provinces.copy()\n",
            "provinces_simplified['geometry'] = provinces['geometry'].simplify(0.02)\n",
            "\n",
            "folium.GeoJson(\n",
            "    provinces_simplified,\n",
            "    style_function=lambda x: {\n",
            "        'fillColor': '#00BCD4',\n",
            "        'color': '#00BCD4',\n",
            "        'weight': 1.5,\n",
            "        'fillOpacity': 0.1\n",
            "    },\n",
            "    tooltip=folium.GeoJsonTooltip(fields=['NAME_1'], aliases=['Provinsi:'])\n",
            ").add_to(m)\n",
            "\n",
            "m"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 4. Pra-pemrosesan Data & Cloud Masking\n",
            "\n",
            "### Scene Classification Layer (SCL) Masking\n",
            "Proses reduksi awan dilakukan secara cloud-native di backend openEO menggunakan Scene Classification Layer (SCL) yang didistribusikan bersama produk Sentinel-2 L2A.\n",
            "\n",
            "Piksel-piksel yang terdeteksi sebagai awan tebal, awan tipis, bayangan awan, atau piksel rusak (kelas SCL: 1, 3, 8, 9, 10, 11) di-mask dan diabaikan dari perhitungan statistik composite."
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Perhitungan Indeks Spektral Lokal\n",
            "Fungsi lokal untuk memproses indeks NDVI, NDWI, MNDWI, EVI, SAVI, dan CMRI secara efisien menggunakan `xarray`."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "def add_spectral_indices(ds):\n",
            "    \"\"\"\n",
            "    Menghitung indeks spektral dan menambahkan variabel baru ke dalam xarray Dataset.\n",
            "    \"\"\"\n",
            "    blue = ds['B02']\n",
            "    green = ds['B03']\n",
            "    red = ds['B04']\n",
            "    nir = ds['B08']\n",
            "    swir1 = ds['B11']\n",
            "    swir2 = ds['B12']\n",
            "    \n",
            "    # Normalized Difference Vegetation Index (NDVI)\n",
            "    ndvi = (nir - red) / (nir + red + 1e-10)\n",
            "    \n",
            "    # Normalized Difference Water Index (NDWI)\n",
            "    ndwi = (green - nir) / (green + nir + 1e-10)\n",
            "    \n",
            "    # Modified Normalized Difference Water Index (MNDWI)\n",
            "    mndwi = (green - swir1) / (green + swir1 + 1e-10)\n",
            "    \n",
            "    # Enhanced Vegetation Index (EVI)\n",
            "    evi = 2.5 * (nir - red) / (nir + 6.0 * red - 7.5 * blue + 1.0 + 1e-10)\n",
            "    \n",
            "    # Soil Adjusted Vegetation Index (SAVI)\n",
            "    savi = 1.5 * (nir - red) / (nir + red + 0.5 + 1e-10)\n",
            "    \n",
            "    # Combined Mangrove Recognition Index (CMRI)\n",
            "    cmri = ndvi - ndwi\n",
            "    \n",
            "    ds['NDVI'] = ndvi\n",
            "    ds['NDWI'] = ndwi\n",
            "    ds['MNDWI'] = mndwi\n",
            "    ds['EVI'] = evi\n",
            "    ds['SAVI'] = savi\n",
            "    ds['CMRI'] = cmri\n",
            "    \n",
            "    return ds"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Pembuatan Composite Sentinel-2 Menggunakan openEO\n",
            "Fungsi pembangun job openEO untuk memproses filter awan, reprojeksi koordinat, resampling, penggabungan temporal menggunakan nilai tengah (median), serta pengunduhan file raster GeoTIFF."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "def get_sentinel2_composite_job(connection, bbox, year, scale_export=SCALE_EXPORT):\n",
            "    \"\"\"\n",
            "    Membuat workflow data cube composite Sentinel-2 bebas awan di server openEO.\n",
            "    \"\"\"\n",
            "    start_date = f'{year}-{DRY_SEASON_START:02d}-01'\n",
            "    end_date = f'{year}-{DRY_SEASON_END:02d}-31'\n",
            "    \n",
            "    extent = {\n",
            "        'west': bbox[0],\n",
            "        'south': bbox[1],\n",
            "        'east': bbox[2],\n",
            "        'north': bbox[3],\n",
            "        'crs': 'EPSG:4326'\n",
            "    }\n",
            "    \n",
            "    cube = connection.load_collection(\n",
            "        'SENTINEL2_L2A',\n",
            "        spatial_extent=extent,\n",
            "        temporal_extent=[start_date, end_date],\n",
            "        bands=['B02', 'B03', 'B04', 'B08', 'B11', 'B12', 'SCL']\n",
            "    )\n",
            "    \n",
            "    scl = cube.band('SCL')\n",
            "    mask = ~((scl == 1) | (scl == 3) | (scl == 8) | (scl == 9) | (scl == 10) | (scl == 11))\n",
            "    masked_cube = cube.mask(mask)\n",
            "    \n",
            "    # Resample spasial sebelum reduksi temporal untuk efisiensi beban komputasi server\n",
            "    res_deg = scale_export / 111320.0\n",
            "    resampled = masked_cube.resample_spatial(resolution=res_deg, projection=4326, method='bilinear')\n",
            "    \n",
            "    # Reduksi temporal menggunakan nilai median\n",
            "    composite = resampled.reduce_dimension(reducer='median', dimension='t')\n",
            "    output_cube = composite.filter_bands(['B02', 'B03', 'B04', 'B08', 'B11', 'B12'])\n",
            "    \n",
            "    return output_cube\n",
            "\n",
            "def get_composite_with_fallback(connection, bbox, year, output_path, scale_export=SCALE_EXPORT):\n",
            "    \"\"\"\n",
            "    Menjalankan openEO batch job untuk memproses composite citra dan mengunduh hasilnya.\n",
            "    \"\"\"\n",
            "    if os.path.exists(output_path):\n",
            "        print(f\"Composite file already exists: {output_path}\")\n",
            "        return\n",
            "        \n",
            "    print(f\"Submitting openEO batch job for composite {year}...\")\n",
            "    cube = get_sentinel2_composite_job(connection, bbox, year, scale_export)\n",
            "    cube = cube.save_result('GTiff')\n",
            "    \n",
            "    job = cube.create_job(title=f'composite_{year}')\n",
            "    job.start_and_wait()\n",
            "    \n",
            "    os.makedirs(os.path.dirname(output_path), exist_ok=True)\n",
            "    import tempfile\n",
            "    with tempfile.TemporaryDirectory() as tmpdir:\n",
            "        job.download_results(tmpdir)\n",
            "        downloaded = glob.glob(os.path.join(tmpdir, '*.tif'))\n",
            "        if downloaded:\n",
            "            shutil.move(downloaded[0], output_path)\n",
            "            print(f\"Composite downloaded and saved: {output_path}\")\n",
            "        else:\n",
            "            raise RuntimeError(\"Failed to retrieve TIFF result from openEO service.\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 5. Analisis Perubahan Garis Pantai (Abrasi & Akresi)"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Deteksi Badan Air & Dinamika Pesisir\n",
            "Fungsi klasifikasi air/darat menggunakan threshold MNDWI dan perhitungan statistik luasan perubahan pantai."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "def classify_water_land(ds, threshold=MNDWI_THRESHOLD):\n",
            "    \"\"\"MNDWI > threshold diklasifikasikan sebagai air (True), sisanya sebagai darat (False).\"\"\"\n",
            "    return (ds['MNDWI'] > threshold).values\n",
            "\n",
            "def detect_shoreline_change(water_t1, water_t2):\n",
            "    \"\"\"\n",
            "    Menganalisis perbedaan grid air.\n",
            "     1 = Abrasi (darat berubah menjadi air)\n",
            "    -1 = Akresi (air berubah menjadi darat)\n",
            "     0 = Stabil\n",
            "    \"\"\"\n",
            "    return water_t2.astype(int) - water_t1.astype(int)\n",
            "\n",
            "def compute_shoreline_stats(change, pixel_area_ha):\n",
            "    abrasi_ha = np.sum(change == 1) * pixel_area_ha\n",
            "    akresi_ha = np.sum(change == -1) * pixel_area_ha\n",
            "    stabil_ha = np.sum(change == 0) * pixel_area_ha\n",
            "    return {\n",
            "        'abrasi_ha': float(abrasi_ha),\n",
            "        'akresi_ha': float(akresi_ha),\n",
            "        'stabil_ha': float(stabil_ha)\n",
            "    }"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 6. Analisis Ekosistem Hutan Mangrove"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Identifikasi & Penilaian Kesehatan Mangrove\n",
            "Fungsi spasial untuk memuat raster spasial Global Mangrove Watch (GMW) v3 lokal, melakukan masking area mangrove, dan klasifikasi NDVI."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "def get_tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):\n",
            "    \"\"\"\n",
            "    Mengidentifikasi nama file tile GMW v3 yang beririsan dengan bounding box analisis.\n",
            "    \"\"\"\n",
            "    lon_start = int(np.floor(min_lon))\n",
            "    lon_end = int(np.floor(max_lon))\n",
            "    lat_start = int(np.floor(min_lat))\n",
            "    lat_end = int(np.floor(max_lat))\n",
            "    \n",
            "    tiles = []\n",
            "    for lon in range(lon_start, lon_end + 1):\n",
            "        for lat_cell in range(lat_start, lat_end + 1):\n",
            "            top_lat = lat_cell + 1\n",
            "            if top_lat > 0:\n",
            "                lat_str = f'N{top_lat:02d}'\n",
            "            elif top_lat == 0:\n",
            "                lat_str = 'N00'\n",
            "            else:\n",
            "                lat_str = f'S{abs(top_lat):02d}'\n",
            "                \n",
            "            if lon >= 0:\n",
            "                lon_str = f'E{lon:03d}'\n",
            "            else:\n",
            "                lon_str = f'W{abs(lon):03d}'\n",
            "                \n",
            "            tile_name = f'GMW_{lat_str}{lon_str}_2020_v3.tif'\n",
            "            tiles.append(tile_name)\n",
            "    return tiles\n",
            "\n",
            "def load_mangrove_mask_rioxarray(bbox, province_geom, tile_dir, target_ds):\n",
            "    \"\"\"\n",
            "    Membuat masker biner hutan mangrove berdasarkan data raster Global Mangrove Watch v3.\n",
            "    \"\"\"\n",
            "    tile_names = get_tiles_for_bbox(*bbox)\n",
            "    tile_paths = [os.path.join(tile_dir, t) for t in tile_names if os.path.exists(os.path.join(tile_dir, t))]\n",
            "    \n",
            "    if not tile_paths:\n",
            "        return np.zeros(target_ds.rio.shape, dtype=bool)\n",
            "        \n",
            "    srcs = [rioxarray.open_rasterio(p) for p in tile_paths]\n",
            "    if len(srcs) == 1:\n",
            "        gmw = srcs[0]\n",
            "    else:\n",
            "        from rioxarray.merge import merge_arrays\n",
            "        gmw = merge_arrays(srcs)\n",
            "        \n",
            "    try:\n",
            "        cropped = gmw.rio.clip([province_geom], crs='EPSG:4326', all_touched=True)\n",
            "        matched = cropped.rio.reproject_match(target_ds)\n",
            "        mask = matched.values[0] == 1\n",
            "    except Exception as e:\n",
            "        print(f\"Warning: GMW clip failed ({e}). Returning empty mask.\")\n",
            "        mask = np.zeros(target_ds.rio.shape, dtype=bool)\n",
            "        \n",
            "    return mask\n",
            "\n",
            "def classify_mangrove_health_threshold(ds, mangrove_mask):\n",
            "    \"\"\"\n",
            "    Mengklasifikasikan kesehatan mangrove berdasarkan NDVI (pedoman Kepmen LH 201/2004).\n",
            "    \"\"\"\n",
            "    ndvi = ds['NDVI'].values\n",
            "    health = np.zeros_like(ndvi, dtype=np.uint8)\n",
            "    \n",
            "    health[ndvi <= NDVI_RUSAK] = 1                              # Rusak\n",
            "    health[(ndvi > NDVI_RUSAK) & (ndvi <= NDVI_SEDANG)] = 2    # Sedang\n",
            "    health[ndvi > NDVI_SEDANG] = 3                              # Sehat\n",
            "    health[~mangrove_mask] = 0                                  # Non-mangrove\n",
            "    return health\n",
            "\n",
            "def compute_mangrove_stats(health, pixel_area_ha):\n",
            "    results = {}\n",
            "    for kelas, label in [(1, 'rusak'), (2, 'sedang'), (3, 'sehat')]:\n",
            "        results[f'mangrove_{label}_ha'] = float(np.sum(health == kelas) * pixel_area_ha)\n",
            "    results['mangrove_total_ha'] = float(np.sum(health > 0) * pixel_area_ha)\n",
            "    return results\n",
            "\n",
            "def classify_mangrove_health_rf(ds, mangrove_mask):\n",
            "    \"\"\"\n",
            "    Klasifikasi kesehatan mangrove alternatif menggunakan algoritme Random Forest lokal.\n",
            "    \"\"\"\n",
            "    class_bands = ['NDVI', 'NDWI', 'MNDWI', 'EVI', 'SAVI', 'CMRI',\n",
            "                   'B02', 'B03', 'B04', 'B08', 'B11', 'B12']\n",
            "    \n",
            "    features_list = []\n",
            "    for band in class_bands:\n",
            "        features_list.append(ds[band].values[mangrove_mask])\n",
            "        \n",
            "    X = np.stack(features_list, axis=1)\n",
            "    valid_mask = ~np.isnan(X).any(axis=1)\n",
            "    X = X[valid_mask]\n",
            "    \n",
            "    ndvi_values = ds['NDVI'].values[mangrove_mask][valid_mask]\n",
            "    y = np.zeros_like(ndvi_values, dtype=int)\n",
            "    y[ndvi_values <= NDVI_RUSAK] = 1\n",
            "    y[(ndvi_values > NDVI_RUSAK) & (ndvi_values <= NDVI_SEDANG)] = 2\n",
            "    y[ndvi_values > NDVI_SEDANG] = 3\n",
            "    \n",
            "    if len(X) == 0:\n",
            "        raise ValueError(\"No valid mangrove pixels found for Random Forest training.\")\n",
            "        \n",
            "    from sklearn.model_selection import train_test_split\n",
            "    from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix\n",
            "    \n",
            "    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)\n",
            "    \n",
            "    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42)\n",
            "    rf.fit(X_train, y_train)\n",
            "    \n",
            "    y_pred = rf.predict(X_test)\n",
            "    acc = accuracy_score(y_test, y_pred)\n",
            "    kappa = cohen_kappa_score(y_test, y_pred)\n",
            "    cm = confusion_matrix(y_test, y_pred)\n",
            "    \n",
            "    all_pixels_features = []\n",
            "    for band in class_bands:\n",
            "        all_pixels_features.append(ds[band].values)\n",
            "        \n",
            "    stacked_all = np.stack(all_pixels_features, axis=-1)\n",
            "    y_dim, x_dim, n_feats = stacked_all.shape\n",
            "    flat_all = stacked_all.reshape(-1, n_feats)\n",
            "    flat_mangrove_mask = mangrove_mask.reshape(-1)\n",
            "    valid_flat_mask = flat_mangrove_mask & (~np.isnan(flat_all).any(axis=1))\n",
            "    \n",
            "    predicted_flat = np.zeros(y_dim * x_dim, dtype=np.uint8)\n",
            "    if np.sum(valid_flat_mask) > 0:\n",
            "        predicted_flat[valid_flat_mask] = rf.predict(flat_all[valid_flat_mask])\n",
            "        \n",
            "    predicted_health = predicted_flat.reshape(y_dim, x_dim)\n",
            "    \n",
            "    metrics = {\n",
            "        'overall_accuracy': float(acc),\n",
            "        'kappa': float(kappa),\n",
            "        'confusion_matrix': cm.tolist()\n",
            "    }\n",
            "    return predicted_health, metrics"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 7. Alur Utama Pemrosesan per Provinsi"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Pipeline Integrasi Provinsi\n",
            "Fungsi agregator untuk merangkum proses analisis spasial garis pantai dan mangrove pada suatu provinsi."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "def analyze_province(connection, province_feature, gadm_path, tile_dir, year_t1=YEAR_T1, year_t2=YEAR_T2, scale_export=SCALE_EXPORT):\n",
            "    geom = province_feature.geometry\n",
            "    province_name = province_feature.NAME_1 if hasattr(province_feature, 'NAME_1') else province_feature['NAME_1']\n",
            "    bbox = geom.bounds\n",
            "    \n",
            "    safe_name = province_name.replace(' ', '_').replace(\"'\", \"\")\n",
            "    os.makedirs('data/composites', exist_ok=True)\n",
            "    composite_path_t1 = f'data/composites/{safe_name}_{year_t1}.tif'\n",
            "    composite_path_t2 = f'data/composites/{safe_name}_{year_t2}.tif'\n",
            "    \n",
            "    get_composite_with_fallback(connection, bbox, year_t1, composite_path_t1, scale_export)\n",
            "    get_composite_with_fallback(connection, bbox, year_t2, composite_path_t2, scale_export)\n",
            "    \n",
            "    ds_t1_raw = rioxarray.open_rasterio(composite_path_t1)\n",
            "    ds_t2_raw = rioxarray.open_rasterio(composite_path_t2)\n",
            "    \n",
            "    band_names = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']\n",
            "    ds_t1 = xr.Dataset({name: ds_t1_raw.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})\n",
            "    ds_t2 = xr.Dataset({name: ds_t2_raw.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})\n",
            "    \n",
            "    ds_t1 = ds_t1.rio.write_crs('EPSG:4326')\n",
            "    ds_t2 = ds_t2.rio.write_crs('EPSG:4326')\n",
            "    \n",
            "    ds_t1 = add_spectral_indices(ds_t1)\n",
            "    ds_t2 = add_spectral_indices(ds_t2)\n",
            "    \n",
            "    water_t1 = classify_water_land(ds_t1)\n",
            "    water_t2 = classify_water_land(ds_t2)\n",
            "    change = detect_shoreline_change(water_t1, water_t2)\n",
            "    \n",
            "    res_x = abs(ds_t2.rio.transform()[0])\n",
            "    res_y = abs(ds_t2.rio.transform()[4])\n",
            "    res_x_m = res_x * 111320.0\n",
            "    res_y_m = res_y * 111320.0\n",
            "    pixel_area_ha = (res_x_m * res_y_m) / 10000.0\n",
            "    \n",
            "    shore_stats = compute_shoreline_stats(change, pixel_area_ha)\n",
            "    \n",
            "    mangrove_mask = load_mangrove_mask_rioxarray(bbox, geom, tile_dir, ds_t2['NDVI'])\n",
            "    health = classify_mangrove_health_threshold(ds_t2, mangrove_mask)\n",
            "    mangrove_stats = compute_mangrove_stats(health, pixel_area_ha)\n",
            "    \n",
            "    mangrove_ndvi = ds_t2['NDVI'].values[mangrove_mask]\n",
            "    mean_ndvi = float(np.mean(mangrove_ndvi)) if len(mangrove_ndvi) > 0 else 0.0\n",
            "    \n",
            "    results = {\n",
            "        'province_name': province_name,\n",
            "        'year_t1': year_t1,\n",
            "        'year_t2': year_t2,\n",
            "        'abrasi_ha': shore_stats['abrasi_ha'],\n",
            "        'akresi_ha': shore_stats['akresi_ha'],\n",
            "        'stabil_ha': shore_stats['stabil_ha'],\n",
            "        'mangrove_total_ha': mangrove_stats['mangrove_total_ha'],\n",
            "        'mangrove_sehat_ha': mangrove_stats['mangrove_sehat_ha'],\n",
            "        'mangrove_sedang_ha': mangrove_stats['mangrove_sedang_ha'],\n",
            "        'mangrove_rusak_ha': mangrove_stats['mangrove_rusak_ha'],\n",
            "        'mangrove_mean_ndvi': mean_ndvi\n",
            "    }\n",
            "    return results"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Konfigurasi Provinsi Analisis\n",
            "Menentukan daftar wilayah provinsi yang akan diproses."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Daftar provinsi yang dianalisis. Gunakan ['all'] untuk memproses seluruh wilayah.\n",
            "test_provinces = ['Bali']\n",
            "\n",
            "if 'all' in test_provinces or not test_provinces:\n",
            "    provinces_to_process = provinces\n",
            "else:\n",
            "    provinces_to_process = provinces[provinces['NAME_1'].isin(test_provinces)]\n",
            "    \n",
            "print(f\"Selected {len(provinces_to_process)} province(s) for analysis: {test_provinces}\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Loop Eksekusi Pipeline\n",
            "Menjalankan iterasi pipeline analisis di setiap provinsi dan menyusun hasilnya dalam format DataFrame."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "rows = []\n",
            "tile_dir = 'data/gmw_v3_2020_gtiff/gmw_v3_2020'\n",
            "\n",
            "for i, prov in enumerate(provinces_to_process.itertuples()):\n",
            "    print(f\"[{i+1}/{len(provinces_to_process)}] Processing {prov.NAME_1}...\")\n",
            "    try:\n",
            "        start_time = time.time()\n",
            "        res = analyze_province(connection, prov, gadm_path, tile_dir, YEAR_T1, YEAR_T2)\n",
            "        \n",
            "        pct_sehat = (res['mangrove_sehat_ha'] / res['mangrove_total_ha'] * 100) if res['mangrove_total_ha'] > 0 else 0\n",
            "        pct_sedang = (res['mangrove_sedang_ha'] / res['mangrove_total_ha'] * 100) if res['mangrove_total_ha'] > 0 else 0\n",
            "        pct_rusak = (res['mangrove_rusak_ha'] / res['mangrove_total_ha'] * 100) if res['mangrove_total_ha'] > 0 else 0\n",
            "        \n",
            "        if res['abrasi_ha'] > res['akresi_ha'] * 1.2:\n",
            "            status_pantai = 'ABRASI'\n",
            "        elif res['akresi_ha'] > res['abrasi_ha'] * 1.2:\n",
            "            status_pantai = 'AKRESI'\n",
            "        else:\n",
            "            status_pantai = 'STABIL'\n",
            "            \n",
            "        if pct_sehat >= 60:\n",
            "            status_mangrove = 'SEHAT'\n",
            "        elif pct_rusak >= 40:\n",
            "            status_mangrove = 'RUSAK'\n",
            "        else:\n",
            "            status_mangrove = 'SEDANG'\n",
            "            \n",
            "        rows.append({\n",
            "            'Provinsi': res['province_name'],\n",
            "            'Abrasi (ha)': round(res['abrasi_ha'], 2),\n",
            "            'Akresi (ha)': round(res['akresi_ha'], 2),\n",
            "            'Net Change (ha)': round(res['akresi_ha'] - res['abrasi_ha'], 2),\n",
            "            'Status Pantai': status_pantai,\n",
            "            'Mangrove Total (ha)': round(res['mangrove_total_ha'], 2),\n",
            "            'Mangrove Sehat (ha)': round(res['mangrove_sehat_ha'], 2),\n",
            "            'Mangrove Sedang (ha)': round(res['mangrove_sedang_ha'], 2),\n",
            "            'Mangrove Rusak (ha)': round(res['mangrove_rusak_ha'], 2),\n",
            "            '% Sehat': round(pct_sehat, 1),\n",
            "            '% Sedang': round(pct_sedang, 1),\n",
            "            '% Rusak': round(pct_rusak, 1),\n",
            "            'Mean NDVI': round(res['mangrove_mean_ndvi'], 4),\n",
            "            'Status Mangrove': status_mangrove\n",
            "        })\n",
            "        print(f\"  Successfully processed {prov.NAME_1} in {time.time() - start_time:.1f}s\")\n",
            "    except Exception as e:\n",
            "        print(f\"  Error processing {prov.NAME_1}: {e}\")\n",
            "\n",
            "df = pd.DataFrame(rows)\n",
            "if not df.empty:\n",
            "    df = df.sort_values('Provinsi').reset_index(drop=True)\n",
            "print(f\"\\nProcessing complete. Loaded data for {len(df)} province(s).\")\n",
            "df"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 8. Analisis & Visualisasi Hasil"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Ringkasan Hasil Analisis Nasional\n",
            "Mengekstrak deskripsi statistik akumulatif dinamika garis pantai dan parameter ekologi mangrove tingkat nasional."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "if not df.empty:\n",
            "    print(\"=\" * 60)\n",
            "    print(\"NATIONAL SUMMARY - INDONESIAN SHORELINE & MANGROVE ANALYSIS\")\n",
            "    print(f\"Shoreline Period: {YEAR_T1} -> {YEAR_T2}\")\n",
            "    print(f\"Mangrove Year:    {YEAR_MANGROVE}\")\n",
            "    print(\"=\" * 60)\n",
            "    \n",
            "    print(f\"\\nSHORELINE DYNAMICS:\")\n",
            "    print(f\"  Total Abrasion  : {df['Abrasi (ha)'].sum():,.1f} ha\")\n",
            "    print(f\"  Total Accretion  : {df['Akresi (ha)'].sum():,.1f} ha\")\n",
            "    print(f\"  Net Change      : {df['Net Change (ha)'].sum():,.1f} ha\")\n",
            "    print(f\"  Provinces with dominant Abrasion: {(df['Status Pantai'] == 'ABRASI').sum()}\")\n",
            "    print(f\"  Provinces with dominant Accretion: {(df['Status Pantai'] == 'AKRESI').sum()}\")\n",
            "    print(f\"  Stable Provinces:                 {(df['Status Pantai'] == 'STABIL').sum()}\")\n",
            "    \n",
            "    print(f\"\\nMANGROVE ECOLOGY:\")\n",
            "    print(f\"  Total Mangrove Area: {df['Mangrove Total (ha)'].sum():,.1f} ha\")\n",
            "    print(f\"  Healthy Mangroves:   {df['Mangrove Sehat (ha)'].sum():,.1f} ha\")\n",
            "    print(f\"  Moderate Mangroves:  {df['Mangrove Sedang (ha)'].sum():,.1f} ha\")\n",
            "    print(f\"  Damaged Mangroves:   {df['Mangrove Rusak (ha)'].sum():,.1f} ha\")\n",
            "    print(f\"  National Mean NDVI:  {df['Mean NDVI'].mean():.4f}\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Perbandingan 10 Provinsi Teratas (Abrasi vs Akresi)\n",
            "Grafik batang horizontal yang memetakan wilayah-wilayah dengan dinamika garis pantai tertinggi."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "if not df.empty and len(df) >= 2:\n",
            "    fig, axes = plt.subplots(1, 2, figsize=(18, 8))\n",
            "    fig.suptitle('Top 10 Provinces - Shoreline Change Dynamics', fontsize=16, fontweight='bold')\n",
            "    \n",
            "    # Top 10 Abrasi\n",
            "    ax1 = axes[0]\n",
            "    top_abrasi = df.nlargest(min(10, len(df)), 'Abrasi (ha)')\n",
            "    colors_abrasi = plt.cm.Reds(np.linspace(0.4, 0.9, len(top_abrasi)))\n",
            "    bars1 = ax1.barh(top_abrasi['Provinsi'], top_abrasi['Abrasi (ha)'], color=colors_abrasi)\n",
            "    ax1.set_xlabel('Abrasion Area (ha)')\n",
            "    ax1.set_title('Top 10 Largest Abrasion Areas')\n",
            "    ax1.invert_yaxis()\n",
            "    \n",
            "    # Top 10 Akresi\n",
            "    ax2 = axes[1]\n",
            "    top_akresi = df.nlargest(min(10, len(df)), 'Akresi (ha)')\n",
            "    colors_akresi = plt.cm.Greens(np.linspace(0.4, 0.9, len(top_akresi)))\n",
            "    bars2 = ax2.barh(top_akresi['Provinsi'], top_akresi['Akresi (ha)'], color=colors_akresi)\n",
            "    ax2.set_xlabel('Accretion Area (ha)')\n",
            "    ax2.set_title('Top 10 Largest Accretion Areas')\n",
            "    ax2.invert_yaxis()\n",
            "    \n",
            "    plt.tight_layout()\n",
            "    plt.savefig('output/figures/top10_shoreline_change.png', dpi=150, bbox_inches='tight')\n",
            "    plt.show()"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Sebaran Luas Kesehatan Mangrove\n",
            "Grafik batang sebaran tingkat kesehatan mangrove pada wilayah terluas, disandingkan dengan komposisi rata-rata nasional."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "if not df.empty:\n",
            "    fig, axes = plt.subplots(1, 2, figsize=(18, 8))\n",
            "    fig.suptitle('Mangrove Health Status by Province', fontsize=16, fontweight='bold')\n",
            "    \n",
            "    # Top 10 Mangrove\n",
            "    ax1 = axes[0]\n",
            "    top_mangrove = df.nlargest(min(10, len(df)), 'Mangrove Total (ha)')\n",
            "    x = np.arange(len(top_mangrove))\n",
            "    width = 0.25\n",
            "    \n",
            "    ax1.barh(x - width, top_mangrove['Mangrove Sehat (ha)'], width, label='Healthy', color='#2ecc71')\n",
            "    ax1.barh(x, top_mangrove['Mangrove Sedang (ha)'], width, label='Moderate', color='#f39c12')\n",
            "    ax1.barh(x + width, top_mangrove['Mangrove Rusak (ha)'], width, label='Damaged', color='#e74c3c')\n",
            "    \n",
            "    ax1.set_yticks(x)\n",
            "    ax1.set_yticklabels(top_mangrove['Provinsi'])\n",
            "    ax1.set_xlabel('Area (ha)')\n",
            "    ax1.set_title('Top Provinces by Mangrove Coverage')\n",
            "    ax1.legend()\n",
            "    ax1.invert_yaxis()\n",
            "    \n",
            "    # Pie Chart\n",
            "    ax2 = axes[1]\n",
            "    total_sehat = df['Mangrove Sehat (ha)'].sum()\n",
            "    total_sedang = df['Mangrove Sedang (ha)'].sum()\n",
            "    total_rusak = df['Mangrove Rusak (ha)'].sum()\n",
            "    \n",
            "    sizes = [total_sehat, total_sedang, total_rusak]\n",
            "    labels = [f'Healthy\\n{total_sehat:,.0f} ha', f'Moderate\\n{total_sedang:,.0f} ha', f'Damaged\\n{total_rusak:,.0f} ha']\n",
            "    colors = ['#2ecc71', '#f39c12', '#e74c3c']\n",
            "    \n",
            "    ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', shadow=True, startangle=90)\n",
            "    ax2.set_title('National Mangrove Health Composition')\n",
            "    \n",
            "    plt.tight_layout()\n",
            "    plt.savefig('output/figures/mangrove_health_summary.png', dpi=150, bbox_inches='tight')\n",
            "    plt.show()"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Perubahan Net Garis Pantai per Provinsi\n",
            "Grafik batang yang menunjukkan nilai net change per provinsi (akresi - abrasi)."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "if not df.empty:\n",
            "    fig, ax = plt.subplots(figsize=(14, 8))\n",
            "    df_sorted = df.sort_values('Net Change (ha)')\n",
            "    colors = ['#e74c3c' if x < 0 else '#2ecc71' for x in df_sorted['Net Change (ha)']]\n",
            "    \n",
            "    bars = ax.barh(df_sorted['Provinsi'], df_sorted['Net Change (ha)'], color=colors)\n",
            "    ax.axvline(x=0, color='black', linewidth=0.8, linestyle='--')\n",
            "    ax.set_xlabel('Net Change (ha)')\n",
            "    ax.set_title(f'Net Shoreline Change per Province ({YEAR_T1} -> {YEAR_T2})', fontsize=14, fontweight='bold')\n",
            "    \n",
            "    plt.tight_layout()\n",
            "    plt.savefig('output/figures/net_change_all_provinces.png', dpi=150, bbox_inches='tight')\n",
            "    plt.show()"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 9. Visualisasi Peta Spasial Interaktif"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Overlay Citra Satelit & Batas Spasial Provinsi\n",
            "Menampilkan peta komposit RGB Sentinel-2 terpotong berdasar batas provinsi untuk verifikasi spasial."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "DEMO_PROVINCE = 'Bali'\n",
            "demo_prov = provinces[provinces['NAME_1'] == DEMO_PROVINCE].iloc[0]\n",
            "geom = demo_prov.geometry\n",
            "bbox = geom.bounds\n",
            "safe_name = DEMO_PROVINCE.replace(' ', '_').replace(\"'\", \"\")\n",
            "\n",
            "composite_path = f'data/composites/{safe_name}_{YEAR_T2}.tif'\n",
            "if os.path.exists(composite_path):\n",
            "    ds = rioxarray.open_rasterio(composite_path)\n",
            "    band_names = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']\n",
            "    ds = xr.Dataset({name: ds.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})\n",
            "    ds = ds.rio.write_crs('EPSG:4326')\n",
            "    ds = add_spectral_indices(ds)\n",
            "    \n",
            "    center_lat = (bbox[1] + bbox[3]) / 2.0\n",
            "    center_lon = (bbox[0] + bbox[2]) / 2.0\n",
            "    \n",
            "    m_demo = folium.Map(location=[center_lat, center_lon], zoom_start=9)\n",
            "    \n",
            "    # Normalisasi RGB linear (kontras 2%-98% clipping)\n",
            "    rgb = np.stack([ds['B04'].values, ds['B03'].values, ds['B02'].values], axis=-1)\n",
            "    p_min, p_max = np.percentile(rgb, (2, 98))\n",
            "    rgb_norm = np.clip((rgb - p_min) / (p_max - p_min + 1e-10), 0, 1)\n",
            "    \n",
            "    from folium.raster_layers import ImageOverlay\n",
            "    img_bounds = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]]\n",
            "    \n",
            "    ImageOverlay(\n",
            "        image=rgb_norm,\n",
            "        bounds=img_bounds,\n",
            "        name=f'RGB {YEAR_T2}',\n",
            "        opacity=0.9\n",
            "    ).add_to(m_demo)\n",
            "    \n",
            "    # Batas Administrasi\n",
            "    folium.GeoJson(\n",
            "        geom,\n",
            "        name=f'Batas {DEMO_PROVINCE}',\n",
            "        style_function=lambda x: {'fillColor': 'none', 'color': '#00BCD4', 'weight': 3}\n",
            "    ).add_to(m_demo)\n",
            "    \n",
            "    folium.LayerControl().add_to(m_demo)\n",
            "    display(m_demo)\n",
            "else:\n",
            "    print(f\"Warning: Composite file {composite_path} not found. Please run the analysis loop first.\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Peta Tematik Nasional (Status Pesisir)\n",
            "Dashboard spasial nasional folium yang menggambarkan kelas dominansi perubahan pesisir tiap provinsi."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "m_national = folium.Map(location=[-2.5, 118], zoom_start=5)\n",
            "\n",
            "if not df.empty:\n",
            "    provinces_merged = provinces.merge(df, left_on='NAME_1', right_on='Provinsi')\n",
            "    provinces_merged_simplified = provinces_merged.copy()\n",
            "    provinces_merged_simplified['geometry'] = provinces_merged['geometry'].simplify(0.02)\n",
            "    \n",
            "    def get_color(row):\n",
            "        if row['Status Pantai'] == 'ABRASI':\n            return '#e74c3c'  # Merah\n",
            "        elif row['Status Pantai'] == 'AKRESI':\n            return '#2ecc71'  # Hijau\n",
            "        else:\n            return '#f39c12'  # Stabil (Kuning)\n",
            "            \n",
            "    folium.GeoJson(\n",
            "        provinces_merged_simplified,\n",
            "        style_function=lambda x: {\n",
            "            'fillColor': get_color(x['properties']),\n",
            "            'color': get_color(x['properties']),\n",
            "            'weight': 1.5,\n",
            "            'fillOpacity': 0.4\n",
            "        },\n",
            "        tooltip=folium.GeoJsonTooltip(fields=['NAME_1', 'Status Pantai', 'Abrasi (ha)', 'Akresi (ha)'],\n",
            "                                     aliases=['Provinsi:', 'Status Pantai:', 'Abrasi (ha):', 'Akresi (ha):'])\n",
            "    ).add_to(m_national)\n",
            "\n",
            "m_national"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 10. Ekspor & Penyimpanan Hasil"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Ekspor Hasil Statistik\n",
            "Menyimpan kompilasi data tabular luas abrasi, akresi, dan mangrove ke file CSV eksternal."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "if not df.empty:\n",
            "    os.makedirs('output', exist_ok=True)\n",
            "    df.to_csv('output/hasil_analisis_pesisir_34_provinsi.csv', index=False, encoding='utf-8-sig')\n",
            "    print(\"Results table saved to output/hasil_analisis_pesisir_34_provinsi.csv\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Penyimpanan Data Raster GIS\n",
            "Informasi penempatan berkas spasial hasil analisis."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "print(\"Composite and output GeoTIFF files are stored under data/composites/\")"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "## 11. Klasifikasi Mangrove Berbasis Random Forest (Supervised)"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "### Pelatihan & Evaluasi Klasifikasi Random Forest Lokal\n",
            "Sel opsional untuk melatih pengklasifikasi acak (Random Forest) guna menilai tingkat kesehatan mangrove dengan input seluruh band spektral."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "RF_PROVINCE = 'Bali'\n",
            "demo_prov = provinces[provinces['NAME_1'] == RF_PROVINCE].iloc[0]\n",
            "geom = demo_prov.geometry\n",
            "bbox = geom.bounds\n",
            "safe_name = RF_PROVINCE.replace(' ', '_').replace(\"'\", \"\")\n",
            "\n",
            "composite_path = f'data/composites/{safe_name}_{YEAR_T2}.tif'\n",
            "tile_dir = 'data/gmw_v3_2020_gtiff/gmw_v3_2020'\n",
            "\n",
            "if os.path.exists(composite_path):\n",
            "    print(f\"Running Random Forest classification for {RF_PROVINCE}...\")\n",
            "    ds = rioxarray.open_rasterio(composite_path)\n",
            "    band_names = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']\n",
            "    ds = xr.Dataset({name: ds.sel(band=i+1).drop_vars('band') for i, name in enumerate(band_names)})\n",
            "    ds = ds.rio.write_crs('EPSG:4326')\n",
            "    ds = add_spectral_indices(ds)\n",
            "    \n",
            "    mangrove_mask = load_mangrove_mask_rioxarray(bbox, geom, tile_dir, ds['NDVI'])\n",
            "    \n",
            "    try:\n",
            "        rf_result, rf_metrics = classify_mangrove_health_rf(ds, mangrove_mask)\n",
            "        print(f\"\\nRandom Forest Accuracy Metrics:\")\n",
            "        print(f\"  Overall Accuracy: {rf_metrics['overall_accuracy']:.2%}\")\n",
            "        print(f\"  Kappa Coefficient: {rf_metrics['kappa']:.4f}\")\n",
            "        print(\"  Confusion Matrix:\")\n",
            "        print(f\"  {rf_metrics['confusion_matrix']}\")\n",
            "        \n",
            "        res_x = abs(ds.rio.transform()[0])\n",
            "        res_y = abs(ds.rio.transform()[4])\n",
            "        res_x_m = res_x * 111320.0\n",
            "        res_y_m = res_y * 111320.0\n",
            "        pixel_area_ha = (res_x_m * res_y_m) / 10000.0\n",
            "        rf_stats = compute_mangrove_stats(rf_result, pixel_area_ha)\n",
            "        print(f\"\\nMangrove Area Classification (Random Forest):\")\n",
            "        print(f\"  Total Mangrove Area: {rf_stats['mangrove_total_ha']:.2f} ha\")\n",
            "        print(f\"  Healthy:             {rf_stats['mangrove_sehat_ha']:.2f} ha\")\n",
            "        print(f\"  Moderate:            {rf_stats['mangrove_sedang_ha']:.2f} ha\")\n",
            "        print(f\"  Damaged:             {rf_stats['mangrove_rusak_ha']:.2f} ha\")\n",
            "    except Exception as e:\n",
            "        print(f\"  Error in RF classification: {e}\")\n",
            "else:\n",
            "    print(f\"Warning: Composite file {composite_path} not found. Please run the analysis loop first.\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "print(\"=\" * 50)\n",
            "print(\"Notebook execution finished.\")\n",
            "print(\"=\" * 50)"
        ]
    }
]

# Build the notebook JSON dict
notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.10.2"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 5
}

# Write notebook
import os
output_path = r"d:\Lombuy IPBuy\Model\Model_Earth.ipynb"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"Successfully generated new {output_path}!")
