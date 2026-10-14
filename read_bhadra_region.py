import json
import numpy as np

path = r"C:\Users\Nehar\Desktop\HELPS\Codes\data\raw\Bhadra\bhadra_entire_region.geojson"
with open(path) as f:
    d = json.load(f)

print("Type:", d.get("type"))
features = d.get("features", [])
print("Feature count:", len(features))
if features:
    for idx, f in enumerate(features[:5]):
        print(f"Feature {idx} properties:", f.get("properties"))
    geom = features[0].get("geometry", {})
    coords = geom.get("coordinates", [])
    pts = np.array(coords).reshape(-1, 2)
    min_lon, min_lat = pts.min(axis=0)
    max_lon, max_lat = pts.max(axis=0)
    print(f"BBox: west={min_lon:.6f}, south={min_lat:.6f}, east={max_lon:.6f}, north={max_lat:.6f}")
