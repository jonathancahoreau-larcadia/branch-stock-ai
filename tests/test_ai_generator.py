"""Contract tests for deterministic MCP-grounded response generation."""

from __future__ import annotations

import copy
import importlib
import inspect
import json
import socket

import pytest


PARTIAL_ANSWER = (
    "Some MCP information is available, but it is insufficient for a complete "
    "grounded answer."
)
UNAVAILABLE_RESPONSE = {
    "status": "unavailable",
    "answer": "I do not have enough information to answer this question.",
    "data": {},
}
SUPPORTED_TYPES = (
    "product_details",
    "product_availability",
    "branch_inventory",
    "shopping_list",
)


@pytest.fixture(autouse=True)
def forbid_real_sockets(monkeypatch):
    """The generator contract is pure and must never open a real socket."""

    def fail_if_socket_is_opened(*_args, **_kwargs):
        raise AssertionError("real network access is forbidden in generator tests")

    monkeypatch.setattr(socket, "socket", fail_if_socket_is_opened)


@pytest.fixture
def generator():
    return importlib.import_module("ai_service.generator")


def envelope(data, *, status="success", **extra):
    result = {"status": status, "data": data}
    result.update(extra)
    return result


def details_data(*, extra=True):
    result = {"external_product_id": "product-123", "name": "Example product"}
    if extra:
        result.update({"description": "DO_NOT_LEAK_DETAIL", "price": 999})
    return result


def products_data(*, extra=True):
    product = {"external_product_id": "product-123", "name": "Example product"}
    if extra:
        product["category"] = "DO_NOT_LEAK_CATEGORY"
    result = {"products": [product]}
    if extra:
        result["metadata"] = "DO_NOT_LEAK_METADATA"
    return result


def stock_for_product_data(*, product_id="product-123", extra=True, branches=None):
    if branches is None:
        branches = [
            {
                "branch_id": 7,
                "branch_name": "Central branch",
                "quantity": 4,
                "branch_metadata": "DO_NOT_LEAK_PRODUCT_BRANCH",
            }
        ]
    result = {"external_product_id": product_id, "branches": branches}
    if extra:
        result["last_updated"] = "DO_NOT_LEAK_TIMESTAMP"
    return result


def branch_stock_data(*, extra=True, stocks=None):
    if stocks is None:
        stocks = [
            {
                "external_product_id": "product-123",
                "quantity": 4,
                "stock_metadata": "DO_NOT_LEAK_STOCK_ITEM",
            }
        ]
    result = {"branch_id": 7, "branch_name": "Central branch", "stocks": stocks}
    if extra:
        result.update(
            {
                "address": "DO_NOT_LEAK_ADDRESS",
                "branch_metadata": "DO_NOT_LEAK_BRANCH",
            }
        )
    return result


def shopping_data(*, complete=True, strategy="single_branch", extra=True):
    visit = {
        "branch_id": 7,
        "branch_name": "Central branch",
        "items": [
            {
                "external_product_id": "product-123",
                "requested_quantity": 2,
                "available_quantity": 4,
                "supplier": "DO_NOT_LEAK_SUPPLIER",
            }
        ],
        "notes": "DO_NOT_LEAK_NOTES",
    }
    result = {
        "complete": complete,
        "strategy": strategy,
        "visits": [visit] if complete else [],
        "missing_items": [],
    }
    if extra:
        result["algorithm"] = "DO_NOT_LEAK_ALGORITHM"
    return result


def incomplete_shopping_data():
    return {
        "complete": False,
        "strategy": "unavailable",
        "visits": [],
        "missing_items": [
            {
                "external_product_id": "product-missing",
                "missing_quantity": 7,
                "reason": "DO_NOT_LEAK_REASON",
            }
        ],
        "diagnostics": "DO_NOT_LEAK_DIAGNOSTICS",
    }


def tool_results(response):
    return response["data"]["tool_results"]


def assert_standard_response_shape(response):
    assert set(response) == {"status", "answer", "data"}
    assert set(response["data"]) == {"question_type", "tool_results"}


def assert_unavailable(response):
    assert response == UNAVAILABLE_RESPONSE


