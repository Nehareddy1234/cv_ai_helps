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

# Look at layer tree / order
s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "project.action",
    "params": {"action": "layer_tree"}
}).encode("utf-8") + b"\n")
resp = json.loads(s.recv(16384).decode("utf-8"))
print("layer_tree:", json.dumps(resp, indent=2))

s.close()
