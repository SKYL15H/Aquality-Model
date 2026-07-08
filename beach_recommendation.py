"""
beach_recommendation.py — Sistem Rekomendasi Pantai Tersehat

Model rekomendasi berbasis skor komposit kesehatan air pantai (Health Score)
yang menggabungkan beberapa parameter kualitas air dari citra Sentinel-2:
  - Persentase area sehat (Pct_Sehat_2026)
  - Kekeruhan air (NDTI) — semakin rendah semakin baik
  - Konsentrasi klorofil-a (NDCI) — semakin rendah semakin baik
  - Total Suspended Solids (TSS) — semakin rendah semakin baik
  - Colored Dissolved Organic Matter (CDOM) — semakin rendah semakin baik
  - Tren kualitas air historis (MEMBAIK > STABIL > MEMBURUK)
  - Dampak industri terdekat (RENDAH > SEDANG > TINGGI)

Penggunaan:
    from beach_recommendation import BeachRecommender
    recommender = BeachRecommender("output/banten_water_quality_beach.json")
    top_beaches = recommender.get_recommendations(top_n=5)
"""

import json
import math
import os
from typing import Any


# ---------------------------------------------------------------------------
# Konstanta bobot parameter untuk skor komposit (v2.0)
# ---------------------------------------------------------------------------

# Klasifikasi energi gelombang pantai berdasarkan kecamatan
# HIGH  = Samudra Hindia (pantai selatan) — ombak besar, turbulensi alami tinggi
# MEDIUM = Selat Sunda (pantai barat) — ombak sedang
# LOW   = Laut Jawa / Teluk Jakarta (pantai utara) — perairan tenang
COASTAL_ENERGY = {
    # Pantai Selatan — Samudra Hindia (HIGH energy)
    "Bayah": "HIGH",
    "Cihara": "HIGH",
    "Malingping": "HIGH",
    "Wanasalam": "HIGH",
    "Panggarangan": "HIGH",
    # Pantai Barat — Selat Sunda (MEDIUM energy)
    "Sumur": "MEDIUM",
    "Panimbang": "MEDIUM",
    "Carita": "MEDIUM",
    "Cinangka": "MEDIUM",
    "Anyar": "MEDIUM",
    "Labuan": "MEDIUM",
    # Pantai Utara — Laut Jawa / Teluk Jakarta (LOW energy)
    "Teluknaga": "LOW",
    "Mauk": "LOW",
    "Kronjo": "LOW",
    "Tirtayasa": "LOW",
    "Pontang": "LOW",
    "Tanara": "LOW",
    "Kasemen": "LOW",
    "Bojonegara": "LOW",
    "Kramatwatu": "LOW",
    "Pulomerak": "LOW",
    "Ciwandan": "LOW",
    "Grogol": "LOW",
}

# Faktor koreksi NDTI berdasarkan energi gelombang pantai.
# Pada pantai berenergi tinggi, sebagian besar kekeruhan bersifat alami
# (turbulensi ombak mengaduk pasir dasar), bukan polusi.
NDTI_CORRECTION = {
    "HIGH": 0.35,    # Hanya 35% NDTI bersifat antropogenik; 65% turbulensi alami
    "MEDIUM": 0.70,  # 30% turbulensi alami
    "LOW": 1.00,     # Tidak dikoreksi — NDTI mencerminkan kondisi sebenarnya
}

# Koreksi kompensasi Pct_Sehat berdasarkan energi pantai.
# Pct_Sehat_2026 dihitung oleh model RF yang menggunakan NDTI mentah,
# sehingga pantai berenergi tinggi dirugikan secara sistematis.
PCT_SEHAT_BOOST = {
    "HIGH": 15.0,    # Tambah 15 pp sebagai kompensasi bias RF
    "MEDIUM": 5.0,   # Koreksi ringan
    "LOW": 0.0,      # Tidak dikoreksi
}

