"""Behavioral contract tests for the Product MCP server.

The tests use the MCP SDK's in-memory client/server session. Product tool
functions are replaced with doubles before every call, so the suite never
contacts the Product API or opens a network socket.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session


def _load_server(monkeypatch: pytest.MonkeyPatch):
    """Load the server with harmless configuration for the imported adapter."""
    monkeypatch.setenv("PRODUCT_API_BASE_URL", "http://product-api.invalid")
    return importlib.import_module("product_mcp_server.server")


def _run(coroutine):
    return asyncio.run(coroutine)


async def _list_tools(server):
    async with create_connected_server_and_client_session(server.mcp) as session:
        return await session.list_tools()


async def _list_resources_and_prompts(server):
    async with create_connected_server_and_client_session(server.mcp) as session:
        return await session.list_resources(), await session.list_prompts()


async def _call_tool(server, name: str, arguments: dict[str, Any] | None = None):
    async with create_connected_server_and_client_session(server.mcp) as session:
        return await session.call_tool(name, arguments)


async def _get_asgi(server, path: str) -> tuple[int, bytes]:
    """Call one public ASGI endpoint without opening a socket."""
    sent: list[dict[str, Any]] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    app = server.mcp.streamable_http_app()
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("testclient", 1234),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )

    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return start["status"], body


def test_public_tool_list_contains_exactly_the_two_product_tools(monkeypatch):
    server = _load_server(monkeypatch)

    result = _run(_list_tools(server))
    tools = {tool.name: tool for tool in result.tools}

    assert set(tools) == {"list_products", "get_product_details"}
    assert tools["list_products"].inputSchema["properties"] == {}
    assert "required" not in tools["list_products"].inputSchema
    details_properties = tools["get_product_details"].inputSchema["properties"]
    assert set(details_properties) == {"external_product_id"}
    assert details_properties["external_product_id"]["type"] == "string"
    assert tools["get_product_details"].inputSchema["required"] == [
        "external_product_id"
    ]


def test_no_resources_or_prompts_are_published(monkeypatch):
    server = _load_server(monkeypatch)

    resources, prompts = _run(_list_resources_and_prompts(server))

    assert resources.resources == []
    assert prompts.prompts == []


def test_public_server_configuration_and_streamable_http_path(monkeypatch):
    server = _load_server(monkeypatch)

    assert server.mcp.name == "Product MCP Server"
    settings = server.mcp.settings
    assert settings.host == "0.0.0.0"
    assert settings.port == 8100
    assert settings.streamable_http_path == "/mcp"
    assert settings.stateless_http is True
    assert settings.json_response is True

    app = server.mcp.streamable_http_app()
    assert any(route.path == "/mcp" for route in app.routes)
    assert any(route.path == "/health" and "GET" in route.methods for route in app.routes)


@pytest.mark.parametrize(
    "envelope",
    [
        {"status": "success", "data": {"products": []}},
        {"status": "not_found", "data": None},
        {
            "status": "error",
            "error": {
                "code": "PRODUCT_API_UNAVAILABLE",
                "message": "Product API is unavailable.",
            },
        },
    ],
)
def test_list_products_delegates_once_and_returns_double_result(
    monkeypatch, envelope
):
    server = _load_server(monkeypatch)
    product_tools = importlib.import_module("product_mcp_server.tools")
    expected = copy.deepcopy(envelope)
    calls: list[tuple[Any, ...]] = []

    async def fake_list_products():
        calls.append(())
        return envelope

    monkeypatch.setattr(product_tools, "list_products", fake_list_products)

    result = _run(_call_tool(server, "list_products"))

    assert calls == [()]
    assert result.isError is False
    assert result.structuredContent == expected
    assert envelope == expected


@pytest.mark.parametrize(
    "envelope",
    [
        {"status": "success", "data": {"external_product_id": "SKU-1"}},
        {"status": "not_found", "data": None},
        {
            "status": "error",
            "error": {
                "code": "PRODUCT_API_INVALID_RESPONSE",
                "message": "Product API response is invalid.",
            },
        },
    ],
)
def test_get_product_details_delegates_once_with_exact_argument_and_returns_result(
    monkeypatch, envelope
):
    server = _load_server(monkeypatch)
    product_tools = importlib.import_module("product_mcp_server.tools")
    expected = copy.deepcopy(envelope)
    calls: list[tuple[str]] = []
    external_product_id = " SKU-1 / blue "

    async def fake_get_product_details(value: str):
        calls.append((value,))
        return envelope

    monkeypatch.setattr(
        product_tools, "get_product_details", fake_get_product_details
    )

    result = _run(
        _call_tool(
            server,
            "get_product_details",
            {"external_product_id": external_product_id},
        )
    )

    assert calls == [(external_product_id,)]
    assert result.isError is False
    assert result.structuredContent == expected
    assert envelope == expected


@pytest.mark.parametrize(
    "arguments",
    [{}, {"external_product_id": 4}, {"external_product_id": None}],
)
def test_invalid_product_detail_arguments_are_rejected_before_the_double(
    monkeypatch, arguments
):
    server = _load_server(monkeypatch)
    product_tools = importlib.import_module("product_mcp_server.tools")
    calls: list[str] = []

    async def fake_get_product_details(value: str):
        calls.append(value)
        return {"status": "success", "data": {}}

    monkeypatch.setattr(
        product_tools, "get_product_details", fake_get_product_details
    )

    result = _run(_call_tool(server, "get_product_details", arguments))

    assert result.isError is True
    assert result.structuredContent is None
    assert calls == []


def test_main_selects_only_streamable_http_transport(monkeypatch):
    server = _load_server(monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(server.mcp, "run", fake_run)

    server.main()

    assert calls == [{"transport": "streamable-http"}]


def test_health_is_a_public_in_memory_asgi_route_without_calling_product_tools(
    monkeypatch,
):
    server = _load_server(monkeypatch)
    product_tools = importlib.import_module("product_mcp_server.tools")

    async def fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("health must not call a Product MCP tool")

    monkeypatch.setattr(product_tools, "list_products", fail_if_called)
    monkeypatch.setattr(product_tools, "get_product_details", fail_if_called)

    status, body = _run(_get_asgi(server, "/health"))

    assert status == 200
    assert body == b'{"status":"ok"}'
    assert json.loads(body) == {"status": "ok"}
