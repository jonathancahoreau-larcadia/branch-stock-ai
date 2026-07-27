"""Unit tests for strict product request validation."""

import pytest

from backoffice.products.schemas import (
    ProductValidationError,
    reject_query_parameters,
    validate_list_query,
    validate_product_identifier,
)


def test_list_query_uses_official_defaults():
    query = validate_list_query({})

    assert query.params == {
        "include_discontinued": "false",
        "limit": "20",
        "offset": "0",
    }
    assert query.limit == 20
    assert query.offset == 0


def test_list_query_accepts_every_documented_filter():
    query = validate_list_query(
        {
            "q": ["  monitor  "],
            "category": [" Displays "],
            "supplier_id": [" SUP-LAB-002 "],
            "include_discontinued": ["true"],
            "min_price": ["50.25"],
            "max_price": ["200"],
            "limit": ["100"],
            "offset": ["20"],
            "sort": ["-unit_price"],
        }
    )

    assert query.params == {
        "q": "monitor",
        "category": "Displays",
        "supplier_id": "SUP-LAB-002",
        "include_discontinued": "true",
        "min_price": "50.25",
        "max_price": "200",
        "limit": "100",
        "offset": "20",
        "sort": "-unit_price",
    }


@pytest.mark.parametrize(
    "sort",
    [
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
    ],
)
def test_list_query_accepts_each_official_sort(sort):
    assert validate_list_query({"sort": [sort]}).params["sort"] == sort


@pytest.mark.parametrize("field", ["q", "category", "supplier_id"])
def test_list_query_rejects_blank_text_filters(field):
    with pytest.raises(ProductValidationError) as error:
        validate_list_query({field: ["  "]})

    assert field in error.value.details["fields"]


@pytest.mark.parametrize("value", ["TRUE", "1", "yes", "", " false "])
def test_list_query_accepts_only_strict_boolean_values(value):
    with pytest.raises(ProductValidationError):
        validate_list_query({"include_discontinued": [value]})


@pytest.mark.parametrize("field", ["min_price", "max_price"])
@pytest.mark.parametrize("value", ["", "abc", "NaN", "Infinity", "-Infinity"])
def test_list_query_rejects_non_finite_prices(field, value):
    with pytest.raises(ProductValidationError):
        validate_list_query({field: [value]})


@pytest.mark.parametrize("value", ["0", "101", "-1", "1.5", "abc", ""])
def test_list_query_rejects_invalid_limit(value):
    with pytest.raises(ProductValidationError):
        validate_list_query({"limit": [value]})


@pytest.mark.parametrize("value", ["-1", "1.5", "abc", ""])
def test_list_query_rejects_invalid_offset(value):
    with pytest.raises(ProductValidationError):
        validate_list_query({"offset": [value]})


def test_list_query_rejects_duplicates_and_unexpected_parameters():
    with pytest.raises(ProductValidationError) as error:
        validate_list_query(
            {
                "q": ["one", "two"],
                "force_error": ["true"],
                "simulate_delay_ms": ["10"],
            }
        )

    fields = error.value.details["fields"]
    assert fields["q"] == "Must be provided at most once."
    assert fields["unexpected"] == [
        "force_error",
        "simulate_delay_ms",
    ]


def test_list_query_rejects_unknown_sort():
    with pytest.raises(ProductValidationError):
        validate_list_query({"sort": ["price"]})


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("  HB-MON-2102  ", "HB-MON-2102"),
        (" 4 ", "4"),
    ],
)
def test_product_identifier_trims_only_exterior(identifier, expected):
    assert validate_product_identifier(identifier) == expected


@pytest.mark.parametrize("identifier", [None, "", " ", "x" * 256])
def test_product_identifier_rejects_invalid_values(identifier):
    with pytest.raises(ProductValidationError):
        validate_product_identifier(identifier)


def test_detail_rejects_every_query_parameter():
    reject_query_parameters({})

    with pytest.raises(ProductValidationError) as error:
        reject_query_parameters({"q": ["monitor"], "unknown": ["1"]})

    assert error.value.details["fields"]["unexpected"] == ["q", "unknown"]
