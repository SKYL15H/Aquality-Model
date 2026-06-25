import openeo

print("Connecting to OpenEO Copernicus Data Space Ecosystem...")
try:
    connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
    print("Connection established successfully!")
    capabilities = connection.capabilities()
    print("API Version:", capabilities.api_version())
    print("Collections available:", len(connection.list_collections()))
except Exception as e:
    print(f"Error: {e}")
