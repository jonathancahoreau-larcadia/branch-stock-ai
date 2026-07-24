"""Validated read-only client for the official Product API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Mapping
from urllib.parse import quote

import httpx


class ProductClientError(RuntimeError):
    """Base class for failures returned by the external Product API."""


class ProductClientConfigurationError(ProductClientError):
    """The client configuration cannot produce a safe request."""


class ProductInvalidIdentifierError(ProductClientError):
    """The supplied external identifier cannot produce a valid request."""


class ProductNotFoundError(ProductClientError):
    """The requested identifier does not exist in the Product API."""


class ProductTimeoutError(ProductClientError):
    """The Product API did not answer within the configured timeout."""


class ProductConnectionError(ProductClientError):
    """The Product API could not be reached."""


class ProductUnexpectedStatusError(ProductClientError):
    """The Product API returned an undocumented HTTP status."""

    def __init__(self, status_code: int) -> None:
        super().__init__(
            f"Product API returned unexpected status {status_code}."
        )
        self.status_code = status_code


class ProductInvalidJsonError(ProductClientError):
    """The Product API response body is not valid JSON."""


class ProductInvalidResponseError(ProductClientError):
    """The Product API JSON does not satisfy its minimum contract."""


@dataclass(frozen=True)
class ProductValidation:
    """Only the external fields required to validate a stock seed."""

    id: int | str
    sku: str
    discontinued: bool

    def matches(self, identifier: str) -> bool:
        """Return whether the API object matches an ID or SKU request."""
        normalized = identifier.strip().casefold()
        return normalized in {
            str(self.id).strip().casefold(),
            self.sku.strip().casefold(),
        }


@dataclass(frozen=True)
class ProductSupplier:
    """Validated supplier fields used by a product detail response."""

    id: str
    name: str
    country: str
    lead_time_days: int
    reliability_score: float


@dataclass(frozen=True)
class ProductData:
    """Validated catalog product independent from the external JSON."""

    id: int
    sku: str
    name: str
    description: str
    category: str
    brand: str
    supplier_id: str
    supplier_name: str
    unit_price: float
    currency: str
    discontinued: bool
    weight_kg: float
    tags: tuple[str, ...]
    updated_at: str
    supplier: ProductSupplier | None = None

    def matches(self, identifier: str) -> bool:
        """Return whether this product matches a numeric ID or SKU."""
        normalized = identifier.strip().casefold()
        return normalized in {
            str(self.id).casefold(),
            self.sku.casefold(),
        }


@dataclass(frozen=True)
class ProductPage:
    """A validated page returned by the external catalog."""

    total: int
    limit: int
    offset: int
    products: tuple[ProductData, ...]


def _required_string(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProductInvalidResponseError(
            f"Product API response contains an invalid {field}."
        )
    return value.strip()


def _required_integer(
    payload: dict,
    field: str,
    *,
    minimum: int = 0,
) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProductInvalidResponseError(
            f"Product API response contains an invalid {field}."
        )
    if value < minimum:
        raise ProductInvalidResponseError(
            f"Product API response contains an invalid {field}."
        )
    return value


def _required_number(
    payload: dict,
    field: str,
    *,
    minimum: float | None = None,
) -> float:
    value = payload.get(field)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ProductInvalidResponseError(
            f"Product API response contains an invalid {field}."
        )
    normalized = float(value)
    if minimum is not None and normalized < minimum:
        raise ProductInvalidResponseError(
            f"Product API response contains an invalid {field}."
        )
    return normalized


def _required_utc_datetime(payload: dict, field: str) -> str:
    value = _required_string(payload, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProductInvalidResponseError(
            f"Product API response contains an invalid {field}."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(
        parsed
    ):
        raise ProductInvalidResponseError(
            f"Product API response contains an invalid {field}."
        )
    return parsed.astimezone(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def _parse_supplier(payload: object) -> ProductSupplier:
    if not isinstance(payload, dict):
        raise ProductInvalidResponseError(
            "Product API response contains an invalid supplier."
        )
    reliability_score = _required_number(
        payload,
        "reliability_score",
        minimum=0,
    )
    if reliability_score > 1:
        raise ProductInvalidResponseError(
            "Product API response contains an invalid reliability_score."
        )
    return ProductSupplier(
        id=_required_string(payload, "id"),
        name=_required_string(payload, "name"),
        country=_required_string(payload, "country"),
        lead_time_days=_required_integer(
            payload,
            "lead_time_days",
            minimum=0,
        ),
        reliability_score=reliability_score,
    )


def _parse_product(
    payload: object,
    *,
    require_supplier: bool,
) -> ProductData:
    if not isinstance(payload, dict):
        raise ProductInvalidResponseError(
            "Product API product must be a JSON object."
        )

    product_id = _required_integer(payload, "id", minimum=1)
    sku = _required_string(payload, "sku")
    tags_value = payload.get("tags")
    if not isinstance(tags_value, list):
        raise ProductInvalidResponseError(
            "Product API response contains invalid tags."
        )
    tags: list[str] = []
    for tag in tags_value:
        if not isinstance(tag, str) or not tag.strip():
            raise ProductInvalidResponseError(
                "Product API response contains invalid tags."
            )
        tags.append(tag.strip())

    discontinued = payload.get("discontinued")
    if not isinstance(discontinued, bool):
        raise ProductInvalidResponseError(
            "Product API response contains an invalid discontinued flag."
        )

    supplier = None
    if require_supplier:
        supplier = _parse_supplier(payload.get("supplier"))

    supplier_id = _required_string(payload, "supplier_id")
    supplier_name = _required_string(payload, "supplier_name")
    if supplier is not None and (
        supplier.id != supplier_id or supplier.name != supplier_name
    ):
        raise ProductInvalidResponseError(
            "Product API supplier data is inconsistent."
        )

    return ProductData(
        id=product_id,
        sku=sku,
        name=_required_string(payload, "name"),
        description=_required_string(payload, "description"),
        category=_required_string(payload, "category"),
        brand=_required_string(payload, "brand"),
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        unit_price=_required_number(payload, "unit_price", minimum=0),
        currency=_required_string(payload, "currency"),
        discontinued=discontinued,
        weight_kg=_required_number(payload, "weight_kg", minimum=0),
        tags=tuple(tags),
        updated_at=_required_utc_datetime(payload, "updated_at"),
        supplier=supplier,
    )


class ProductClient:
    """Fetch and validate catalog data without local persistence."""

    def __init__(
        self,
        base_url: str,
        timeout: float | str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(base_url, str):
            raise ProductClientConfigurationError(
                "Product API base URL is required."
            )
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise ProductClientConfigurationError(
                "Product API base URL is required."
            )
        try:
            parsed_base_url = httpx.URL(normalized_base_url)
        except httpx.InvalidURL as exc:
            raise ProductClientConfigurationError(
                "Product API base URL is invalid."
            ) from exc
        if (
            parsed_base_url.scheme not in {"http", "https"}
            or not parsed_base_url.host
            or parsed_base_url.query
            or parsed_base_url.fragment
        ):
            raise ProductClientConfigurationError(
                "Product API base URL is invalid."
            )

        try:
            normalized_timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ProductClientConfigurationError(
                "Product API timeout must be a positive number."
            ) from exc

        if not math.isfinite(normalized_timeout) or normalized_timeout <= 0:
            raise ProductClientConfigurationError(
                "Product API timeout must be a positive number."
            )

        self._base_url = normalized_base_url
        self._timeout = normalized_timeout
        self._transport = transport

    def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> object:
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json"},
                )
        except httpx.TimeoutException as exc:
            raise ProductTimeoutError(
                "Product API request timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise ProductConnectionError(
                "Product API is unreachable."
            ) from exc

        if response.status_code == 404 and allow_not_found:
            raise ProductNotFoundError(
                "Product identifier was not found."
            )
        if response.status_code != 200:
            raise ProductUnexpectedStatusError(response.status_code)

        content_type = response.headers.get("content-type", "")
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type != "application/json" and not media_type.endswith(
            "+json"
        ):
            raise ProductInvalidResponseError(
                "Product API response has an invalid content type."
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ProductInvalidJsonError(
                "Product API returned invalid JSON."
            ) from exc

    @staticmethod
    def _validated_identifier(identifier: object) -> str:
        if not isinstance(identifier, str):
            raise ProductInvalidIdentifierError(
                "Product identifier must be a string."
            )
        normalized = identifier.strip()
        if not normalized or len(normalized) > 255:
            raise ProductInvalidIdentifierError(
                "Product identifier is invalid."
            )
        return normalized

    def list_products(
        self,
        params: Mapping[str, str],
    ) -> ProductPage:
        """Return one validated page from the official list endpoint."""
        payload = self._request_json(
            "/api/v1/products",
            params=params,
        )
        if not isinstance(payload, dict):
            raise ProductInvalidResponseError(
                "Product API list response must be a JSON object."
            )

        total = _required_integer(payload, "count", minimum=0)
        limit = _required_integer(payload, "limit", minimum=1)
        offset = _required_integer(payload, "offset", minimum=0)
        if limit > 100:
            raise ProductInvalidResponseError(
                "Product API response contains an invalid limit."
            )

        try:
            expected_limit = int(params.get("limit", "20"))
            expected_offset = int(params.get("offset", "0"))
        except (TypeError, ValueError) as exc:
            raise ProductInvalidResponseError(
                "Product API request pagination is invalid."
            ) from exc
        if limit != expected_limit or offset != expected_offset:
            raise ProductInvalidResponseError(
                "Product API pagination does not match the request."
            )

        results = payload.get("results")
        if not isinstance(results, list):
            raise ProductInvalidResponseError(
                "Product API list response is missing results."
            )
        expected_size = (
            min(limit, total - offset) if offset < total else 0
        )
        if len(results) != expected_size:
            raise ProductInvalidResponseError(
                "Product API pagination is inconsistent."
            )

        products = tuple(
            _parse_product(product, require_supplier=False)
            for product in results
        )
        return ProductPage(
            total=total,
            limit=limit,
            offset=offset,
            products=products,
        )

    def get_product_details(self, identifier: str) -> ProductData:
        """Return a validated full product matching an ID or SKU."""
        normalized_identifier = self._validated_identifier(identifier)
        encoded_identifier = quote(normalized_identifier, safe="")
        payload = self._request_json(
            f"/api/v1/products/{encoded_identifier}",
            allow_not_found=True,
        )
        product = _parse_product(payload, require_supplier=True)
        if not product.matches(normalized_identifier):
            raise ProductInvalidResponseError(
                "Product API returned a different product."
            )
        return product

    def get_product(self, identifier: str) -> ProductValidation:
        """Return the seed-compatible minimum product representation."""
        product = self.get_product_details(identifier)
        return ProductValidation(
            id=product.id,
            sku=product.sku,
            discontinued=product.discontinued,
        )


__all__ = [
    "ProductClient",
    "ProductClientConfigurationError",
    "ProductClientError",
    "ProductConnectionError",
    "ProductData",
    "ProductInvalidIdentifierError",
    "ProductInvalidJsonError",
    "ProductInvalidResponseError",
    "ProductNotFoundError",
    "ProductPage",
    "ProductSupplier",
    "ProductTimeoutError",
    "ProductUnexpectedStatusError",
    "ProductValidation",
]