# Risiko polusi urban/antropogenik per kecamatan (0 = pristine, 1 = sangat tercemar).
# Parameter proxy berdasarkan kepadatan penduduk, aktivitas industri, jarak dari
# pusat urban, dan keberadaan muara sungai yang membawa limbah domestik.
URBAN_POLLUTION_RISK = {
    # Pantai Utara — dekat Jakarta/Tangerang urban sprawl
    "Teluknaga": 0.90,   # Suburban Tangerang, sangat dekat Jakarta
    "Mauk": 0.75,        # Pesisir Tangerang, urban sedang
    "Kronjo": 0.65,      # Semi-urban Tangerang
    # Pesisir industri Cilegon
    "Pulomerak": 0.85,   # Industri berat + Pelabuhan Merak
    "Ciwandan": 0.90,    # Hub industri baja/kimia
    "Grogol": 0.75,      # Industri utara Cilegon
    "Bojonegara": 0.80,  # Galangan kapal + industri
    # Pesisir Serang
    "Kasemen": 0.70,     # Pelabuhan ikan + tambak padat
    "Kramatwatu": 0.65,  # Dekat zona industri
    "Tirtayasa": 0.50,   # Tambak pedesaan
    "Pontang": 0.55,     # Muara sungai + tambak
    "Tanara": 0.50,      # Limpasan pertanian
    # Pantai Barat — zona wisata
    "Anyar": 0.45,       # Pariwisata, pembangunan sedang
    "Cinangka": 0.40,    # Pariwisata sedang
    "Carita": 0.40,      # Pariwisata
    "Labuan": 0.55,      # Pelabuhan ikan + PLTU Labuan
    # Barat daya — kurang berkembang
    "Panimbang": 0.30,   # KEK pariwisata berkembang
    "Sumur": 0.15,       # Penyangga TN Ujung Kulon, pristine
    # Pantai Selatan — terpencil dan alami
    "Bayah": 0.25,       # Terpencil, ada pertambangan semen
    "Cihara": 0.15,      # Sangat terpencil
    "Malingping": 0.20,  # Terpencil
    "Wanasalam": 0.35,   # Pelabuhan ikan Binuangeun
    "Panggarangan": 0.20, # Terpencil, tambang rakyat
}

# Skor sirkulasi perairan berdasarkan energi gelombang.
# Prinsip oseanografi: energi gelombang tinggi = sirkulasi lebih baik = dilusi
# polutan lebih cepat = perairan lebih bersih secara alami.
SIRKULASI_SCORES = {
    "HIGH": 1.0,     # Sirkulasi sangat baik
    "MEDIUM": 0.6,   # Sirkulasi cukup
    "LOW": 0.2,      # Sirkulasi lemah, polutan terakumulasi
}

# Bobot setiap parameter dalam perhitungan Health Score v2.0 (total = 1.0)
WEIGHTS = {
    "pct_sehat": 0.25,          # Persentase area sehat (terkoreksi bias pantai)
    "ndti_inv": 0.15,           # Kekeruhan (terkoreksi energi gelombang)
    "ndci_inv": 0.10,           # Klorofil-a (inverted)
    "tss_inv": 0.05,            # TSS (inverted)
    "cdom_inv": 0.05,           # CDOM (inverted)
    "tren": 0.10,               # Tren kualitas historis
    "industri_inv": 0.10,       # Dampak industri terdekat (inverted)
    "polusi_urban_inv": 0.15,   # Risiko polusi urban (inverted — rendah = bagus)
    "sirkulasi_pantai": 0.05,   # Bonus sirkulasi perairan (tinggi = bagus)
}

# Skor kualitatif untuk tren kualitas
TREN_SCORES = {
    "MEMBAIK": 1.0,
    "STABIL": 0.5,
    "MEMBURUK": 0.0,
}

# Skor kualitatif untuk kategori dampak industri (inverted: rendah = baik)
INDUSTRI_SCORES = {
    "RENDAH": 1.0,
    "SEDANG": 0.5,
    "TINGGI": 0.0,
}

# Label klasifikasi Health Score
HEALTH_LABELS = [
    (80, "SANGAT DIREKOMENDASIKAN"),
    (60, "DIREKOMENDASIKAN"),
    (40, "CUKUP DIREKOMENDASIKAN"),
    (20, "KURANG DIREKOMENDASIKAN"),
    (0, "TIDAK DIREKOMENDASIKAN"),
]


