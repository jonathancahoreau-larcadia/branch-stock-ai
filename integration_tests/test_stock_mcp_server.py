"""Behavioral contract tests for the Stock MCP server.

All calls use the MCP SDK memory session or the server ASGI application
directly. The Stock tools are replaced with local doubles, so these tests never
open a socket or contact PostgreSQL, Docker, or an external API.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
import socket
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session


def _load_server():
    return importlib.import_module("stock_mcp_server.server")


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


async def _request_asgi(
    server, method: str, path: str
) -> tuple[int, bytes]:
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
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("memory-test", 1234),
            "server": ("memory-test", 80),
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


def test_mcp_publishes_exactly_the_four_stock_tools_and_no_extra_surface():
    server = _load_server()

    result = _run(_list_tools(server))
    assert {tool.name for tool in result.tools} == {
        "list_branch_stock",
        "get_stock_for_product",
        "find_branches_with_stock",
        "find_branches_for_shopping_list",
    }

    resources, prompts = _run(_list_resources_and_prompts(server))
    assert resources.resources == []
    assert prompts.prompts == []


def test_mcp_schemas_expose_the_contract_types_and_required_arguments():
    server = _load_server()
    tools = {tool.name: tool for tool in _run(_list_tools(server)).tools}

    branch_schema = tools["list_branch_stock"].inputSchema
    assert set(branch_schema["properties"]) == {"branch_id"}
    assert branch_schema["properties"]["branch_id"]["type"] == "integer"
    assert branch_schema["required"] == ["branch_id"]

    product_schema = tools["get_stock_for_product"].inputSchema
    assert set(product_schema["properties"]) == {"external_product_id"}
    assert product_schema["properties"]["external_product_id"]["type"] == "string"
    assert product_schema["required"] == ["external_product_id"]

    quantity_schema = tools["find_branches_with_stock"].inputSchema
    assert set(quantity_schema["properties"]) == {"external_product_id", "quantity"}
    assert quantity_schema["properties"]["external_product_id"]["type"] == "string"
    assert quantity_schema["properties"]["quantity"]["type"] == "integer"
    assert quantity_schema["required"] == ["external_product_id", "quantity"]

    shopping_schema = tools["find_branches_for_shopping_list"].inputSchema
    assert set(shopping_schema["properties"]) == {"items"}
    assert shopping_schema["properties"]["items"]["type"] == "array"
    assert shopping_schema["properties"]["items"]["items"]["type"] == "object"
    assert shopping_schema["required"] == ["items"]


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_call"),
    [
        ("list_branch_stock", {"branch_id": 0}, (0,)),
        ("list_branch_stock", {"branch_id": -4}, (-4,)),
        (
            "find_branches_with_stock",
            {"external_product_id": "SKU-1", "quantity": 0},
            ("SKU-1", 0),
        ),
        (
            "find_branches_with_stock",
            {"external_product_id": "SKU-1", "quantity": -4},
            ("SKU-1", -4),
        ),
    ],
)
def test_real_integer_values_are_delegated_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: dict[str, Any],
    expected_call: tuple[Any, ...],
):
    server = _load_server()
    stock_tools = importlib.import_module("stock_mcp_server.tools")
    calls: list[tuple[Any, ...]] = []

    def fake_tool(*received: Any) -> dict[str, Any]:
        calls.append(received)
        return {"status": "success", "data": {}}

    monkeypatch.setattr(stock_tools, tool_name, fake_tool)

    result = _run(_call_tool(server, tool_name, arguments))

    assert result.isError is False
    assert calls == [expected_call]


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("list_branch_stock", {"branch_id": "4"}),
        ("list_branch_stock", {"branch_id": True}),
        ("list_branch_stock", {"branch_id": 4.0}),
        ("list_branch_stock", {"branch_id": None}),
        ("list_branch_stock", {}),
        ("find_branches_with_stock", {"external_product_id": "SKU-1", "quantity": "4"}),
        ("find_branches_with_stock", {"external_product_id": "SKU-1", "quantity": True}),
        ("find_branches_with_stock", {"external_product_id": "SKU-1", "quantity": 4.0}),
        ("find_branches_with_stock", {"external_product_id": "SKU-1", "quantity": None}),
        ("find_branches_with_stock", {"external_product_id": "SKU-1"}),
    ],
)
def test_invalid_strict_integer_arguments_are_rejected_before_delegation(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: dict[str, Any],
):
    server = _load_server()
    stock_tools = importlib.import_module("stock_mcp_server.tools")
    calls: list[tuple[Any, ...]] = []

    def fail_if_called(*received: Any) -> dict[str, Any]:
        calls.append(received)
        return {"status": "success", "data": {}}

    monkeypatch.setattr(stock_tools, tool_name, fail_if_called)

    result = _run(_call_tool(server, tool_name, arguments))

    assert result.isError is True
    assert result.structuredContent is None
    assert calls == []


@pytest.mark.parametrize(
    "envelope",
    [
        {"status": "success", "data": {"branches": []}},
        {"status": "not_found", "data": None},
        {
            "status": "error",
            "error": {
                "code": "STOCK_DATABASE_UNAVAILABLE",
                "message": "Stock database is unavailable.",
            },
        },
    ],
)
def test_mcp_session_preserves_each_validated_envelope(
    monkeypatch: pytest.MonkeyPatch, envelope: dict[str, Any]
):
    server = _load_server()
    stock_tools = importlib.import_module("stock_mcp_server.tools")
    expected = copy.deepcopy(envelope)
    calls: list[tuple[str]] = []

    def fake_get_stock_for_product(value: str) -> dict[str, Any]:
        calls.append((value,))
        return envelope

    monkeypatch.setattr(
        stock_tools, "get_stock_for_product", fake_get_stock_for_product
    )

    result = _run(
        _call_tool(
            server,
            "get_stock_for_product",
            {"external_product_id": "SKU-1"},
        )
    )

    assert calls == [("SKU-1",)]
    assert result.isError is False
    assert result.structuredContent == expected
    assert envelope == expected


def test_items_are_passed_without_coercing_their_internal_values(
    monkeypatch: pytest.MonkeyPatch,
):
    server = _load_server()
    stock_tools = importlib.import_module("stock_mcp_server.tools")
    items = [{"external_product_id": "SKU-1", "quantity": "2", "extra": 4.0}]
    calls: list[list[dict[str, Any]]] = []

    def fake_tool(received: list[dict[str, Any]]) -> dict[str, Any]:
        calls.append(received)
        return {"status": "success", "data": {}}

    monkeypatch.setattr(stock_tools, "find_branches_for_shopping_list", fake_tool)

    result = _run(
        _call_tool(server, "find_branches_for_shopping_list", {"items": items})
    )

    assert result.isError is False
    assert calls == [items]
    assert isinstance(calls[0][0]["quantity"], str)
    assert isinstance(calls[0][0]["extra"], float)


def test_health_is_an_in_memory_route_without_tools_database_or_network(
    monkeypatch: pytest.MonkeyPatch,
):
    server = _load_server()
    stock_tools = importlib.import_module("stock_mcp_server.tools")
    monkeypatch.setenv(
        "STOCK_MCP_DATABASE_URL",
        "postgresql://stock_reader:secret-value@database/hbntory",
    )

    def fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("health must not call a Stock MCP tool")

    for tool_name in (
        "list_branch_stock",
        "get_stock_for_product",
        "find_branches_with_stock",
        "find_branches_for_shopping_list",
    ):
        monkeypatch.setattr(stock_tools, tool_name, fail_if_called)

    def fail_if_connect(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("health must not connect to the network")

    monkeypatch.setattr(socket.socket, "connect", fail_if_connect)

    status, body = _run(_request_asgi(server, "GET", "/health"))

    assert status == 200
    assert body == b'{"status":"ok"}'
    assert json.loads(body) == {"status": "ok"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_health_rejects_every_non_get_method(method: str):
    server = _load_server()

    status, _body = _run(_request_asgi(server, method, "/health"))

    assert status == 405
