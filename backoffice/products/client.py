"""Read-only client for validating products against the official API."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx


class ProductClientError(RuntimeError):
    """Base class for failures returned by the external Product API."""


class ProductClientConfigurationError(ProductClientError):
    """The client configuration cannot produce a safe request."""


class ProductNotFoundError(ProductClientError):
    """The requested identifier does not exist in the Product API."""


class ProductTimeoutError(ProductClientError):
    """The Product API did not answer within the configured timeout."""


class ProductConnectionError(ProductClientError):
    """The Product API could not be reached."""


class ProductUnexpectedStatusError(ProductClientError):
    """The Product API returned an undocumented HTTP status."""


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
        return identifier in {str(self.id).strip(), self.sku.strip()}


class ProductClient:
    """Fetch and validate one product without persisting product details."""

    def __init__(
        self,
        base_url: str,
        timeout: float | str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized_base_url = str(base_url).strip().rstrip("/")
        if not normalized_base_url:
            raise ProductClientConfigurationError(
                "Product API base URL is required."
            )

        try:
            normalized_timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ProductClientConfigurationError(
                "Product API timeout must be a positive number."
            ) from exc

        if normalized_timeout <= 0:
            raise ProductClientConfigurationError(
                "Product API timeout must be a positive number."
            )

        self._base_url = normalized_base_url
        self._timeout = normalized_timeout
        self._transport = transport

    def get_product(self, identifier: str) -> ProductValidation:
        """Return the minimum validated representation of one product."""
        encoded_identifier = quote(identifier, safe="")
        url = (
            f"{self._base_url}/api/v1/products/{encoded_identifier}"
        )

        try:
            with httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.get(
                    url,
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

        if response.status_code == 404:
            raise ProductNotFoundError("Product identifier was not found.")
        if response.status_code != 200:
            raise ProductUnexpectedStatusError(
                "Product API returned unexpected status "
                f"{response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProductInvalidJsonError(
                "Product API returned invalid JSON."
            ) from exc

        return self._parse_product(payload)

    @staticmethod
    def _parse_product(payload: object) -> ProductValidation:
        if not isinstance(payload, dict):
            raise ProductInvalidResponseError(
                "Product API response must be a JSON object."
            )

        required_fields = {"id", "sku", "name", "discontinued"}
        if not required_fields.issubset(payload):
            raise ProductInvalidResponseError(
                "Product API response is missing required fields."
            )

        product_id = payload["id"]
        sku = payload["sku"]
        name = payload["name"]
        discontinued = payload["discontinued"]

        valid_id = (
            isinstance(product_id, (int, str))
            and not isinstance(product_id, bool)
            and bool(str(product_id).strip())
        )
        if not valid_id:
            raise ProductInvalidResponseError(
                "Product API response contains an invalid id."
            )
        if not isinstance(sku, str) or not sku.strip():
            raise ProductInvalidResponseError(
                "Product API response contains an invalid sku."
            )
        if not isinstance(name, str) or not name.strip():
            raise ProductInvalidResponseError(
                "Product API response contains an invalid name."
            )
        if not isinstance(discontinued, bool):
            raise ProductInvalidResponseError(
                "Product API response contains an invalid discontinued flag."
            )

        return ProductValidation(
            id=product_id,
            sku=sku.strip(),
            discontinued=discontinued,
        )


__all__ = [
    "ProductClient",
    "ProductClientConfigurationError",
    "ProductClientError",
    "ProductConnectionError",
    "ProductInvalidJsonError",
    "ProductInvalidResponseError",
    "ProductNotFoundError",
    "ProductTimeoutError",
    "ProductUnexpectedStatusError",
    "ProductValidation",
]
