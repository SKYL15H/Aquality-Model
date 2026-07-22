"""
generate_maps.py — Regenerate Folium maps for all 51 beaches and 14 industries
"""

import json
import os
import folium
from folium import plugins

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

BEACH_JSON = os.path.join(OUTPUT_DIR, "banten_water_quality_beach.json")
RECOMMENDATIONS_JSON = os.path.join(OUTPUT_DIR, "banten_beach_recommendations.json")
GEOJSON_PATH = os.path.join(OUTPUT_DIR, "banten_coastal_beaches.geojson")
INDUSTRIES_JSON = os.path.join(OUTPUT_DIR, "banten_industries.json")
KECAMATAN_GEOJSON = os.path.join(OUTPUT_DIR, "banten_coastal_kecamatan_land.geojson")

MAP_HTML = os.path.join(OUTPUT_DIR, "banten_water_quality_map.html")
HEATMAP_HTML = os.path.join(OUTPUT_DIR, "heatmap_industri.html")


def get_color_by_score(score):
    if score >= 80:
        return "green", "#2ecc71"
    elif score >= 60:
        return "blue", "#3498db"
    elif score >= 40:
        return "orange", "#f39c12"
    elif score >= 20:
        return "red", "#e74c3c"
    else:
        return "darkred", "#900c3f"


def generate_main_map():
    print("Generating main Folium map...")
    with open(RECOMMENDATIONS_JSON, "r", encoding="utf-8") as f:
        recs = json.load(f)

    with open(INDUSTRIES_JSON, "r", encoding="utf-8") as f:
        industries = json.load(f)

    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        beach_geojson = json.load(f)

    kec_geojson = None
    if os.path.exists(KECAMATAN_GEOJSON):
        with open(KECAMATAN_GEOJSON, "r", encoding="utf-8") as f:
            kec_geojson = json.load(f)

    # Initialize map centered on Banten
    m = folium.Map(location=[-6.3, 106.0], zoom_start=9, tiles="cartodbpositron")

    # 1. Layer Kecamatan
    if kec_geojson:
        kec_layer = folium.FeatureGroup(name="Batas Kecamatan Pesisir", show=True)
        folium.GeoJson(
            kec_geojson,
            style_function=lambda x: {
                "fillColor": "#bdc3c7",
                "color": "#7f8c8d",
                "weight": 1,
                "fillOpacity": 0.15,
            },
            tooltip=folium.GeoJsonTooltip(fields=["Kecamatan", "Kabupaten_Kota"], aliases=["Kecamatan:", "Kab/Kota:"])
        ).add_to(kec_layer)
        kec_layer.add_to(m)

    # 2. Layer Industri
    ind_layer = folium.FeatureGroup(name="Lokasi Industri & Pabrik", show=True)
    for ind in industries:
        popup_html = f"""
        <div style="font-family: sans-serif; width: 220px;">
            <h4 style="margin: 0 0 5px 0; color: #c0392b;">🏭 {ind.get('nama', '')}</h4>
            <p style="margin: 2px 0;"><b>Tipe:</b> {ind.get('tipe', '')}</p>
            <p style="margin: 2px 0;"><b>Jarak ke Pesisir:</b> {ind.get('distance_to_coast_km', 0)} km</p>
            <p style="margin: 2px 0;"><b>Skor Risiko:</b> <span style="color: #e74c3c; font-weight: bold;">{ind.get('risk_score', 0)}/100</span></p>
        </div>
        """
        folium.Marker(
            location=[ind["latitude"], ind["longitude"]],
            icon=folium.Icon(color="red", icon="industry", prefix="fa"),
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"🏭 {ind['nama']} ({ind['tipe']})"
        ).add_to(ind_layer)
    ind_layer.add_to(m)

    # 3. Layer Pantai (Markers & Polygons)
    beach_layer = folium.FeatureGroup(name="Pantai Banten (51 Lokasi)", show=True)

    # Map beach name to geojson geometry
    geom_map = {f["properties"]["Pantai"]: f["geometry"] for f in beach_geojson.get("features", [])}

    for b in recs:
        name = b["pantai"]
        lat = b["latitude"]
        lon = b["longitude"]
        score = b["health_score"]
        label = b["label_rekomendasi"]
        rank = b["ranking"]
        color_name, hex_color = get_color_by_score(score)

        popup_html = f"""
        <div style="font-family: sans-serif; width: 260px;">
            <h3 style="margin: 0 0 5px 0; color: #2c3e50;">🏖️ #{rank} {name}</h3>
            <p style="margin: 2px 0;"><b>Lokasi:</b> {b.get('kecamatan', '')}, {b.get('kabupaten_kota', '')}</p>
            <p style="margin: 2px 0;"><b>Desa:</b> {b.get('desa', '-')}</p>
            <p style="margin: 2px 0;"><b>Kode ADM4:</b> <code>{b.get('kode_adm4', '-')}</code></p>
            <hr style="margin: 8px 0; border: none; border-top: 1px solid #ddd;">
            <p style="margin: 2px 0; font-size: 14px;"><b>Health Score:</b> <span style="color: {hex_color}; font-weight: bold; font-size: 16px;">{score}/100</span></p>
            <p style="margin: 2px 0;"><b>Status:</b> <span style="background: {hex_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{label}</span></p>
            <p style="margin: 4px 0 0 0; font-size: 12px; color: #555;"><b>Industri Terdekat:</b> {b.get('industri_terdekat', '')} ({b.get('jarak_industri_km', '')} km)</p>
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            icon=folium.Icon(color=color_name, icon="umbrella-beach", prefix="fa"),
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"🏖️ #{rank} {name} ({score}/100)"
        ).add_to(beach_layer)

        # Polygon
        if name in geom_map:
            folium.GeoJson(
                {"type": "Feature", "geometry": geom_map[name]},
                style_function=lambda x, col=hex_color: {
                    "fillColor": col,
                    "color": col,
                    "weight": 2,
                    "fillOpacity": 0.35,
                }
            ).add_to(beach_layer)

    beach_layer.add_to(m)

    # Layer Control
    folium.LayerControl(position="topright").add_to(m)

    m.save(MAP_HTML)
    print(f"Map updated & saved: {MAP_HTML}")


def generate_heatmap():
    print("Generating Heatmap Folium map...")
    with open(INDUSTRIES_JSON, "r", encoding="utf-8") as f:
        industries = json.load(f)

    with open(RECOMMENDATIONS_JSON, "r", encoding="utf-8") as f:
        beaches = json.load(f)

    m = folium.Map(location=[-6.3, 106.0], zoom_start=9, tiles="cartodbpositron")

    # Heatmap data based on industry risk
    heat_data = [[ind["latitude"], ind["longitude"], ind.get("risk_score", 50) / 100.0] for ind in industries]
    plugins.HeatMap(heat_data, radius=25, blur=15, max_zoom=12).add_to(m)

    # Add beach markers
    for b in beaches:
        folium.CircleMarker(
            location=[b["latitude"], b["longitude"]],
            radius=6,
            popup=f"🏖️ {b['pantai']} (Score: {b['health_score']})",
            color="#2980b9",
            fill=True,
            fill_color="#3498db",
            fill_opacity=0.8,
        ).add_to(m)

    m.save(HEATMAP_HTML)
    print(f"Heatmap updated & saved: {HEATMAP_HTML}")


if __name__ == "__main__":
    generate_main_map()
    generate_heatmap()
