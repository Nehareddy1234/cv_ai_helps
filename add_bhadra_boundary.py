from clean_rpc import send_rpc
import os

boundary_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_boundary.geojson"

# 1. Add vector layer
r_add = send_rpc("project.action", {
    "action": "add_vector",
    "source": boundary_path,
    "name": "Bhadra Sanctuary Boundary (HELPS AOI)"
})
print("Added layer:", r_add)

layer_id = r_add.get("result", {}).get("id")

if layer_id:
    # 2. Style layer with bright crimson boundary and clear outline
    r_style = send_rpc("cartography.style", {
        "layer": layer_id,
        "mode": "simple",
        "color": "#FF1744",
        "opacity": 0.15,
        "width": 2.2
    })
    print("Styled boundary layer:", r_style)

    # 3. Move boundary layer to top
    send_rpc("layer.manage", {
        "action": "move_layer",
        "layer": layer_id,
        "index": 0
    })

    # 4. Zoom to full Bhadra boundary extent
    r_zoom = send_rpc("project.action", {
        "action": "zoom_layer",
        "layer": layer_id
    })
    print("Zoomed to full Bhadra sanctuary:", r_zoom)

# 5. Also add the final landing zones from Codes if available
codes_gpkg = r"C:\Users\Nehar\Desktop\HELPS\Codes\data\processed\Bhadra\sentinel2\2026-06-01\bhadra_final_open_land_zones.gpkg"
if os.path.exists(codes_gpkg):
    r_zones = send_rpc("project.action", {
        "action": "add_vector",
        "source": codes_gpkg,
        "name": "HELPS Analyzed Landing Zones (Codes)"
    })
    print("Added Codes landing zones layer:", r_zones)
    zones_id = r_zones.get("result", {}).get("id")
    if zones_id:
        send_rpc("cartography.style", {
            "layer": zones_id,
            "mode": "simple",
            "color": "#00E676",
            "opacity": 0.6,
            "width": 1.2
        })
        send_rpc("layer.manage", {
            "action": "move_layer",
            "layer": zones_id,
            "index": 1
        })

send_rpc("project.action", {"action": "refresh"})
send_rpc("project.action", {"action": "save"})
print("Project updated and saved!")
