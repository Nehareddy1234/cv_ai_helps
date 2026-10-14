from clean_rpc import send_rpc

r = send_rpc("project.action", {"action": "save"})
print("Project saved in QGIS:", r)
