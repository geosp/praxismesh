"""Sample shop MCP server, run as a stdio subprocess per harness turn.

Read-only tools: `lookup_price`, `lookup_stock`, `get_discount`, `get_setting`.
Side-effecting tool: `record_order`, idempotent per task (RFC: Side effects and
idempotency). Its key is sha256 of the task ID (`PRAXIS_TASK_ID`), the tool name
and the canonical JSON of its arguments; the order and the key commit in one
transaction, so a repeat returns the recorded result. The database URL comes
from `PRAXIS_SAMPLE_DB_URL`, which the worker passes to this server only.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PRICES = {"SKU-1": 12.50, "SKU-2": 7.25, "SKU-3": 31.00, "SKU-4": 4.10, "SKU-5": 22.40}
STOCK = {"SKU-1": 3, "SKU-2": 40, "SKU-3": 0, "SKU-4": 18, "SKU-5": 2}
DISCOUNTS = {"SPRING": 15, "VIP": 25}
SETTINGS = {"max_errors": "3", "listen_port": "8443", "greeting": "hola", "retries": "4"}

server = MCPServer(name="sample-shop")
_engine: AsyncEngine | None = None


def idempotency_key(task_id: str, tool: str, args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{task_id}\0{tool}\0{canonical}".encode()).hexdigest()


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = os.environ.get("PRAXIS_SAMPLE_DB_URL", "")
        if not url:
            raise RuntimeError("PRAXIS_SAMPLE_DB_URL is not set for the sample MCP server")
        _engine = create_async_engine(url)
    return _engine


@server.tool(description="Return the unit price in USD for a product SKU, e.g. SKU-1.")
def lookup_price(sku: str) -> float:
    if sku not in PRICES:
        raise ValueError(f"unknown sku {sku}")
    return PRICES[sku]


@server.tool(description="Return the number of units in stock for a product SKU.")
def lookup_stock(sku: str) -> int:
    if sku not in STOCK:
        raise ValueError(f"unknown sku {sku}")
    return STOCK[sku]


@server.tool(description="Return the discount percentage for a discount code.")
def get_discount(code: str) -> int:
    if code not in DISCOUNTS:
        raise ValueError(f"unknown code {code}")
    return DISCOUNTS[code]


@server.tool(description="Return the value of a named configuration setting as a string.")
def get_setting(key: str) -> str:
    if key not in SETTINGS:
        raise ValueError(f"unknown setting {key}")
    return SETTINGS[key]


@server.tool(
    description=(
        "Record an order of qty units of a SKU. Recording the same order again in the "
        "same task returns the earlier result instead of creating a second order."
    )
)
async def record_order(sku: str, qty: int) -> dict[str, Any]:
    if sku not in PRICES:
        raise ValueError(f"unknown sku {sku}")
    if qty < 1:
        raise ValueError("qty must be at least 1")
    task_id = os.environ.get("PRAXIS_TASK_ID", "")
    if not task_id:
        raise RuntimeError("PRAXIS_TASK_ID is not set")
    key = idempotency_key(task_id, "record_order", {"sku": sku, "qty": qty})
    async with engine().begin() as conn:
        claimed = await conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, task_id, tool, result) "
                "VALUES (:k, :t, 'record_order', '{}') ON CONFLICT (key) DO NOTHING RETURNING key"
            ),
            {"k": key, "t": task_id},
        )
        if claimed.first() is None:
            recorded = (
                await conn.execute(
                    text("SELECT result FROM idempotency_keys WHERE key = :k"), {"k": key}
                )
            ).scalar_one()
            return {**recorded, "repeated": True}
        order_id = (
            await conn.execute(
                text(
                    "INSERT INTO sample_orders (task_id, sku, qty, idempotency_key) "
                    "VALUES (:t, :s, :q, :k) RETURNING order_id"
                ),
                {"t": task_id, "s": sku, "q": qty, "k": key},
            )
        ).scalar_one()
        result = {"order_id": order_id, "sku": sku, "qty": qty, "total": PRICES[sku] * qty}
        await conn.execute(
            text("UPDATE idempotency_keys SET result = :r WHERE key = :k"),
            {"r": json.dumps(result), "k": key},
        )
    return {**result, "repeated": False}
