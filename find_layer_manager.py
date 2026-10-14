path = r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp\dispatcher.py"
text = open(path, "r", encoding="utf-8").read()

for line in text.splitlines():
    if "layer_manager" in line:
        print(line)
