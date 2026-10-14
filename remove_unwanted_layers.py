from clean_rpc import send_rpc
import time

to_remove = [
    "HELPS_Analyzed_Landing_Zones__Codes__79b7fa12_9c94_4fdc_b197_fa35be0261c8",
    "SAM_Mask__Raster__ed5008eb_9266_4839_95fd_6e93cf0f0cb7",
    "Segmented_Polygons__SAM_Geo__22f9df89_3fdc_4f74_8d67_16b50ea44ddd"
]

for lid in to_remove:
    print(f"Removing {lid}...")
    try:
        r = send_rpc("project.action", {
            "action": "remove_layer",
            "layer": lid
        }, timeout=30.0)
        print("Result:", r)
    except Exception as e:
        print("Error:", e)
    time.sleep(0.5)

send_rpc("project.action", {"action": "refresh"}, timeout=30.0)
send_rpc("project.action", {"action": "save"}, timeout=30.0)
print("Done removing unwanted layers!")
