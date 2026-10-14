import json
import numpy as np

path = r"C:\Users\Nehar\Desktop\HELPS\Codes\data\inputs\45295356fafbdae35c06ddec\2026-06-01\aoi.geojson"
with open(path) as f:
    d = json.load(f)

print("AOI GeoJSON Type:", d.get("type"))
features = d.get("features", [])
print("Feature count:", len(features))
if features:
    props = features[0].get("properties", {})
    print("Properties:", props)
    geom = features[0].get("geometry", {})
    print("Geometry type:", geom.get("type"))
    coords = geom.get("coordinates", [])
    pts = np.array(coords).reshape(-1, 2)
    min_lon, min_lat = pts.min(axis=0)
    max_lon, max_lat = pts.max(axis=0)
    print(f"Bounding Box: west={min_lon:.6f}, south={min_lat:.6f}, east={max_lon:.6f}, north={max_lat:.6f}")
    print(f"Center: lon={(min_lon+max_lon)/2:.6f}, lat={(min_lat+max_lat)/2:.6f}")
