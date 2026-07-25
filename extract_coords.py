import json

with open('output/banten_water_quality_beach.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for name, d in data.items():
    lat = d.get('latitude', 0)
    lon = d.get('longitude', 0)
    print(f"{name} | {lat} | {lon}")
