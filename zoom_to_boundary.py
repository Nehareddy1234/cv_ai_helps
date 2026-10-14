from clean_rpc import send_rpc

boundary_id = "Bhadra_Sanctuary_Boundary__HELPS_AOI__761b98d4_4597_4d5f_8822_0ccd089f02db"

r = send_rpc("project.action", {
    "action": "zoom_layer",
    "layer": boundary_id
})
print("Zoomed to full sanctuary boundary:", r)

snap = send_rpc("session.snapshot", {"detail": "summary"})
print("Updated Canvas:", snap.get("result", {}).get("canvas"))
send_rpc("project.action", {"action": "save"})
