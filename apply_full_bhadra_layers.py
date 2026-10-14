from clean_rpc import send_rpc
import time

RGB_TIF = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_entire_rgb.tif"
MASK_GPKG = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_entire_masks.gpkg"
MASK_QML = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_classifications.qml"
BOUNDARY_QML = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_boundary.qml"

print("1. Adding Bhadra Satellite Imagery (Full Sanctuary RGB)...")
r_rgb = send_rpc("project.action", {
    "action": "add_raster",
    "source": RGB_TIF,
    "name": "Bhadra Satellite Imagery (Full Sanctuary RGB)"
}, timeout=30.0)
print("RGB layer added:", r_rgb.get("result", {}).get("id"))
rgb_id = r_rgb.get("result", {}).get("id")

print("\n2. Adding SamGeo Classifications (Full Bhadra Region)...")
r_vec = send_rpc("project.action", {
    "action": "add_vector",
    "source": MASK_GPKG,
    "name": "SamGeo Classifications (Full Bhadra Region)"
}, timeout=30.0)
print("Vector layer added:", r_vec.get("result", {}).get("id"))
vec_id = r_vec.get("result", {}).get("id")

if vec_id:
    print("\n3. Loading classified style onto SamGeo vector layer...")
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
    print(f"\n4. Applying clean boundary styling to {boundary_id}...")
    r_bstyle = send_rpc("project.action", {
        "action": "load_style",
        "layer": boundary_id,
        "path": BOUNDARY_QML
    }, timeout=30.0)
    print("Boundary style loaded:", r_bstyle.get("result", {}).get("message"))

    print("\n5. Moving boundary to top (index 0)...")
    send_rpc("layer.manage", {
        "action": "move_layer",
        "layer": boundary_id,
        "index": 0
    }, timeout=30.0)

    if vec_id:
        print("Moving SamGeo classifications to index 1...")
        send_rpc("layer.manage", {
            "action": "move_layer",
            "layer": vec_id,
            "index": 1
        }, timeout=30.0)

    if rgb_id:
        print("Moving RGB raster to index 2...")
        send_rpc("layer.manage", {
            "action": "move_layer",
            "layer": rgb_id,
            "index": 2
        }, timeout=30.0)

    print("\n6. Zooming canvas to Bhadra outer boundary...")
    r_zoom = send_rpc("project.action", {
        "action": "zoom_layer",
        "layer": boundary_id
    }, timeout=30.0)
    print("Zoomed to boundary:", r_zoom.get("result", {}).get("extent"))

print("\n7. Refreshing map canvas and saving project...")
send_rpc("project.action", {"action": "refresh"}, timeout=30.0)
send_rpc("project.action", {"action": "save"}, timeout=30.0)

print("\nAll done! Layers configured and project saved successfully.")
