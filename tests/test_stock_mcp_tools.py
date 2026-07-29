"""Contract tests for the public Stock MCP tools."""

from __future__ import annotations

import importlib
import inspect
from typing import Any

import pytest


INVALID_BRANCH_ID = {
    "status": "error",
    "error": {
        "code": "INVALID_BRANCH_ID",
        "message": "Branch identifier is invalid.",
    },
}
INVALID_PRODUCT_ID = {
    "status": "error",
    "error": {
        "code": "INVALID_EXTERNAL_PRODUCT_ID",
        "message": "Product identifier is invalid.",
    },
}
INVALID_QUANTITY = {
    "status": "error",
    "error": {
        "code": "INVALID_QUANTITY",
        "message": "Quantity must be a strictly positive integer.",
    },
}
INVALID_SHOPPING_LIST = {
    "status": "error",
    "error": {
        "code": "INVALID_SHOPPING_LIST",
        "message": "Shopping list is invalid.",
    },
}


def _error(code: str, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message}}


def _load_tools():
    return importlib.import_module("stock_mcp_server.tools")


def test_public_surface_contains_exactly_the_four_stock_tools():
    tools = _load_tools()

    assert tools.__all__ == [
        "list_branch_stock",
        "get_stock_for_product",
        "find_branches_with_stock",
        "find_branches_for_shopping_list",
    ]
    assert all(inspect.isfunction(getattr(tools, name)) for name in tools.__all__)
    assert all(
        not inspect.iscoroutinefunction(getattr(tools, name)) for name in tools.__all__
    )


def test_new_tools_have_the_contractual_public_signatures():
    tools = _load_tools()

    assert list(inspect.signature(tools.find_branches_with_stock).parameters) == [
        "external_product_id",
        "quantity",
    ]
    assert list(
        inspect.signature(tools.find_branches_for_shopping_list).parameters
    ) == ["items"]


def test_public_surface_has_no_arbitrary_sql_tool():
    tools = _load_tools()

    assert not hasattr(tools, "execute_sql")


@pytest.mark.parametrize("branch_id", [None, 0, -1, True, 1.5, "1"])
def test_list_branch_stock_rejects_invalid_ids_without_repository_call(
    monkeypatch, branch_id
):
    tools = _load_tools()
    calls: list[Any] = []

    def fail_repository(value: Any) -> None:
        calls.append(value)
        raise AssertionError("invalid branch IDs must not reach the repository")

    monkeypatch.setattr(tools.repository, "fetch_branch_stock", fail_repository)

    assert tools.list_branch_stock(branch_id) == INVALID_BRANCH_ID
    assert calls == []


def test_list_branch_stock_projects_a_known_branch_and_hides_unapproved_fields(monkeypatch):
    tools = _load_tools()
    calls: list[int] = []

    def fake_repository(branch_id: int) -> dict[str, Any]:
        calls.append(branch_id)
        return {
            "branch_id": 2,
            "branch_name": "Toulon",
            "private_branch_field": "must not be exposed",
            "stocks": [
                {
                    "external_product_id": "product-123",
                    "quantity": 8,
                    "stock_id": 17,
                },
            ],
        }

    monkeypatch.setattr(tools.repository, "fetch_branch_stock", fake_repository)

    assert tools.list_branch_stock(2) == {
        "status": "success",
        "data": {
            "branch_id": 2,
            "branch_name": "Toulon",
            "stocks": [
                {"external_product_id": "product-123", "quantity": 8},
            ],
        },
    }
    assert calls == [2]


def test_list_branch_stock_returns_success_for_known_branch_without_positive_stock(
    monkeypatch,
):
    tools = _load_tools()
    calls: list[int] = []

    def fake_repository(branch_id: int) -> dict[str, Any]:
        calls.append(branch_id)
        return {"branch_id": 3, "branch_name": "Paris", "stocks": []}

    monkeypatch.setattr(tools.repository, "fetch_branch_stock", fake_repository)

    assert tools.list_branch_stock(3) == {
        "status": "success",
        "data": {"branch_id": 3, "branch_name": "Paris", "stocks": []},
    }
    assert calls == [3]


