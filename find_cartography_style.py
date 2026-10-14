path = r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp\dispatcher.py"
text = open(path, "r", encoding="utf-8").read()

idx = text.find("cartography.style")
print(text[idx-100:idx+400])
