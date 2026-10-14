from clean_rpc import send_rpc
import time

MASK_GPKG = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_entire_masks_clipped.gpkg"
RGB_TIF = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_sanctuary_rgb.tif"
MASK_QML = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_classifications.qml"
BOUNDARY_QML = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_boundary.qml"

snap = send_rpc("session.snapshot", {"detail": "summary"}, timeout=30.0)
layers = snap.get("result", {}).get("layers", [])

# Remove previous unclipped versions
for l in layers:
    if "SamGeo Classifications" in l.get("name", "") or "Full Sanctuary RGB" in l.get("name", ""):
        print(f"Removing old layer: {l['name']} ({l['id']})")
        send_rpc("project.action", {"action": "remove_layer", "layer": l["id"]}, timeout=30.0)

# Add masked RGB raster
print("Adding Bhadra Satellite Imagery (Sanctuary RGB)...")
r_rgb = send_rpc("project.action", {
    "action": "add_raster",
    "source": RGB_TIF,
    "name": "Bhadra Satellite Imagery (Sanctuary RGB)"
}, timeout=30.0)
rgb_id = r_rgb.get("result", {}).get("id")
print("RGB layer added:", rgb_id)

# Add clipped SamGeo vector classifications
print("Adding SamGeo Classifications (Full Bhadra Region)...")
r_vec = send_rpc("project.action", {
    "action": "add_vector",
    "source": MASK_GPKG,
    "name": "SamGeo Classifications (Full Bhadra Region)"
}, timeout=30.0)
vec_id = r_vec.get("result", {}).get("id")
print("Vector layer added:", vec_id)

if vec_id:
    print("Loading thematic categorized style on SamGeo vector layer...")
    r_style = send_rpc("project.action", {
        "action": "load_style",
        "layer": vec_id,
        "path": MASK_QML
    }, timeout=30.0)
    print("Style loaded:", r_style.get("result", {}).get("message"))

# Find boundary layer ID
snap = send_rpc("session.snapshot", {"detail": "summary"}, timeout=30.0)
layers = snap.get("result", {}).get("layers", [])
boundary_id = None
for l in layers:
    if "Boundary" in l.get("name", ""):
        boundary_id = l["id"]
        break

if boundary_id:
    print(f"Applying crisp outer boundary styling to {boundary_id}...")
    send_rpc("project.action", {
        "action": "load_style",
        "layer": boundary_id,
        "path": BOUNDARY_QML
    }, timeout=30.0)

    print("Re-ordering layers...")
    send_rpc("layer.manage", {"action": "move_layer", "layer": boundary_id, "index": 0}, timeout=30.0)
    if vec_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": vec_id, "index": 1}, timeout=30.0)
    if rgb_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": rgb_id, "index": 2}, timeout=30.0)

    print("Zooming canvas to Bhadra outer boundary...")
    send_rpc("project.action", {"action": "zoom_layer", "layer": boundary_id}, timeout=30.0)

send_rpc("project.action", {"action": "refresh"}, timeout=30.0)
send_rpc("project.action", {"action": "save"}, timeout=30.0)
print("Complete!")