def test_list_branch_stock_returns_not_found_for_unknown_branch(monkeypatch):
    tools = _load_tools()
    monkeypatch.setattr(tools.repository, "fetch_branch_stock", lambda _branch_id: None)

    assert tools.list_branch_stock(999) == {"status": "not_found", "data": None}


@pytest.mark.parametrize(
    "repository_error",
    [
        "StockRepositoryConfigurationError",
        "StockRepositoryTimeoutError",
        "StockRepositoryUnavailableError",
        "StockRepositoryError",
    ],
)
def test_list_branch_stock_maps_repository_errors_to_safe_mcp_errors(
    monkeypatch, repository_error
):
    tools = _load_tools()
    error_type = getattr(tools.repository, repository_error)

    def fail_repository(_branch_id: int) -> None:
        raise error_type("dsn=secret; SELECT password")

    monkeypatch.setattr(tools.repository, "fetch_branch_stock", fail_repository)
    result = tools.list_branch_stock(2)
    expected_code = {
        "StockRepositoryConfigurationError": "STOCK_DATABASE_INVALID_CONFIGURATION",
        "StockRepositoryTimeoutError": "STOCK_DATABASE_TIMEOUT",
        "StockRepositoryUnavailableError": "STOCK_DATABASE_UNAVAILABLE",
        "StockRepositoryError": "STOCK_DATABASE_ERROR",
    }[repository_error]

    assert result == _error(
        expected_code,
        {
            "StockRepositoryConfigurationError": "Stock database configuration is invalid.",
            "StockRepositoryTimeoutError": "Stock database request timed out.",
            "StockRepositoryUnavailableError": "Stock database is unavailable.",
            "StockRepositoryError": "Stock database query failed.",
        }[repository_error],
    )
    assert "secret" not in repr(result)


@pytest.mark.parametrize(
    "identifier", [None, 123, True, "", "   ", "x" * 256, f" {'x' * 256} "]
)
def test_get_stock_for_product_rejects_invalid_ids_without_repository_call(
    monkeypatch, identifier
):
    tools = _load_tools()
    calls: list[Any] = []

    def fail_repository(value: Any) -> None:
        calls.append(value)
        raise AssertionError("invalid product IDs must not reach the repository")

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fail_repository)

    assert tools.get_stock_for_product(identifier) == INVALID_PRODUCT_ID
    assert calls == []


def test_get_stock_for_product_strips_identifier_and_keeps_zero_quantity(monkeypatch):
    tools = _load_tools()
    calls: list[str] = []

    def fake_repository(identifier: str) -> list[dict[str, Any]]:
        calls.append(identifier)
        return [
            {
                "branch_id": 2,
                "branch_name": "Toulon",
                "quantity": 0,
                "private_field": "must not be exposed",
            },
            {"branch_id": 7, "branch_name": "Toulouse", "quantity": 4},
        ]

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fake_repository)

    assert tools.get_stock_for_product("  product-123  ") == {
        "status": "success",
        "data": {
            "external_product_id": "product-123",
            "branches": [
                {"branch_id": 2, "branch_name": "Toulon", "quantity": 0},
                {"branch_id": 7, "branch_name": "Toulouse", "quantity": 4},
            ],
        },
    }
    assert calls == ["product-123"]


def test_get_stock_for_product_returns_success_for_empty_stock(monkeypatch):
    tools = _load_tools()
    monkeypatch.setattr(tools.repository, "fetch_product_stock", lambda _id: [])

    assert tools.get_stock_for_product("missing-product") == {
        "status": "success",
        "data": {"external_product_id": "missing-product", "branches": []},
    }


