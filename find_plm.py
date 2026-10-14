path = r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp"
import os
for root, dirs, files in os.walk(path):
    for f in files:
        if f.endswith(".py"):
            text = open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore").read()
            if "class ProjectLayerManager" in text:
                print(f"Found in {f}")
