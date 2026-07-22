"""Stock MCP Server — read-only stock data for the AI agent."""

import os
from mcp.server.fastmcp import FastMCP
from db import (
    list_branch_stock,
    get_stock_for_product,
    find_branches_with_stock,
    find_branches_for_shopping_list,
)

mcp = FastMCP("stock-mcp")


@mcp.tool()
def list_branch_stock_tool(branch_id: int) -> dict:
    if branch_id <= 0:
        return {"status": "error", "error": {"code": "INVALID_BRANCH_ID", "message": "branch_id must be positive"}}
    result = list_branch_stock(branch_id)
    if result is None:
        return {"status": "error", "error": {"code": "BRANCH_NOT_FOUND", "message": f"branch {branch_id} not found"}}
    return {"status": "success", "data": result}


@mcp.tool()
def get_stock_for_product_tool(product_id: str) -> dict:
    if not (product_id and product_id.strip()):
        return {"status": "error", "error": {"code": "INVALID_PRODUCT_ID", "message": "empty product_id"}}
    return {"status": "success", "data": get_stock_for_product(product_id)}


@mcp.tool()
def find_branches_with_stock_tool(product_id: str, quantity: int) -> dict:
    if not (product_id and product_id.strip()):
        return {"status": "error", "error": {"code": "INVALID_PRODUCT_ID", "message": "empty product_id"}}
    if quantity <= 0:
        return {"status": "error", "error": {"code": "INVALID_QUANTITY", "message": "quantity must be positive"}}
    return {"status": "success", "data": find_branches_with_stock(product_id, quantity)}


@mcp.tool()
def find_branches_for_shopping_list_tool(items: list) -> dict:
    if not items:
        return {"status": "error", "error": {"code": "INVALID_SHOPPING_LIST", "message": "empty items list"}}
    for it in items:
        if not it.get("external_product_id") or not it["external_product_id"].strip():
            return {"status": "error", "error": {"code": "INVALID_ITEM", "message": "missing product_id"}}
        if it.get("quantity", 0) <= 0:
            return {"status": "error", "error": {"code": "INVALID_QUANTITY", "message": "quantity must be positive"}}
    return {"status": "success", "data": find_branches_for_shopping_list(items)}


if __name__ == "__main__":
    mcp.run()
