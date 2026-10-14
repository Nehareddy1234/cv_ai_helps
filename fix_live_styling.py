import socket
import json
from pathlib import Path

conn_path = Path.home() / ".qgis-mcp" / "connection.json"
conn = json.loads(conn_path.read_text(encoding="utf-8"))
host = conn["host"]
port = int(conn["port"])
token = conn["token"]
protocol = conn.get("protocol", 1)

s = socket.create_connection((host, port), timeout=5.0)

s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "bridge.hello",
    "params": {"token": token, "protocol": protocol}
}).encode("utf-8") + b"\n")
s.recv(16384)

layer_id = "Segmented_Polygons__SAM_Geo__22f9df89_3fdc_4f74_8d67_16b50ea44ddd"

# 1. Apply categorized styling with proper type matching
s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "cartography.style",
    "params": {
        "layer": layer_id,
        "mode": "categorized",
        "field": "value",
        "opacity": 0.65,
        "width": 1.2
    }
}).encode("utf-8") + b"\n")
resp = json.loads(s.recv(65536).decode("utf-8"))
print("Style result:", resp)

# 2. Zoom to the layer extent
s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 3,
    "method": "project.action",
    "params": {
        "action": "zoom_layer",
        "layer": layer_id
    }
}).encode("utf-8") + b"\n")
resp2 = json.loads(s.recv(65536).decode("utf-8"))
print("Zoom result:", resp2)

# 3. Trigger canvas refresh
s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 4,
    "method": "project.action",
    "params": {
        "action": "refresh"
    }
}).encode("utf-8") + b"\n")
resp3 = json.loads(s.recv(65536).decode("utf-8"))
print("Refresh result:", resp3)

s.close()
