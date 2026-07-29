"""Public, read-only Product MCP tools."""

from __future__ import annotations

from typing import Any

from . import product_api


__all__ = ["list_products", "get_product_details"]

_INVALID_IDENTIFIER = {
    "status": "error",
    "error": {
        "code": "INVALID_EXTERNAL_PRODUCT_ID",
        "message": "Product identifier is invalid.",
    },
}
_INVALID_RESPONSE = {
    "status": "error",
    "error": {
        "code": "PRODUCT_API_INVALID_RESPONSE",
        "message": "Product API response is invalid.",
    },
}


def _is_integer(value: Any, *, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_product(product: Any) -> bool:
    return (
        isinstance(product, dict)
        and _is_integer(product.get("id"), minimum=1)
        and _is_non_empty_string(product.get("sku"))
        and _is_non_empty_string(product.get("name"))
    )


def _project_product(product: dict[str, Any]) -> dict[str, str]:
    return {
        "external_product_id": product["sku"],
        "name": product["name"],
    }


def _valid_page(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False

    count = payload.get("count")
    limit = payload.get("limit")
    offset = payload.get("offset")
    products = payload.get("results")
    if not (
        _is_integer(count, minimum=0)
        and _is_integer(limit, minimum=1)
        and limit <= 100
        and _is_integer(offset, minimum=0)
        and isinstance(products, list)
    ):
        return False

    expected_length = min(limit, max(count - offset, 0))
    return len(products) == expected_length and all(
        _valid_product(product) for product in products
    )


def _matches_identifier(product: dict[str, Any], identifier: str) -> bool:
    if identifier.isdecimal():
        return product["id"] == int(identifier)
    return product["sku"].casefold() == identifier.casefold()


async def list_products() -> dict[str, Any]:
    """Return the validated Product API page in the public MCP projection."""
    result = await product_api.list_products()
    if result.get("status") != "success":
        return result

    payload = result.get("data")
    if not _valid_page(payload):
        return _INVALID_RESPONSE

    return {
        "status": "success",
        "data": {
            "products": [_project_product(product) for product in payload["results"]]
        },
    }


async def get_product_details(external_product_id: str) -> dict[str, Any]:
    """Return one validated product in the public MCP projection."""
    if not isinstance(external_product_id, str):
        return _INVALID_IDENTIFIER

    identifier = external_product_id.strip()
    if not identifier or len(identifier) > 255:
        return _INVALID_IDENTIFIER

    result = await product_api.get_product_details(identifier)
    if result.get("status") != "success":
        return result

    product = result.get("data")
    if not _valid_product(product) or not _matches_identifier(product, identifier):
        return _INVALID_RESPONSE

    return {"status": "success", "data": _project_product(product)}
