path = r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp\dispatcher.py"
text = open(path, "r", encoding="utf-8").read()

idx = text.find("def project_action")
print(text[idx+2000:idx+3500])
