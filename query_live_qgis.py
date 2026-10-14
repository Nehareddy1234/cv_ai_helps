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

# session.snapshot
s.sendall(json.dumps({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "session.snapshot",
    "params": {"detail": "full"}
}).encode("utf-8") + b"\n")

resp2 = json.loads(s.recv(131072).decode("utf-8"))
print("Session Snapshot:\n", json.dumps(resp2, indent=2))

s.close()
