import sys

deps = ['openeo', 'rasterio', 'rioxarray', 'xarray', 'geopandas', 'shapely', 'folium', 'sklearn', 'fiona']
missing = []

for dep in deps:
    try:
        __import__(dep)
        print(f"OK: {dep} is installed")
    except ImportError:
        print(f"MISSING: {dep} is NOT installed")
        missing.append(dep)

if missing:
    print(f"\nMissing packages: {' '.join(missing)}")
    sys.exit(1)
else:
    print("\nOK: All packages are installed!")
    sys.exit(0)
