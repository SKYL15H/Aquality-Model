"""
api_server.py — FastAPI Server untuk Coast-Vision

Menyajikan data hasil pre-computation ke frontend website.
Hanya membaca file JSON dan model .joblib yang sudah disiapkan oleh batch_process.py.

Penggunaan:
    uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


# ---------------------------------------------------------------------------
# Inisialisasi Aplikasi
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Coast-Vision API",
    description=(
        "API analisis pesisir Indonesia: deteksi abrasi/akresi garis pantai "
        "dan klasifikasi kesehatan hutan mangrove 34 provinsi."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Load Data Pre-Computed
# ---------------------------------------------------------------------------

STATS_PATH = "output/provinces_stats.json"
MODEL_META_PATH = "output/model/model_metadata.json"

PROVINCE_STATS = {}
MODEL_METADATA = {}


@app.on_event("startup")
def load_data():
    global PROVINCE_STATS, MODEL_METADATA

    if os.path.exists(STATS_PATH):
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            PROVINCE_STATS.update(json.load(f))
        print(f"Loaded statistics for {len(PROVINCE_STATS)} province(s).")
    else:
        print(f"Warning: {STATS_PATH} not found. Run batch_process.py first.")

    if os.path.exists(MODEL_META_PATH):
        with open(MODEL_META_PATH, "r", encoding="utf-8") as f:
            MODEL_METADATA.update(json.load(f))
        print("Loaded model metadata.")
    else:
        print(f"Warning: {MODEL_META_PATH} not found.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Coast-Vision API",
        "version": "1.0.0",
        "description": "Analisis pesisir & mangrove 34 provinsi Indonesia",
        "endpoints": {
            "provinces_list": "/api/provinces",
            "province_detail": "/api/provinces/{name}",
            "national_summary": "/api/summary",
            "model_info": "/api/model/info",
        },
    }


@app.get("/api/provinces")
def list_provinces():
    """Daftar seluruh provinsi yang sudah diproses."""
    provinces = []
    for name, data in PROVINCE_STATS.items():
        provinces.append({
            "name": name,
            "status_pantai": data.get("status_pantai"),
            "status_mangrove": data.get("status_mangrove"),
        })
    provinces.sort(key=lambda x: x["name"])
    return {
        "total": len(provinces),
        "provinces": provinces,
    }


@app.get("/api/provinces/{name}")
def get_province(name: str):
    """Detail statistik untuk satu provinsi."""
    # Cari case-insensitive
    matched = None
    for key in PROVINCE_STATS:
        if key.lower() == name.lower():
            matched = key
            break

    if matched is None:
        available = sorted(PROVINCE_STATS.keys())
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Province '{name}' not found.",
                "available": available,
            },
        )

    return PROVINCE_STATS[matched]


@app.get("/api/summary")
def national_summary():
    """Ringkasan statistik nasional (agregat seluruh provinsi yang sudah diproses)."""
    if not PROVINCE_STATS:
        raise HTTPException(status_code=404, detail="No data available.")

    total_abrasi   = sum(p.get("abrasi_ha", 0) for p in PROVINCE_STATS.values())
    total_akresi   = sum(p.get("akresi_ha", 0) for p in PROVINCE_STATS.values())
    total_mangrove = sum(p.get("mangrove_total_ha", 0) for p in PROVINCE_STATS.values())
    total_sehat    = sum(p.get("mangrove_sehat_ha", 0) for p in PROVINCE_STATS.values())
    total_sedang   = sum(p.get("mangrove_sedang_ha", 0) for p in PROVINCE_STATS.values())
    total_rusak    = sum(p.get("mangrove_rusak_ha", 0) for p in PROVINCE_STATS.values())

    ndvi_values = [
        p.get("mean_ndvi", 0)
        for p in PROVINCE_STATS.values()
        if p.get("mean_ndvi", 0) > 0
    ]
    mean_ndvi = sum(ndvi_values) / len(ndvi_values) if ndvi_values else 0

    status_counts = {"ABRASI": 0, "AKRESI": 0, "STABIL": 0}
    for p in PROVINCE_STATS.values():
        s = p.get("status_pantai", "STABIL")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "total_provinces": len(PROVINCE_STATS),
        "period": {
            "baseline_year": 2017,
            "comparison_year": 2026,
        },
        "shoreline": {
            "total_abrasi_ha": round(total_abrasi, 2),
            "total_akresi_ha": round(total_akresi, 2),
            "net_change_ha": round(total_akresi - total_abrasi, 2),
            "provinces_abrasi": status_counts.get("ABRASI", 0),
            "provinces_akresi": status_counts.get("AKRESI", 0),
            "provinces_stabil": status_counts.get("STABIL", 0),
        },
        "mangrove": {
            "total_area_ha": round(total_mangrove, 2),
            "sehat_ha": round(total_sehat, 2),
            "sedang_ha": round(total_sedang, 2),
            "rusak_ha": round(total_rusak, 2),
            "mean_ndvi": round(mean_ndvi, 4),
        },
    }


@app.get("/api/model/info")
def model_info():
    """Metadata dan metrik akurasi model Random Forest."""
    if not MODEL_METADATA:
        raise HTTPException(
            status_code=404,
            detail="Model metadata not available. Run batch_process.py first.",
        )
    return MODEL_METADATA
