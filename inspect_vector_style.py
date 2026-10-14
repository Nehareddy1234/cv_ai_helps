path = r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp\cartography.py"
text = open(path, "r", encoding="utf-8").read()

idx = text.find("def style")
print(text[idx:idx+1500])
