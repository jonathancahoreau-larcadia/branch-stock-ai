"""Unit tests for the validated official Product API client."""

import httpx
import pytest

from backoffice.products.client import (
    ProductClient,
    ProductClientConfigurationError,
    ProductConnectionError,
    ProductInvalidIdentifierError,
    ProductInvalidJsonError,
    ProductInvalidResponseError,
    ProductNotFoundError,
    ProductTimeoutError,
    ProductUnexpectedStatusError,
)

SUPPLIER_PAYLOAD = {
    "id": "SUP-LAB-002",
    "name": "LabForge Supplies",
    "contact_email": "private@example.test",
    "country": "UY",
    "lead_time_days": 7,
    "reliability_score": 0.94,
}
PRODUCT_PAYLOAD = {
    "id": 4,
    "sku": "HB-MON-2102",
    "name": "24 inch Compact Monitor",
    "description": "A compact display.",
    "category": "Displays",
    "brand": "LabForge",
    "supplier_id": "SUP-LAB-002",
    "supplier_name": "LabForge Supplies",
    "unit_price": 169.99,
    "currency": "USD",
    "discontinued": False,
    "weight_kg": 3.9,
    "tags": ["display", "compact"],
    "updated_at": "2026-05-22T12:00:00Z",
}
DETAIL_PAYLOAD = {**PRODUCT_PAYLOAD, "supplier": SUPPLIER_PAYLOAD}
JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8"}


def _response(status, *, json=None, content=None, headers=None):
    return httpx.Response(
        status,
        json=json,
        content=content,
        headers=headers or JSON_HEADERS,
    )


def _client(handler) -> ProductClient:
    return ProductClient(
        "http://localhost:5001",
        5,
        transport=httpx.MockTransport(handler),
    )


def test_seed_compatible_get_product_returns_validation_fields():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/products/HB-MON-2102"
        return _response(200, json=DETAIL_PAYLOAD)

    product = _client(handler).get_product(" HB-MON-2102 ")

    assert product.id == 4
    assert product.sku == "HB-MON-2102"
    assert product.discontinued is False
    assert product.matches("hb-mon-2102")
    assert not hasattr(product, "name")


@pytest.mark.parametrize("identifier", ["4", "HB-MON-2102"])
def test_product_detail_accepts_numeric_id_or_sku(identifier):
    client = _client(
        lambda request: _response(200, json=DETAIL_PAYLOAD)
    )

    product = client.get_product_details(identifier)

    assert product.id == 4
    assert product.sku == "HB-MON-2102"
    assert product.supplier.id == "SUP-LAB-002"


def test_product_list_forwards_validated_query_and_normalizes_page():
    params = {
        "q": "monitor",
        "category": "Displays",
        "supplier_id": "SUP-LAB-002",
        "include_discontinued": "false",
        "min_price": "50",
        "max_price": "200",
        "limit": "1",
        "offset": "0",
        "sort": "-unit_price",
    }

    def handler(request):
        assert request.url.path == "/api/v1/products"
        assert dict(request.url.params) == params
        return _response(
            200,
            json={
                "count": 1,
                "limit": 1,
                "offset": 0,
                "results": [{**PRODUCT_PAYLOAD, "unknown": "ignored"}],
                "unknown": "ignored",
            },
        )

    page = _client(handler).list_products(params)

    assert page.total == 1
    assert page.limit == 1
    assert page.offset == 0
    assert len(page.products) == 1
    assert page.products[0].sku == "HB-MON-2102"
    assert not hasattr(page.products[0], "unknown")


def test_product_list_accepts_an_empty_page_after_last_offset():
    page = _client(
        lambda request: _response(
            200,
            json={
                "count": 1,
                "limit": 20,
                "offset": 20,
                "results": [],
            },
        )
    ).list_products({"limit": "20", "offset": "20"})

    assert page.total == 1
    assert page.products == ()


def test_discontinued_product_is_preserved():
    payload = {**DETAIL_PAYLOAD, "discontinued": True}

    product = _client(
        lambda request: _response(200, json=payload)
    ).get_product_details("HB-MON-2102")

    assert product.discontinued is True


def test_product_client_reports_unknown_product():
    client = _client(
        lambda request: _response(
            404,
            json={"error": "not_found"},
        )
    )

    with pytest.raises(ProductNotFoundError, match="not found"):
        client.get_product_details("UNKNOWN")


