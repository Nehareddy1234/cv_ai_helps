from clean_rpc import send_rpc

vec_id = "Segmented_Polygons__SAM_Geo__22f9df89_3fdc_4f74_8d67_16b50ea44ddd"

# Apply fire color ramp with high-contrast outlines and semi-transparent fill
r = send_rpc("cartography.style", {
    "layer": vec_id,
    "mode": "categorized",
    "field": "value",
    "color_ramp": "fire",
    "opacity": 0.5,
    "width": 1.6
})
print("Applied fire style:", r.get("result", {}).get("style", {}).get("dump", "")[:300])

send_rpc("project.action", {"action": "refresh"})
print("Refreshed")