@pytest.mark.parametrize(
    ("repository_error", "expected"),
    [
        (
            "StockRepositoryConfigurationError",
            _error(
                "STOCK_DATABASE_INVALID_CONFIGURATION",
                "Stock database configuration is invalid.",
            ),
        ),
        (
            "StockRepositoryTimeoutError",
            _error("STOCK_DATABASE_TIMEOUT", "Stock database request timed out."),
        ),
        (
            "StockRepositoryUnavailableError",
            _error("STOCK_DATABASE_UNAVAILABLE", "Stock database is unavailable."),
        ),
        (
            "StockRepositoryError",
            _error("STOCK_DATABASE_ERROR", "Stock database query failed."),
        ),
    ],
)
def test_get_stock_for_product_maps_repository_errors_without_leaking_details(
    monkeypatch, repository_error, expected
):
    tools = _load_tools()
    error_type = getattr(tools.repository, repository_error)

    def fail_repository(_identifier: str) -> None:
        raise error_type("dsn=secret; SELECT password")

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fail_repository)

    assert tools.get_stock_for_product("product-123") == expected


@pytest.mark.parametrize(
    ("identifier", "quantity", "expected"),
    [
        (None, 1, INVALID_PRODUCT_ID),
        (None, None, INVALID_PRODUCT_ID),
        (None, 0, INVALID_PRODUCT_ID),
        (True, 0, INVALID_PRODUCT_ID),
        ("", 1, INVALID_PRODUCT_ID),
        ("", None, INVALID_PRODUCT_ID),
        ("   ", 1, INVALID_PRODUCT_ID),
        ("x" * 256, 1, INVALID_PRODUCT_ID),
        (f" {'x' * 256} ", 1, INVALID_PRODUCT_ID),
        ("x" * 256, -1, INVALID_PRODUCT_ID),
        ("product-123", None, INVALID_QUANTITY),
        ("product-123", 0, INVALID_QUANTITY),
        ("product-123", -1, INVALID_QUANTITY),
        ("product-123", 1.5, INVALID_QUANTITY),
        ("product-123", "1", INVALID_QUANTITY),
        ("product-123", True, INVALID_QUANTITY),
    ],
)
def test_find_branches_with_stock_validates_before_repository_call(
    monkeypatch, identifier, quantity, expected
):
    tools = _load_tools()
    calls: list[Any] = []

    def fail_repository(value: Any) -> None:
        calls.append(value)
        raise AssertionError("invalid input must not reach the repository")

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fail_repository)

    assert tools.find_branches_with_stock(identifier, quantity) == expected
    assert calls == []


def test_find_branches_with_stock_projects_inclusive_matches_and_normalizes_id(
    monkeypatch,
):
    tools = _load_tools()
    calls: list[str] = []

    def fake_repository(identifier: str) -> list[dict[str, Any]]:
        calls.append(identifier)
        return [
            {
                "branch_id": 4,
                "branch_name": "Paris",
                "quantity": 10,
                "private_branch_field": "not public",
            },
            {"branch_id": 2, "branch_name": "Toulon", "quantity": 3},
            {"branch_id": 7, "branch_name": "Toulouse", "quantity": 2},
        ]

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fake_repository)

    assert tools.find_branches_with_stock("  product-123  ", 3) == {
        "status": "success",
        "data": {
            "external_product_id": "product-123",
            "requested_quantity": 3,
            "branches": [
                {"branch_id": 4, "branch_name": "Paris", "available_quantity": 10},
                {"branch_id": 2, "branch_name": "Toulon", "available_quantity": 3},
            ],
        },
    }
    assert calls == ["product-123"]


def test_find_branches_with_stock_returns_success_for_no_matching_branch(monkeypatch):
    tools = _load_tools()
    calls: list[str] = []

    def fake_repository(identifier: str) -> list[dict[str, Any]]:
        calls.append(identifier)
        return []

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fake_repository)

    assert tools.find_branches_with_stock("product-123", 1) == {
        "status": "success",
        "data": {
            "external_product_id": "product-123",
            "requested_quantity": 1,
            "branches": [],
        },
    }
    assert calls == ["product-123"]


