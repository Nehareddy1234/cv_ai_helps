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

# layer.inspect
s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "layer.inspect",
    "params": {
        "layer": "Segmented_Polygons__SAM_Geo__22f9df89_3fdc_4f74_8d67_16b50ea44ddd",
        "include": ["style", "metadata", "schema"]
    }
}).encode("utf-8") + b"\n")
resp = json.loads(s.recv(65536).decode("utf-8"))
print("Vector Layer Inspection:\n", json.dumps(resp, indent=2))

s.close()
