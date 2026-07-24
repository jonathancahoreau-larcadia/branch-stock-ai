"""Strict request validation for branch-scoped stock operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backoffice.products.schemas import (
    ProductValidationError,
    validate_product_identifier,
)


class StockValidationError(ValueError):
    """A stock request does not match the documented structure."""

    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__("Invalid stock request.")
        self.details = details


class InvalidQuantityError(ValueError):
    """A supplied movement quantity is not a positive JSON integer."""

    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__("Invalid stock quantity.")
        self.details = details


@dataclass(frozen=True)
class StockListFilters:
    """Validated list filters."""

    available_only: bool


@dataclass(frozen=True)
class StockMovementData:
    """Validated add/remove payload."""

    quantity: int


def validate_list_filters(
    query: dict[str, list[str]],
) -> StockListFilters:
    """Accept only one strict ``available_only`` boolean."""
    unexpected = sorted(set(query) - {"available_only"})
    errors: dict[str, Any] = {}
    if unexpected:
        errors["unexpected"] = unexpected

    values = query.get("available_only", [])
    if len(values) > 1:
        errors["available_only"] = "Must be provided at most once."
        available_only = True
    elif not values:
        available_only = True
    elif values[0] not in {"true", "false"}:
        errors["available_only"] = "Must be true or false."
        available_only = True
    else:
        available_only = values[0] == "true"

    if errors:
        raise StockValidationError({"fields": errors})
    return StockListFilters(available_only=available_only)


def reject_query_parameters(query: dict[str, list[str]]) -> None:
    """Reject every query parameter on detail and movement routes."""
    if query:
        raise StockValidationError(
            {"fields": {"unexpected": sorted(query)}}
        )


def validate_external_product_id(identifier: object) -> str:
    """Reuse the product API's numeric-ID/SKU validation contract."""
    try:
        return validate_product_identifier(identifier)
    except ProductValidationError as error:
        raise StockValidationError(error.details) from error


def validate_movement_payload(payload: object) -> StockMovementData:
    """Require an object containing exactly one positive integer quantity."""
    if not isinstance(payload, dict):
        raise StockValidationError(
            {"fields": {"body": "Must be a JSON object."}}
        )

    unexpected = sorted(set(payload) - {"quantity"})
    if unexpected:
        raise StockValidationError(
            {"fields": {"unexpected": unexpected}}
        )
    if "quantity" not in payload:
        raise StockValidationError(
            {"fields": {"quantity": "This field is required."}}
        )

    quantity = payload["quantity"]
    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity <= 0
    ):
        raise InvalidQuantityError(
            {
                "fields": {
                    "quantity": "Must be a strictly positive integer.",
                }
            }
        )
    return StockMovementData(quantity=quantity)


__all__ = [
    "InvalidQuantityError",
    "StockListFilters",
    "StockMovementData",
    "StockValidationError",
    "reject_query_parameters",
    "validate_external_product_id",
    "validate_list_filters",
    "validate_movement_payload",
]