def assert_no_leaked_input_fields(response):
    serialized = json.dumps(response, sort_keys=True)
    for marker in (
        "DO_NOT_LEAK_DETAIL",
        "DO_NOT_LEAK_CATEGORY",
        "DO_NOT_LEAK_METADATA",
        "DO_NOT_LEAK_TIMESTAMP",
        "DO_NOT_LEAK_ADDRESS",
        "DO_NOT_LEAK_BRANCH",
        "DO_NOT_LEAK_PRODUCT_BRANCH",
        "DO_NOT_LEAK_STOCK_ITEM",
        "DO_NOT_LEAK_SUPPLIER",
        "DO_NOT_LEAK_NOTES",
        "DO_NOT_LEAK_ALGORITHM",
        "DO_NOT_LEAK_REASON",
        "DO_NOT_LEAK_DIAGNOSTICS",
    ):
        assert marker not in serialized


def assert_answer_excludes_values(response, values):
    """Ensure the narrative does not copy business values from another input."""

    for value in values:
        assert str(value) not in response["answer"]


def test_public_surface_reexports_types_and_exposes_only_contract_callable(generator):
    classifier = importlib.import_module("ai_service.classifier")

    assert generator.SUPPORTED_QUESTION_TYPES is classifier.SUPPORTED_QUESTION_TYPES
    assert generator.SUPPORTED_QUESTION_TYPES == SUPPORTED_TYPES
    signature = inspect.signature(generator.generate_grounded_response)
    assert tuple(signature.parameters) == ("question_type", "mcp_results")


@pytest.mark.parametrize("question_type", [None, 4, True, [], {}, "other"])
def test_invalid_question_type_raises_value_error(generator, question_type):
    with pytest.raises(ValueError):
        generator.generate_grounded_response(question_type, {})


@pytest.mark.parametrize("mcp_results", [None, [], (), "results", 4, True])
def test_mcp_results_must_be_a_dictionary(generator, mcp_results):
    with pytest.raises(ValueError):
        generator.generate_grounded_response("product_details", mcp_results)


def test_unsupported_question_has_exact_response_and_requires_no_tools(generator):
    response = generator.generate_grounded_response("unsupported", {})

    assert response == {
        "status": "unsupported",
        "answer": "This question is outside the supported inventory scope.",
        "data": {"supported_question_types": list(SUPPORTED_TYPES)},
    }


def test_unsupported_question_rejects_non_empty_results(generator):
    with pytest.raises(ValueError):
        generator.generate_grounded_response("unsupported", {"ignored": {}})


@pytest.mark.parametrize(
    ("question_type", "unexpected_key"),
    [
        ("product_details", "list_products"),
        ("product_availability", "list_branch_stock"),
        ("branch_inventory", "get_product_details"),
        ("shopping_list", "get_stock_for_product"),
    ],
)
def test_each_family_rejects_unallowlisted_tool(generator, question_type, unexpected_key):
    with pytest.raises(ValueError):
        generator.generate_grounded_response(question_type, {unexpected_key: {}})


def test_non_string_tool_key_is_rejected(generator):
    with pytest.raises(ValueError):
        generator.generate_grounded_response("product_details", {1: {}})


@pytest.mark.parametrize("question_type", SUPPORTED_TYPES)
def test_no_exploitable_tool_result_returns_exact_unavailable_response(
    generator, question_type
):
    assert_unavailable(generator.generate_grounded_response(question_type, {}))


@pytest.mark.parametrize("status", ["not_found", "error", "pending", None])
def test_non_success_envelopes_are_unavailable_and_never_leak_errors(generator, status):
    if status == "error":
        result = envelope(
            None,
            status=status,
            error={"code": "SECRET_ERROR_CODE", "message": "SECRET_ERROR_MESSAGE"},
        )
    else:
        result = envelope(
            {"secret": "DO_NOT_LEAK_MALFORMED_DATA"},
            status=status,
            arbitrary="DO_NOT_LEAK_ARBITRARY_FIELD",
        )

    response = generator.generate_grounded_response(
        "product_details", {"get_product_details": result}
    )

    assert_unavailable(response)
    serialized = json.dumps(response)
    assert "SECRET_ERROR_CODE" not in serialized
    assert "SECRET_ERROR_MESSAGE" not in serialized
    assert "DO_NOT_LEAK" not in serialized


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        {"status": "success"},
        {"data": details_data()},
        {"status": "success", "data": []},
        {"status": "success", "data": {"name": "missing id"}},
    ],
)
def test_malformed_envelopes_or_data_are_unavailable(generator, result):
    response = generator.generate_grounded_response(
        "product_details", {"get_product_details": result}
    )
    assert_unavailable(response)


