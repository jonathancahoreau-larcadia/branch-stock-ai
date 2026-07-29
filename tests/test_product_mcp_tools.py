"""Contract tests for the public, read-only Product MCP tools.

These tests deliberately exercise the HTTP boundary.  They are the source of
truth for the Product MCP envelope; the adapter must not leak Product API
payloads or implementation-specific error details.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import sys
from collections.abc import Callable
from typing import Any

import httpx
import pytest


JSON_HEADERS = {"content-type": "application/json; charset=utf-8"}
BASE_URL = "http://product-api:8080/"


def _error(code: str, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message}}


INVALID_IDENTIFIER = _error(
    "INVALID_EXTERNAL_PRODUCT_ID", "Product identifier is invalid."
)
INVALID_CONFIGURATION = _error(
    "PRODUCT_API_INVALID_CONFIGURATION",
    "Product API configuration is invalid.",
)
TIMEOUT = _error("PRODUCT_API_TIMEOUT", "Product API request timed out.")
UNAVAILABLE = _error("PRODUCT_API_UNAVAILABLE", "Product API is unavailable.")
INVALID_RESPONSE = _error(
    "PRODUCT_API_INVALID_RESPONSE", "Product API response is invalid."
)


def _response(
    status_code: int,
    *,
    payload: Any | None = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    if payload is not None:
        return httpx.Response(status_code, json=payload, headers=headers or JSON_HEADERS)
    return httpx.Response(status_code, content=content or b"", headers=headers or JSON_HEADERS)


def _load_tools(monkeypatch: pytest.MonkeyPatch):
    """Import a fresh server package without making config import-time state."""
    monkeypatch.setenv("PRODUCT_API_BASE_URL", BASE_URL)
    monkeypatch.delenv("PRODUCT_API_TIMEOUT", raising=False)
    for name in tuple(sys.modules):
        if name == "product_mcp_server" or name.startswith("product_mcp_server."):
            del sys.modules[name]
    return importlib.import_module("product_mcp_server.tools")


def _install_http(
    monkeypatch: pytest.MonkeyPatch, outcome: httpx.Response | BaseException
) -> dict[str, list[Any]]:
    """Replace the transport, recording every HTTP client configuration and GET."""
    calls: dict[str, list[Any]] = {"timeouts": [], "urls": []}

    class CapturingAsyncClient:
        def __init__(self, *, timeout: Any, **_kwargs: Any) -> None:
            calls["timeouts"].append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def get(self, url: str, **_kwargs: Any) -> httpx.Response:
            calls["urls"].append(url)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)
    return calls


def _run(function: Callable[..., Any], *args: Any) -> dict[str, Any]:
    return asyncio.run(function(*args))


def _valid_list_payload(*, sku: str = "HB-MON-2102") -> dict[str, Any]:
    return {
        "count": 1,
        "limit": 20,
        "offset": 0,
        "results": [{"id": 4, "sku": sku, "name": "24 inch Compact Monitor"}],
    }


def _valid_detail_payload(*, sku: str = "HB-MON-2102") -> dict[str, Any]:
    return {
        "id": 4,
        "sku": sku,
        "name": "24 inch Compact Monitor",
        "supplier_email": "must-not-be-projected@example.test",
    }


def test_public_api_is_exactly_two_async_tools_and_contains_no_write_or_pg_code(monkeypatch):
    tools = _load_tools(monkeypatch)
    package = importlib.import_module("product_mcp_server")
    product_api = importlib.import_module("product_mcp_server.product_api")

    assert package.__all__ == ["list_products", "get_product_details"]
    assert tools.__all__ == ["list_products", "get_product_details"]
    assert all(
        inspect.iscoroutinefunction(getattr(package, name)) for name in package.__all__
    )

    tree = ast.parse(inspect.getsource(product_api))
    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    invoked_methods = {
        node.func.attr.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not imported_modules.intersection({"sqlalchemy", "psycopg", "asyncpg"})
    assert not invoked_methods.intersection({"post", "put", "patch", "delete"})


def test_list_projects_only_sku_and_name_from_valid_page(monkeypatch):
    tools = _load_tools(monkeypatch)
    calls = _install_http(monkeypatch, _response(200, payload=_valid_list_payload()))

    result = _run(tools.list_products)

    assert result == {
        "status": "success",
        "data": {
            "products": [
                {
                    "external_product_id": "HB-MON-2102",
                    "name": "24 inch Compact Monitor",
                }
            ]
        },
    }
    assert calls == {
        "timeouts": [5],
        "urls": ["http://product-api:8080/api/v1/products"],
    }


def test_list_accepts_a_consistent_empty_page(monkeypatch):
    tools = _load_tools(monkeypatch)
    calls = _install_http(
        monkeypatch,
        _response(200, payload={"count": 0, "limit": 20, "offset": 0, "results": []}),
    )

    assert _run(tools.list_products) == {"status": "success", "data": {"products": []}}
    assert calls["urls"] == ["http://product-api:8080/api/v1/products"]


def test_detail_accepts_numeric_identifier_and_projects_only_sku_and_name(monkeypatch):
    tools = _load_tools(monkeypatch)
    calls = _install_http(monkeypatch, _response(200, payload=_valid_detail_payload()))

    result = _run(tools.get_product_details, "4")

    assert result == {
        "status": "success",
        "data": {
            "external_product_id": "HB-MON-2102",
            "name": "24 inch Compact Monitor",
        },
    }
    assert calls["urls"] == ["http://product-api:8080/api/v1/products/4"]


def test_detail_normalizes_and_percent_encodes_a_sku_identifier(monkeypatch):
    tools = _load_tools(monkeypatch)
    calls = _install_http(
        monkeypatch,
        _response(200, payload=_valid_detail_payload(sku="HB MON/4")),
    )

    assert _run(tools.get_product_details, "  hb mon/4  ") == {
        "status": "success",
        "data": {"external_product_id": "HB MON/4", "name": "24 inch Compact Monitor"},
    }
    assert calls["urls"] == ["http://product-api:8080/api/v1/products/hb%20mon%2F4"]


@pytest.mark.parametrize("identifier", [None, 4, True, "", "   ", "x" * 256])
def test_detail_rejects_invalid_identifier_without_http(monkeypatch, identifier):
    tools = _load_tools(monkeypatch)
    calls = _install_http(monkeypatch, _response(200, payload=_valid_detail_payload()))

    assert _run(tools.get_product_details, identifier) == INVALID_IDENTIFIER
    assert calls == {"timeouts": [], "urls": []}


@pytest.mark.parametrize("base_url", [None, "", "product-api:8080", "ftp://product-api:8080"])
def test_invalid_product_api_base_url_is_a_per_call_configuration_error(monkeypatch, base_url):
    tools = _load_tools(monkeypatch)
    calls = _install_http(monkeypatch, _response(200, payload=_valid_list_payload()))
    if base_url is None:
        monkeypatch.delenv("PRODUCT_API_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("PRODUCT_API_BASE_URL", base_url)

    assert _run(tools.list_products) == INVALID_CONFIGURATION
    assert calls == {"timeouts": [], "urls": []}


@pytest.mark.parametrize("timeout", ["0", "-1", "not-a-number"])
def test_invalid_timeout_is_a_per_call_configuration_error(monkeypatch, timeout):
    tools = _load_tools(monkeypatch)
    calls = _install_http(monkeypatch, _response(200, payload=_valid_list_payload()))
    monkeypatch.setenv("PRODUCT_API_TIMEOUT", timeout)

    assert _run(tools.list_products) == INVALID_CONFIGURATION
    assert calls == {"timeouts": [], "urls": []}


def test_timeout_configuration_is_read_for_each_call_and_defaults_to_five(monkeypatch):
    tools = _load_tools(monkeypatch)
    calls = _install_http(monkeypatch, _response(200, payload=_valid_list_payload()))

    assert _run(tools.list_products)["status"] == "success"
    monkeypatch.setenv("PRODUCT_API_TIMEOUT", "2.5")
    assert _run(tools.list_products)["status"] == "success"

    assert calls["timeouts"] == [5, 2.5]


@pytest.mark.parametrize("function,args", [("list_products", ()), ("get_product_details", ("HB-MON-2102",))])
def test_not_found_uses_the_exact_mcp_envelope(monkeypatch, function, args):
    tools = _load_tools(monkeypatch)
    _install_http(monkeypatch, _response(404))

    assert _run(getattr(tools, function), *args) == {"status": "not_found", "data": None}


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (httpx.TimeoutException("late"), TIMEOUT),
        (httpx.RequestError("offline"), UNAVAILABLE),
        (_response(500), UNAVAILABLE),
        (_response(503), UNAVAILABLE),
        (_response(418), INVALID_RESPONSE),
    ],
)
def test_transport_and_http_failures_have_stable_exact_errors(monkeypatch, outcome, expected):
    tools = _load_tools(monkeypatch)
    _install_http(monkeypatch, outcome)

    assert _run(tools.list_products) == expected


@pytest.mark.parametrize(
    "response",
    [
        _response(200, payload=_valid_list_payload(), headers={"content-type": "text/html"}),
        _response(200, content=b"not-json"),
        _response(200, payload=[]),
        _response(200, payload={"count": True, "limit": 20, "offset": 0, "results": []}),
        _response(200, payload={"count": -1, "limit": 20, "offset": 0, "results": []}),
        _response(200, payload={"count": 1, "limit": True, "offset": 0, "results": []}),
        _response(200, payload={"count": 1, "limit": 101, "offset": 0, "results": []}),
        _response(200, payload={"count": 1, "limit": 20, "offset": True, "results": []}),
        _response(200, payload={"count": 1, "limit": 20, "offset": -1, "results": []}),
        _response(200, payload={"count": 1, "limit": 20, "offset": 0, "results": {}}),
        _response(200, payload={"count": 1, "limit": 20, "offset": 0, "results": []}),
        _response(200, payload={"count": 1, "limit": 20, "offset": 0, "results": [{"id": 4, "sku": " ", "name": "name"}]}),
        _response(200, payload={"count": 1, "limit": 20, "offset": 0, "results": [{"id": 4, "sku": "sku", "name": " "}]}),
    ],
)
def test_list_rejects_invalid_http_content_json_and_schema(monkeypatch, response):
    tools = _load_tools(monkeypatch)
    _install_http(monkeypatch, response)

    assert _run(tools.list_products) == INVALID_RESPONSE


@pytest.mark.parametrize(
    "payload",
    [
        {"sku": "HB-MON-2102", "name": "name"},
        {"id": True, "sku": "HB-MON-2102", "name": "name"},
        {"id": 0, "sku": "HB-MON-2102", "name": "name"},
        {"id": -1, "sku": "HB-MON-2102", "name": "name"},
        {"id": "4", "sku": "HB-MON-2102", "name": "name"},
        {"id": 4, "sku": "", "name": "name"},
        {"id": 4, "sku": "HB-MON-2102", "name": " "},
        {"id": 4, "sku": "OTHER", "name": "name"},
    ],
)
def test_detail_rejects_bad_schema_or_a_product_that_does_not_match_request(monkeypatch, payload):
    tools = _load_tools(monkeypatch)
    _install_http(monkeypatch, _response(200, payload=payload))

    assert _run(tools.get_product_details, "HB-MON-2102") == INVALID_RESPONSE
