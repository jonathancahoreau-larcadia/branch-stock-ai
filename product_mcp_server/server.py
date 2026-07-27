"""MCP protocol adapter for the Product service."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from product_mcp_server import tools


mcp = FastMCP(
    "Product MCP Server",
    host="0.0.0.0",
    port=8100,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def list_products() -> dict[str, Any]:
    """List products through the Product tools layer."""
    return await tools.list_products()


@mcp.tool()
async def get_product_details(external_product_id: str) -> dict[str, Any]:
    """Get product details through the Product tools layer."""
    return await tools.get_product_details(external_product_id)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Return the liveness status without invoking Product tools."""
    return JSONResponse({"status": "ok"})


def main() -> None:
    """Start the stateless Streamable HTTP MCP server."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