def test_product_details_success_projects_only_public_fields_and_is_grounded(generator):
    response = generator.generate_grounded_response(
        "product_details",
        {
            "get_product_details": envelope(
                details_data(), envelope_marker="DO_NOT_LEAK_ENVELOPE"
            )
        },
    )

    assert_standard_response_shape(response)
    assert response["status"] == "success"
    assert response["data"]["question_type"] == "product_details"
    assert tool_results(response) == {
        "get_product_details": {
            "external_product_id": "product-123",
            "name": "Example product",
        }
    }
    assert "product-123" in response["answer"]
    assert "Example product" in response["answer"]
    assert "999" not in response["answer"]
    assert_no_leaked_input_fields(response)
    assert "DO_NOT_LEAK_ENVELOPE" not in json.dumps(response)


def test_product_details_answer_does_not_reuse_values_from_another_product(generator):
    first_response = generator.generate_grounded_response(
        "product_details",
        {
            "get_product_details": envelope(
                {"external_product_id": "product-theta-305", "name": "Theta pasta"}
            )
        },
    )
    second_response = generator.generate_grounded_response(
        "product_details",
        {
            "get_product_details": envelope(
                {"external_product_id": "product-iota-806", "name": "Iota coffee"}
            )
        },
    )

    assert first_response["status"] == second_response["status"] == "success"
    assert_answer_excludes_values(
        first_response, ("product-iota-806", "Iota coffee")
    )
    assert_answer_excludes_values(
        second_response, ("product-theta-305", "Theta pasta")
    )


def test_product_availability_success_combines_matching_product_and_stock(generator):
    response = generator.generate_grounded_response(
        "product_availability",
        {
            "get_product_details": envelope(details_data(extra=False)),
            "get_stock_for_product": envelope(stock_for_product_data(extra=True)),
        },
    )

    assert_standard_response_shape(response)
    assert response["status"] == "success"
    assert response["data"]["question_type"] == "product_availability"
    assert list(tool_results(response)) == [
        "get_product_details",
        "get_stock_for_product",
    ]
    assert tool_results(response) == {
        "get_product_details": {
            "external_product_id": "product-123",
            "name": "Example product",
        },
        "get_stock_for_product": {
            "external_product_id": "product-123",
            "branches": [
                {"branch_id": 7, "branch_name": "Central branch", "quantity": 4}
            ],
        },
    }
    for expected in ("product-123", "Example product", "Central branch", "4"):
        assert expected in response["answer"]
    assert_no_leaked_input_fields(response)


def test_product_availability_with_no_branches_is_a_successful_real_empty_stock(generator):
    response = generator.generate_grounded_response(
        "product_availability",
        {
            "get_product_details": envelope(details_data(extra=False)),
            "get_stock_for_product": envelope(
                stock_for_product_data(extra=False, branches=[])
            ),
        },
    )

    assert response["status"] == "success"
    assert response["data"]["question_type"] == "product_availability"
    assert tool_results(response)["get_stock_for_product"]["branches"] == []
    assert "product-123" in response["answer"]
    assert "no stock" in response["answer"].lower()


def test_product_availability_answer_uses_only_the_current_product_and_stock_values(
    generator,
):
    first = {
        "get_product_details": envelope(
            {
                "external_product_id": "product-alpha-041",
                "name": "Alpha tea",
            }
        ),
        "get_stock_for_product": envelope(
            {
                "external_product_id": "product-alpha-041",
                "branches": [
                    {"branch_id": 17, "branch_name": "Alpha branch", "quantity": 23}
                ],
            }
        ),
    }
    second = {
        "get_product_details": envelope(
            {
                "external_product_id": "product-beta-907",
                "name": "Beta rice",
            }
        ),
        "get_stock_for_product": envelope(
            {
                "external_product_id": "product-beta-907",
                "branches": [
                    {"branch_id": 29, "branch_name": "Beta branch", "quantity": 31}
                ],
            }
        ),
    }

    first_response = generator.generate_grounded_response("product_availability", first)
    second_response = generator.generate_grounded_response("product_availability", second)

    assert first_response["status"] == second_response["status"] == "success"
    assert_answer_excludes_values(
        first_response,
        ("product-beta-907", "Beta rice", 29, "Beta branch", 31),
    )
    assert_answer_excludes_values(
        second_response,
        ("product-alpha-041", "Alpha tea", 17, "Alpha branch", 23),
    )


