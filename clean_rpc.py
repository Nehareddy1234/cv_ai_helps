import socket
import json
from pathlib import Path

conn_path = Path.home() / ".qgis-mcp" / "connection.json"
conn = json.loads(conn_path.read_text(encoding="utf-8"))
host = conn["host"]
port = int(conn["port"])
token = conn["token"]
protocol = conn.get("protocol", 1)

def send_rpc(method, params, timeout=30.0):
    s = socket.create_connection((host, port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "bridge.hello",
        "params": {"token": token, "protocol": protocol}
    }).encode("utf-8") + b"\n")
    
    # Read until handshake response
    data = ""
    while "\n" not in data:
        data += s.recv(4096).decode("utf-8")
    
    # Send actual request
    s.sendall(json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": method,
        "params": params
    }).encode("utf-8") + b"\n")
    
    # Read responses line by line until id 2
    buffer = ""
    while True:
        chunk = s.recv(4096).decode("utf-8")
        if not chunk:
            break
        buffer += chunk
        lines = buffer.split("\n")
        buffer = lines[-1]
        for line in lines[:-1]:
            if not line.strip():
                continue
            msg = json.loads(line)
            if msg.get("id") == 2:
                s.close()
                return msg
    s.close()
    return None
