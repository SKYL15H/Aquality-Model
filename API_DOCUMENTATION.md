# Coast-Vision API Documentation

Dokumentasi lengkap API Coast-Vision untuk deteksi abrasi/akresi garis pantai dan klasifikasi kesehatan hutan mangrove.

---

## 🚀 Cara Menjalankan Server Lokal

1. **Instalasi Dependensi**
   Pastikan Python sudah terinstal, lalu instal seluruh library yang diperlukan:
   ```bash
   pip install -r requirements.txt
   ```

2. **Jalankan FastAPI Server**
   Jalankan server menggunakan Uvicorn:
   ```bash
   uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Akses Swagger / Interactive Docs**
   * **Swagger UI (Interactive Docs)**: [http://localhost:8000/docs](http://localhost:8000/docs)
   * **ReDoc (Alternative Docs)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📄 Spesifikasi OpenAPI (Swagger)

Di dalam repositori ini, file **`openapi.json`** telah digenerate secara otomatis. Teman Anda bisa langsung mengimpor file `openapi.json` ini ke dalam:
* **Postman** (Import -> select file `openapi.json`)
* **Insomnia**
* **Swagger Editor** ([editor.swagger.io](https://editor.swagger.io/))

---

## 🛠️ Daftar Endpoint API

### 1. General

#### `GET /`
Mengembalikan status layanan, versi, dan rute endpoint yang tersedia.
* **Response (JSON)**:
  ```json
  {
    "service": "Coast-Vision API",
    "version": "1.0.0",
    "description": "Analisis pesisir & mangrove 34 provinsi Indonesia",
    "endpoints": { ... }
  }
  ```

---

### 2. Provinces & National Summary

#### `GET /api/provinces`
Mengembalikan daftar seluruh provinsi yang telah diproses beserta ringkasan status pantai dan status mangrovenya.
* **Response (JSON)**:
  ```json
  {
    "total": 34,
    "provinces": [
      {
        "name": "Banten",
        "status_pantai": "ABRASI",
        "status_mangrove": "SEDANG"
      }
    ]
  }
  ```

#### `GET /api/provinces/{name}`
Mengembalikan statistik detail (abrasi, akresi, dan area mangrove) untuk provinsi tertentu.
* **Path Parameters**:
  * `name` (string): Nama provinsi (case-insensitive, contoh: `banten`).
* **Response (JSON)**:
  ```json
  {
    "abrasi_ha": 120.5,
    "akresi_ha": 45.2,
    "mangrove_total_ha": 3500.0,
    "mangrove_sehat_ha": 2000.0,
    "mangrove_sedang_ha": 1000.0,
    "mangrove_rusak_ha": 500.0,
    "status_pantai": "ABRASI",
    "status_mangrove": "SEDANG",
    "mean_ndvi": 0.65
  }
  ```

#### `GET /api/summary`
Mengembalikan agregat statistik nasional dari seluruh data provinsi yang sudah diproses.
* **Response (JSON)**:
  ```json
  {
    "total_provinces": 1,
    "period": { "baseline_year": 2017, "comparison_year": 2026 },
    "shoreline": {
      "total_abrasi_ha": 120.5,
      "total_akresi_ha": 45.2,
      "net_change_ha": -75.3,
      "provinces_abrasi": 1,
      "provinces_akresi": 0,
      "provinces_stabil": 0
    },
    "mangrove": {
      "total_area_ha": 3500.0,
      "sehat_ha": 2000.0,
      "sedang_ha": 1000.0,
      "rusak_ha": 500.0,
      "mean_ndvi": 0.65
    }
  }
  ```

---

### 3. Water Quality (Banten)

#### `GET /api/water-quality/leaderboard`
Mengembalikan peringkat kualitas air bersih di tingkat kecamatan pesisir Banten, diurutkan dari persentase area air sehat (`Pct_Sehat_2026`) tertinggi.
* **Response (JSON)**:
  ```json
  {
    "total": 15,
    "leaderboard": [
      {
        "kecamatan": "Sumur",
        "kabupaten_kota": "Pandeglang",
        "pct_sehat_2026": 94.5,
        "status_kualitas_2026": "SEHAT",
        "latitude": -6.65,
        "longitude": 105.58,
        "industri_terdekat": "PLTU Labuan",
        "jarak_industri_km": 25.4,
        "kategori_dampak_industri": "RENDAH"
      }
    ]
  }
  ```

#### `GET /api/water-quality/kecamatan/{name}`
Mengembalikan data kualitas air detail untuk kecamatan tertentu di Banten beserta penjelasan/analisis narasi ilmiah otomatis.
* **Path Parameters**:
  * `name` (string): Nama kecamatan (contoh: `anyar`, `ciwandan`).
* **Response (JSON)**:
  ```json
  {
    "Kabupaten_Kota": "Cilegon",
    "Pct_Sehat_2026": 25.3,
    "Mean_NDTI_2026": 0.082,
    "Mean_NDCI_2026": 0.095,
    "Status_Kualitas_2026": "TIDAK SEHAT",
    "centroid_latitude": -6.01,
    "centroid_longitude": 105.95,
    "industri_terdekat": "Krakatau Steel",
    "jarak_industri_km": 1.2,
    "kategori_dampak_industri": "TINGGI",
    "kecamatan": "Ciwandan",
    "penjelasan_kualitas": "Status Kualitas Air di Ciwandan diklasifikasikan sebagai TIDAK SEHAT. Kecamatan Ciwandan merupakan wilayah Pelabuhan Logistik Ciwandan dan pusat industri berat..."
  }
  ```

#### `GET /api/water-quality/beach/leaderboard`
Mengembalikan peringkat kualitas air di lokasi-lokasi pantai wisata di Banten.
* **Response (JSON)**:
  ```json
  {
    "total": 10,
    "leaderboard": [
      {
        "pantai": "Pantai Carita",
        "kecamatan": "Carita",
        "kabupaten_kota": "Pandeglang",
        "pct_sehat_2026": 88.2,
        "status_kualitas_2026": "SEHAT",
        "latitude": -6.28,
        "longitude": 105.83,
        "industri_terdekat": "PLTU Labuan",
        "jarak_industri_km": 12.3,
        "kategori_dampak_industri": "RENDAH"
      }
    ]
  }
  ```

#### `GET /api/water-quality/beach/{name}`
Mengembalikan data kualitas air beserta narasi penjelasan keamanan aktivitas wisata (seperti berenang) untuk pantai tertentu di Banten.
* **Path Parameters**:
  * `name` (string): Nama pantai (contoh: `pantai carita`).

---

### 4. Model & Industry Data

#### `GET /api/model/info`
Mengembalikan metadata pelatihan model Random Forest, metrik performa (Akurasi, F1-Score, Precision, Recall), dan feature importance.

#### `GET /api/industries`
Mengembalikan daftar koordinat lokasi industri/pabrik besar di sekitar pesisir Banten yang digunakan untuk menghitung jarak dampak industri.