def test_branch_inventory_success_correlates_only_projected_product_and_stock_data(
    generator,
):
    response = generator.generate_grounded_response(
        "branch_inventory",
        {
            "list_products": envelope(products_data()),
            "list_branch_stock": envelope(branch_stock_data()),
        },
    )

    assert_standard_response_shape(response)
    assert response["status"] == "success"
    assert response["data"]["question_type"] == "branch_inventory"
    assert list(tool_results(response)) == ["list_products", "list_branch_stock"]
    assert tool_results(response) == {
        "list_products": {
            "products": [
                {"external_product_id": "product-123", "name": "Example product"}
            ]
        },
        "list_branch_stock": {
            "branch_id": 7,
            "branch_name": "Central branch",
            "stocks": [{"external_product_id": "product-123", "quantity": 4}],
        },
    }
    for expected in ("Central branch", "product-123", "Example product", "4"):
        assert expected in response["answer"]
    assert_no_leaked_input_fields(response)


def test_branch_inventory_with_no_stocks_is_a_successful_real_empty_stock(generator):
    response = generator.generate_grounded_response(
        "branch_inventory",
        {
            "list_products": envelope({"products": []}),
            "list_branch_stock": envelope(branch_stock_data(extra=False, stocks=[])),
        },
    )

    assert response["status"] == "success"
    assert response["data"]["question_type"] == "branch_inventory"
    assert tool_results(response)["list_products"] == {"products": []}
    assert tool_results(response)["list_branch_stock"]["stocks"] == []
    assert "no stock" in response["answer"].lower()


def test_branch_inventory_answer_does_not_invent_values_from_another_projection(
    generator,
):
    first = {
        "list_products": envelope(
            {
                "products": [
                    {"external_product_id": "product-gamma-118", "name": "Gamma soap"}
                ]
            }
        ),
        "list_branch_stock": envelope(
            {
                "branch_id": 37,
                "branch_name": "Gamma branch",
                "stocks": [{"external_product_id": "product-gamma-118", "quantity": 43}],
            }
        ),
    }
    second = {
        "list_products": envelope(
            {
                "products": [
                    {"external_product_id": "product-delta-826", "name": "Delta flour"}
                ]
            }
        ),
        "list_branch_stock": envelope(
            {
                "branch_id": 48,
                "branch_name": "Delta branch",
                "stocks": [{"external_product_id": "product-delta-826", "quantity": 59}],
            }
        ),
    }

    first_response = generator.generate_grounded_response("branch_inventory", first)
    second_response = generator.generate_grounded_response("branch_inventory", second)

    assert first_response["status"] == second_response["status"] == "success"
    assert_answer_excludes_values(
        first_response,
        ("product-delta-826", "Delta flour", 48, "Delta branch", 59),
    )
    assert_answer_excludes_values(
        second_response,
        ("product-gamma-118", "Gamma soap", 37, "Gamma branch", 43),
    )


def test_shopping_list_complete_success_projects_nested_visit_data(generator):
    source = {
        "list_products": envelope(products_data()),
        "find_branches_for_shopping_list": envelope(shopping_data()),
    }
    response = generator.generate_grounded_response("shopping_list", source)

    assert_standard_response_shape(response)
    assert response["status"] == "success"
    assert response["data"]["question_type"] == "shopping_list"
    assert list(tool_results(response)) == [
        "list_products",
        "find_branches_for_shopping_list",
    ]
    projected_shopping = tool_results(response)["find_branches_for_shopping_list"]
    assert projected_shopping == {
        "complete": True,
        "strategy": "single_branch",
        "visits": [
            {
                "branch_id": 7,
                "branch_name": "Central branch",
                "items": [
                    {
                        "external_product_id": "product-123",
                        "requested_quantity": 2,
                        "available_quantity": 4,
                    }
                ],
            }
        ],
        "missing_items": [],
    }
    for expected in ("single_branch", "Central branch", "product-123", "2", "4"):
        assert expected in response["answer"]
    assert_no_leaked_input_fields(response)


def test_shopping_list_multiple_branch_success_accepts_the_contract_strategy(generator):
    data = shopping_data(strategy="multiple_branches", extra=False)
    second_visit = copy.deepcopy(data["visits"][0])
    second_visit["branch_id"] = 8
    second_visit["branch_name"] = "North branch"
    data["visits"].append(second_visit)
    response = generator.generate_grounded_response(
        "shopping_list",
        {
            "list_products": envelope({"products": []}),
            "find_branches_for_shopping_list": envelope(data),
        },
    )

    assert response["status"] == "success"
    assert response["data"]["question_type"] == "shopping_list"
    projected = tool_results(response)["find_branches_for_shopping_list"]
    assert projected["strategy"] == "multiple_branches"
    assert [visit["branch_id"] for visit in projected["visits"]] == [7, 8]
    assert "Central branch" in response["answer"]
    assert "North branch" in response["answer"]


