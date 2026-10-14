from clean_rpc import send_rpc

snap = send_rpc("session.snapshot", {"detail": "summary"})
print("Canvas:", snap.get("result", {}).get("canvas"))
layers = snap.get("result", {}).get("layers", [])
print("\nCurrent Active Layers in QGIS:")
for idx, l in enumerate(layers):
    print(f" {idx+1}. {l['name']} ({l['type']}) - Valid: {l['valid']}, Source: {l.get('source')}")