@pytest.mark.parametrize(
    ("repository_error", "expected_code", "expected_message"),
    [
        (
            "StockRepositoryConfigurationError",
            "STOCK_DATABASE_INVALID_CONFIGURATION",
            "Stock database configuration is invalid.",
        ),
        (
            "StockRepositoryTimeoutError",
            "STOCK_DATABASE_TIMEOUT",
            "Stock database request timed out.",
        ),
        (
            "StockRepositoryUnavailableError",
            "STOCK_DATABASE_UNAVAILABLE",
            "Stock database is unavailable.",
        ),
        (
            "StockRepositoryError",
            "STOCK_DATABASE_ERROR",
            "Stock database query failed.",
        ),
    ],
)
def test_find_branches_with_stock_maps_repository_errors_without_leaking_details(
    monkeypatch, repository_error, expected_code, expected_message
):
    tools = _load_tools()
    error_type = getattr(tools.repository, repository_error)

    def fail_repository(_identifier: str) -> None:
        raise error_type("dsn=secret; SELECT password")

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fail_repository)

    result = tools.find_branches_with_stock("product-123", 2)

    assert result == _error(expected_code, expected_message)
    assert "secret" not in repr(result)
    assert "SELECT" not in repr(result)


@pytest.mark.parametrize(
    "items",
    [
        None,
        {},
        (),
        [],
        [None],
        [{}],
        [{"external_product_id": "product-123"}],
        [{"quantity": 1}],
        [{"external_product_id": "product-123", "quantity": 1}, {}],
    ],
)
def test_shopping_list_rejects_invalid_containers_before_any_repository_call(
    monkeypatch, items
):
    tools = _load_tools()
    calls: list[Any] = []

    def fail_repository(value: Any) -> None:
        calls.append(value)
        raise AssertionError("invalid shopping lists must not reach the repository")

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fail_repository)

    assert tools.find_branches_for_shopping_list(items) == INVALID_SHOPPING_LIST
    assert calls == []


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([{"external_product_id": None, "quantity": 1}], INVALID_PRODUCT_ID),
        ([{"external_product_id": 123, "quantity": 1}], INVALID_PRODUCT_ID),
        ([{"external_product_id": True, "quantity": 1}], INVALID_PRODUCT_ID),
        ([{"external_product_id": "x" * 256, "quantity": 1}], INVALID_PRODUCT_ID),
        ([{"external_product_id": f" {'x' * 256} ", "quantity": 1}], INVALID_PRODUCT_ID),
        ([{"external_product_id": " ", "quantity": 1}], INVALID_PRODUCT_ID),
        ([{"external_product_id": "product-123", "quantity": None}], INVALID_QUANTITY),
        ([{"external_product_id": "product-123", "quantity": 0}], INVALID_QUANTITY),
        ([{"external_product_id": "product-123", "quantity": -1}], INVALID_QUANTITY),
        ([{"external_product_id": "product-123", "quantity": 1.5}], INVALID_QUANTITY),
        ([{"external_product_id": "product-123", "quantity": "1"}], INVALID_QUANTITY),
        ([{"external_product_id": "product-123", "quantity": True}], INVALID_QUANTITY),
    ],
)
def test_shopping_list_rejects_invalid_item_values_before_any_repository_call(
    monkeypatch, items, expected
):
    tools = _load_tools()
    calls: list[Any] = []

    def fail_repository(value: Any) -> None:
        calls.append(value)
        raise AssertionError("invalid shopping-list items must not reach the repository")

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fail_repository)

    assert tools.find_branches_for_shopping_list(items) == expected
    assert calls == []


@pytest.mark.parametrize(
    "items",
    [
        [
            {"external_product_id": "product-1", "quantity": 1},
            {"external_product_id": 123, "quantity": 1},
        ],
        [
            {"external_product_id": "product-1", "quantity": 1},
            {"external_product_id": True, "quantity": 1},
        ],
        [
            {"external_product_id": "product-1", "quantity": 1},
            {"external_product_id": "x" * 256, "quantity": 1},
        ],
        [
            {"external_product_id": "product-1", "quantity": 1},
            {"external_product_id": f" {'x' * 256} ", "quantity": 1},
        ],
        [
            {"external_product_id": "product-1", "quantity": 1},
            {"external_product_id": "", "quantity": 1},
        ],
        [
            {"external_product_id": "product-1", "quantity": 1},
            {"external_product_id": "product-2", "quantity": 0},
        ],
    ],
)
def test_shopping_list_validates_invalid_values_after_valid_item_before_repository(
    monkeypatch, items
):
    tools = _load_tools()
    calls: list[Any] = []

    def fail_repository(value: Any) -> None:
        calls.append(value)
        raise AssertionError("the whole list must be validated before repository calls")

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fail_repository)

    expected = (
        INVALID_QUANTITY
        if items[-1]["external_product_id"] == "product-2"
        else INVALID_PRODUCT_ID
    )
    assert tools.find_branches_for_shopping_list(items) == expected
    assert calls == []


