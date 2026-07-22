import json

with open("output/banten_beach_recommendations.json", "r", encoding="utf-8") as f:
    data = json.load(f)

new_names = {
    "Pantai Batu Hideung", "Pantai Lalassa", "Pantai Cipenyu", "Pantai Pandan Carita",
    "Pantai Labuan", "Pantai Teluk Lada", "Pantai Ujung Kulon", "Pantai Ciantir",
    "Pantai Legon Pari", "Pantai Pulo Manuk", "Pantai Goa Langir", "Pantai Cibobos",
    "Pantai Citarate", "Pantai Cibareno", "Pantai Panggarangan", "Pantai Marina",
    "Pantai Batu Saung", "Pantai Karang Pamulang", "Pantai Pontang", "Pantai Tanara",
    "Pantai Tanjung Burung", "Pantai Dadap", "Pantai Pakuhaji", "Pantai Pulorida",
    "Pantai Pulau Merak Kecil"
}

print(f"{'Rank':<5} | {'Nama Pantai':<24} | {'Kab/Kota':<10} | {'Kecamatan':<12} | {'Desa':<15} | {'Kode ADM4':<13} | {'Skor':<6} | {'Label Rekomendasi'}")
print("-" * 120)
for b in data:
    if b["pantai"] in new_names:
        print(f"{b['ranking']:<5} | {b['pantai']:<24} | {b['kabupaten_kota']:<10} | {b['kecamatan']:<12} | {b['desa']:<15} | {b['kode_adm4']:<13} | {b['health_score']:<6} | {b['label_rekomendasi']}")
