"""Container-side MCP transport for the trusted host recovery fixture executor."""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

TOOLS = [
    {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    }
    for name, description in (
        ("write_note", "Write the controller-selected recovery note."),
        ("read_note", "Read the recovery note from the current workspace."),
        ("effect_once", "Commit the controller-selected idempotent fixture effect."),
    )
]


def dispatch(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": params["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "recovery-fixture", "version": "1"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        tools = (
            json.loads(Path("/opt/spike/task-tools.json").read_text())
            if os.environ.get("PRAXIS_SPIKE_TASK_TOOLS") == "1"
            else TOOLS
        )
        return {"tools": tools}
    if method != "tools/call":
        raise ValueError("unsupported method")
    if os.environ.get("PRAXIS_SPIKE_STALL_CHILD") == "1":
        # Dedicated bounded-tool fixture descendant, owned by this container.
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"])
    connection = http.client.HTTPConnection("fixture", timeout=90)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(90)
    connection.sock.connect("/run/ipc/tools.sock")
    try:
        connection.request(
            "POST", "/tool", json.dumps(params), {"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        return {
            "isError": response.status != 200,
            "content": [{"type": "text", "text": json.dumps(body)}],
        }
    finally:
        connection.close()


def main():
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        try:
            response = {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": dispatch(request["method"], request.get("params", {})),
            }
        except Exception as error:
            response = {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": -32603, "message": type(error).__name__},
            }
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