def test_shopping_list_answer_uses_only_values_from_its_current_plan(generator):
    first = {
        "list_products": envelope(
            {"products": [{"external_product_id": "product-epsilon-203", "name": "Epsilon oil"}]}
        ),
        "find_branches_for_shopping_list": envelope(
            {
                "complete": True,
                "strategy": "single_branch",
                "visits": [
                    {
                        "branch_id": 61,
                        "branch_name": "Epsilon branch",
                        "items": [
                            {
                                "external_product_id": "product-epsilon-203",
                                "requested_quantity": 2,
                                "available_quantity": 6,
                            }
                        ],
                    }
                ],
                "missing_items": [],
            }
        ),
    }
    second = {
        "list_products": envelope(
            {"products": [{"external_product_id": "product-zeta-704", "name": "Zeta beans"}]}
        ),
        "find_branches_for_shopping_list": envelope(
            {
                "complete": True,
                "strategy": "single_branch",
                "visits": [
                    {
                        "branch_id": 72,
                        "branch_name": "Zeta branch",
                        "items": [
                            {
                                "external_product_id": "product-zeta-704",
                                "requested_quantity": 5,
                                "available_quantity": 9,
                            }
                        ],
                    }
                ],
                "missing_items": [],
            }
        ),
    }

    first_response = generator.generate_grounded_response("shopping_list", first)
    second_response = generator.generate_grounded_response("shopping_list", second)

    assert first_response["status"] == second_response["status"] == "success"
    assert_answer_excludes_values(
        first_response,
        ("product-zeta-704", "Zeta beans", 72, "Zeta branch", 5, 9),
    )
    assert_answer_excludes_values(
        second_response,
        ("product-epsilon-203", "Epsilon oil", 61, "Epsilon branch", 2, 6),
    )


def test_partial_with_one_missing_expected_tool_uses_fixed_fact_free_answer(generator):
    cases = [
        (
            "product_availability",
            {"get_product_details": envelope(details_data(extra=False))},
            {"get_product_details"},
        ),
        (
            "branch_inventory",
            {"list_products": envelope(products_data(extra=False))},
            {"list_products"},
        ),
        (
            "shopping_list",
            {"list_products": envelope(products_data(extra=False))},
            {"list_products"},
        ),
    ]
    for question_type, results, expected_tools in cases:
        response = generator.generate_grounded_response(question_type, results)
        assert_standard_response_shape(response)
        assert response["status"] == "partial"
        assert response["answer"] == PARTIAL_ANSWER
        assert set(tool_results(response)) == expected_tools


@pytest.mark.parametrize(
    ("question_type", "results", "expected_tool_results"),
    [
        (
            "product_availability",
            {
                "get_product_details": envelope(
                    {
                        "external_product_id": "product-123",
                        "name": "",
                        "description": "DO_NOT_LEAK_DETAIL",
                        "price": 999,
                    }
                ),
                "get_stock_for_product": envelope(stock_for_product_data()),
            },
            {
                "get_stock_for_product": {
                    "external_product_id": "product-123",
                    "branches": [
                        {
                            "branch_id": 7,
                            "branch_name": "Central branch",
                            "quantity": 4,
                        }
                    ],
                }
            },
        ),
        (
            "branch_inventory",
            {
                "list_products": envelope(
                    {
                        "products": [
                            {
                                "external_product_id": "product-invalid",
                                "name": "",
                                "category": "DO_NOT_LEAK_CATEGORY",
                            }
                        ],
                        "metadata": "DO_NOT_LEAK_METADATA",
                    }
                ),
                "list_branch_stock": envelope(branch_stock_data()),
            },
            {
                "list_branch_stock": {
                    "branch_id": 7,
                    "branch_name": "Central branch",
                    "stocks": [
                        {
                            "external_product_id": "product-123",
                            "quantity": 4,
                        }
                    ],
                }
            },
        ),
        (
            "shopping_list",
            {
                "list_products": envelope(
                    {
                        "products": [
                            {
                                "external_product_id": "product-invalid",
                                "name": "",
                                "category": "DO_NOT_LEAK_CATEGORY",
                            }
                        ],
                        "metadata": "DO_NOT_LEAK_METADATA",
                    }
                ),
                "find_branches_for_shopping_list": envelope(shopping_data()),
            },
            {
                "find_branches_for_shopping_list": {
                    "complete": True,
                    "strategy": "single_branch",
                    "visits": [
                        {
                            "branch_id": 7,
                            "branch_name": "Central branch",
                            "items": [
                                {
                                    "external_product_id": "product-123",
                                    "requested_quantity": 2,
                                    "available_quantity": 4,
                                }
                            ],
                        }
                    ],
                    "missing_items": [],
                }
            },
        ),
    ],
)
def test_partial_with_only_second_expected_tool_projects_that_tool_exclusively(
    generator, question_type, results, expected_tool_results
):
    response = generator.generate_grounded_response(question_type, results)

    assert_standard_response_shape(response)
    assert response["status"] == "partial"
    assert response["answer"] == PARTIAL_ANSWER
    assert tool_results(response) == expected_tool_results
    assert_no_leaked_input_fields(response)
    assert "999" not in response["answer"]


