import openeo

connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
print("Listing band names of SENTINEL2_L2A:")
try:
    collection = connection.describe_collection("SENTINEL2_L2A")
    bands = [b["name"] for b in collection["cube:dimensions"]["bands"]["values"]]
    print("Bands:", bands)
except Exception as e:
    print("Error:", e)