def test_shopping_list_merges_normalized_duplicates_and_calls_repository_once_per_id(
    monkeypatch,
):
    tools = _load_tools()
    calls: list[str] = []
    stock_by_product = {
        "product-1": [
            {"branch_id": 2, "branch_name": "Toulon", "quantity": 5, "private": "x"}
        ],
        "product-2": [
            {"branch_id": 7, "branch_name": "Toulouse", "quantity": 1}
        ],
    }

    def fake_repository(identifier: str) -> list[dict[str, Any]]:
        calls.append(identifier)
        return stock_by_product[identifier]

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fake_repository)

    assert tools.find_branches_for_shopping_list(
        [
            {"external_product_id": " product-1 ", "quantity": 2},
            {"external_product_id": "product-2", "quantity": 1, "ignored": True},
            {"external_product_id": "product-1", "quantity": 3},
        ]
    ) == {
        "status": "success",
        "data": {
            "complete": True,
            "strategy": "multiple_branches",
            "visits": [
                {
                    "branch_id": 2,
                    "branch_name": "Toulon",
                    "items": [
                        {
                            "external_product_id": "product-1",
                            "requested_quantity": 5,
                            "available_quantity": 5,
                        }
                    ],
                },
                {
                    "branch_id": 7,
                    "branch_name": "Toulouse",
                    "items": [
                        {
                            "external_product_id": "product-2",
                            "requested_quantity": 1,
                            "available_quantity": 1,
                        }
                    ],
                },
            ],
            "missing_items": [],
        },
    }
    assert calls == ["product-1", "product-2"]


def test_shopping_list_prefers_the_first_single_branch_and_preserves_item_order(
    monkeypatch,
):
    tools = _load_tools()
    stock_by_product = {
        "product-1": [
            {"branch_id": 2, "branch_name": "Toulon", "quantity": 8},
            {"branch_id": 4, "branch_name": "Paris", "quantity": 4},
        ],
        "product-2": [
            {"branch_id": 2, "branch_name": "Toulon", "quantity": 6, "secret": "x"}
        ],
    }
    monkeypatch.setattr(
        tools.repository,
        "fetch_product_stock",
        lambda identifier: stock_by_product[identifier],
    )

    result = tools.find_branches_for_shopping_list(
        [
            {"external_product_id": "product-2", "quantity": 5},
            {"external_product_id": "product-1", "quantity": 4},
        ]
    )

    assert result == {
        "status": "success",
        "data": {
            "complete": True,
            "strategy": "single_branch",
            "visits": [
                {
                    "branch_id": 2,
                    "branch_name": "Toulon",
                    "items": [
                        {
                            "external_product_id": "product-2",
                            "requested_quantity": 5,
                            "available_quantity": 6,
                        },
                        {
                            "external_product_id": "product-1",
                            "requested_quantity": 4,
                            "available_quantity": 8,
                        },
                    ],
                }
            ],
            "missing_items": [],
        },
    }


def test_shopping_list_breaks_single_branch_ties_by_branch_name_then_id(monkeypatch):
    tools = _load_tools()
    stock_by_product = {
        "product-1": [
            {"branch_id": 3, "branch_name": "Beta", "quantity": 5},
            {"branch_id": 9, "branch_name": "Beta", "quantity": 5},
        ],
        "product-2": [
            {"branch_id": 3, "branch_name": "Beta", "quantity": 2},
            {"branch_id": 9, "branch_name": "Beta", "quantity": 2},
        ],
    }
    monkeypatch.setattr(
        tools.repository,
        "fetch_product_stock",
        lambda identifier: stock_by_product[identifier],
    )

    assert tools.find_branches_for_shopping_list(
        [
            {"external_product_id": "product-1", "quantity": 4},
            {"external_product_id": "product-2", "quantity": 2},
        ]
    ) == {
        "status": "success",
        "data": {
            "complete": True,
            "strategy": "single_branch",
            "visits": [
                {
                    "branch_id": 3,
                    "branch_name": "Beta",
                    "items": [
                        {
                            "external_product_id": "product-1",
                            "requested_quantity": 4,
                            "available_quantity": 5,
                        },
                        {
                            "external_product_id": "product-2",
                            "requested_quantity": 2,
                            "available_quantity": 2,
                        },
                    ],
                }
            ],
            "missing_items": [],
        },
    }


