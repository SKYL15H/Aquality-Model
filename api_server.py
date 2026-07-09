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
        "API analisis kualitas air pesisir Banten dan sistem rekomendasi pantai tersehat."
    ),
    version="1.1.0",
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

MODEL_META_PATH = "output/model/model_metadata.json"
BANTEN_WATER_PATH = "output/banten_water_quality_kecamatan.json"
BANTEN_BEACH_PATH = "output/banten_water_quality_beach.json"
BANTEN_INDUSTRIES_PATH = "output/banten_industries.json"
BANTEN_BEACH_GEOJSON_PATH = "output/banten_coastal_beaches.geojson"

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
        "context": "daerah muara Ciujung bagian hilir dan kawasan vegetasi pesisir",
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
        "sources": ["erosi tebing alami", "sedimentasi sungai lokal", "turbulensi pasir akibat ombak"]
    },
    "panggarangan": {
        "context": "pesisir terbuka dengan aktivitas tambang batu bara tradisional/pasir di hulu",
        "sources": ["limpasan sedimen tambang rakyat", "erosi pantai alami", "buangan domestik sungai"]
    }
}


def _build_industry_text(stats: dict) -> str:
    """Membangun teks konteks dampak industri untuk narasi penjelasan.
    
    Menggunakan 3 metrik: jarak industri terdekat, kepadatan, dan Indeks Dampak Industri (IDI).
    """
    industri = stats.get("industri_terdekat")
    jarak = stats.get("jarak_industri_km")
    idi = stats.get("indeks_dampak_industri", 0)
    kategori = stats.get("kategori_dampak_industri", "")
    tipe = stats.get("tipe_industri", "")
    n_radius = stats.get("jumlah_industri_radius_10km", 0)
    industri_relevan = stats.get("industri_relevan_terdekat")
    jarak_relevan = stats.get("jarak_industri_relevan_km")
    
    if not industri or jarak is None:
        return ""
    
    # Bangun teks berdasarkan IDI
    if idi >= 30:
        text = (
            f" Indeks Dampak Industri di wilayah ini **{idi}/100** (kategori **{kategori}**) "
            f"dengan {n_radius} fasilitas industri dalam radius 10 km."
        )
        if industri_relevan and jarak_relevan:
            text += f" Industri paling relevan terhadap pencemaran air adalah {industri_relevan} berjarak **{jarak_relevan} km**."
        text += " Tekanan kumulatif industri terhadap kualitas perairan sangat signifikan."
    elif idi >= 15:
        text = (
            f" Indeks Dampak Industri **{idi}/100** ({kategori}) dengan {n_radius} industri dalam radius 10 km. "
            f"Industri terdekat: {industri} ({tipe}) berjarak **{jarak} km**. "
            f"Pengaruh industri terhadap kualitas perairan bersifat moderat."
        )
    elif idi >= 5:
        text = (
            f" Indeks Dampak Industri **{idi}/100** ({kategori}). "
            f"Industri terdekat adalah {industri} ({tipe}) berjarak **{jarak} km** "
            f"dengan dampak relatif rendah terhadap kualitas air."
        )
    else:
        text = (
            f" Indeks Dampak Industri sangat rendah (**{idi}/100**). "
            f"Industri terdekat ({industri}) berjarak **{jarak} km** — "
            f"dampak industri terhadap kualitas air sangat minimal."
        )
    
    return text


def _build_demographic_and_urban_text(stats: dict) -> str:
    """Membangun teks penjelasan untuk kepadatan penduduk dan indeks pengaruh urban."""
    density = stats.get("kepadatan_penduduk_kecamatan")
    ipu = stats.get("indeks_pengaruh_urban")
    kec = stats.get("Kecamatan", "pesisir Banten")
    
    if density is None or ipu is None:
        return ""
        
    text = f" Wilayah ini memiliki kepadatan penduduk **{density:,.0f} jiwa/km²**."
    if ipu >= 60:
        text += f" Indeks Pengaruh Urban bernilai **TINGGI** ({ipu}/100) akibat dekatnya perairan dengan sprawl metropolitan/pusat aktivitas perkotaan utama."
    elif ipu >= 30:
        text += f" Indeks Pengaruh Urban bernilai **SEDANG** ({ipu}/100) dengan kontribusi limpasan domestik perkotaan sedang."
    else:
        text += f" Indeks Pengaruh Urban bernilai **RENDAH** ({ipu}/100) karena lokasinya relatif terpencil dari aglomerasi perkotaan utama."
    return text