@pytest.mark.parametrize(
    ("question_type", "results", "expected_tool"),
    [
        (
            "product_availability",
            {
                "get_product_details": envelope(details_data(extra=False)),
                "get_stock_for_product": envelope(
                    None,
                    status="error",
                    error={"code": "SECRET_ERROR", "message": "DO_NOT_LEAK_ERROR"},
                ),
            },
            "get_product_details",
        ),
        (
            "branch_inventory",
            {
                "list_products": envelope(products_data(extra=False)),
                "list_branch_stock": {
                    "status": "success",
                    "data": {"branch_id": 7},
                    "diagnostics": "DO_NOT_LEAK_DIAGNOSTICS",
                },
            },
            "list_products",
        ),
        (
            "shopping_list",
            {
                "list_products": envelope(products_data(extra=False)),
                "find_branches_for_shopping_list": envelope(
                    {"complete": True},
                    status="success",
                    arbitrary="DO_NOT_LEAK_ARBITRARY",
                ),
            },
            "list_products",
        ),
    ],
)
def test_partial_with_valid_tool_and_error_or_malformed_companion_is_grounded_only_in_valid_tool(
    generator, question_type, results, expected_tool
):
    response = generator.generate_grounded_response(question_type, results)

    assert_standard_response_shape(response)
    assert response["status"] == "partial"
    assert response["answer"] == PARTIAL_ANSWER
    assert list(tool_results(response)) == [expected_tool]
    assert_no_leaked_input_fields(response)
    serialized = json.dumps(response)
    assert "SECRET_ERROR" not in serialized
    assert "DO_NOT_LEAK_ERROR" not in serialized
    assert "DO_NOT_LEAK_ARBITRARY" not in serialized
    assert "DO_NOT_LEAK_DIAGNOSTICS" not in serialized


def test_product_stock_identifier_contradiction_excludes_stock_and_uses_fixed_answer(
    generator,
):
    response = generator.generate_grounded_response(
        "product_availability",
        {
            "get_product_details": envelope(details_data(extra=False)),
            "get_stock_for_product": envelope(
                stock_for_product_data(product_id="different-product", extra=False)
            ),
        },
    )

    assert_standard_response_shape(response)
    assert response["status"] == "partial"
    assert response["answer"] == PARTIAL_ANSWER
    assert tool_results(response) == {
        "get_product_details": {
            "external_product_id": "product-123",
            "name": "Example product",
        }
    }
    assert "different-product" not in json.dumps(response)


def test_incomplete_shopping_list_is_partial_and_does_not_recalculate_a_plan(generator):
    response = generator.generate_grounded_response(
        "shopping_list",
        {
            "list_products": envelope(products_data(extra=False)),
            "find_branches_for_shopping_list": envelope(incomplete_shopping_data()),
        },
    )

    assert_standard_response_shape(response)
    assert response["status"] == "partial"
    assert tool_results(response)["find_branches_for_shopping_list"] == {
        "complete": False,
        "strategy": "unavailable",
        "visits": [],
        "missing_items": [
            {"external_product_id": "product-missing", "missing_quantity": 7}
        ],
    }
    assert "unavailable" in response["answer"]
    assert "product-missing" in response["answer"]
    assert "7" in response["answer"]
    assert "Central branch" not in response["answer"]
    assert_no_leaked_input_fields(response)