def test_shopping_list_assigns_shared_item_to_first_selected_branch(monkeypatch):
    tools = _load_tools()
    stock_by_product = {
        "shared": [
            {"branch_id": 2, "branch_name": "Alpha", "quantity": 8},
            {"branch_id": 3, "branch_name": "Beta", "quantity": 8},
        ],
        "alpha-only": [
            {"branch_id": 2, "branch_name": "Alpha", "quantity": 5}
        ],
        "beta-only": [
            {"branch_id": 3, "branch_name": "Beta", "quantity": 5}
        ],
    }
    monkeypatch.setattr(
        tools.repository,
        "fetch_product_stock",
        lambda identifier: stock_by_product[identifier],
    )

    assert tools.find_branches_for_shopping_list(
        [
            {"external_product_id": "shared", "quantity": 4},
            {"external_product_id": "alpha-only", "quantity": 2},
            {"external_product_id": "beta-only", "quantity": 3},
        ]
    ) == {
        "status": "success",
        "data": {
            "complete": True,
            "strategy": "multiple_branches",
            "visits": [
                {
                    "branch_id": 2,
                    "branch_name": "Alpha",
                    "items": [
                        {
                            "external_product_id": "shared",
                            "requested_quantity": 4,
                            "available_quantity": 8,
                        },
                        {
                            "external_product_id": "alpha-only",
                            "requested_quantity": 2,
                            "available_quantity": 5,
                        },
                    ],
                },
                {
                    "branch_id": 3,
                    "branch_name": "Beta",
                    "items": [
                        {
                            "external_product_id": "beta-only",
                            "requested_quantity": 3,
                            "available_quantity": 5,
                        }
                    ],
                },
            ],
            "missing_items": [],
        },
    }


def test_shopping_list_uses_minimal_deterministic_multi_branch_plan(monkeypatch):
    tools = _load_tools()
    stock_by_product = {
        "product-1": [
            {"branch_id": 2, "branch_name": "Alpha", "quantity": 3},
            {"branch_id": 20, "branch_name": "Zulu", "quantity": 3},
        ],
        "product-2": [
            {"branch_id": 3, "branch_name": "Beta", "quantity": 2},
            {"branch_id": 7, "branch_name": "Beta", "quantity": 2},
        ],
    }
    monkeypatch.setattr(
        tools.repository,
        "fetch_product_stock",
        lambda identifier: stock_by_product[identifier],
    )

    assert tools.find_branches_for_shopping_list(
        [
            {"external_product_id": "product-1", "quantity": 3},
            {"external_product_id": "product-2", "quantity": 2},
        ]
    ) == {
        "status": "success",
        "data": {
            "complete": True,
            "strategy": "multiple_branches",
            "visits": [
                {
                    "branch_id": 2,
                    "branch_name": "Alpha",
                    "items": [
                        {
                            "external_product_id": "product-1",
                            "requested_quantity": 3,
                            "available_quantity": 3,
                        }
                    ],
                },
                {
                    "branch_id": 3,
                    "branch_name": "Beta",
                    "items": [
                        {
                            "external_product_id": "product-2",
                            "requested_quantity": 2,
                            "available_quantity": 2,
                        }
                    ],
                },
            ],
            "missing_items": [],
        },
    }