def generate_explanation(kec_name: str, stats: dict) -> str:
    """Menghasilkan narasi penjelasan tingkat kelayakan pesisir berdasarkan kepadatan penduduk, urbanisasi, dan industri."""
    name_lower = kec_name.lower()
    
    # Ambil profil daerah
    profile = DISTRICT_CONTEXTS.get(name_lower)
    
    if profile:
        context_text = f"Kecamatan {kec_name} merupakan {profile['context']}. "
        sources_text = f"Kondisi ini dipengaruhi oleh {', '.join(profile['sources'])}."
    else:
        # Fallback berdasarkan kabupaten
        kab = stats.get("Kabupaten_Kota", "Banten")
        context_text = f"Kecamatan {kec_name} terletak di wilayah pesisir {kab}. "
        sources_text = "Kondisi ini dipengaruhi oleh aktivitas domestik dan kepadatan penduduk sekitar pesisir."

    # Teks jarak industri & demografi/urban
    industry_text = _build_industry_text(stats)
    demo_urban_text = _build_demographic_and_urban_text(stats)
    
    # Tentukan kelayakan umum berdasarkan Indeks Dampak Industri (IDI) dan Indeks Pengaruh Urban (IPU)
    idi = stats.get("indeks_dampak_industri", 0.0)
    ipu = stats.get("indeks_pengaruh_urban", 0.0)
    
    if idi >= 30 or ipu >= 60:
        reason = (
            f"Kawasan pesisir di {kec_name} dinilai memiliki **TEKANAN LINGKUNGAN TINGGI**. {context_text}"
            f"Tingginya aktivitas industri dan/atau kepadatan pemukiman urban di wilayah ini memberikan kontribusi polutan antropogenik yang signifikan ke perairan pesisir."
            f"{demo_urban_text}{industry_text}"
        )
    elif idi >= 15 or ipu >= 30:
        reason = (
            f"Kawasan pesisir di {kec_name} berada dalam kondisi kelayakan lingkungan **SEDANG**. {context_text}"
            f"Terdapat tekanan antropogenik menengah dari pemukiman domestik atau area industri regional."
            f"{demo_urban_text}{industry_text}"
        )
    else:
        reason = (
            f"Kawasan pesisir di {kec_name} diklasifikasikan memiliki kelayakan lingkungan **SANGAT BAIK (Lestari)**. {context_text}"
            f"Kondisi alam sekitar terjaga dengan kepadatan penduduk yang minim serta jarak yang sangat jauh dari kawasan industri berat."
            f"{demo_urban_text}{industry_text}"
        )
        
    return reason


@app.on_event("startup")
def load_data():
    global MODEL_METADATA, BANTEN_WATER_STATS, BANTEN_BEACH_STATS, BEACH_RECOMMENDER, BANTEN_BEACH_GEOJSON

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
        "description": "Analisis kualitas air pesisir Banten & Sistem Rekomendasi Pantai Tersehat",
        "endpoints": {
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


# Rute abrasi, akresi, dan mangrove provinsi dihapus


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
            "indeks_dampak_industri": stats.get("indeks_dampak_industri"),
            "jumlah_industri_radius_10km": stats.get("jumlah_industri_radius_10km"),
            "kepadatan_industri": stats.get("kepadatan_industri"),
            "industri_relevan_terdekat": stats.get("industri_relevan_terdekat"),
            "jarak_industri_relevan_km": stats.get("jarak_industri_relevan_km"),
            "kepadatan_penduduk_kecamatan": stats.get("kepadatan_penduduk_kecamatan"),
            "indeks_pengaruh_urban": stats.get("indeks_pengaruh_urban"),
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
    """Menghasilkan narasi penjelasan kelayakan pantai berdasarkan demografi, urban, dan jarak industri."""
    kec_name = stats.get("Kecamatan", "pesisir Banten")
    
    # Teks jarak industri & demografi/urban
    industry_text = _build_industry_text(stats)
    demo_urban_text = _build_demographic_and_urban_text(stats)
    
    idi = stats.get("indeks_dampak_industri", 0.0)
    ipu = stats.get("indeks_pengaruh_urban", 0.0)
    
    if idi >= 30 or ipu >= 60:
        return (
            f"Kawasan pesisir di {beach_name} ({kec_name}) dinilai memiliki **TEKANAN LINGKUNGAN TINGGI**. "
            f"Hal ini dipengaruhi oleh tingginya aktivitas manusia perkotaan atau letaknya yang dekat dengan pusat industri."
            f"{demo_urban_text}{industry_text}"
        )
    elif idi >= 15 or ipu >= 30:
        return (
            f"Kawasan pesisir di {beach_name} ({kec_name}) berada dalam kondisi kelayakan lingkungan **SEDANG**. "
            f"Terdapat pengaruh antropogenik menengah dari pemukiman perkotaan sekitar atau aktivitas pelabuhan/industri regional."
            f"{demo_urban_text}{industry_text}"
        )
    else:
        return (
            f"Kawasan pesisir di {beach_name} ({kec_name}) diklasifikasikan memiliki kelayakan lingkungan **SANGAT BAIK (Lestari)**. "
            f"Wilayah pantai sangat bersih dari pencemaran darat karena kepadatan penduduk lokal sangat rendah dan jauh dari kawasan industri berat."
            f"{demo_urban_text}{industry_text}"
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
            "indeks_dampak_industri": stats.get("indeks_dampak_industri"),
            "jumlah_industri_radius_10km": stats.get("jumlah_industri_radius_10km"),
            "kepadatan_industri": stats.get("kepadatan_industri"),
            "industri_relevan_terdekat": stats.get("industri_relevan_terdekat"),
            "jarak_industri_relevan_km": stats.get("jarak_industri_relevan_km"),
            "kepadatan_penduduk_kecamatan": stats.get("kepadatan_penduduk_kecamatan"),
            "indeks_pengaruh_urban": stats.get("indeks_pengaruh_urban"),
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
    - 25% Persentase area air sehat (terkoreksi bias pantai)
    - 15% Kejernihan air (terkoreksi energi gelombang pantai)
    - 10% Kadar klorofil-a (1 - NDCI, inverted)
    - 5%  Kandungan padatan tersuspensi (1 - TSS, inverted)
    - 5%  Bahan organik terlarut (1 - CDOM, inverted)
    - 10% Tren kualitas historis (MEMBAIK > STABIL > MEMBURUK)
    - 10% Dampak industri terdekat (RENDAH > SEDANG > TINGGI)
    - 15% Risiko polusi urban (rendah = bagus)
    - 5%  Bonus sirkulasi perairan (energi gelombang tinggi = bagus)
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
        "model": "Multi-Criteria Weighted Health Score v2.0",
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
