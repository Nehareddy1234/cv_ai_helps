from clean_rpc import send_rpc

snap = send_rpc("session.snapshot", {"detail": "full"})
layers = snap.get("result", {}).get("layers", [])
print("Layers in session:")
for l in layers:
    print(f" - {l['name']} (id: {l['id']}, type: {l['type']}, opacity: {l.get('opacity')})")