def test_product_client_reports_timeout_without_url():
    def handler(request):
        raise httpx.ReadTimeout("private timeout detail", request=request)

    with pytest.raises(ProductTimeoutError, match="timed out") as error:
        _client(handler).get_product_details("HB-MON-2102")

    assert "localhost" not in str(error.value)
    assert "private timeout detail" not in str(error.value)


def test_product_client_reports_connection_failure_without_detail():
    def handler(request):
        raise httpx.ConnectError("private DNS detail", request=request)

    with pytest.raises(ProductConnectionError, match="unreachable") as error:
        _client(handler).get_product_details("HB-MON-2102")

    assert "private DNS detail" not in str(error.value)


@pytest.mark.parametrize("status", [400, 429, 500, 503])
def test_product_client_preserves_unexpected_http_status(status):
    client = _client(
        lambda request: _response(
            status,
            json={"private": "upstream body"},
        )
    )

    with pytest.raises(ProductUnexpectedStatusError) as error:
        client.get_product_details("HB-MON-2102")

    assert error.value.status_code == status
    assert "upstream body" not in str(error.value)
    assert "localhost" not in str(error.value)


def test_product_client_reports_invalid_json():
    client = _client(
        lambda request: _response(
            200,
            content=b"not-json",
        )
    )

    with pytest.raises(ProductInvalidJsonError, match="invalid JSON"):
        client.get_product_details("HB-MON-2102")


@pytest.mark.parametrize(
    "content_type",
    ["", "text/plain", "text/html; charset=utf-8"],
)
def test_product_client_rejects_invalid_content_type(content_type):
    client = _client(
        lambda request: _response(
            200,
            json=DETAIL_PAYLOAD,
            headers={"Content-Type": content_type},
        )
    )

    with pytest.raises(ProductInvalidResponseError):
        client.get_product_details("HB-MON-2102")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {key: value for key, value in DETAIL_PAYLOAD.items() if key != "name"},
        {**DETAIL_PAYLOAD, "id": True},
        {**DETAIL_PAYLOAD, "unit_price": "169.99"},
        {**DETAIL_PAYLOAD, "tags": ["valid", ""]},
        {**DETAIL_PAYLOAD, "updated_at": "not-a-date"},
        {**DETAIL_PAYLOAD, "discontinued": "false"},
        {**DETAIL_PAYLOAD, "supplier": None},
        {
            **DETAIL_PAYLOAD,
            "supplier": {**SUPPLIER_PAYLOAD, "id": "OTHER"},
        },
    ],
)
def test_product_client_rejects_invalid_product_or_supplier(payload):
    client = _client(lambda request: _response(200, json=payload))

    with pytest.raises(ProductInvalidResponseError):
        client.get_product_details("HB-MON-2102")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"count": 0, "limit": 20, "offset": 0},
        {"count": 1, "limit": 20, "offset": 0, "results": []},
        {
            "count": 1,
            "limit": 21,
            "offset": 0,
            "results": [PRODUCT_PAYLOAD],
        },
        {
            "count": -1,
            "limit": 20,
            "offset": 0,
            "results": [],
        },
    ],
)
def test_product_client_rejects_incomplete_or_incoherent_page(payload):
    client = _client(lambda request: _response(200, json=payload))

    with pytest.raises(ProductInvalidResponseError):
        client.list_products({"limit": "20", "offset": "0"})


def test_product_client_rejects_product_not_matching_identifier():
    client = _client(
        lambda request: _response(
            200,
            json={
                **DETAIL_PAYLOAD,
                "id": 99,
                "sku": "OTHER-SKU",
            },
        )
    )

    with pytest.raises(ProductInvalidResponseError, match="different"):
        client.get_product_details("HB-MON-2102")


@pytest.mark.parametrize("identifier", [None, "", " ", "x" * 256])
def test_product_client_rejects_invalid_identifier(identifier):
    with pytest.raises(ProductInvalidIdentifierError):
        _client(lambda request: None).get_product_details(identifier)


@pytest.mark.parametrize(
    ("base_url", "timeout"),
    [
        (None, 5),
        ("", 5),
        ("not-a-url", 5),
        ("ftp://example.test", 5),
        ("http://example.test?secret=value", 5),
        ("http://example.test", 0),
        ("http://example.test", "nan"),
    ],
)
def test_product_client_rejects_invalid_configuration(base_url, timeout):
    with pytest.raises(ProductClientConfigurationError):
        ProductClient(base_url, timeout)
