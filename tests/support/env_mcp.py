"""Test-only stdio MCP server that reports its process environment."""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

server = MCPServer(name="environment-fixture")


@server.tool(description="Return the subprocess environment as a JSON object.")
def environment() -> dict[str, str]:
    return dict(os.environ)


if __name__ == "__main__":
    server.run("stdio")