def _assert_invalid_result_is_unavailable(generator, question_type, tool_name, data):
    response = generator.generate_grounded_response(
        question_type, {tool_name: envelope(data)}
    )
    assert_unavailable(response)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"external_product_id": "", "name": "Name"},
        {"external_product_id": "   ", "name": "Name"},
        {"external_product_id": "id", "name": ""},
        {"external_product_id": "id", "name": "   "},
        {"external_product_id": 4, "name": "Name"},
        {"external_product_id": "id", "name": 4},
        [],
    ],
)
def test_product_details_schema_violations_invalidate_the_whole_result(generator, data):
    _assert_invalid_result_is_unavailable(
        generator, "product_details", "get_product_details", data
    )


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"products": None},
        {"products": {}},
        {"products": [{"external_product_id": "id"}]},
        {"products": [{"name": "Name"}]},
        {"products": [{"external_product_id": "", "name": "Name"}]},
        {"products": [{"external_product_id": "id", "name": " "}]},
        {"products": [{"external_product_id": True, "name": "Name"}]},
        {"products": [{"external_product_id": "id", "name": 1}]},
        {"products": ["not a product"]},
    ],
)
def test_list_products_schema_violations_invalidate_the_whole_result(generator, data):
    _assert_invalid_result_is_unavailable(
        generator, "branch_inventory", "list_products", data
    )


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"external_product_id": "id"},
        {"external_product_id": " ", "branches": []},
        {"external_product_id": 4, "branches": []},
        {"external_product_id": "id", "branches": {}},
        {
            "external_product_id": "id",
            "branches": [{"branch_id": 1, "branch_name": "B"}],
        },
        {
            "external_product_id": "id",
            "branches": [{"branch_id": 0, "branch_name": "B", "quantity": 1}],
        },
        {
            "external_product_id": "id",
            "branches": [{"branch_id": True, "branch_name": "B", "quantity": 1}],
        },
        {
            "external_product_id": "id",
            "branches": [{"branch_id": 1, "branch_name": " ", "quantity": 1}],
        },
        {
            "external_product_id": "id",
            "branches": [{"branch_id": 1, "branch_name": 9, "quantity": 1}],
        },
        {
            "external_product_id": "id",
            "branches": [{"branch_id": 1, "branch_name": "B", "quantity": -1}],
        },
        {
            "external_product_id": "id",
            "branches": [{"branch_id": 1, "branch_name": "B", "quantity": True}],
        },
    ],
)
def test_product_stock_schema_violations_invalidate_the_whole_result(generator, data):
    _assert_invalid_result_is_unavailable(
        generator, "product_availability", "get_stock_for_product", data
    )


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"branch_id": 1, "branch_name": "B"},
        {"branch_id": 0, "branch_name": "B", "stocks": []},
        {"branch_id": True, "branch_name": "B", "stocks": []},
        {"branch_id": 1, "branch_name": " ", "stocks": []},
        {"branch_id": 1, "branch_name": 9, "stocks": []},
        {"branch_id": 1, "branch_name": "B", "stocks": {}},
        {
            "branch_id": 1,
            "branch_name": "B",
            "stocks": [{"external_product_id": "id"}],
        },
        {
            "branch_id": 1,
            "branch_name": "B",
            "stocks": [{"external_product_id": " ", "quantity": 1}],
        },
        {
            "branch_id": 1,
            "branch_name": "B",
            "stocks": [{"external_product_id": 9, "quantity": 1}],
        },
        {
            "branch_id": 1,
            "branch_name": "B",
            "stocks": [{"external_product_id": "id", "quantity": 0}],
        },
        {
            "branch_id": 1,
            "branch_name": "B",
            "stocks": [{"external_product_id": "id", "quantity": True}],
        },
    ],
)
def test_branch_stock_schema_violations_invalidate_the_whole_result(generator, data):
    _assert_invalid_result_is_unavailable(
        generator, "branch_inventory", "list_branch_stock", data
    )


def valid_shopping_data():
    return {
        "complete": True,
        "strategy": "single_branch",
        "visits": [
            {
                "branch_id": 1,
                "branch_name": "B",
                "items": [
                    {
                        "external_product_id": "id",
                        "requested_quantity": 1,
                        "available_quantity": 1,
                    }
                ],
            }
        ],
        "missing_items": [],
    }