class BeachRecommender:
    """Sistem rekomendasi pantai berdasarkan skor komposit kesehatan air."""

    def __init__(self, data_path: str | None = None, data_dict: dict | None = None):
        """
        Args:
            data_path: Path ke file JSON banten_water_quality_beach.json
            data_dict: Alternatif — langsung kirim dict data pantai
                       (berguna saat dipanggil dari api_server.py yang sudah load data)
        """
        if data_dict is not None:
            self.raw_data = data_dict
        elif data_path and os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                self.raw_data = json.load(f)
        else:
            self.raw_data = {}

        self._scores: list[dict[str, Any]] = []
        if self.raw_data:
            self._compute_all_scores()

    # ------------------------------------------------------------------
    # Normalisasi Min-Max ke skala 0-100
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(value: float, min_val: float, max_val: float, invert: bool = False) -> float:
        """Normalisasi nilai ke skala 0-100. Jika invert=True, nilai rendah → skor tinggi."""
        if max_val == min_val:
            return 50.0  # fallback jika semua nilai sama
        norm = (value - min_val) / (max_val - min_val)
        if invert:
            norm = 1.0 - norm
        return max(0.0, min(100.0, norm * 100.0))

    # ------------------------------------------------------------------
    # Hitung skor komposit untuk semua pantai
    # ------------------------------------------------------------------

    def _compute_all_scores(self) -> None:
        """Menghitung Health Score v2.0 untuk seluruh pantai.
        
        Perbedaan dari v1.0:
        - NDTI dikoreksi berdasarkan energi gelombang pantai (HIGH/MEDIUM/LOW)
        - Pct_Sehat mendapat kompensasi boost untuk pantai berenergi tinggi
        - Ditambahkan parameter risiko polusi urban/antropogenik
        - Ditambahkan bonus sirkulasi perairan
        """
        beaches = self.raw_data

        # 1. Tentukan tipe pantai dan koreksi NDTI untuk setiap pantai
        corrected_data = {}
        for name, stats in beaches.items():
            kec = stats.get("Kecamatan", "")
            energy_type = COASTAL_ENERGY.get(kec, "MEDIUM")
            correction = NDTI_CORRECTION.get(energy_type, 1.0)
            boost = PCT_SEHAT_BOOST.get(energy_type, 0.0)

            raw_ndti = abs(stats.get("Mean_NDTI_2026", 0.0))
            corrected_ndti = raw_ndti * correction  # Koreksi NDTI

            raw_pct = stats.get("Pct_Sehat_2026", 0.0)
            corrected_pct = min(100.0, raw_pct + boost)  # Kompensasi Pct_Sehat

            corrected_data[name] = {
                "energy_type": energy_type,
                "corrected_ndti": corrected_ndti,
                "corrected_pct": corrected_pct,
            }

        # 2. Kumpulkan nilai terkoreksi untuk normalisasi min-max
        pct_vals = [v["corrected_pct"] for v in corrected_data.values()]
        ndti_vals = [v["corrected_ndti"] for v in corrected_data.values()]
        ndci_vals = [abs(b.get("Mean_NDCI_2026", 0.0)) for b in beaches.values()]
        tss_vals = [b.get("Mean_TSS_2026", 0.0) for b in beaches.values()]
        cdom_vals = [b.get("Mean_CDOM_2026", 0.0) for b in beaches.values()]

        min_pct, max_pct = min(pct_vals), max(pct_vals)
        min_ndti, max_ndti = min(ndti_vals), max(ndti_vals)
        min_ndci, max_ndci = min(ndci_vals), max(ndci_vals)
        min_tss, max_tss = min(tss_vals), max(tss_vals)
        min_cdom, max_cdom = min(cdom_vals), max(cdom_vals)

        results = []
        for name, stats in beaches.items():
            kec = stats.get("Kecamatan", "")
            cd = corrected_data[name]
            energy_type = cd["energy_type"]

            pct_sehat = cd["corrected_pct"]
            ndti = cd["corrected_ndti"]
            ndci = abs(stats.get("Mean_NDCI_2026", 0.0))
            tss = stats.get("Mean_TSS_2026", 0.0)
            cdom = stats.get("Mean_CDOM_2026", 0.0)
            tren = stats.get("Tren_Kualitas", "STABIL")
            kategori_industri = stats.get("kategori_dampak_industri", "RENDAH")

            # Risiko polusi urban (0-1, 0 = pristine)
            polusi_urban = URBAN_POLLUTION_RISK.get(kec, 0.40)

            # Normalisasi parameter ke skala 0-100
            s_pct = self._normalize(pct_sehat, min_pct, max_pct)
            s_ndti = self._normalize(ndti, min_ndti, max_ndti, invert=True)
            s_ndci = self._normalize(ndci, min_ndci, max_ndci, invert=True)
            s_tss = self._normalize(tss, min_tss, max_tss, invert=True)
            s_cdom = self._normalize(cdom, min_cdom, max_cdom, invert=True)
            s_tren = TREN_SCORES.get(tren, 0.5) * 100.0
            s_industri = INDUSTRI_SCORES.get(kategori_industri, 0.5) * 100.0
            # Polusi urban inverted: risiko rendah (0) → skor tinggi (100)
            s_polusi_urban = (1.0 - polusi_urban) * 100.0
            # Sirkulasi pantai berdasarkan energi gelombang
            s_sirkulasi = SIRKULASI_SCORES.get(energy_type, 0.5) * 100.0

            # Hitung skor komposit (weighted sum) v2.0
            health_score = (
                WEIGHTS["pct_sehat"] * s_pct
                + WEIGHTS["ndti_inv"] * s_ndti
                + WEIGHTS["ndci_inv"] * s_ndci
                + WEIGHTS["tss_inv"] * s_tss
                + WEIGHTS["cdom_inv"] * s_cdom
                + WEIGHTS["tren"] * s_tren
                + WEIGHTS["industri_inv"] * s_industri
                + WEIGHTS["polusi_urban_inv"] * s_polusi_urban
                + WEIGHTS["sirkulasi_pantai"] * s_sirkulasi
            )
            health_score = round(health_score, 2)

            # Tentukan label rekomendasi
            label = "TIDAK DIREKOMENDASIKAN"
            for threshold, lbl in HEALTH_LABELS:
                if health_score >= threshold:
                    label = lbl
                    break

            results.append({
                "pantai": name,
                "slug": stats.get("slug") or "".join(c if c.isalnum() or c in " -" else "" for c in name.lower().strip()).replace(" ", "-").replace("--", "-"),
                "kecamatan": kec,
                "kabupaten_kota": stats.get("Kabupaten_Kota"),
                "latitude": stats.get("latitude"),
                "longitude": stats.get("longitude"),
                "url_gambar": stats.get("Url_gambar") or stats.get("url_gambar"),
                "health_score": health_score,
                "label_rekomendasi": label,
                # Parameter individual
                "pct_sehat_2026": stats.get("Pct_Sehat_2026", 0.0),
                "pct_sehat_terkoreksi": round(pct_sehat, 1),
                "status_kualitas_2026": stats.get("Status_Kualitas_2026"),
                "mean_ndti_2026": stats.get("Mean_NDTI_2026", 0.0),
                "ndti_terkoreksi": round(ndti, 4),
                "mean_ndci_2026": stats.get("Mean_NDCI_2026", 0.0),
                "mean_tss_2026": stats.get("Mean_TSS_2026", 0.0),
                "mean_cdom_2026": stats.get("Mean_CDOM_2026", 0.0),
                "tren_kualitas": tren,
                "industri_terdekat": stats.get("industri_terdekat"),
                "jarak_industri_km": stats.get("jarak_industri_km"),
                "kategori_dampak_industri": kategori_industri,
                # Parameter baru v2.0
                "tipe_pantai": energy_type,
                "risiko_polusi_urban": round(polusi_urban, 2),
                # Breakdown skor per parameter (untuk transparansi)
                "skor_detail": {
                    "skor_pct_sehat": round(s_pct, 2),
                    "skor_kekeruhan": round(s_ndti, 2),
                    "skor_klorofil": round(s_ndci, 2),
                    "skor_tss": round(s_tss, 2),
                    "skor_cdom": round(s_cdom, 2),
                    "skor_tren": round(s_tren, 2),
                    "skor_industri": round(s_industri, 2),
                    "skor_polusi_urban": round(s_polusi_urban, 2),
                    "skor_sirkulasi": round(s_sirkulasi, 2),
                },
            })

        # Urutkan berdasarkan Health Score tertinggi
        results.sort(key=lambda x: x["health_score"], reverse=True)

        # Tambahkan ranking
        for i, r in enumerate(results, start=1):
            r["ranking"] = i

        self._scores = results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_recommendations(self, top_n: int | None = None) -> list[dict[str, Any]]:
        """
        Mengembalikan daftar pantai yang direkomendasikan, diurutkan
        berdasarkan Health Score tertinggi.

        Args:
            top_n: Jumlah pantai teratas yang dikembalikan. None = semua.
        """
        if top_n is not None:
            return self._scores[:top_n]
        return self._scores

    def get_beach_score(self, beach_name: str) -> dict[str, Any] | None:
        """Mengembalikan skor detail untuk satu pantai (case-insensitive)."""
        for entry in self._scores:
            if entry["pantai"].lower() == beach_name.lower():
                return entry
        return None

    def get_summary(self) -> dict[str, Any]:
        """Mengembalikan ringkasan statistik model rekomendasi."""
        if not self._scores:
            return {"total_pantai": 0}

        scores = [s["health_score"] for s in self._scores]
        labels = {}
        for s in self._scores:
            lbl = s["label_rekomendasi"]
            labels[lbl] = labels.get(lbl, 0) + 1

        return {
            "total_pantai": len(self._scores),
            "health_score_min": min(scores),
            "health_score_max": max(scores),
            "health_score_mean": round(sum(scores) / len(scores), 2),
            "distribusi_label": labels,
            "bobot_parameter": WEIGHTS,
            "pantai_terbaik": self._scores[0]["pantai"] if self._scores else None,
            "pantai_terburuk": self._scores[-1]["pantai"] if self._scores else None,
        }

    def generate_recommendation_text(self, beach_entry: dict[str, Any]) -> str:
        """Menghasilkan narasi rekomendasi v2.0 untuk satu pantai."""
        name = beach_entry["pantai"]
        kec = beach_entry.get("kecamatan", "")
        score = beach_entry["health_score"]
        label = beach_entry["label_rekomendasi"]
        ranking = beach_entry["ranking"]
        total = len(self._scores)
        pct = beach_entry.get("pct_sehat_2026", 0)
        tren = beach_entry.get("tren_kualitas", "STABIL")
        detail = beach_entry.get("skor_detail", {})
        tipe_pantai = beach_entry.get("tipe_pantai", "MEDIUM")
        polusi_urban = beach_entry.get("risiko_polusi_urban", 0.4)

        if label == "SANGAT DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) menduduki peringkat **#{ranking}** dari {total} pantai "
                f"dengan Health Score **{score}/100** — **SANGAT DIREKOMENDASIKAN** untuk dikunjungi. "
                f"Perairan pantai ini memiliki tingkat kebersihan tertinggi di antara pantai-pantai yang dianalisis "
                f"dengan {pct}% area laut dalam kondisi sehat."
            )
        elif label == "DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) berada di peringkat **#{ranking}** dari {total} pantai "
                f"dengan Health Score **{score}/100** — **DIREKOMENDASIKAN**. "
                f"Kondisi perairan cukup baik dengan {pct}% area sehat, menjadikannya pilihan layak untuk wisata pantai."
            )
        elif label == "CUKUP DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) berada di peringkat **#{ranking}** dari {total} pantai "
                f"dengan Health Score **{score}/100** — **CUKUP DIREKOMENDASIKAN**. "
                f"Kualitas air berada di tingkat menengah ({pct}% area sehat). Pengunjung disarankan tetap berhati-hati."
            )
        elif label == "KURANG DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) mendapat peringkat **#{ranking}** dari {total} pantai "
                f"dengan Health Score **{score}/100** — **KURANG DIREKOMENDASIKAN**. "
                f"Hanya {pct}% area perairan yang tergolong sehat. Disarankan untuk membatasi aktivitas berenang."
            )
        else:
            intro = (
                f"**{name}** ({kec}) berada di peringkat terbawah **#{ranking}** dari {total} pantai "
                f"dengan Health Score **{score}/100** — **TIDAK DIREKOMENDASIKAN** untuk aktivitas air. "
                f"Perairan pantai ini hanya memiliki {pct}% area sehat."
            )

        # Konteks tipe pantai
        tipe_labels = {
            "HIGH": "pantai berenergi tinggi menghadap Samudra Hindia dengan sirkulasi perairan yang sangat baik",
            "MEDIUM": "pantai berenergi sedang di Selat Sunda dengan sirkulasi perairan cukup baik",
            "LOW": "pantai berenergi rendah di Laut Jawa/Teluk Jakarta dengan sirkulasi perairan terbatas",
        }
        tipe_text = f" Pantai ini termasuk kategori {tipe_labels.get(tipe_pantai, 'pantai pesisir')}."

        # Konteks polusi urban
        if polusi_urban >= 0.70:
            polusi_text = f" Risiko polusi antropogenik **TINGGI** (skor risiko: {polusi_urban:.0%}) karena kedekatan dengan pusat urban padat dan/atau kawasan industri."
        elif polusi_urban >= 0.40:
            polusi_text = f" Risiko polusi antropogenik **SEDANG** (skor risiko: {polusi_urban:.0%}) dari aktivitas pariwisata dan pemukiman sekitar."
        else:
            polusi_text = f" Risiko polusi antropogenik **RENDAH** (skor risiko: {polusi_urban:.0%}) karena lokasi terpencil dan minim aktivitas urban."

        # Tambahkan insight tren
        if tren == "MEMBAIK":
            tren_text = " Tren kualitas air **MEMBAIK** dibandingkan tahun 2017."
        elif tren == "MEMBURUK":
            tren_text = " Perlu diperhatikan bahwa kualitas air menunjukkan tren **MEMBURUK** sejak 2017."
        else:
            tren_text = " Kualitas air **STABIL** dibandingkan kondisi tahun 2017."

        # Insight parameter dominan
        best_param = max(detail.items(), key=lambda x: x[1])
        worst_param = min(detail.items(), key=lambda x: x[1])

        param_names = {
            "skor_pct_sehat": "persentase area sehat",
            "skor_kekeruhan": "kejernihan air",
            "skor_klorofil": "kadar klorofil-a",
            "skor_tss": "kandungan padatan tersuspensi",
            "skor_cdom": "bahan organik terlarut",
            "skor_tren": "tren historis",
            "skor_industri": "jarak dari industri",
            "skor_polusi_urban": "rendahnya polusi urban",
            "skor_sirkulasi": "sirkulasi perairan",
        }

        param_text = (
            f" Keunggulan utama: {param_names.get(best_param[0], best_param[0])} "
            f"(skor: {best_param[1]}). Aspek terlemah: "
            f"{param_names.get(worst_param[0], worst_param[0])} (skor: {worst_param[1]})."
        )

        return intro + tipe_text + polusi_text + tren_text + param_text

    def save_to_json(self, output_path: str) -> None:
        """Menyimpan hasil rekomendasi lengkap ke file JSON."""
        enriched_scores = []
        for entry in self._scores:
            enriched_entry = dict(entry)
            enriched_entry["narasi_rekomendasi"] = self.generate_recommendation_text(entry)
            enriched_scores.append(enriched_entry)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(enriched_scores, f, indent=2, ensure_ascii=False)
        print(f"Berhasil menyimpan hasil rekomendasi ke: {output_path}")


