#!/usr/bin/env python3
"""
Update live QGIS session and saved project with SamGeo classification on Esri Map:
1. Remove cloudy Sentinel-2 and previous workflow layers.
2. Ensure clean Esri World Imagery is the base map.
3. Add SamGeo classifications generated on Esri imagery across the entire Bhadra sanctuary.
4. Style vector classifications with distinct, semi-transparent colors and crisp outlines.
5. Keep official Bhadra Sanctuary AOI boundary outline on top.
6. Zoom canvas to the full Bhadra sanctuary and save.
"""

import os
from clean_rpc import send_rpc

ESRI_GPKG = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_esri_masks.gpkg"
ESRI_TIF = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_esri_sanctuary.tif"
BOUNDARY_GEOJSON = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_boundary.geojson"

def update_qgis():
    print("Connecting to live QGIS session via RPC...")
    snap = send_rpc("session.snapshot", {"detail": "full"})
    if not snap or "result" not in snap:
        print("[Error] Could not get session snapshot from QGIS.")
        return

    layers = snap.get("result", {}).get("layers", [])
    print(f"Current layers in QGIS ({len(layers)}):")
    for l in layers:
        print(f" - {l.get('name')} (ID: {l.get('id')})")

    # 1. Remove old/cloudy Sentinel layers and previous workflow layers
    layers_to_remove_keywords = ["sentinel", "sanctuary rgb", "codes", "landing zones", "test", "bhadra_masks"]
    for l in layers:
        name_lower = (l.get("name") or "").lower()
        lid = l.get("id")
        if any(kw in name_lower for kw in layers_to_remove_keywords):
            print(f"Removing outdated layer: {l.get('name')} ({lid})")
            send_rpc("layer.manage", {"action": "remove_layer", "layer": lid})

    # Also remove any previous samgeo masks if we are adding new ones
    for l in layers:
        name_lower = (l.get("name") or "").lower()
        lid = l.get("id")
        if "samgeo" in name_lower:
            print(f"Replacing previous SamGeo layer: {l.get('name')} ({lid})")
            send_rpc("layer.manage", {"action": "remove_layer", "layer": lid})

    # 2. Ensure Esri XYZ basemap is present
    snap_after = send_rpc("session.snapshot", {"detail": "summary"})
    current_layer_names = [l.get("name") for l in snap_after.get("result", {}).get("layers", [])]

    esri_layer_id = None
    for l in snap_after.get("result", {}).get("layers", []):
        if "esri" in (l.get("name") or "").lower():
            esri_layer_id = l.get("id")
            break

    if not esri_layer_id:
        print("Adding Esri World Imagery basemap...")
        r_esri = send_rpc("project.action", {
            "action": "add_raster",
            "source": "crs=EPSG:3857&format&type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}&zmax=18&zmin=0",
            "name": "Esri World Imagery"
        })
        esri_layer_id = r_esri.get("result", {}).get("id")

    # 3. Add clean clipped Esri Sanctuary raster
    if os.path.exists(ESRI_TIF):
        print("Adding clipped Esri Sanctuary imagery...")
        r_clipped = send_rpc("project.action", {
            "action": "add_raster",
            "source": ESRI_TIF,
            "name": "Bhadra Esri Imagery (Sanctuary AOI)"
        })
        clipped_id = r_clipped.get("result", {}).get("id")
    else:
        clipped_id = None

    # 4. Add new SamGeo vector classifications
    print(f"Adding SamGeo classifications from {ESRI_GPKG}...")
    r_vec = send_rpc("project.action", {
        "action": "add_vector",
        "source": ESRI_GPKG,
        "name": "SamGeo Classifications (Esri Map - Full Bhadra)"
    })
    vec_id = r_vec.get("result", {}).get("id")
    print(f"Added SamGeo layer with ID: {vec_id}")

    if vec_id:
        print("Styling SamGeo vector layer with high-contrast semi-transparent categories...")
        # Style with vibrant color ramp
        send_rpc("cartography.style", {
            "layer": vec_id,
            "mode": "categorized",
            "field": "value",
            "color_ramp": "Spectral",
            "opacity": 0.55,
            "width": 1.0
        })

    # 5. Ensure official Bhadra boundary is present and on top
    boundary_id = None
    for l in snap_after.get("result", {}).get("layers", []):
        if "boundary" in (l.get("name") or "").lower():
            boundary_id = l.get("id")
            break

    if not boundary_id and os.path.exists(BOUNDARY_GEOJSON):
        print("Adding official Bhadra Sanctuary boundary...")
        r_b = send_rpc("project.action", {
            "action": "add_vector",
            "source": BOUNDARY_GEOJSON,
            "name": "Bhadra Sanctuary Boundary (HELPS AOI)"
        })
        boundary_id = r_b.get("result", {}).get("id")

    if boundary_id:
        # Style boundary with distinct crimson outline and no fill
        send_rpc("cartography.style", {
            "layer": boundary_id,
            "mode": "simple",
            "color": "#E53935",
            "opacity": 0.0,
            "width": 2.5
        })

    # 6. Re-order layers (Top to Bottom):
    # Index 0: Boundary
    # Index 1: SamGeo Classifications
    # Index 2: Clipped Esri Imagery
    # Index 3: Global Esri XYZ Basemap
    if boundary_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": boundary_id, "index": 0})
    if vec_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": vec_id, "index": 1})
    if clipped_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": clipped_id, "index": 2})
    if esri_layer_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": esri_layer_id, "index": 3})

    # 7. Zoom to full Bhadra boundary
    target_zoom_layer = boundary_id if boundary_id else vec_id
    if target_zoom_layer:
        print(f"Zooming to layer {target_zoom_layer}...")
        send_rpc("project.action", {"action": "zoom_layer", "layer": target_zoom_layer})

    # 8. Refresh and save
    send_rpc("project.action", {"action": "refresh"})
    send_rpc("project.action", {"action": "save"})
    print("[SUCCESS] Live QGIS project updated and saved perfectly!")

if __name__ == "__main__":
    update_qgis()
