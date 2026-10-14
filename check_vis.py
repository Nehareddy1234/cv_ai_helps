from clean_rpc import send_rpc

snap = send_rpc("session.snapshot", {"detail": "full"})
vis = snap.get("result", {}).get("visible_layer_ids", [])
layers = snap.get("result", {}).get("layers", [])

print("Visible IDs:", vis)
print("All layers:")
for l in layers:
    is_vis = l["id"] in vis
    print(f" - {l['name']} (ID: {l['id']}, Visible: {is_vis})")
