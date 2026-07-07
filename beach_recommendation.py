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
# Konstanta bobot parameter untuk skor komposit
# ---------------------------------------------------------------------------

# Bobot setiap parameter dalam perhitungan Health Score (total = 1.0)
WEIGHTS = {
    "pct_sehat": 0.30,       # Persentase area sehat — faktor utama
    "ndti_inv": 0.20,        # Kekeruhan (inverted — rendah = bagus)
    "ndci_inv": 0.10,        # Klorofil-a (inverted — rendah = bagus)
    "tss_inv": 0.10,         # TSS (inverted — rendah = bagus)
    "cdom_inv": 0.05,        # CDOM (inverted — rendah = bagus)
    "tren": 0.15,            # Tren kualitas historis
    "industri_inv": 0.10,    # Dampak industri terdekat (inverted)
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
        """Menghitung Health Score untuk seluruh pantai dan menyimpannya dalam self._scores."""
        beaches = self.raw_data

        # 1. Kumpulkan nilai mentah untuk normalisasi
        pct_vals = [b.get("Pct_Sehat_2026", 0.0) for b in beaches.values()]
        ndti_vals = [abs(b.get("Mean_NDTI_2026", 0.0)) for b in beaches.values()]
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
            pct_sehat = stats.get("Pct_Sehat_2026", 0.0)
            ndti = abs(stats.get("Mean_NDTI_2026", 0.0))
            ndci = abs(stats.get("Mean_NDCI_2026", 0.0))
            tss = stats.get("Mean_TSS_2026", 0.0)
            cdom = stats.get("Mean_CDOM_2026", 0.0)
            tren = stats.get("Tren_Kualitas", "STABIL")
            kategori_industri = stats.get("kategori_dampak_industri", "RENDAH")

            # Normalisasi
            s_pct = self._normalize(pct_sehat, min_pct, max_pct)
            s_ndti = self._normalize(ndti, min_ndti, max_ndti, invert=True)
            s_ndci = self._normalize(ndci, min_ndci, max_ndci, invert=True)
            s_tss = self._normalize(tss, min_tss, max_tss, invert=True)
            s_cdom = self._normalize(cdom, min_cdom, max_cdom, invert=True)
            s_tren = TREN_SCORES.get(tren, 0.5) * 100.0
            s_industri = INDUSTRI_SCORES.get(kategori_industri, 0.5) * 100.0

            # Hitung skor komposit (weighted sum)
            health_score = (
                WEIGHTS["pct_sehat"] * s_pct
                + WEIGHTS["ndti_inv"] * s_ndti
                + WEIGHTS["ndci_inv"] * s_ndci
                + WEIGHTS["tss_inv"] * s_tss
                + WEIGHTS["cdom_inv"] * s_cdom
                + WEIGHTS["tren"] * s_tren
                + WEIGHTS["industri_inv"] * s_industri
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
                "kecamatan": stats.get("Kecamatan"),
                "kabupaten_kota": stats.get("Kabupaten_Kota"),
                "latitude": stats.get("latitude"),
                "longitude": stats.get("longitude"),
                "url_gambar": stats.get("Url_gambar") or stats.get("url_gambar"),
                "health_score": health_score,
                "label_rekomendasi": label,
                # Parameter individual
                "pct_sehat_2026": pct_sehat,
                "status_kualitas_2026": stats.get("Status_Kualitas_2026"),
                "mean_ndti_2026": stats.get("Mean_NDTI_2026", 0.0),
                "mean_ndci_2026": stats.get("Mean_NDCI_2026", 0.0),
                "mean_tss_2026": stats.get("Mean_TSS_2026", 0.0),
                "mean_cdom_2026": stats.get("Mean_CDOM_2026", 0.0),
                "tren_kualitas": tren,
                "industri_terdekat": stats.get("industri_terdekat"),
                "jarak_industri_km": stats.get("jarak_industri_km"),
                "kategori_dampak_industri": kategori_industri,
                # Breakdown skor per parameter (untuk transparansi)
                "skor_detail": {
                    "skor_pct_sehat": round(s_pct, 2),
                    "skor_kekeruhan": round(s_ndti, 2),
                    "skor_klorofil": round(s_ndci, 2),
                    "skor_tss": round(s_tss, 2),
                    "skor_cdom": round(s_cdom, 2),
                    "skor_tren": round(s_tren, 2),
                    "skor_industri": round(s_industri, 2),
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
        """Menghasilkan narasi rekomendasi untuk satu pantai."""
        name = beach_entry["pantai"]
        kec = beach_entry.get("kecamatan", "")
        score = beach_entry["health_score"]
        label = beach_entry["label_rekomendasi"]
        ranking = beach_entry["ranking"]
        total = len(self._scores)
        pct = beach_entry.get("pct_sehat_2026", 0)
        tren = beach_entry.get("tren_kualitas", "STABIL")
        detail = beach_entry.get("skor_detail", {})

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

        # Tambahkan insight tren
        if tren == "MEMBAIK":
            tren_text = " Kabar baiknya, tren kualitas air di pantai ini **MEMBAIK** dibandingkan tahun 2017."
        elif tren == "MEMBURUK":
            tren_text = " Perlu diperhatikan bahwa kualitas air di pantai ini menunjukkan tren **MEMBURUK** sejak 2017."
        else:
            tren_text = " Kualitas air di pantai ini **STABIL** dibandingkan kondisi tahun 2017."

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
        }

        param_text = (
            f" Keunggulan utama pantai ini adalah {param_names.get(best_param[0], best_param[0])} "
            f"(skor: {best_param[1]}), sedangkan aspek yang perlu ditingkatkan adalah "
            f"{param_names.get(worst_param[0], worst_param[0])} (skor: {worst_param[1]})."
        )

        return intro + tren_text + param_text

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
