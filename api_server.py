"""
api_server.py — FastAPI Server untuk Aquality

Menyajikan data hasil pre-computation ke frontend website.
Hanya membaca file JSON dan model .joblib yang sudah disiapkan oleh batch_process.py.

Penggunaan:
    uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
"""

import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from beach_recommendation import BeachRecommender


# ---------------------------------------------------------------------------
# Inisialisasi Aplikasi
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Aquality API",
    description=(
        "API analisis kualitas air daerah pesisir"
        "provinsi banten."
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

# Mounting folder output sebagai static files agar peta HTML bisa diakses
if os.path.exists("output"):
    app.mount("/static", StaticFiles(directory="output"), name="static")


# ---------------------------------------------------------------------------
# Load Data Pre-Computed & Konteks Wilayah
# ---------------------------------------------------------------------------

STATS_PATH = "output/provinces_stats.json"
MODEL_META_PATH = "output/model/model_metadata.json"
BANTEN_WATER_PATH = "output/banten_water_quality_kecamatan.json"
BANTEN_BEACH_PATH = "output/banten_water_quality_beach.json"
BANTEN_INDUSTRIES_PATH = "output/banten_industries.json"
BANTEN_BEACH_GEOJSON_PATH = "output/banten_coastal_beaches.geojson"

PROVINCE_STATS = {}
MODEL_METADATA = {}
BANTEN_WATER_STATS = {}
BANTEN_BEACH_STATS = {}
BANTEN_INDUSTRIES = []
BANTEN_BEACH_GEOJSON = {}
BEACH_RECOMMENDER: BeachRecommender | None = None

# Kamus profil geografis/aktivitas nyata untuk kecamatan pesisir Banten
DISTRICT_CONTEXTS = {
    # Cilegon
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
    # Serang Kota & Kabupaten
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
    # Pandeglang
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
    # Lebak
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


def _build_industry_text(stats: dict) -> str:
    """Membangun teks konteks jarak industri untuk narasi penjelasan."""
    industri = stats.get("industri_terdekat")
    jarak = stats.get("jarak_industri_km")
    kategori = stats.get("kategori_dampak_industri")
    tipe = stats.get("tipe_industri", "")
    
    if not industri or jarak is None:
        return ""
    
    if kategori == "TINGGI":
        return (
            f" Lokasi ini berada dalam radius dampak **TINGGI** dari fasilitas industri {industri} ({tipe}) "
            f"yang berjarak hanya **{jarak} km**, sehingga potensi kontribusi polutan industri terhadap penurunan kualitas air sangat signifikan."
        )
    elif kategori == "SEDANG":
        return (
            f" Terdapat fasilitas industri {industri} ({tipe}) dalam radius **{jarak} km** "
            f"dengan kategori dampak **SEDANG**, yang berpotensi turut memengaruhi kondisi kualitas perairan."
        )
    else:
        return (
            f" Industri terdekat adalah {industri} ({tipe}) berjarak **{jarak} km** "
            f"dengan kategori dampak **RENDAH**."
        )


def generate_explanation(kec_name: str, stats: dict) -> str:
    """Menghasilkan narasi penjelasan kualitas air yang menggabungkan parameter satelit, profil wilayah, dan jarak industri."""
    name_lower = kec_name.lower()
    status = stats.get("Status_Kualitas_2026", "TIDAK SEHAT")
    ndti = stats.get("Mean_NDTI_2026", 0.0)
    ndci = stats.get("Mean_NDCI_2026", 0.0)
    
    # Ambil profil daerah
    profile = DISTRICT_CONTEXTS.get(name_lower)
    
    if profile:
        context_text = f"Kecamatan {kec_name} merupakan {profile['context']}. "
        sources_text = f"Kondisi ini dipengaruhi oleh {', '.join(profile['sources'])}."
    else:
        # Fallback berdasarkan kabupaten
        kab = stats.get("Kabupaten_Kota", "Banten")
        context_text = f"Kecamatan {kec_name} terletak di wilayah pesisir {kab}. "
        sources_text = "Kondisi ini dipengaruhi oleh aktivitas domestik dan limpasan permukaan sekitar perairan pesisir."

    # Teks jarak industri
    industry_text = _build_industry_text(stats)

    if status == "TIDAK SEHAT":
        reason = (
            f"Status Kualitas Air di {kec_name} diklasifikasikan sebagai **TIDAK SEHAT**. {context_text}"
        )
        param_reasons = []
        if ndti > 0.05:
            param_reasons.append(
                f"tingkat kekeruhan air (NDTI: {ndti:.4f}) melebihi ambang batas aman 0.05 yang menandakan sedimentasi pantai yang tinggi"
            )
        if ndci > 0.08:
            param_reasons.append(
                f"konsentrasi klorofil-a (NDCI: {ndci:.4f}) melampaui batas aman 0.08 yang mengindikasikan adanya blooming alga (eutrofikasi) akibat penumpukan zat hara/nutrien"
            )
            
        if param_reasons:
            reason += "Hal ini terbukti secara ilmiah melalui analisis citra Sentinel-2 di mana " + " dan ".join(param_reasons) + ". "
        else:
            reason += f"Hasil analisis menunjukkan akumulasi parameter fisik-kimiawi air (TSS/CDOM) melampaui baku mutu optimal. "
            
        reason += sources_text + industry_text
        
    elif status == "SEDANG":
        reason = (
            f"Kualitas air pesisir di {kec_name} berada dalam kondisi **SEDANG**. {context_text}"
            f"Meskipun parameter kekeruhan (NDTI: {ndti:.4f}) dan klorofil-a (NDCI: {ndci:.4f}) masih berada dalam tingkat toleransi wajar, "
            f"tetap diperlukan pengawasan karena adanya kontribusi polusi dari {', '.join(profile['sources']) if profile else 'aktivitas antropogenik lokal'}."
            f"{industry_text}"
        )
    else: # SEHAT
        reason = (
            f"Kualitas air pesisir di {kec_name} diklasifikasikan sebagai **SEHAT** (Optimum). {context_text}"
            f"Kondisi fisik perairan terpantau sangat bersih dengan kekeruhan rendah (NDTI: {ndti:.4f}) dan kadar klorofil-a (NDCI: {ndci:.4f}) yang seimbang, "
            f"menunjukkan sirkulasi perairan yang baik serta minimnya dampak negatif dari {', '.join(profile['sources']) if profile else 'limbah domestik perkotaan'}."
            f"{industry_text}"
        )
        
    return reason


@app.on_event("startup")
def load_data():
    global PROVINCE_STATS, MODEL_METADATA, BANTEN_WATER_STATS, BANTEN_BEACH_STATS, BEACH_RECOMMENDER, BANTEN_BEACH_GEOJSON

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

    if os.path.exists(BANTEN_WATER_PATH):
        with open(BANTEN_WATER_PATH, "r", encoding="utf-8") as f:
            BANTEN_WATER_STATS.update(json.load(f))
        print(f"Loaded water quality statistics for {len(BANTEN_WATER_STATS)} Banten districts.")
    else:
        print(f"Warning: {BANTEN_WATER_PATH} not found.")

    if os.path.exists(BANTEN_BEACH_PATH):
        with open(BANTEN_BEACH_PATH, "r", encoding="utf-8") as f:
            BANTEN_BEACH_STATS.update(json.load(f))
        print(f"Loaded water quality statistics for {len(BANTEN_BEACH_STATS)} Banten beaches.")
    else:
        print(f"Warning: {BANTEN_BEACH_PATH} not found.")

    global BANTEN_INDUSTRIES
    if os.path.exists(BANTEN_INDUSTRIES_PATH):
        with open(BANTEN_INDUSTRIES_PATH, "r", encoding="utf-8") as f:
            BANTEN_INDUSTRIES = json.load(f)
        print(f"Loaded {len(BANTEN_INDUSTRIES)} industry locations.")
    else:
        print(f"Warning: {BANTEN_INDUSTRIES_PATH} not found.")

    if os.path.exists(BANTEN_BEACH_GEOJSON_PATH):
        with open(BANTEN_BEACH_GEOJSON_PATH, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
            for feature in geojson_data.get("features", []):
                beach_name = feature.get("properties", {}).get("Pantai")
                if beach_name:
                    BANTEN_BEACH_GEOJSON[beach_name.lower()] = feature
        print(f"Loaded {len(BANTEN_BEACH_GEOJSON)} beach GeoJSON features.")
    else:
        print(f"Warning: {BANTEN_BEACH_GEOJSON_PATH} not found.")

    # Inisialisasi sistem rekomendasi pantai
    if BANTEN_BEACH_STATS:
        BEACH_RECOMMENDER = BeachRecommender(data_dict=BANTEN_BEACH_STATS)
        summary = BEACH_RECOMMENDER.get_summary()
        print(f"Beach Recommender initialized: {summary['total_pantai']} beaches scored, "
              f"best={summary['pantai_terbaik']}, mean_score={summary['health_score_mean']}")
    else:
        BEACH_RECOMMENDER = None
        print("Warning: Beach Recommender not initialized — no beach data available.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["General"])
def root():
    return {
        "service": "Aquality API",
        "version": "1.1.0",
        "description": "Analisis kualitas air provinsi banten + sistem rekomendasi pantai terbersih",
        "endpoints": {
            "provinces_list": "/api/provinces",
            "province_detail": "/api/provinces/{name}",
            "national_summary": "/api/summary",
            "model_info": "/api/model/info",
            "water_quality_leaderboard": "/api/water-quality/explore",
            "water_quality_district": "/api/water-quality/kecamatan/{name}",
            "water_quality_beach_leaderboard": "/api/water-quality/beach/explore",
            "water_quality_beach": "/api/water-quality/beach/{name}",
            "analyze_beach_by_slug": "/api/analyze/{slug}",
            "industries": "/api/industries",
            "recommendation_beaches": "/api/recommendation/beaches?top_n=5",
            "recommendation_beach_detail": "/api/recommendation/beaches/{name}",
            "recommendation_summary": "/api/recommendation/summary",
            "static_maps": "/static/banten_water_quality_map.html"
        },
    }


@app.get("/api/provinces", tags=["Provinces & National Summary"])
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


@app.get("/api/provinces/{name}", tags=["Provinces & National Summary"])
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


@app.get("/api/summary", tags=["Provinces & National Summary"])
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


@app.get("/api/model/info", tags=["Model & Industry Data"])
def model_info():
    """Metadata dan metrik akurasi model Random Forest."""
    if not MODEL_METADATA:
        raise HTTPException(
            status_code=404,
            detail="Model metadata not available. Run batch_process.py first.",
        )
    return MODEL_METADATA


# ---------------------------------------------------------------------------
# Endpoints Kualitas Air Kecamatan (Banten Leaderboard & Detail)
# ---------------------------------------------------------------------------

@app.get("/api/water-quality/explore", tags=["Water Quality - Kecamatan"])
def get_leaderboard():
    """Mengembalikan daftar kecamatan terbersih pesisir Banten diurutkan berdasarkan Pct_Sehat_2026 secara descending."""
    if not BANTEN_WATER_STATS:
        raise HTTPException(
            status_code=404,
            detail="Banten water quality statistics not loaded. Please run analysis script first."
        )
    
    leaderboard = []
    for kec_name, stats in BANTEN_WATER_STATS.items():
        leaderboard.append({
            "kecamatan": kec_name,
            "kabupaten_kota": stats.get("Kabupaten_Kota"),
            "pct_sehat_2026": stats.get("Pct_Sehat_2026", 0.0),
            "status_kualitas_2026": stats.get("Status_Kualitas_2026"),
            "latitude": stats.get("centroid_latitude"),
            "longitude": stats.get("centroid_longitude"),
            "industri_terdekat": stats.get("industri_terdekat"),
            "jarak_industri_km": stats.get("jarak_industri_km"),
            "kategori_dampak_industri": stats.get("kategori_dampak_industri"),
            "url_gambar": stats.get("Url_gambar") or stats.get("url_gambar")
        })
        
    # Urutkan berdasarkan Pct_Sehat_2026 tertinggi
    leaderboard.sort(key=lambda x: x["pct_sehat_2026"], reverse=True)
    return {
        "total": len(leaderboard),
        "leaderboard": leaderboard
    }


@app.get("/api/water-quality/kecamatan/{name}", tags=["Water Quality - Kecamatan"])
def get_district_water_quality(name: str):
    """Mengembalikan statistik rinci untuk satu kecamatan di Banten beserta alasan semantik kondisi airnya."""
    # Pencarian case-insensitive
    matched_key = None
    for key in BANTEN_WATER_STATS:
        if key.lower() == name.lower():
            matched_key = key
            break
            
    if matched_key is None:
        raise HTTPException(
            status_code=404,
            detail=f"Kecamatan '{name}' tidak ditemukan di data Banten. Gunakan daftar di leaderboard."
        )
        
    stats = BANTEN_WATER_STATS[matched_key]
    
    # Generate penjelasan dinamis
    explanation = generate_explanation(matched_key, stats)
    
    # Buat salinan statistik dan tambahkan narasi penjelasannya
    response_data = dict(stats)
    response_data["kecamatan"] = matched_key
    response_data["penjelasan_kualitas"] = explanation
    
    return response_data


def generate_beach_explanation(beach_name: str, stats: dict) -> str:
    """Menghasilkan narasi penjelasan kualitas air tingkat pantai dengan konteks jarak industri."""
    status = stats.get("Status_Kualitas_2026", "TIDAK SEHAT")
    ndti = stats.get("Mean_NDTI_2026", 0.0)
    ndci = stats.get("Mean_NDCI_2026", 0.0)
    kec_name = stats.get("Kecamatan", "pesisir Banten")
    
    # Teks jarak industri
    industry_text = _build_industry_text(stats)
    
    if status == "SEHAT":
        return (
            f"Kualitas air di {beach_name} ({kec_name}) tergolong **SEHAT** (Bersih). "
            f"Kondisi perairan pantai sangat bersih dengan kekeruhan rendah (NDTI: {ndti:.4f}) dan klorofil-a (NDCI: {ndci:.4f}) yang normal, "
            f"menjadikannya sangat aman dan nyaman untuk kegiatan pariwisata atau berenang."
            f"{industry_text}"
        )
    elif status == "SEDANG":
        return (
            f"Kualitas air di {beach_name} ({kec_name}) berada dalam kondisi **SEDANG**. "
            f"Perairan pantai cukup bersih namun tingkat kekeruhan (NDTI: {ndti:.4f}) atau klorofil-a (NDCI: {ndci:.4f}) menunjukkan nilai ambang batas wajar. "
            f"Pengunjung dihimbau tetap menjaga kebersihan pantai sekitar."
            f"{industry_text}"
        )
    else: # TIDAK SEHAT
        reasons = []
        if ndti > 0.05:
            reasons.append(f"tingginya kekeruhan air (NDTI: {ndti:.4f}) akibat limpasan sedimen darat")
        if ndci > 0.08:
            reasons.append(f"kadar klorofil-a yang tinggi (NDCI: {ndci:.4f}) yang menandakan penumpukan nutrien/blooming alga")
        reason_str = " dan ".join(reasons) if reasons else "penurunan baku mutu air laut pesisir"
        return (
            f"Kualitas air di {beach_name} ({kec_name}) tergolong **TIDAK SEHAT** (Tercemar). "
            f"Analisis menunjukkan {reason_str}. Disarankan untuk membatasi aktivitas kontak langsung seperti berenang di sekitar perairan pantai ini."
            f"{industry_text}"
        )


@app.get("/api/water-quality/beach/explore", tags=["Water Quality - Beach"])
def get_beach_leaderboard():
    """Mengembalikan daftar pantai terbersih di pesisir Banten diurutkan berdasarkan Pct_Sehat_2026 secara descending."""
    if not BANTEN_BEACH_STATS:
        raise HTTPException(
            status_code=404,
            detail="Banten beach water quality statistics not loaded. Please run analysis script first."
        )
    
    leaderboard = []
    for beach_name, stats in BANTEN_BEACH_STATS.items():
        leaderboard.append({
            "pantai": beach_name,
            "slug": stats.get("slug") or "".join(c if c.isalnum() or c in " -" else "" for c in beach_name.lower().strip()).replace(" ", "-").replace("--", "-"),
            "kecamatan": stats.get("Kecamatan"),
            "kabupaten_kota": stats.get("Kabupaten_Kota"),
            "pct_sehat_2026": stats.get("Pct_Sehat_2026", 0.0),
            "status_kualitas_2026": stats.get("Status_Kualitas_2026"),
            "latitude": stats.get("latitude"),
            "longitude": stats.get("longitude"),
            "industri_terdekat": stats.get("industri_terdekat"),
            "jarak_industri_km": stats.get("jarak_industri_km"),
            "kategori_dampak_industri": stats.get("kategori_dampak_industri"),
            "url_gambar": stats.get("Url_gambar") or stats.get("url_gambar")
        })
        
    leaderboard.sort(key=lambda x: x["pct_sehat_2026"], reverse=True)
    return {
        "total": len(leaderboard),
        "leaderboard": leaderboard
    }


@app.get("/api/water-quality/beach/{name}", tags=["Water Quality - Beach"])
def get_beach_water_quality(name: str):
    """Mengembalikan statistik rinci untuk satu pantai di Banten beserta penjelasan semantiknya."""
    matched_key = None
    for key in BANTEN_BEACH_STATS:
        if key.lower() == name.lower():
            matched_key = key
            break
            
    if matched_key is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pantai '{name}' tidak ditemukan di data Banten. Gunakan daftar di leaderboard."
        )
        
    stats = BANTEN_BEACH_STATS[matched_key]
    explanation = generate_beach_explanation(matched_key, stats)
    
    response_data = dict(stats)
    response_data["pantai"] = matched_key
    response_data["slug"] = stats.get("slug") or "".join(c if c.isalnum() or c in " -" else "" for c in matched_key.lower().strip()).replace(" ", "-").replace("--", "-")
    response_data["penjelasan_kualitas"] = explanation
    response_data["geojson"] = BANTEN_BEACH_GEOJSON.get(matched_key.lower())
    
    return response_data


@app.get("/analyze/{slug}", tags=["Water Quality - Beach"])
@app.get("/api/analyze/{slug}", tags=["Water Quality - Beach"])
def analyze_beach_by_slug(slug: str):
    """Mengembalikan analisis kualitas air rinci untuk satu pantai berdasarkan slug-nya (contoh: 'pantai-carita')."""
    matched_key = None
    for key, stats in BANTEN_BEACH_STATS.items():
        item_slug = stats.get("slug") or "".join(c if c.isalnum() or c in " -" else "" for c in key.lower().strip()).replace(" ", "-").replace("--", "-")
        if item_slug.lower() == slug.lower():
            matched_key = key
            break
            
    if matched_key is None:
        available_slugs = [
            stats.get("slug") or "".join(c if c.isalnum() or c in " -" else "" for c in k.lower().strip()).replace(" ", "-").replace("--", "-")
            for k, stats in BANTEN_BEACH_STATS.items()
        ]
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Pantai dengan slug '{slug}' tidak ditemukan.",
                "available_slugs": available_slugs
            }
        )
        
    stats = BANTEN_BEACH_STATS[matched_key]
    explanation = generate_beach_explanation(matched_key, stats)
    
    response_data = dict(stats)
    response_data["pantai"] = matched_key
    response_data["slug"] = stats.get("slug") or "".join(c if c.isalnum() or c in " -" else "" for c in matched_key.lower().strip()).replace(" ", "-").replace("--", "-")
    response_data["penjelasan_kualitas"] = explanation
    response_data["geojson"] = BANTEN_BEACH_GEOJSON.get(matched_key.lower())
    
    return response_data


# ---------------------------------------------------------------------------
# Endpoint Daftar Industri/Pabrik
# ---------------------------------------------------------------------------

@app.get("/api/industries", tags=["Model & Industry Data"])
def get_industries():
    """Mengembalikan daftar seluruh industri/pabrik besar di Banten beserta koordinatnya."""
    return {
        "total": len(BANTEN_INDUSTRIES),
        "industries": BANTEN_INDUSTRIES
    }


# ---------------------------------------------------------------------------
# Endpoints Sistem Rekomendasi Pantai Tersehat
# ---------------------------------------------------------------------------

@app.get("/api/recommendation/beaches", tags=["Beach Recommendation"])
def get_beach_recommendations(
    top_n: int = Query(default=None, ge=1, le=100, description="Jumlah pantai teratas. Kosongkan untuk semua."),
    min_score: float = Query(default=None, ge=0, le=100, description="Filter: Health Score minimum."),
):
    """Mengembalikan daftar rekomendasi pantai tersehat di Banten, diurutkan berdasarkan Health Score tertinggi.
    
    Health Score dihitung dari kombinasi multi-parameter:
    - 30% Persentase area air sehat (Pct_Sehat_2026)
    - 20% Kejernihan air (1 - NDTI, inverted)
    - 10% Kadar klorofil-a (1 - NDCI, inverted)
    - 10% Kandungan padatan tersuspensi (1 - TSS, inverted)
    - 5%  Bahan organik terlarut (1 - CDOM, inverted)
    - 15% Tren kualitas historis (MEMBAIK > STABIL > MEMBURUK)
    - 10% Dampak industri terdekat (RENDAH > SEDANG > TINGGI)
    """
    if BEACH_RECOMMENDER is None:
        raise HTTPException(
            status_code=404,
            detail="Sistem rekomendasi belum diinisialisasi. Data pantai tidak tersedia."
        )
    
    results = BEACH_RECOMMENDER.get_recommendations(top_n=top_n)
    
    # Filter berdasarkan minimum score jika diberikan
    if min_score is not None:
        results = [r for r in results if r["health_score"] >= min_score]
    
    # Tambahkan narasi untuk setiap pantai
    enriched = []
    for beach in results:
        entry = dict(beach)
        entry["narasi_rekomendasi"] = BEACH_RECOMMENDER.generate_recommendation_text(beach)
        enriched.append(entry)
    
    return {
        "total": len(enriched),
        "model": "Multi-Criteria Weighted Health Score v1.0",
        "recommendations": enriched
    }


@app.get("/api/recommendation/beaches/{name}", tags=["Beach Recommendation"])
def get_beach_recommendation_detail(name: str):
    """Mengembalikan skor rekomendasi dan narasi detail untuk satu pantai berdasarkan nama."""
    if BEACH_RECOMMENDER is None:
        raise HTTPException(
            status_code=404,
            detail="Sistem rekomendasi belum diinisialisasi."
        )
    
    result = BEACH_RECOMMENDER.get_beach_score(name)
    if result is None:
        available = [b["pantai"] for b in BEACH_RECOMMENDER.get_recommendations()]
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Pantai '{name}' tidak ditemukan.",
                "available": available
            }
        )
    
    response = dict(result)
    response["narasi_rekomendasi"] = BEACH_RECOMMENDER.generate_recommendation_text(result)
    return response


@app.get("/api/recommendation/summary", tags=["Beach Recommendation"])
def get_recommendation_summary():
    """Ringkasan statistik model rekomendasi: distribusi label, skor rata-rata, bobot parameter."""
    if BEACH_RECOMMENDER is None:
        raise HTTPException(
            status_code=404,
            detail="Sistem rekomendasi belum diinisialisasi."
        )
    
    return BEACH_RECOMMENDER.get_summary()
