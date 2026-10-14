from clean_rpc import send_rpc

snap = send_rpc("session.snapshot", {"detail": "full"})
# Let's inspect the actual layer tree via capabilities_invoke or snapshot
layers = snap.get("result", {}).get("layers", [])
print("Layer list count:", len(layers))
for l in layers:
    print(l["name"])
