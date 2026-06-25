"""
batch_process.py — Batch Processing 34 Provinsi & Training Model RF

Skrip ini dijalankan secara OFFLINE (di PC lokal / server) untuk:
1. Memproses seluruh 34 provinsi Indonesia via openEO + analisis lokal.
2. Melatih model Random Forest pada data mangrove gabungan.
3. Menyimpan hasil ke file JSON dan model .joblib untuk deployment API.

Penggunaan:
    python batch_process.py                     # proses semua provinsi
    python batch_process.py --provinces Bali Banten   # proses provinsi tertentu
    python batch_process.py --skip-openeo       # skip download, pakai composite yang sudah ada
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier

import coast_vision as cv


def derive_status(res):
    """Hitung persentase dan tentukan status pantai/mangrove dari hasil analisis."""
    total = res["mangrove_total_ha"]
    pct_sehat  = (res["mangrove_sehat_ha"]  / total * 100) if total > 0 else 0
    pct_sedang = (res["mangrove_sedang_ha"] / total * 100) if total > 0 else 0
    pct_rusak  = (res["mangrove_rusak_ha"]  / total * 100) if total > 0 else 0

    if res["abrasi_ha"] > res["akresi_ha"] * 1.2:
        status_pantai = "ABRASI"
    elif res["akresi_ha"] > res["abrasi_ha"] * 1.2:
        status_pantai = "AKRESI"
    else:
        status_pantai = "STABIL"

    if pct_sehat >= 60:
        status_mangrove = "SEHAT"
    elif pct_rusak >= 40:
        status_mangrove = "RUSAK"
    else:
        status_mangrove = "SEDANG"

    return {
        "pct_sehat": round(pct_sehat, 1),
        "pct_sedang": round(pct_sedang, 1),
        "pct_rusak": round(pct_rusak, 1),
        "status_pantai": status_pantai,
        "status_mangrove": status_mangrove,
    }


def build_province_record(res):
    """Gabungkan hasil analisis dan status menjadi satu dict."""
    status = derive_status(res)
    return {
        "provinsi": res["province_name"],
        "year_t1": res["year_t1"],
        "year_t2": res["year_t2"],
        "abrasi_ha": round(res["abrasi_ha"], 2),
        "akresi_ha": round(res["akresi_ha"], 2),
        "net_change_ha": round(res["akresi_ha"] - res["abrasi_ha"], 2),
        "status_pantai": status["status_pantai"],
        "mangrove_total_ha": round(res["mangrove_total_ha"], 2),
        "mangrove_sehat_ha": round(res["mangrove_sehat_ha"], 2),
        "mangrove_sedang_ha": round(res["mangrove_sedang_ha"], 2),
        "mangrove_rusak_ha": round(res["mangrove_rusak_ha"], 2),
        "pct_sehat": status["pct_sehat"],
        "pct_sedang": status["pct_sedang"],
        "pct_rusak": status["pct_rusak"],
        "mean_ndvi": round(res["mangrove_mean_ndvi"], 4),
        "status_mangrove": status["status_mangrove"],
    }


def train_rf_model(provinces_gdf, tile_dir=cv.TILE_DIR):
    """
    Melatih model Random Forest pada data mangrove dari provinsi
    yang composite-nya sudah tersedia.

    Returns
    -------
    rf_model : RandomForestClassifier atau None
    rf_metrics : dict atau None
    """
    print("\n" + "=" * 60)
    print("TRAINING RANDOM FOREST MODEL")
    print("=" * 60)

    all_X = []
    all_y = []

    class_bands = [
        "NDVI", "NDWI", "MNDWI", "EVI", "SAVI", "CMRI",
        "B02", "B03", "B04", "B08", "B11", "B12",
    ]

    for _, prov_row in provinces_gdf.iterrows():
        name = prov_row["NAME_1"]
        safe_name = name.replace(" ", "_").replace("'", "")
        path_t2 = os.path.join(cv.COMPOSITE_DIR, f"{safe_name}_{cv.YEAR_T2}.tif")

        if not os.path.exists(path_t2):
            continue

        print(f"  Collecting training data from {name}...")
        try:
            ds = cv.load_composite_as_dataset(path_t2)
            geom = prov_row.geometry
            bbox = geom.bounds

            mangrove_mask = cv.load_mangrove_mask_rioxarray(
                bbox, geom, tile_dir, ds["NDVI"],
            )

            if np.sum(mangrove_mask) == 0:
                print(f"    No mangrove pixels found, skipping.")
                continue

            features = [ds[band].values[mangrove_mask] for band in class_bands]
            X = np.stack(features, axis=1)
            valid = ~np.isnan(X).any(axis=1)
            X = X[valid]

            ndvi_vals = ds["NDVI"].values[mangrove_mask][valid]
            y = np.zeros_like(ndvi_vals, dtype=int)
            y[ndvi_vals <= cv.NDVI_RUSAK] = 1
            y[(ndvi_vals > cv.NDVI_RUSAK) & (ndvi_vals <= cv.NDVI_SEDANG)] = 2
            y[ndvi_vals > cv.NDVI_SEDANG] = 3

            all_X.append(X)
            all_y.append(y)
            print(f"    Collected {len(X)} valid pixels.")
        except Exception as exc:
            print(f"    Error: {exc}")

    if not all_X:
        print("  No training data available. Skipping model training.")
        return None, None

    X_combined = np.concatenate(all_X, axis=0)
    y_combined = np.concatenate(all_y, axis=0)
    print(f"\n  Total training samples: {len(X_combined)}")
    print(f"  Class distribution: rusak={np.sum(y_combined==1)}, "
          f"sedang={np.sum(y_combined==2)}, sehat={np.sum(y_combined==3)}")

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix

    X_train, X_test, y_train, y_test = train_test_split(
        X_combined, y_combined, test_size=0.3, random_state=42, stratify=y_combined,
    )

    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42)
    rf.fit(X_train, y_train)

    y_pred = rf.predict(X_test)
    acc   = accuracy_score(y_test, y_pred)
    kappa = cohen_kappa_score(y_test, y_pred)
    cm    = confusion_matrix(y_test, y_pred)

    metrics = {
        "overall_accuracy": round(float(acc), 4),
        "kappa": round(float(kappa), 4),
        "confusion_matrix": cm.tolist(),
        "n_training_samples": int(len(X_train)),
        "n_test_samples": int(len(X_test)),
        "feature_names": class_bands,
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    print(f"\n  Overall Accuracy: {acc:.2%}")
    print(f"  Kappa Coefficient: {kappa:.4f}")
    print(f"  Confusion Matrix:\n  {cm}")

    return rf, metrics


def main():
    parser = argparse.ArgumentParser(
        description="Batch processing 34 provinsi Indonesia."
    )
    parser.add_argument(
        "--provinces", nargs="*", default=None,
        help="Daftar provinsi yang diproses (default: semua).",
    )
    parser.add_argument(
        "--skip-openeo", action="store_true",
        help="Lewati download openEO, hanya proses composite yang sudah ada.",
    )
    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Load data provinsi
    # -----------------------------------------------------------------------
    if not os.path.exists(cv.GADM_PATH):
        print(f"Error: GADM file not found at {cv.GADM_PATH}")
        print("Run data_downloader.py first.")
        sys.exit(1)

    provinces = cv.load_provinces()
    province_names = sorted(provinces["NAME_1"].unique().tolist())

    if args.provinces:
        selected = [p for p in province_names if p in args.provinces]
        if not selected:
            print(f"Error: None of {args.provinces} found in GADM data.")
            sys.exit(1)
        provinces_to_process = provinces[provinces["NAME_1"].isin(selected)]
    else:
        provinces_to_process = provinces

    print("=" * 60)
    print("COAST-VISION BATCH PROCESSING")
    print(f"Provinces: {len(provinces_to_process)}")
    print(f"Baseline: {cv.YEAR_T1} -> Comparison: {cv.YEAR_T2}")
    print(f"Skip openEO: {args.skip_openeo}")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # Koneksi openEO (jika diperlukan)
    # -----------------------------------------------------------------------
    connection = None
    if not args.skip_openeo:
        try:
            import openeo
            print("\nConnecting to openEO CDSE...")
            connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
            connection.authenticate_oidc()
            print("Authentication successful.")
        except Exception as exc:
            print(f"Warning: openEO connection failed ({exc}).")
            print("Continuing with --skip-openeo mode.")
            args.skip_openeo = True

    # -----------------------------------------------------------------------
    # Proses per provinsi
    # -----------------------------------------------------------------------
    results = []

    for i, prov in enumerate(provinces_to_process.itertuples()):
        name = prov.NAME_1
        print(f"\n[{i+1}/{len(provinces_to_process)}] Processing {name}...")

        if args.skip_openeo:
            # Cek apakah composite sudah tersedia
            safe_name = name.replace(" ", "_").replace("'", "")
            path_t1 = os.path.join(cv.COMPOSITE_DIR, f"{safe_name}_{cv.YEAR_T1}.tif")
            path_t2 = os.path.join(cv.COMPOSITE_DIR, f"{safe_name}_{cv.YEAR_T2}.tif")

            if not os.path.exists(path_t1) or not os.path.exists(path_t2):
                print(f"  Skipping {name}: composite files not found.")
                continue

            # Analisis lokal tanpa openEO
            try:
                t0 = time.time()
                ds_t1 = cv.load_composite_as_dataset(path_t1)
                ds_t2 = cv.load_composite_as_dataset(path_t2)

                water_t1 = cv.classify_water_land(ds_t1)
                water_t2 = cv.classify_water_land(ds_t2)
                change = cv.detect_shoreline_change(water_t1, water_t2)

                pixel_area_ha = cv.compute_pixel_area_ha(ds_t2)
                shore_stats = cv.compute_shoreline_stats(change, pixel_area_ha)

                geom = prov.geometry
                bbox = geom.bounds
                mangrove_mask = cv.load_mangrove_mask_rioxarray(
                    bbox, geom, cv.TILE_DIR, ds_t2["NDVI"],
                )
                health = cv.classify_mangrove_health_threshold(ds_t2, mangrove_mask)
                mangrove_stats = cv.compute_mangrove_stats(health, pixel_area_ha)

                mangrove_ndvi = ds_t2["NDVI"].values[mangrove_mask]
                mean_ndvi = float(np.mean(mangrove_ndvi)) if len(mangrove_ndvi) > 0 else 0.0

                res = {
                    "province_name": name,
                    "year_t1": cv.YEAR_T1,
                    "year_t2": cv.YEAR_T2,
                    "abrasi_ha": shore_stats["abrasi_ha"],
                    "akresi_ha": shore_stats["akresi_ha"],
                    "stabil_ha": shore_stats["stabil_ha"],
                    "mangrove_total_ha": mangrove_stats["mangrove_total_ha"],
                    "mangrove_sehat_ha": mangrove_stats["mangrove_sehat_ha"],
                    "mangrove_sedang_ha": mangrove_stats["mangrove_sedang_ha"],
                    "mangrove_rusak_ha": mangrove_stats["mangrove_rusak_ha"],
                    "mangrove_mean_ndvi": mean_ndvi,
                }

                record = build_province_record(res)
                results.append(record)
                print(f"  Done in {time.time() - t0:.1f}s")
            except Exception as exc:
                print(f"  Error: {exc}")
        else:
            try:
                t0 = time.time()
                res = cv.analyze_province(
                    connection, prov, cv.TILE_DIR,
                    cv.YEAR_T1, cv.YEAR_T2, cv.SCALE_EXPORT,
                )
                record = build_province_record(res)
                results.append(record)
                print(f"  Done in {time.time() - t0:.1f}s")
            except Exception as exc:
                print(f"  Error: {exc}")

    # -----------------------------------------------------------------------
    # Simpan hasil statistik
    # -----------------------------------------------------------------------
    os.makedirs("output/model", exist_ok=True)

    if results:
        # JSON per provinsi (untuk API)
        stats_dict = {r["provinsi"]: r for r in results}
        stats_path = "output/provinces_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats_dict, f, indent=2, ensure_ascii=False)
        print(f"\nStatistics saved to {stats_path}")

        # CSV ringkasan
        df = pd.DataFrame(results)
        csv_path = "output/hasil_analisis_pesisir_34_provinsi.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"CSV saved to {csv_path}")

    # -----------------------------------------------------------------------
    # Training model Random Forest
    # -----------------------------------------------------------------------
    rf_model, rf_metrics = train_rf_model(provinces)

    if rf_model is not None:
        model_path = "output/model/mangrove_rf.joblib"
        joblib.dump(rf_model, model_path)
        print(f"\nRF model saved to {model_path}")

        meta_path = "output/model/model_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(rf_metrics, f, indent=2, ensure_ascii=False)
        print(f"Model metadata saved to {meta_path}")

    # -----------------------------------------------------------------------
    # Ringkasan
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETE")
    print(f"Provinces processed: {len(results)}")
    if rf_model:
        print(f"RF model accuracy: {rf_metrics['overall_accuracy']:.2%}")
    print("=" * 60)


if __name__ == "__main__":
    main()
