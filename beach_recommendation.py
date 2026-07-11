"""
beach_recommendation.py — Sistem Rekomendasi Pantai Tersehat

Model rekomendasi berbasis skor kelayakan pantai (Health Score)
yang menggabungkan beberapa parameter terestrial & human footprint:
  - Indeks Dampak Industri (IDI) komposit
  - Kepadatan Penduduk Kecamatan pesisir Banten
  - Indeks Pengaruh Urban (IPU) dari pusat perkotaan terdekat

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

# Bobot setiap parameter dalam perhitungan Health Score v4.0 (total = 1.0)
# Murni berbasis data spasial darat & human footprint (tidak menggunakan Sentinel-2)
WEIGHTS = {
    "industri_inv": 0.40,           # Indeks Dampak Industri (IDI) Inverted (40%)
    "kepadatan_penduduk_inv": 0.30, # Kepadatan penduduk kecamatan Inverted (30%)
    "pengaruh_urban_inv": 0.30,     # Indeks Pengaruh Urban (IPU) Inverted (30%)
}

# Skor kualitatif untuk kategori dampak industri (inverted: rendah = baik)
# 5 level berdasarkan Indeks Dampak Industri (IDI)
INDUSTRI_SCORES = {
    "SANGAT RENDAH": 1.0,
    "RENDAH": 0.75,
    "SEDANG": 0.5,
    "TINGGI": 0.25,
    "SANGAT TINGGI": 0.0,
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
        """Menghitung Health Score v4.0 untuk seluruh pantai.
        
        Sistem di-upgrade murni berbasis terrestrial & human footprint:
        - Indeks Dampak Industri (IDI)
        - Kepadatan Penduduk Kecamatan
        - Indeks Pengaruh Urban (IPU)
        """
        beaches = self.raw_data

        # 1. Kumpulkan nilai untuk normalisasi min-max
        density_vals = [b.get("kepadatan_penduduk_kecamatan", 500.0) for b in beaches.values()]
        influence_vals = [b.get("indeks_pengaruh_urban", 0.0) for b in beaches.values()]
        idi_vals = [b.get("indeks_dampak_industri", 0.0) for b in beaches.values()]

        min_density, max_density = min(density_vals), max(density_vals)
        min_influence, max_influence = min(influence_vals), max(influence_vals)
        min_idi, max_idi = min(idi_vals), max(idi_vals)

        results = []
        for name, stats in beaches.items():
            kec = stats.get("Kecamatan", "")
            idi_raw = stats.get("indeks_dampak_industri", 0.0)
            density_val = stats.get("kepadatan_penduduk_kecamatan", 500.0)
            influence_val = stats.get("indeks_pengaruh_urban", 0.0)

            # Normalisasi parameter ke skala 0-100 (Inverted: semakin tinggi = semakin buruk)
            s_industri = self._normalize(idi_raw, min_idi, max_idi, invert=True)
            s_density = self._normalize(density_val, min_density, max_density, invert=True)
            s_influence = self._normalize(influence_val, min_influence, max_influence, invert=True)

            # Hitung skor komposit (weighted sum) murni darat v4.0
            health_score = (
                WEIGHTS["industri_inv"] * s_industri
                + WEIGHTS["kepadatan_penduduk_inv"] * s_density
                + WEIGHTS["pengaruh_urban_inv"] * s_influence
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
                # Terrestrial & Human footprint parameters
                "industri_terdekat": stats.get("industri_terdekat"),
                "jarak_industri_km": stats.get("jarak_industri_km"),
                "kategori_dampak_industri": stats.get("kategori_dampak_industri"),
                "indeks_dampak_industri": idi_raw,
                "industri_relevan_terdekat": stats.get("industri_relevan_terdekat"),
                "jarak_industri_relevan_km": stats.get("jarak_industri_relevan_km"),
                "jumlah_industri_radius_10km": stats.get("jumlah_industri_radius_10km", 0),
                "kepadatan_industri": stats.get("kepadatan_industri", 0),
                "kepadatan_penduduk_kecamatan": density_val,
                "indeks_pengaruh_urban": influence_val,
                # Skor detail
                "skor_detail": {
                    "skor_industri": round(s_industri, 2),
                    "skor_kepadatan_penduduk": round(s_density, 2),
                    "skor_pengaruh_urban": round(s_influence, 2),
                },
            })

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
        """Menghasilkan narasi rekomendasi kelayakan pantai berdasarkan model terrestrial/human footprint."""
        name = beach_entry["pantai"]
        kec = beach_entry.get("kecamatan", "")
        score = beach_entry["health_score"]
        label = beach_entry["label_rekomendasi"]
        ranking = beach_entry["ranking"]
        total = len(self._scores)
        detail = beach_entry.get("skor_detail", {})
        idi = beach_entry.get("indeks_dampak_industri", 0)
        n_industri = beach_entry.get("jumlah_industri_radius_10km", 0)
        density = beach_entry.get("kepadatan_penduduk_kecamatan", 500.0)
        ipu = beach_entry.get("indeks_pengaruh_urban", 0.0)

        if label == "SANGAT DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) menduduki peringkat **#{ranking}** dari {total} pantai "
                f"dengan skor kelayakan lingkungan **{score}/100** — **SANGAT DIREKOMENDASIKAN**. "
                f"Kawasan pesisir pantai ini memiliki tekanan antropogenik paling minimal dan kondisi lingkungan darat yang paling asri."
            )
        elif label == "DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) berada di peringkat **#{ranking}** dari {total} pantai "
                f"dengan skor kelayakan lingkungan **{score}/100** — **DIREKOMENDASIKAN**. "
                f"Kondisi lingkungan sekitar pantai tergolong baik untuk tujuan rekreasi karena minimnya polusi."
            )
        elif label == "CUKUP DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) berada di peringkat **#{ranking}** dari {total} pantai "
                f"dengan skor kelayakan lingkungan **{score}/100** — **CUKUP DIREKOMENDASIKAN**. "
                f"Lingkungan pesisir berada di tingkat kelayakan menengah. Pengunjung disarankan tetap memperhatikan kebersihan sekitar."
            )
        elif label == "KURANG DIREKOMENDASIKAN":
            intro = (
                f"**{name}** ({kec}) mendapat peringkat **#{ranking}** dari {total} pantai "
                f"dengan skor kelayakan lingkungan **{score}/100** — **KURANG DIREKOMENDASIKAN**. "
                f"Tekanan dari aktivitas perkotaan atau industri sekitar cukup terasa di wilayah pesisir ini."
            )
        else:
            intro = (
                f"**{name}** ({kec}) berada di peringkat terbawah **#{ranking}** dari {total} pantai "
                f"dengan skor kelayakan lingkungan **{score}/100** — **TIDAK DIREKOMENDASIKAN** untuk aktivitas wisata. "
                f"Tekanan antropogenik (industri/perkotaan) di pesisir ini sangat tinggi."
            )

        # Konteks Kepadatan Penduduk & Urban Influence
        demografi_text = f" Kecamatan {kec} memiliki kepadatan penduduk **{density:,.0f} jiwa/km²**."
        if ipu >= 60:
            urban_text = f" Indeks Pengaruh Urban pantai ini sangat **TINGGI** ({ipu}/100) karena lokasinya yang dekat dengan aglomerasi metropolitan utama Banten."
        elif ipu >= 30:
            urban_text = f" Indeks Pengaruh Urban bersifat **SEDANG** ({ipu}/100) dengan pengaruh limpasan urban moderat."
        else:
            urban_text = f" Indeks Pengaruh Urban pantai ini **RENDAH** ({ipu}/100) karena lokasinya yang terisolasi secara alami dari pusat perkotaan."

        # Konteks dampak industri (3 metrik baru)
        kategori_industri = beach_entry.get("kategori_dampak_industri", "RENDAH")
        if idi >= 30:
            industri_text = f" Indeks Dampak Industri **{idi}/100** ({kategori_industri}) — terdapat {n_industri} industri dalam radius 10 km yang secara kumulatif memberikan dampak tekanan tinggi di wilayah ini."
        elif idi >= 15:
            industri_text = f" Indeks Dampak Industri **{idi}/100** ({kategori_industri}) — pengaruh kawasan industri bersifat moderat dengan {n_industri} industri dalam radius 10 km."
        elif idi >= 5:
            industri_text = f" Indeks Dampak Industri **{idi}/100** ({kategori_industri}) — dampak industri relatif rendah ({n_industri} industri dalam radius 10 km)."
        else:
            industri_text = f" Indeks Dampak Industri **{idi}/100** ({kategori_industri}) — pantai ini sangat jauh dari kawasan industri sehingga dampak polusi industri sangat minimal."

        # Insight parameter dominan
        best_param = max(detail.items(), key=lambda x: x[1])
        worst_param = min(detail.items(), key=lambda x: x[1])

        param_names = {
            "skor_industri": "indeks dampak industri",
            "skor_kepadatan_penduduk": "skor kepadatan penduduk",
            "skor_pengaruh_urban": "skor pengaruh urban",
        }

        param_text = (
            f" Keunggulan utama: {param_names.get(best_param[0], best_param[0])} "
            f"(skor: {best_param[1]}). Aspek terlemah: "
            f"{param_names.get(worst_param[0], worst_param[0])} (skor: {worst_param[1]})."
        )

        return intro + demografi_text + urban_text + industri_text + param_text

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
        print(f"      Industri      : {beach['industri_terdekat']} ({beach['jarak_industri_km']} km, {beach['kategori_dampak_industri']})")

    print("\n" + "-" * 70)
    print("[NARASI] REKOMENDASI TOP 1:")
    print("-" * 70)
    top1 = recommender.get_recommendations(top_n=1)[0]
    print(f"\n{recommender.generate_recommendation_text(top1)}")
    print()
