import re

with open(r"C:\Users\Nehar\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\qgis_agent_mcp\dispatcher.py", "r", encoding="utf-8") as f:
    text = f.read()

# Look for method registrations like self.register("method.name", handler)
methods = re.findall(r'register\(\s*["\']([^"\']+)["\']', text)
if not methods:
    methods = re.findall(r'case\s+["\']([^"\']+)["\']', text)
if not methods:
    methods = re.findall(r'["\']([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)["\']', text)

print("Registered methods:", list(set(methods))[:50])
