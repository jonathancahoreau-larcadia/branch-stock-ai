"""Public read-only Stock MCP tools."""

from __future__ import annotations

from itertools import combinations
from typing import Any

from . import repository


__all__ = [
    "list_branch_stock",
    "get_stock_for_product",
    "find_branches_with_stock",
    "find_branches_for_shopping_list",
]

_INVALID_BRANCH_ID = {
    "status": "error",
    "error": {
        "code": "INVALID_BRANCH_ID",
        "message": "Branch identifier is invalid.",
    },
}

_INVALID_EXTERNAL_PRODUCT_ID = {
    "status": "error",
    "error": {
        "code": "INVALID_EXTERNAL_PRODUCT_ID",
        "message": "Product identifier is invalid.",
    },
}

_INVALID_QUANTITY = {
    "status": "error",
    "error": {
        "code": "INVALID_QUANTITY",
        "message": "Quantity must be a strictly positive integer.",
    },
}

_INVALID_SHOPPING_LIST = {
    "status": "error",
    "error": {
        "code": "INVALID_SHOPPING_LIST",
        "message": "Shopping list is invalid.",
    },
}

_REPOSITORY_ERRORS = (
    (
        repository.StockRepositoryConfigurationError,
        "STOCK_DATABASE_INVALID_CONFIGURATION",
        "Stock database configuration is invalid.",
    ),
    (
        repository.StockRepositoryTimeoutError,
        "STOCK_DATABASE_TIMEOUT",
        "Stock database request timed out.",
    ),
    (
        repository.StockRepositoryUnavailableError,
        "STOCK_DATABASE_UNAVAILABLE",
        "Stock database is unavailable.",
    ),
    (
        repository.StockRepositoryError,
        "STOCK_DATABASE_ERROR",
        "Stock database query failed.",
    ),
)


def _normalize_external_product_id(external_product_id: Any) -> str | None:
    if not isinstance(external_product_id, str):
        return None

    normalized_id = external_product_id.strip()
    if not normalized_id or len(normalized_id) > 255:
        return None
    return normalized_id


def _is_valid_quantity(quantity: Any) -> bool:
    return (
        not isinstance(quantity, bool)
        and isinstance(quantity, int)
        and quantity > 0
    )


def _repository_error_response(error: RuntimeError) -> dict[str, Any]:
    for error_type, code, message in _REPOSITORY_ERRORS:
        if isinstance(error, error_type):
            return {
                "status": "error",
                "error": {"code": code, "message": message},
            }
    return {
        "status": "error",
        "error": {
            "code": "STOCK_DATABASE_ERROR",
            "message": "Stock database query failed.",
        },
    }


def list_branch_stock(branch_id: int) -> dict[str, Any]:
    """Return the strictly positive stock quantities for one branch."""

    if isinstance(branch_id, bool) or not isinstance(branch_id, int) or branch_id <= 0:
        return _INVALID_BRANCH_ID

    try:
        branch = repository.fetch_branch_stock(branch_id)
    except (
        repository.StockRepositoryConfigurationError,
        repository.StockRepositoryTimeoutError,
        repository.StockRepositoryUnavailableError,
        repository.StockRepositoryError,
    ) as error:
        return _repository_error_response(error)

    if branch is None:
        return {"status": "not_found", "data": None}

    return {
        "status": "success",
        "data": {
            "branch_id": branch["branch_id"],
            "branch_name": branch["branch_name"],
            "stocks": [
                {
                    "external_product_id": stock["external_product_id"],
                    "quantity": stock["quantity"],
                }
                for stock in branch["stocks"]
            ],
        },
    }


def get_stock_for_product(external_product_id: str) -> dict[str, Any]:
    """Return all known branch quantities for one external product."""

    normalized_id = _normalize_external_product_id(external_product_id)
    if normalized_id is None:
        return _INVALID_EXTERNAL_PRODUCT_ID

    try:
        branches = repository.fetch_product_stock(normalized_id)
    except (
        repository.StockRepositoryConfigurationError,
        repository.StockRepositoryTimeoutError,
        repository.StockRepositoryUnavailableError,
        repository.StockRepositoryError,
    ) as error:
        return _repository_error_response(error)

    return {
        "status": "success",
        "data": {
            "external_product_id": normalized_id,
            "branches": [
                {
                    "branch_id": branch["branch_id"],
                    "branch_name": branch["branch_name"],
                    "quantity": branch["quantity"],
                }
                for branch in branches
            ],
        },
    }


