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

# Handshake
s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "bridge.hello",
    "params": {"token": token, "protocol": protocol}
}).encode("utf-8") + b"\n")
s.recv(16384)

# canvas.control -> set_extent
params = {
    "action": "set_extent",
    "extent": [8417500.0, 1538300.0, 8420600.0, 1541300.0],
    "crs": "EPSG:3857"
}

s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "canvas.control",
    "params": params
}).encode("utf-8") + b"\n")

resp = json.loads(s.recv(16384).decode("utf-8"))
print("set_extent response:", resp)

s.close()
