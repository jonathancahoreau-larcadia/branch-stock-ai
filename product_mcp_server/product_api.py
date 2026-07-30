"""Asynchronous, read-only access to the external Product API."""

from __future__ import annotations

import math
import os
from typing import Any
from urllib.parse import quote, urlsplit

import httpx


DEFAULT_TIMEOUT = 5

_INVALID_CONFIGURATION = {
    "status": "error",
    "error": {
        "code": "PRODUCT_API_INVALID_CONFIGURATION",
        "message": "Product API configuration is invalid.",
    },
}
_TIMEOUT = {
    "status": "error",
    "error": {
        "code": "PRODUCT_API_TIMEOUT",
        "message": "Product API request timed out.",
    },
}
_UNAVAILABLE = {
    "status": "error",
    "error": {
        "code": "PRODUCT_API_UNAVAILABLE",
        "message": "Product API is unavailable.",
    },
}
_INVALID_RESPONSE = {
    "status": "error",
    "error": {
        "code": "PRODUCT_API_INVALID_RESPONSE",
        "message": "Product API response is invalid.",
    },
}


def _configuration() -> tuple[str, int | float] | None:
    base_url = os.environ.get("PRODUCT_API_BASE_URL", "").strip()
    parsed_url = urlsplit(base_url)
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        return None

    timeout_value = os.environ.get("PRODUCT_API_TIMEOUT")
    if timeout_value is None:
        timeout: int | float = DEFAULT_TIMEOUT
    else:
        try:
            timeout = float(timeout_value)
        except ValueError:
            return None
        if not math.isfinite(timeout) or timeout <= 0:
            return None

    return base_url.rstrip("/"), timeout


def _is_json_response(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "")
    return content_type.split(";", 1)[0].strip().lower() == "application/json"


async def _get(
    path: str,
    *,
    params: dict[str, int] | None = None,
) -> dict[str, Any]:
    configuration = _configuration()
    if configuration is None:
        return _INVALID_CONFIGURATION

    base_url, timeout = configuration
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url}{path}", params=params)
    except httpx.TimeoutException:
        return _TIMEOUT
    except httpx.RequestError:
        return _UNAVAILABLE

    if response.status_code == 404:
        return {"status": "not_found", "data": None}
    if 500 <= response.status_code <= 599:
        return _UNAVAILABLE
    if response.status_code != 200 or not _is_json_response(response):
        return _INVALID_RESPONSE

    try:
        payload = response.json()
    except (TypeError, ValueError):
        return _INVALID_RESPONSE
    return {"status": "success", "data": payload}


async def list_products(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Fetch one Product API page without exposing transport exceptions."""
    return await _get(
        "/api/v1/products",
        params={"limit": limit, "offset": offset},
    )


async def get_product_details(external_product_id: str) -> dict[str, Any]:
    """Fetch one product using a safely encoded path component."""
    encoded_identifier = quote(external_product_id, safe="")
    return await _get(f"/api/v1/products/{encoded_identifier}")