def find_branches_with_stock(
    external_product_id: str,
    quantity: int,
) -> dict[str, Any]:
    """Return branches able to supply the complete requested quantity."""

    normalized_id = _normalize_external_product_id(external_product_id)
    if normalized_id is None:
        return _INVALID_EXTERNAL_PRODUCT_ID
    if not _is_valid_quantity(quantity):
        return _INVALID_QUANTITY

    try:
        branches = repository.fetch_product_stock(normalized_id)
    except (
        repository.StockRepositoryConfigurationError,
        repository.StockRepositoryTimeoutError,
        repository.StockRepositoryUnavailableError,
        repository.StockRepositoryError,
    ) as error:
        return _repository_error_response(error)

    return {
        "status": "success",
        "data": {
            "external_product_id": normalized_id,
            "requested_quantity": quantity,
            "branches": [
                {
                    "branch_id": branch["branch_id"],
                    "branch_name": branch["branch_name"],
                    "available_quantity": branch["quantity"],
                }
                for branch in branches
                if branch["quantity"] >= quantity
            ],
        },
    }


def find_branches_for_shopping_list(items: list[dict]) -> dict[str, Any]:
    """Return a deterministic minimal branch plan for a shopping list."""

    if not isinstance(items, list) or not items:
        return _INVALID_SHOPPING_LIST
    if any(
        not isinstance(item, dict)
        or "external_product_id" not in item
        or "quantity" not in item
        for item in items
    ):
        return _INVALID_SHOPPING_LIST

    requested_quantities: dict[str, int] = {}
    for item in items:
        normalized_id = _normalize_external_product_id(
            item["external_product_id"]
        )
        if normalized_id is None:
            return _INVALID_EXTERNAL_PRODUCT_ID

        quantity = item["quantity"]
        if not _is_valid_quantity(quantity):
            return _INVALID_QUANTITY

        requested_quantities[normalized_id] = (
            requested_quantities.get(normalized_id, 0) + quantity
        )

    stock_by_product: dict[str, list[dict[str, Any]]] = {}
    try:
        for external_product_id in requested_quantities:
            stock_by_product[external_product_id] = (
                repository.fetch_product_stock(external_product_id)
            )
    except (
        repository.StockRepositoryConfigurationError,
        repository.StockRepositoryTimeoutError,
        repository.StockRepositoryUnavailableError,
        repository.StockRepositoryError,
    ) as error:
        return _repository_error_response(error)

    missing_items = []
    for external_product_id, requested_quantity in requested_quantities.items():
        best_available_quantity = max(
            (
                branch["quantity"]
                for branch in stock_by_product[external_product_id]
            ),
            default=0,
        )
        if best_available_quantity < requested_quantity:
            missing_items.append(
                {
                    "external_product_id": external_product_id,
                    "missing_quantity": (
                        requested_quantity - best_available_quantity
                    ),
                }
            )

    if missing_items:
        return {
            "status": "success",
            "data": {
                "complete": False,
                "strategy": "unavailable",
                "visits": [],
                "missing_items": missing_items,
            },
        }

    branch_stock: dict[tuple[str, int], dict[str, int]] = {}
    for external_product_id, branches in stock_by_product.items():
        for branch in branches:
            branch_key = (branch["branch_name"], branch["branch_id"])
            branch_stock.setdefault(branch_key, {})[external_product_id] = branch[
                "quantity"
            ]

    ordered_branches = sorted(branch_stock)
    selected_branches: tuple[tuple[str, int], ...] | None = None
    for branch_count in range(1, len(ordered_branches) + 1):
        for candidate_branches in combinations(ordered_branches, branch_count):
            if all(
                any(
                    branch_stock[branch].get(external_product_id, 0)
                    >= requested_quantity
                    for branch in candidate_branches
                )
                for external_product_id, requested_quantity
                in requested_quantities.items()
            ):
                selected_branches = candidate_branches
                break
        if selected_branches is not None:
            break

    visits_by_branch = {
        branch: {
            "branch_id": branch[1],
            "branch_name": branch[0],
            "items": [],
        }
        for branch in selected_branches or ()
    }
    for external_product_id, requested_quantity in requested_quantities.items():
        for branch in selected_branches or ():
            available_quantity = branch_stock[branch].get(external_product_id, 0)
            if available_quantity >= requested_quantity:
                visits_by_branch[branch]["items"].append(
                    {
                        "external_product_id": external_product_id,
                        "requested_quantity": requested_quantity,
                        "available_quantity": available_quantity,
                    }
                )
                break

    return {
        "status": "success",
        "data": {
            "complete": True,
            "strategy": (
                "single_branch"
                if selected_branches is not None and len(selected_branches) == 1
                else "multiple_branches"
            ),
            "visits": list(visits_by_branch.values()),
            "missing_items": [],
        },
    }
