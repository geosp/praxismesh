"""Disposable stdio MCP fixture; no user database or credentials."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PRICES = {"SKU-1": 12.5, "SKU-2": 7.25, "SKU-3": 31.0}
STOCK = {"SKU-1": 3, "SKU-2": 40, "SKU-3": 0}
SCHEMA = {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]}
TOOLS = [
    {"name": "lookup_price", "description": "Return unit price for a SKU.", "inputSchema": SCHEMA},
    {
        "name": "lookup_stock",
        "description": "Return available stock for a SKU.",
        "inputSchema": SCHEMA,
    },
]


def dispatch(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": params["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sample-shop-spike-fixture", "version": "1"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params["name"]
        args = params.get("arguments", {})
        allowed = name in ("lookup_price", "lookup_stock")
        with Path("/run/fixture-calls.jsonl").open("a") as stream:
            stream.write(json.dumps({"tool": name, "admitted": allowed}) + "\n")
        if not allowed:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "refused: ungranted tool"}],
            }
        values = PRICES if name == "lookup_price" else STOCK
        return {"content": [{"type": "text", "text": json.dumps(values[args["sku"]])}]}
    raise ValueError("unsupported method")


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
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": -32603, "message": type(exc).__name__},
            }
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
