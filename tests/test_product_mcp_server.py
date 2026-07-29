"""Public behavioral checks for the Product MCP protocol adapter (P2-T02).

This suite intentionally uses the public MCP session and ASGI interfaces. It
does not inspect source text or require a socket, Product API, or PostgreSQL.
The broader integration suite contains the parameterized envelope and schema
coverage; these tests keep the repository-level server suite compatible with
that contract.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session


def _load_server(monkeypatch: pytest.MonkeyPatch):
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


async def _call_tool(server, name: str, arguments: dict[str, Any]):
    async with create_connected_server_and_client_session(server.mcp) as session:
        return await session.call_tool(name, arguments)


async def _get_asgi(server, path: str) -> tuple[int, bytes]:
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


def test_repository_server_suite_matches_the_public_mcp_surface(monkeypatch):
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

    resources, prompts = _run(_list_resources_and_prompts(server))
    assert resources.resources == []
    assert prompts.prompts == []


def test_repository_server_suite_checks_public_configuration_and_mcp_path(monkeypatch):
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
    assert any(route.path == "/health" for route in app.routes)


def test_repository_server_suite_checks_main_transport(monkeypatch):
    server = _load_server(monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(server.mcp, "run", fake_run)

    server.main()

    assert calls == [{"transport": "streamable-http"}]


def test_repository_server_suite_checks_health_in_memory_without_tool_access(
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


def test_repository_server_suite_preserves_structured_delegation(monkeypatch):
    server = _load_server(monkeypatch)
    product_tools = importlib.import_module("product_mcp_server.tools")
    calls: list[tuple[str, Any]] = []
    list_envelope = {"status": "success", "data": {"products": []}}
    detail_envelope = {"status": "not_found", "data": None}

    async def fake_list_products():
        calls.append(("list", None))
        return list_envelope

    async def fake_get_product_details(value: str):
        calls.append(("detail", value))
        return detail_envelope

    monkeypatch.setattr(product_tools, "list_products", fake_list_products)
    monkeypatch.setattr(
        product_tools, "get_product_details", fake_get_product_details
    )

    list_result = _run(_call_tool(server, "list_products", {}))
    detail_result = _run(
        _call_tool(server, "get_product_details", {"external_product_id": "SKU-1"})
    )

    assert calls == [("list", None), ("detail", "SKU-1")]
    assert list_result.isError is False
    assert list_result.structuredContent == list_envelope
    assert detail_result.isError is False
    assert detail_result.structuredContent == detail_envelope
