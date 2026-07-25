"""Strict input validation for Backoffice product consultation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any


class ProductValidationError(ValueError):
    """A product request does not match the Backoffice contract."""

    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__("Invalid product request.")
        self.details = details


@dataclass(frozen=True)
class ProductListQuery:
    """Validated query parameters ready for the external API."""

    params: dict[str, str]
    limit: int
    offset: int


SORT_VALUES = {
    "name",
    "sku",
    "category",
    "unit_price",
    "updated_at",
    "-name",
    "-sku",
    "-category",
    "-unit_price",
    "-updated_at",
}
LIST_FIELDS = {
    "q",
    "category",
    "supplier_id",
    "include_discontinued",
    "min_price",
    "max_price",
    "limit",
    "offset",
    "sort",
}
INTEGER_PATTERN = re.compile(r"^[0-9]+$")


def _one_value(
    query: dict[str, list[str]],
    field: str,
    errors: dict[str, Any],
) -> str | None:
    values = query.get(field, [])
    if len(values) > 1:
        errors[field] = "Must be provided at most once."
        return None
    return values[0] if values else None


def validate_list_query(
    query: dict[str, list[str]],
) -> ProductListQuery:
    """Validate every supported external catalog parameter strictly."""
    errors: dict[str, Any] = {}
    unexpected = sorted(set(query) - LIST_FIELDS)
    if unexpected:
        errors["unexpected"] = unexpected

    raw_values = {
        field: _one_value(query, field, errors) for field in LIST_FIELDS
    }
    params: dict[str, str] = {
        "include_discontinued": "false",
        "limit": "20",
        "offset": "0",
    }

    for field in ("q", "category", "supplier_id"):
        value = raw_values[field]
        if value is None:
            continue
        normalized = value.strip()
        if not normalized:
            errors[field] = "Must not be empty."
        else:
            params[field] = normalized

    include_discontinued = raw_values["include_discontinued"]
    if include_discontinued is not None:
        if include_discontinued not in {"true", "false"}:
            errors["include_discontinued"] = "Must be true or false."
        else:
            params["include_discontinued"] = include_discontinued

    for field in ("min_price", "max_price"):
        value = raw_values[field]
        if value is None:
            continue
        normalized = value.strip()
        try:
            parsed = Decimal(normalized)
        except (InvalidOperation, ValueError):
            parsed = None
        if parsed is None or not parsed.is_finite():
            errors[field] = "Must be a finite number."
        else:
            params[field] = normalized

    limit = 20
    raw_limit = raw_values["limit"]
    if raw_limit is not None:
        if not INTEGER_PATTERN.fullmatch(raw_limit):
            errors["limit"] = "Must be an integer between 1 and 100."
        else:
            limit = int(raw_limit)
            if not 1 <= limit <= 100:
                errors["limit"] = "Must be an integer between 1 and 100."
            else:
                params["limit"] = str(limit)

    offset = 0
    raw_offset = raw_values["offset"]
    if raw_offset is not None:
        if not INTEGER_PATTERN.fullmatch(raw_offset):
            errors["offset"] = "Must be a non-negative integer."
        else:
            offset = int(raw_offset)
            params["offset"] = str(offset)

    sort = raw_values["sort"]
    if sort is not None:
        if sort not in SORT_VALUES:
            errors["sort"] = "Must be a supported sort value."
        else:
            params["sort"] = sort

    if errors:
        raise ProductValidationError({"fields": errors})
    return ProductListQuery(params=params, limit=limit, offset=offset)


def validate_product_identifier(identifier: object) -> str:
    """Validate and trim only the exterior of a numeric ID or SKU."""
    if not isinstance(identifier, str):
        raise ProductValidationError(
            {"fields": {"external_product_id": "Must be a string."}}
        )
    normalized = identifier.strip()
    if not normalized:
        raise ProductValidationError(
            {
                "fields": {
                    "external_product_id": "Must not be empty.",
                }
            }
        )
    if len(normalized) > 255:
        raise ProductValidationError(
            {
                "fields": {
                    "external_product_id": (
                        "Must not exceed 255 characters."
                    ),
                }
            }
        )
    return normalized


def reject_query_parameters(query: dict[str, list[str]]) -> None:
    """Reject every query parameter on the product detail endpoint."""
    if query:
        raise ProductValidationError(
            {"fields": {"unexpected": sorted(query)}}
        )


__all__ = [
    "ProductListQuery",
    "ProductValidationError",
    "reject_query_parameters",
    "validate_list_query",
    "validate_product_identifier",
]
