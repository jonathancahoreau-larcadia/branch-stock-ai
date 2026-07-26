"""Unit tests for strict Stocks API validation."""

import pytest

from backoffice.stocks.schemas import (
    InvalidQuantityError,
    StockValidationError,
    reject_query_parameters,
    validate_external_product_id,
    validate_list_filters,
    validate_movement_payload,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ({}, True),
        ({"available_only": ["true"]}, True),
        ({"available_only": ["false"]}, False),
    ],
)
def test_list_filter_accepts_only_strict_booleans(query, expected):
    assert validate_list_filters(query).available_only is expected


@pytest.mark.parametrize(
    "query",
    [
        {"available_only": ["TRUE"]},
        {"available_only": ["1"]},
        {"available_only": ["true", "false"]},
        {"branch_id": ["2"]},
    ],
)
def test_list_filter_rejects_invalid_duplicate_or_extra_values(query):
    with pytest.raises(StockValidationError):
        validate_list_filters(query)


@pytest.mark.parametrize("identifier", [" 42 ", " HB-MON-2102 "])
def test_identifier_is_trimmed_and_accepts_numeric_or_sku(identifier):
    assert validate_external_product_id(identifier) == identifier.strip()


@pytest.mark.parametrize("identifier", [" ", "x" * 256])
def test_identifier_rejects_blank_or_too_long_values(identifier):
    with pytest.raises(StockValidationError):
        validate_external_product_id(identifier)


def test_detail_and_movements_reject_every_query_parameter():
    with pytest.raises(StockValidationError):
        reject_query_parameters({"branch_id": ["2"]})


def test_movement_requires_exact_quantity_field():
    assert validate_movement_payload({"quantity": 3}).quantity == 3
    for payload in (
        None,
        [],
        {},
        {"quantity": 1, "branch_id": 2},
    ):
        with pytest.raises(StockValidationError):
            validate_movement_payload(payload)


@pytest.mark.parametrize(
    "quantity",
    [True, False, "1", 1.0, 0, -1, None],
)
def test_movement_rejects_every_non_positive_strict_integer(quantity):
    with pytest.raises(InvalidQuantityError):
        validate_movement_payload({"quantity": quantity})