def test_shopping_list_does_not_split_one_item_between_branches(monkeypatch):
    tools = _load_tools()
    monkeypatch.setattr(
        tools.repository,
        "fetch_product_stock",
        lambda _identifier: [
            {"branch_id": 2, "branch_name": "Alpha", "quantity": 6},
            {"branch_id": 3, "branch_name": "Beta", "quantity": 4},
        ],
    )

    assert tools.find_branches_for_shopping_list(
        [{"external_product_id": "product-1", "quantity": 10}]
    ) == {
        "status": "success",
        "data": {
            "complete": False,
            "strategy": "unavailable",
            "visits": [],
            "missing_items": [
                {"external_product_id": "product-1", "missing_quantity": 4}
            ],
        },
    }


def test_shopping_list_reports_unavailable_items_in_normalized_order(monkeypatch):
    tools = _load_tools()
    stock_by_product = {
        "product-1": [
            {"branch_id": 2, "branch_name": "Alpha", "quantity": 2}
        ],
        "product-2": [],
    }
    calls: list[str] = []

    def fake_repository(identifier: str) -> list[dict[str, Any]]:
        calls.append(identifier)
        return stock_by_product[identifier]

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fake_repository)

    assert tools.find_branches_for_shopping_list(
        [
            {"external_product_id": " product-1 ", "quantity": 5},
            {"external_product_id": "product-2", "quantity": 3},
        ]
    ) == {
        "status": "success",
        "data": {
            "complete": False,
            "strategy": "unavailable",
            "visits": [],
            "missing_items": [
                {"external_product_id": "product-1", "missing_quantity": 3},
                {"external_product_id": "product-2", "missing_quantity": 3},
            ],
        },
    }
    assert calls == ["product-1", "product-2"]


def test_shopping_list_missing_items_excludes_available_items(monkeypatch):
    tools = _load_tools()
    stock_by_product = {
        "available-product": [
            {"branch_id": 2, "branch_name": "Alpha", "quantity": 5}
        ],
        "missing-product": [
            {"branch_id": 3, "branch_name": "Beta", "quantity": 1}
        ],
    }
    monkeypatch.setattr(
        tools.repository,
        "fetch_product_stock",
        lambda identifier: stock_by_product[identifier],
    )

    assert tools.find_branches_for_shopping_list(
        [
            {"external_product_id": "available-product", "quantity": 5},
            {"external_product_id": "missing-product", "quantity": 2},
        ]
    ) == {
        "status": "success",
        "data": {
            "complete": False,
            "strategy": "unavailable",
            "visits": [],
            "missing_items": [
                {"external_product_id": "missing-product", "missing_quantity": 1}
            ],
        },
    }


@pytest.mark.parametrize(
    ("repository_error", "expected"),
    [
        (
            "StockRepositoryConfigurationError",
            _error(
                "STOCK_DATABASE_INVALID_CONFIGURATION",
                "Stock database configuration is invalid.",
            ),
        ),
        (
            "StockRepositoryTimeoutError",
            _error("STOCK_DATABASE_TIMEOUT", "Stock database request timed out."),
        ),
        (
            "StockRepositoryUnavailableError",
            _error("STOCK_DATABASE_UNAVAILABLE", "Stock database is unavailable."),
        ),
        (
            "StockRepositoryError",
            _error("STOCK_DATABASE_ERROR", "Stock database query failed."),
        ),
    ],
)
def test_shopping_list_maps_repository_errors_without_partial_result(
    monkeypatch, repository_error, expected
):
    tools = _load_tools()
    error_type = getattr(tools.repository, repository_error)
    calls: list[str] = []

    def fake_repository(identifier: str) -> list[dict[str, Any]]:
        calls.append(identifier)
        if identifier == "product-2":
            raise error_type("dsn=secret; SELECT password")
        return [{"branch_id": 2, "branch_name": "Alpha", "quantity": 5}]

    monkeypatch.setattr(tools.repository, "fetch_product_stock", fake_repository)

    result = tools.find_branches_for_shopping_list(
        [
            {"external_product_id": "product-1", "quantity": 1},
            {"external_product_id": "product-2", "quantity": 1},
        ]
    )

    assert result == expected
    assert calls == ["product-1", "product-2"]
    assert "secret" not in repr(result)
    assert "SELECT" not in repr(result)
