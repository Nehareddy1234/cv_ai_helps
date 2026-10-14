from clean_rpc import send_rpc

vec_id = "SamGeo_Classifications__Full_Bhadra_Region__4fa32ac6_23f8_496c_8525_d429cf0bf771"
boundary_id = "Bhadra_Sanctuary_Boundary__HELPS_AOI__1b486ed7_3a04_477c_8489_0a345169687a"
rgb_id = "Bhadra_Satellite_Imagery__Sanctuary_RGB__3906455f_b33e_42ee_9b32_44a2efdc3d2a"

# Move layers:
# 1. Boundary to index 0 (top)
send_rpc("layer.manage", {"action": "move_layer", "layer": boundary_id, "index": 0})
# 2. Vector classifications to index 1
send_rpc("layer.manage", {"action": "move_layer", "layer": vec_id, "index": 1})
# 3. Satellite raster to index 2
send_rpc("layer.manage", {"action": "move_layer", "layer": rgb_id, "index": 2})

send_rpc("project.action", {"action": "refresh"})
send_rpc("project.action", {"action": "save"})
print("Layer order updated!")