def test_shopping_rejects_available_quantity_below_requested_quantity(generator):
    data = valid_shopping_data()
    data["visits"][0]["items"][0].update(
        requested_quantity=5,
        available_quantity=4,
    )

    response = generator.generate_grounded_response(
        "shopping_list",
        {"find_branches_for_shopping_list": envelope(data)},
    )

    assert_unavailable(response)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(complete=1),
        lambda d: d.update(strategy="unknown"),
        lambda d: d.update(visits={}),
        lambda d: d.update(missing_items={}),
        lambda d: d.update(visits=["not a visit"]),
        lambda d: d["visits"][0].update(branch_id=0),
        lambda d: d["visits"][0].update(branch_id=True),
        lambda d: d["visits"][0].update(branch_name=" "),
        lambda d: d["visits"][0].update(branch_name=9),
        lambda d: d["visits"][0].update(items=[]),
        lambda d: d["visits"][0].update(items={}),
        lambda d: d["visits"][0].update(items=["not an item"]),
        lambda d: d["visits"][0]["items"][0].update(external_product_id=""),
        lambda d: d["visits"][0]["items"][0].update(external_product_id=9),
        lambda d: d["visits"][0]["items"][0].update(requested_quantity=0),
        lambda d: d["visits"][0]["items"][0].update(requested_quantity=True),
        lambda d: d["visits"][0]["items"][0].update(available_quantity=0),
        lambda d: d["visits"][0]["items"][0].update(available_quantity=True),
        lambda d: d.update(missing_items=["not a missing item"]),
        lambda d: d.update(missing_items=[{"external_product_id": "id"}]),
        lambda d: d.update(
            missing_items=[{"external_product_id": "id", "missing_quantity": 0}]
        ),
        lambda d: d.update(
            missing_items=[{"external_product_id": "id", "missing_quantity": True}]
        ),
        lambda d: d.update(
            missing_items=[{"external_product_id": 9, "missing_quantity": 1}]
        ),
    ],
)
def test_shopping_nested_schema_violations_invalidate_the_whole_result(generator, mutate):
    data = valid_shopping_data()
    mutate(data)
    _assert_invalid_result_is_unavailable(
        generator, "shopping_list", "find_branches_for_shopping_list", data
    )


@pytest.mark.parametrize(
    "data",
    [
        {
            "complete": True,
            "strategy": "unavailable",
            "visits": valid_shopping_data()["visits"],
            "missing_items": [],
        },
        {
            "complete": True,
            "strategy": "single_branch",
            "visits": [],
            "missing_items": [],
        },
        {
            "complete": True,
            "strategy": "single_branch",
            "visits": valid_shopping_data()["visits"] * 2,
            "missing_items": [],
        },
        {
            "complete": True,
            "strategy": "multiple_branches",
            "visits": valid_shopping_data()["visits"],
            "missing_items": [],
        },
        {
            "complete": False,
            "strategy": "single_branch",
            "visits": [],
            "missing_items": [{"external_product_id": "id", "missing_quantity": 1}],
        },
        {
            "complete": False,
            "strategy": "unavailable",
            "visits": valid_shopping_data()["visits"],
            "missing_items": [{"external_product_id": "id", "missing_quantity": 1}],
        },
        {
            "complete": False,
            "strategy": "unavailable",
            "visits": [],
            "missing_items": [],
        },
    ],
)
def test_shopping_coherence_violations_invalidate_the_whole_result(generator, data):
    _assert_invalid_result_is_unavailable(
        generator, "shopping_list", "find_branches_for_shopping_list", data
    )


def test_all_success_projections_are_independent_and_input_is_immutable(generator):
    source = {
        "get_product_details": envelope(details_data()),
    }
    original = copy.deepcopy(source)
    response = generator.generate_grounded_response("product_details", source)

    assert source == original
    response["data"]["tool_results"]["get_product_details"]["name"] = "changed"
    response_again = generator.generate_grounded_response("product_details", source)
    assert source == original
    assert response_again["data"]["tool_results"]["get_product_details"]["name"] == (
        "Example product"
    )


def test_mutating_input_after_generation_does_not_change_returned_projection(generator):
    source = {"get_product_details": envelope(details_data(extra=False))}
    response = generator.generate_grounded_response("product_details", source)
    source["get_product_details"]["data"]["name"] = "mutated after call"

    assert response["data"]["tool_results"]["get_product_details"]["name"] == (
        "Example product"
    )
