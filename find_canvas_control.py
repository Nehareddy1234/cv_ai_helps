import os
import re

path = r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp"
for root, dirs, files in os.walk(path):
    for f in files:
        if f.endswith(".py"):
            fp = os.path.join(root, f)
            text = open(fp, "r", encoding="utf-8", errors="ignore").read()
            if "canvas.control" in text:
                print(f"Found in {f}")
                # print matching lines
                for line in text.splitlines():
                    if "canvas.control" in line or "zoom" in line.lower() and "def " in line:
                        print("  ", line[:100])
