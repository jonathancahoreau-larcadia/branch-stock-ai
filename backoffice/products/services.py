"""Product API orchestration and stable Backoffice serialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from flask import current_app

from .client import (
    ProductClient,
    ProductClientConfigurationError,
    ProductConnectionError,
    ProductData,
    ProductInvalidIdentifierError,
    ProductInvalidJsonError,
    ProductInvalidResponseError,
    ProductNotFoundError,
    ProductPage,
    ProductTimeoutError,
    ProductUnexpectedStatusError,
)
from .schemas import ProductListQuery


class ProductServiceError(RuntimeError):
    """A stable failure returned by product consultation services."""

    code = "INTERNAL_ERROR"
    status = 500


class ProductNotFoundServiceError(ProductServiceError):
    code = "PRODUCT_NOT_FOUND"
    status = 404


class ProductTimeoutServiceError(ProductServiceError):
    code = "PRODUCT_API_TIMEOUT"
    status = 504


class ProductUnavailableServiceError(ProductServiceError):
    code = "PRODUCT_API_UNAVAILABLE"
    status = 503


class ProductInvalidResponseServiceError(ProductServiceError):
    code = "PRODUCT_API_INVALID_RESPONSE"
    status = 502


@dataclass(frozen=True)
class ProductListResult:
    """Serialized product page and validated external pagination."""

    data: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


def _product_client() -> ProductClient:
    return ProductClient(
        current_app.config.get("PRODUCT_API_BASE_URL"),
        current_app.config.get("PRODUCT_API_TIMEOUT"),
    )


Result = TypeVar("Result")


def _external_call(operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except ProductNotFoundError as error:
        raise ProductNotFoundServiceError from error
    except ProductTimeoutError as error:
        raise ProductTimeoutServiceError from error
    except ProductConnectionError as error:
        raise ProductUnavailableServiceError from error
    except ProductUnexpectedStatusError as error:
        if 500 <= error.status_code <= 599:
            raise ProductUnavailableServiceError from error
        raise ProductInvalidResponseServiceError from error
    except (
        ProductInvalidJsonError,
        ProductInvalidResponseError,
    ) as error:
        raise ProductInvalidResponseServiceError from error
    except (
        ProductClientConfigurationError,
        ProductInvalidIdentifierError,
    ) as error:
        raise ProductServiceError from error


def serialize_product_summary(product: ProductData) -> dict[str, Any]:
    """Serialize the exact product fields allowed in list responses."""
    return {
        "external_product_id": product.sku,
        "name": product.name,
        "category": product.category,
        "brand": product.brand,
        "unit_price": product.unit_price,
        "currency": product.currency,
        "discontinued": product.discontinued,
    }


def serialize_product_detail(product: ProductData) -> dict[str, Any]:
    """Serialize a full product without supplier contact or duplicate IDs."""
    if product.supplier is None:
        raise ProductInvalidResponseServiceError
    supplier = product.supplier
    return {
        "external_product_id": product.sku,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "brand": product.brand,
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "country": supplier.country,
            "lead_time_days": supplier.lead_time_days,
            "reliability_score": supplier.reliability_score,
        },
        "unit_price": product.unit_price,
        "currency": product.currency,
        "discontinued": product.discontinued,
        "weight_kg": product.weight_kg,
        "tags": list(product.tags),
        "updated_at": product.updated_at,
    }


def list_products(query: ProductListQuery) -> ProductListResult:
    """Fetch and serialize one validated external catalog page."""
    try:
        client = _product_client()
    except ProductClientConfigurationError as error:
        raise ProductServiceError from error
    page: ProductPage = _external_call(
        lambda: client.list_products(query.params)
    )
    return ProductListResult(
        data=[
            serialize_product_summary(product)
            for product in page.products
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


def get_product(identifier: str) -> dict[str, Any]:
    """Fetch and serialize one validated external product detail."""
    try:
        client = _product_client()
    except ProductClientConfigurationError as error:
        raise ProductServiceError from error
    product = _external_call(
        lambda: client.get_product_details(identifier)
    )
    return serialize_product_detail(product)


__all__ = [
    "ProductInvalidResponseServiceError",
    "ProductListResult",
    "ProductNotFoundServiceError",
    "ProductServiceError",
    "ProductTimeoutServiceError",
    "ProductUnavailableServiceError",
    "get_product",
    "list_products",
    "serialize_product_detail",
    "serialize_product_summary",
]
