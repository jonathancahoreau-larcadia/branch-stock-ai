"""MCP protocol adapter for the Stock service."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from stock_mcp_server import tools


mcp = FastMCP(
    "Stock MCP Server",
    host="0.0.0.0",
    port=8200,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def list_branch_stock(
    branch_id: Annotated[int, Field(strict=True)],
) -> dict[str, Any]:
    """List stock for one branch through the Stock tools layer."""
    return tools.list_branch_stock(branch_id)


@mcp.tool()
def get_stock_for_product(external_product_id: str) -> dict[str, Any]:
    """Get stock for one product through the Stock tools layer."""
    return tools.get_stock_for_product(external_product_id)


@mcp.tool()
def find_branches_with_stock(
    external_product_id: str,
    quantity: Annotated[int, Field(strict=True)],
) -> dict[str, Any]:
    """Find branches with enough stock through the Stock tools layer."""
    return tools.find_branches_with_stock(external_product_id, quantity)


@mcp.tool()
def find_branches_for_shopping_list(
    items: list[dict],
) -> dict[str, Any]:
    """Find branches for a shopping list through the Stock tools layer."""
    return tools.find_branches_for_shopping_list(items)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Return the liveness status without invoking Stock tools."""
    return JSONResponse({"status": "ok"})


def main() -> None:
    """Start the stateless Streamable HTTP MCP server."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
