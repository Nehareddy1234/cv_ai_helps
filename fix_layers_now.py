from clean_rpc import send_rpc

vec_id = "Segmented_Polygons__SAM_Geo__22f9df89_3fdc_4f74_8d67_16b50ea44ddd"
mask_id = "SAM_Mask__Raster__ed5008eb_9266_4839_95fd_6e93cf0f0cb7"
sat_id = "Bhadra_Satellite_Imagery__Esri_World_Imagery__e64edfe8_c224_430a_ac27_62620e2a3872"
esri_id = "_03fe1f87_3431_4e21_8101_6c4a2448fd27"

# 1. Hide the raw mask raster so it doesn't cover anything
r1 = send_rpc("layer.manage", {
    "action": "set_visibility",
    "layer": mask_id,
    "visible": False
})
print("Hide mask raster:", r1)

# 2. Make sure vector polygons are visible
r2 = send_rpc("layer.manage", {
    "action": "set_visibility",
    "layer": vec_id,
    "visible": True
})
print("Show vector polygons:", r2)

# 3. Move vector polygons to the very top (index 0)
r3 = send_rpc("layer.manage", {
    "action": "move_layer",
    "layer": vec_id,
    "index": 0
})
print("Move vector to top:", r3)

# 4. Move satellite imagery below vector (index 1)
r4 = send_rpc("layer.manage", {
    "action": "move_layer",
    "layer": sat_id,
    "index": 1
})
print("Move sat layer:", r4)

# 5. Move Esri basemap to the bottom
r5 = send_rpc("layer.manage", {
    "action": "move_layer",
    "layer": esri_id,
    "index": 3
})
print("Move Esri basemap:", r5)

# 6. Zoom to vector layer extent
r6 = send_rpc("project.action", {
    "action": "zoom_layer",
    "layer": vec_id
})
print("Zoom to vector layer:", r6)

# 7. Refresh canvas
r7 = send_rpc("project.action", {
    "action": "refresh"
})
print("Canvas refreshed:", r7)
