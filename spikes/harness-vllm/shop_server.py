"""Tiny stdio MCP server used by every spike task ("shop" data).

Both harnesses connect to this same server, so the MCP tool path is identical.
"""

from mcp.server.mcpserver import MCPServer

PRICES = {"SKU-1": 12.50, "SKU-2": 7.25, "SKU-3": 31.00, "SKU-4": 4.10, "SKU-5": 22.40}
STOCK = {"SKU-1": 3, "SKU-2": 40, "SKU-3": 0, "SKU-4": 18, "SKU-5": 2}
DISCOUNTS = {"SPRING": 15, "VIP": 25}
SETTINGS = {"max_errors": "3", "listen_port": "8443", "greeting": "hola", "retries": "4"}

server = MCPServer(name="shop")


@server.tool(description="Return the unit price in USD for a product SKU, e.g. SKU-1.")
def get_price(sku: str) -> float:
    if sku not in PRICES:
        raise ValueError(f"unknown sku {sku}")
    return PRICES[sku]


@server.tool(description="Return the number of units in stock for a product SKU.")
def get_stock(sku: str) -> int:
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


if __name__ == "__main__":
    server.run("stdio")
