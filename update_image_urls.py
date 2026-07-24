"""
Script to update url_gambar for all 51 beaches in banten_water_quality_beach.json
Maps each beach slug to the correct image URL from Vercel Blob storage.
"""

import json

BASE = "https://uqjvr3hvnh8nfixj.public.blob.vercel-storage.com/images/"

# Mapping: slug -> image filename (from the provided URL list)
SLUG_TO_IMAGE = {
    "pantai-batu-hideung":         "batu-hideung.jpg",
    "pantai-lalassa":              "lalasa-tanjung-lesung.jpg",
    "pantai-anyer":                "pantai-anyer.jpg",
    "pantai-bagedur":              "pantai-bagedur.jpg",
    "pantai-batu-saung":           "pantai-batu-saung.jpg",
    "pantai-binuangeun":           "pantai-binuangeun.jpg",
    "pantai-pulau-cangkir":        "pantai-cangkir.jpg",
    "pantai-caringin":             "pantai-caringin.jpg",
    "pantai-carita":               "pantai-carita.jpg",
    "pantai-ciantir":              "pantai-ciantir-banten.jpg",
    "pantai-cibareno":             "pantai-cibareno.jpg",
    "pantai-cibobos":              "pantai-cibobos.jpg",
    "pantai-pasir-putih-cihara":   "pantai-cihara.jpeg",
    "pantai-cipenyu":              "pantai-cipenyu.jpg",
    "pantai-ciputih":              "pantai-ciputih.jpg",
    "pantai-citarate":             "pantai-citarate.jpg",
    "pantai-dadap":                "pantai-dadap.jpg",
    "pantai-goa-langir":           "pantai-goa-langir.jpg",
    "pantai-jambu":                "pantai-jambu.jpg",
    "pantai-karang-bolong":        "pantai-karang-bolong.jpg",
    "pantai-karang-pamulang":      "pantai-karang-pamulang.jpg",
    "pantai-karang-songsong":      "pantai-karang-songsong.jpg",
    "pantai-labuan":               "pantai-labuan.jpg",
    "pantai-teluk-lada":           "pantai-ladda.jpg",
    "pantai-legon-pari":           "pantai-legon-pari.jpg",
    "pantai-lontar":               "pantai-lontar.jpg",
    "pantai-marbella":             "pantai-marbella.jpg",
    "pantai-marina":               "pantai-marina-anyer.jpg",
    "pantai-pakuhaji":             "pantai-pakuhaji.jpg",
    "pantai-pandan-carita":        "pantai-pandan.jpg",
    "pantai-panggarangan":         "pantai-panggarangan.jpg",
    "pantai-florida-indah":        "pantai-pasir-putih-florida.png",
    "pantai-pasir-putih-florida":  "pantai-pasir-putih-florida.png",
    "pantai-pasir-putih-sirih":    "pantai-pasir-putih-sirih.jpg",
    "pantai-pontang":              "pantai-pontang.jpg",
    "pantai-pulau-merak-besar":    "pantai-pulau-merak-besar.jpg",
    "pantai-pulau-merak-kecil":    "pantai-pulau-merak-kecil.jpg",
    "pantai-pulo-manuk":           "pantai-pulo-manuk.jpg",
    "pantai-pulorida":             "pantai-pulorida.jpg",
    "pantai-sambolo":              "pantai-sambolo.jpg",
    "pantai-sangiang":             "pantai-sangiang.jpg",
    "pantai-tanara":               "pantai-tanara.jpg",
    "pantai-tanjung-burung":       "pantai-tanjung-burung.jpg",
    "pantai-tanjung-kait":         "pantai-tanjung-kait.jpg",
    "pantai-tanjung-layar":        "pantai-tanjung-layar.jpg",
    "pantai-tanjung-lesung":       "pantai-tanjung-lesung.png",
    "pantai-tanjung-pasir":        "pantai-tanjung-pasir.jpg",
    "pantai-karang-taraje":        "pantai-taraje.jpg",
    "pantai-ujung-kulon":          "pantai-ujung-kulon.jpg",
    "pantai-pulau-umang":          "pantai-umang.jpeg",
    "pantai-sawarna":              "sawarna.jpg",
}


def main():
    path = "output/banten_water_quality_beach.json"
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"Total beaches in JSON: {len(data)}")
    
    updated = 0
    not_matched = []
    
    for beach_name, stats in data.items():
        slug = stats.get("slug", "")
        if not slug:
            # Generate slug from name
            slug = "".join(c if c.isalnum() or c in " -" else "" for c in beach_name.lower().strip()).replace(" ", "-").replace("--", "-")
        
        if slug in SLUG_TO_IMAGE:
            old_url = stats.get("url_gambar", "")
            new_url = BASE + SLUG_TO_IMAGE[slug]
            stats["url_gambar"] = new_url
            status = "UPDATED" if old_url != new_url else "SAME"
            print(f"  {status}: {beach_name} ({slug}) -> {SLUG_TO_IMAGE[slug]}")
            updated += 1
        else:
            not_matched.append((beach_name, slug))
            print(f"  NO MATCH: {beach_name} ({slug})")
    
    # Write back
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n--- Summary ---")
    print(f"Updated: {updated}/{len(data)} beaches")
    if not_matched:
        print(f"Not matched ({len(not_matched)}):")
        for name, slug in not_matched:
            print(f"  - {name} ({slug})")
    else:
        print("All beaches matched successfully!")


if __name__ == "__main__":
    main()