# ---------------------------------------------------------------------------
# Standalone execution untuk testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DATA_PATH = os.path.join("output", "banten_water_quality_beach.json")

    if not os.path.exists(DATA_PATH):
        print(f"File tidak ditemukan: {DATA_PATH}")
        print("Jalankan dari direktori Model/")
        exit(1)

    recommender = BeachRecommender(DATA_PATH)
    
    # Simpan hasil rekomendasi ke file JSON
    output_json_path = os.path.join("output", "banten_beach_recommendations.json")
    recommender.save_to_json(output_json_path)

    print("=" * 70)
    print("[BEACH] SISTEM REKOMENDASI PANTAI TERSEHAT - PESISIR BANTEN")
    print("=" * 70)

    summary = recommender.get_summary()
    print(f"\nTotal Pantai Dianalisis : {summary['total_pantai']}")
    print(f"Health Score Rata-Rata  : {summary['health_score_mean']}")
    print(f"Pantai Terbaik          : {summary['pantai_terbaik']}")
    print(f"Pantai Terburuk         : {summary['pantai_terburuk']}")
    print(f"\nDistribusi Label:")
    for label, count in summary["distribusi_label"].items():
        print(f"  - {label}: {count} pantai")

    print("\n" + "-" * 70)
    print("[TOP 5] PANTAI TERSEHAT:")
    print("-" * 70)

    for beach in recommender.get_recommendations(top_n=5):
        print(f"\n  #{beach['ranking']}  {beach['pantai']} ({beach['kecamatan']}, {beach['kabupaten_kota']})")
        print(f"      Health Score  : {beach['health_score']}/100")
        print(f"      Label         : {beach['label_rekomendasi']}")
        print(f"      Pct Sehat     : {beach['pct_sehat_2026']}%")
        print(f"      Tren          : {beach['tren_kualitas']}")
        print(f"      Industri      : {beach['industri_terdekat']} ({beach['jarak_industri_km']} km, {beach['kategori_dampak_industri']})")

    print("\n" + "-" * 70)
    print("[NARASI] REKOMENDASI TOP 1:")
    print("-" * 70)
    top1 = recommender.get_recommendations(top_n=1)[0]
    print(f"\n{recommender.generate_recommendation_text(top1)}")
    print()
