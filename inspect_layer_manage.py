path = r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp\dispatcher.py"
text = open(path, "r", encoding="utf-8").read()

idx = text.find("def layer_manage")
if idx != -1:
    print(text[idx:idx+1500])
else:
    print("def layer_manage not found")
