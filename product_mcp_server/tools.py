"""Public, read-only Product MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
import math
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


def _valid_page(
    payload: Any,
    *,
    expected_limit: int,
    expected_offset: int,
    expected_count: int | None,
) -> bool:
    if not isinstance(payload, dict):
        return False

    count = payload.get("count")
    limit = payload.get("limit")
    offset = payload.get("offset")
    products = payload.get("results")
    if not (
        _is_integer(count, minimum=0)
        and _is_integer(limit, minimum=1)
        and limit == expected_limit
        and _is_integer(offset, minimum=0)
        and offset == expected_offset
        and isinstance(products, list)
    ):
        return False
    if expected_count is not None and count != expected_count:
        return False

    expected_length = min(limit, max(count - offset, 0))
    return len(products) == expected_length and all(
        _valid_product(product) for product in products
    )


def _number(value: Any, *, minimum: float = 0) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= minimum
    )


def _utc_datetime(value: Any) -> bool:
    if not _is_non_empty_string(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() == timezone.utc.utcoffset(parsed)
    )


def _valid_detail(product: Any) -> bool:
    if not _valid_product(product):
        return False
    supplier = product.get("supplier")
    tags = product.get("tags")
    return (
        all(
            _is_non_empty_string(product.get(field))
            for field in (
                "description",
                "category",
                "brand",
                "currency",
            )
        )
        and isinstance(supplier, dict)
        and all(
            _is_non_empty_string(supplier.get(field))
            for field in ("id", "name", "country")
        )
        and _is_integer(supplier.get("lead_time_days"), minimum=0)
        and _number(supplier.get("reliability_score"))
        and supplier["reliability_score"] <= 1
        and _number(product.get("unit_price"))
        and isinstance(product.get("discontinued"), bool)
        and _number(product.get("weight_kg"))
        and isinstance(tags, list)
        and all(_is_non_empty_string(tag) for tag in tags)
        and _utc_datetime(product.get("updated_at"))
    )


def _project_detail(product: dict[str, Any]) -> dict[str, Any]:
    supplier = product["supplier"]
    return {
        "external_product_id": product["sku"],
        "name": product["name"],
        "description": product["description"],
        "category": product["category"],
        "brand": product["brand"],
        "supplier": {
            "id": supplier["id"],
            "name": supplier["name"],
            "country": supplier["country"],
            "lead_time_days": supplier["lead_time_days"],
            "reliability_score": supplier["reliability_score"],
        },
        "unit_price": product["unit_price"],
        "currency": product["currency"],
        "discontinued": product["discontinued"],
        "weight_kg": product["weight_kg"],
        "tags": list(product["tags"]),
        "updated_at": product["updated_at"],
    }


def _matches_identifier(product: dict[str, Any], identifier: str) -> bool:
    if identifier.isdecimal():
        return product["id"] == int(identifier)
    return product["sku"].casefold() == identifier.casefold()


async def list_products() -> dict[str, Any]:
    """Return every validated Product API page in deterministic order."""
    limit = 100
    offset = 0
    total: int | None = None
    products: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_skus: set[str] = set()
    while total is None or offset < total:
        result = await product_api.list_products(limit=limit, offset=offset)
        if result.get("status") != "success":
            return result
        payload = result.get("data")
        if not _valid_page(
            payload,
            expected_limit=limit,
            expected_offset=offset,
            expected_count=total,
        ):
            return _INVALID_RESPONSE
        if total is None:
            total = payload["count"]
        for product in payload["results"]:
            product_id = product["id"]
            canonical_sku = product["sku"].casefold()
            if product_id in seen_ids or canonical_sku in seen_skus:
                return _INVALID_RESPONSE
            seen_ids.add(product_id)
            seen_skus.add(canonical_sku)
            products.append(_project_product(product))
        offset += limit
    return {
        "status": "success",
        "data": {"products": products},
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
    if not _valid_detail(product) or not _matches_identifier(product, identifier):
        return _INVALID_RESPONSE

    return {"status": "success", "data": _project_detail(product)}
