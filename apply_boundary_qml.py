from clean_rpc import send_rpc

boundary_id = "Bhadra_Sanctuary_Boundary__HELPS_AOI__761b98d4_4597_4d5f_8822_0ccd089f02db"
qml_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_boundary.qml"

r = send_rpc("project.action", {
    "action": "load_style",
    "layer": boundary_id,
    "path": qml_path
})
print("Load style response:", r)

send_rpc("project.action", {"action": "refresh"})
send_rpc("project.action", {"action": "save"})
print("Boundary style loaded and project saved!")
