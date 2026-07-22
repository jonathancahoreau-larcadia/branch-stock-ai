"""MCP server that wraps the external Product API."""

import os
from mcp.server.fastmcp import FastMCP
from product_client import ProductClient

mcp = FastMCP("product-mcp")
api = ProductClient(os.environ["PRODUCT_API_BASE_URL"])


@mcp.tool()
async def list_products() -> dict:
    try:
        return {"status": "success", "data": {"products": await api.list_products()}}
    except Exception as e:
        return {"status": "error", "error": {"code": _map(e), "message": str(e)}}


@mcp.tool()
async def get_product_details(product_id: str) -> dict:
    if not (product_id and product_id.strip()):
        return {"status": "error", "error": {
            "code": "INVALID_PRODUCT_ID", "message": "empty product_id"}}

    try:
        data = await api.get_product(product_id)
        if data is None:
            return {"status": "not_found", "data": None}
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "error": {"code": _map(e), "message": str(e)}}


def _map(exc):
    t = type(exc).__name__
    if t == "ProductAPITimeout":
        return "PRODUCT_API_TIMEOUT"
    if t == "ProductAPIUnavailable":
        return "PRODUCT_API_UNAVAILABLE"
    if t == "ProductAPIInvalidResponse":
        return "PRODUCT_API_INVALID_RESPONSE"
    return "PRODUCT_API_ERROR"


if __name__ == "__main__":
    mcp.run()
