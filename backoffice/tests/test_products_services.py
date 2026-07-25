"""Unit tests for product service mapping and serialization."""

import pytest

from backoffice.products.client import (
    ProductClientConfigurationError,
    ProductConnectionError,
    ProductData,
    ProductInvalidJsonError,
    ProductInvalidResponseError,
    ProductNotFoundError,
    ProductPage,
    ProductSupplier,
    ProductTimeoutError,
    ProductUnexpectedStatusError,
)
from backoffice.products.schemas import ProductListQuery
from backoffice.products.services import (
    ProductInvalidResponseServiceError,
    ProductNotFoundServiceError,
    ProductServiceError,
    ProductTimeoutServiceError,
    ProductUnavailableServiceError,
    get_product,
    list_products,
    serialize_product_detail,
    serialize_product_summary,
)


@pytest.fixture()
def product():
    return ProductData(
        id=4,
        sku="HB-MON-2102",
        name="24 inch Compact Monitor",
        description="A compact display.",
        category="Displays",
        brand="LabForge",
        supplier_id="SUP-LAB-002",
        supplier_name="LabForge Supplies",
        unit_price=169.99,
        currency="USD",
        discontinued=False,
        weight_kg=3.9,
        tags=("display", "compact"),
        updated_at="2026-05-22T12:00:00Z",
        supplier=ProductSupplier(
            id="SUP-LAB-002",
            name="LabForge Supplies",
            country="UY",
            lead_time_days=7,
            reliability_score=0.94,
        ),
    )


def _query():
    return ProductListQuery(
        params={
            "include_discontinued": "false",
            "limit": "20",
            "offset": "0",
        },
        limit=20,
        offset=0,
    )


def test_product_summary_uses_exact_whitelist(product):
    assert serialize_product_summary(product) == {
        "external_product_id": "HB-MON-2102",
        "name": "24 inch Compact Monitor",
        "category": "Displays",
        "brand": "LabForge",
        "unit_price": 169.99,
        "currency": "USD",
        "discontinued": False,
    }


def test_product_detail_uses_exact_whitelist_without_contact(product):
    detail = serialize_product_detail(product)

    assert detail == {
        "external_product_id": "HB-MON-2102",
        "name": "24 inch Compact Monitor",
        "description": "A compact display.",
        "category": "Displays",
        "brand": "LabForge",
        "supplier": {
            "id": "SUP-LAB-002",
            "name": "LabForge Supplies",
            "country": "UY",
            "lead_time_days": 7,
            "reliability_score": 0.94,
        },
        "unit_price": 169.99,
        "currency": "USD",
        "discontinued": False,
        "weight_kg": 3.9,
        "tags": ["display", "compact"],
        "updated_at": "2026-05-22T12:00:00Z",
    }
    assert "contact_email" not in detail["supplier"]
    assert "id" not in detail
    assert "supplier_id" not in detail
    assert "supplier_name" not in detail


def test_list_products_uses_external_page_and_serializes(
    monkeypatch,
    product,
):
    class FakeClient:
        def list_products(self, params):
            assert params == _query().params
            return ProductPage(
                total=1,
                limit=20,
                offset=0,
                products=(product,),
            )

    monkeypatch.setattr(
        "backoffice.products.services._product_client",
        lambda: FakeClient(),
    )

    result = list_products(_query())

    assert result.total == 1
    assert result.limit == 20
    assert result.offset == 0
    assert result.data == [serialize_product_summary(product)]


def test_get_product_returns_only_serialized_detail(monkeypatch, product):
    class FakeClient:
        def get_product_details(self, identifier):
            assert identifier == "HB-MON-2102"
            return product

    monkeypatch.setattr(
        "backoffice.products.services._product_client",
        lambda: FakeClient(),
    )

    assert get_product("HB-MON-2102") == serialize_product_detail(product)


@pytest.mark.parametrize(
    ("client_error", "service_error", "code", "status"),
    [
        (
            ProductNotFoundError("private upstream not found"),
            ProductNotFoundServiceError,
            "PRODUCT_NOT_FOUND",
            404,
        ),
        (
            ProductTimeoutError("private upstream timeout"),
            ProductTimeoutServiceError,
            "PRODUCT_API_TIMEOUT",
            504,
        ),
        (
            ProductConnectionError("private network detail"),
            ProductUnavailableServiceError,
            "PRODUCT_API_UNAVAILABLE",
            503,
        ),
        (
            ProductUnexpectedStatusError(503),
            ProductUnavailableServiceError,
            "PRODUCT_API_UNAVAILABLE",
            503,
        ),
        (
            ProductUnexpectedStatusError(429),
            ProductInvalidResponseServiceError,
            "PRODUCT_API_INVALID_RESPONSE",
            502,
        ),
        (
            ProductInvalidJsonError("private invalid JSON detail"),
            ProductInvalidResponseServiceError,
            "PRODUCT_API_INVALID_RESPONSE",
            502,
        ),
        (
            ProductInvalidResponseError("private response detail"),
            ProductInvalidResponseServiceError,
            "PRODUCT_API_INVALID_RESPONSE",
            502,
        ),
    ],
)
def test_external_errors_are_mapped_stably(
    monkeypatch,
    client_error,
    service_error,
    code,
    status,
):
    class FakeClient:
        def list_products(self, params):
            raise client_error

    monkeypatch.setattr(
        "backoffice.products.services._product_client",
        lambda: FakeClient(),
    )

    with pytest.raises(service_error) as error:
        list_products(_query())

    assert error.value.code == code
    assert error.value.status == status
    assert str(client_error) not in str(error.value)


def test_invalid_local_configuration_becomes_internal_error(monkeypatch):
    def invalid_client():
        raise ProductClientConfigurationError("private configuration")

    monkeypatch.setattr(
        "backoffice.products.services._product_client",
        invalid_client,
    )

    with pytest.raises(ProductServiceError) as error:
        list_products(_query())

    assert error.value.code == "INTERNAL_ERROR"
    assert error.value.status == 500
    assert "private configuration" not in str(error.value)


def test_detail_without_validated_supplier_is_invalid(product):
    product_without_supplier = ProductData(
        **{
            **product.__dict__,
            "supplier": None,
        }
    )

    with pytest.raises(ProductInvalidResponseServiceError):
        serialize_product_detail(product_without_supplier)
