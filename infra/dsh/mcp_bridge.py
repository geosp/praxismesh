"""Stdio MCP server inside the DSH container (DSH migration plan D4, R14).

DSH's MCP client starts this for the one granted server. It lists the catalog the
worker wrote to `config/tools.json` and forwards every call to the worker's
executor through the socket in the attempt tree; no tool body runs here.

Standard library only.
"""

from __future__ import annotations

import http.client
import json
import socket
import sys
from pathlib import Path

TREE = Path("/run/attempt")
GATEWAY = TREE / "ipc/gateway.sock"
CALL_TIMEOUT_S = 150


def dispatch(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": params["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "praxis", "version": "1"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": json.loads((TREE / "config/tools.json").read_text())}
    if method != "tools/call":
        raise ValueError("unsupported method")
    connection = http.client.HTTPConnection("executor", timeout=CALL_TIMEOUT_S)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(CALL_TIMEOUT_S)
    connection.sock.connect(str(GATEWAY))
    try:
        connection.request(
            "POST", "/tool", json.dumps(params), {"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        return {
            "isError": bool(body.get("is_error")) or response.status != 200,
            "content": [{"type": "text", "text": str(body.get("text", ""))}],
        }
    finally:
        connection.close()


def main() -> None:
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
