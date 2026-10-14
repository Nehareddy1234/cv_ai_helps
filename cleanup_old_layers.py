from clean_rpc import send_rpc

snap = send_rpc("session.snapshot", {"detail": "full"})
layers = snap.get("result", {}).get("layers", [])

print("Current layers:")
for l in layers:
    print(f" - {l['name']} ({l['id']})")

# Unwanted layers to remove
remove_keywords = [
    "HELPS Analyzed Landing Zones",
    "SAM Mask",
    "Segmented Polygons",
    "Bhadra Satellite Imagery"
]

for l in layers:
    name = l["name"]
    lid = l["id"]
    if any(k in name for k in remove_keywords):
        print(f"Removing layer: {name} ({lid})")
        r = send_rpc("project.action", {
            "action": "remove_layer",
            "layer": lid
        })
        print(f"Result: {r}")

send_rpc("project.action", {"action": "refresh"})
send_rpc("project.action", {"action": "save"})
print("Cleanup complete!")
