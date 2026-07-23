"""Unit tests for the external Product API validation client."""

import httpx
import pytest

from backoffice.products.client import (
    ProductClient,
    ProductConnectionError,
    ProductInvalidJsonError,
    ProductInvalidResponseError,
    ProductNotFoundError,
    ProductTimeoutError,
    ProductUnexpectedStatusError,
)

PRODUCT_PAYLOAD = {
    "id": 2102,
    "sku": "HB-MON-2102",
    "name": "Test monitor",
    "discontinued": False,
}


def _client(handler) -> ProductClient:
    return ProductClient(
        "http://localhost:5001",
        5,
        transport=httpx.MockTransport(handler),
    )


def test_product_client_returns_only_validation_fields_for_valid_product():
    """A valid 200 response is normalized without retaining product details."""
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/products/HB-MON-2102"
        return httpx.Response(200, json=PRODUCT_PAYLOAD)

    product = _client(handler).get_product("HB-MON-2102")

    assert product.id == 2102
    assert product.sku == "HB-MON-2102"
    assert product.discontinued is False
    assert not hasattr(product, "name")


def test_product_client_reports_unknown_product():
    """A documented 404 is distinct from technical API failures."""
    client = _client(lambda request: httpx.Response(404, json={}))

    with pytest.raises(ProductNotFoundError, match="not found"):
        client.get_product("UNKNOWN")


def test_product_client_reports_timeout():
    """HTTP timeouts become a stable client error without exposing the URL."""
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProductTimeoutError, match="timed out") as error:
        _client(handler).get_product("HB-MON-2102")

    assert "localhost" not in str(error.value)


def test_product_client_reports_connection_failure():
    """Connection failures are distinct from timeouts and HTTP statuses."""
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(ProductConnectionError, match="unreachable"):
        _client(handler).get_product("HB-MON-2102")


def test_product_client_reports_unexpected_http_status():
    """Undocumented HTTP statuses are rejected without including the URL."""
    client = _client(
        lambda request: httpx.Response(503, text="private upstream body")
    )

    with pytest.raises(
        ProductUnexpectedStatusError,
        match="status 503",
    ) as error:
        client.get_product("HB-MON-2102")

    assert "private upstream body" not in str(error.value)
    assert "localhost" not in str(error.value)


def test_product_client_reports_invalid_json():
    """A successful HTTP response still requires a valid JSON body."""
    client = _client(
        lambda request: httpx.Response(200, content=b"not-json")
    )

    with pytest.raises(ProductInvalidJsonError, match="invalid JSON"):
        client.get_product("HB-MON-2102")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"id": 2102, "sku": "HB-MON-2102", "name": "Monitor"},
        {**PRODUCT_PAYLOAD, "sku": ""},
        {**PRODUCT_PAYLOAD, "discontinued": "false"},
    ],
)
def test_product_client_reports_invalid_response_structure(payload):
    """Missing or mistyped required fields are never accepted."""
    client = _client(lambda request: httpx.Response(200, json=payload))

    with pytest.raises(ProductInvalidResponseError):
        client.get_product("HB-MON-2102")


def test_product_client_returns_discontinued_state_for_seed_rejection():
    """The client preserves the flag required by the seed decision."""
    payload = {**PRODUCT_PAYLOAD, "discontinued": True}
    client = _client(lambda request: httpx.Response(200, json=payload))

    product = client.get_product("HB-MON-2102")

    assert product.discontinued is True
