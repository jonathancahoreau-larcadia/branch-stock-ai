"""Contract tests for the public AI-to-MCP Streamable HTTP client.

All transport and SDK session objects are local doubles.  No test opens a
socket or contacts a Product MCP, Stock MCP, Product API, database, Docker
service, or the Internet.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import inspect
import math
import socket
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import mcp
import pytest
from mcp.client import session as mcp_session
from mcp.client import streamable_http


PRODUCT_URL = "https://product.example"
STOCK_URL = "http://stock.example"
PRODUCT_TOOLS = ("list_products", "get_product_details")
STOCK_TOOLS = (
    "list_branch_stock",
    "get_stock_for_product",
    "find_branches_with_stock",
    "find_branches_for_shopping_list",
)


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture(autouse=True)
def forbid_real_sockets(monkeypatch):
    def fail_if_socket_connects(*_args, **_kwargs):
        raise AssertionError("AI MCP client tests must not connect a real socket")

    # asyncio.run() needs to create its local wakeup socket. Guard the network
    # connection boundary instead, so the event loop remains usable while any
    # accidental upstream connection still fails immediately.
    monkeypatch.setattr(socket.socket, "connect", fail_if_socket_connects)
    monkeypatch.setattr(socket, "create_connection", fail_if_socket_connects)


def _result(envelope: Any, *, is_error: bool = False):
    return SimpleNamespace(isError=is_error, structuredContent=envelope)


def _patch_sdk(monkeypatch, client_module, state, *, result=None, error_phase=None, error=None):
    """Install doubles at both public SDK locations and imported aliases."""

    class FakeTransport:
        def __init__(self, url, *args, **kwargs):
            state["transport"] = {
                "url": url,
                "args": args,
                "kwargs": kwargs,
            }
            if error_phase == "transport_construct":
                raise error

        async def __aenter__(self):
            state["transport_entered"] += 1
            if error_phase == "transport_enter":
                raise error
            return ("read-stream", "write-stream", lambda: "session-id")

        async def __aexit__(self, *_args):
            state["transport_exited"] += 1

    class FakeSession:
        def __init__(self, read_stream, write_stream, *args, **kwargs):
            state["session_constructor"] = {
                "read_stream": read_stream,
                "write_stream": write_stream,
                "args": args,
                "kwargs": kwargs,
            }
            if error_phase == "session_construct":
                raise error

        async def __aenter__(self):
            state["session_entered"] += 1
            if error_phase == "session_enter":
                raise error
            return self

        async def __aexit__(self, *_args):
            state["session_exited"] += 1

        async def initialize(self):
            state["initialize_calls"] += 1
            if error_phase == "initialize":
                raise error
            return SimpleNamespace()

        async def call_tool(self, name, arguments=None, *args, **kwargs):
            state["tool_calls"].append(
                {"name": name, "arguments": arguments, "args": args, "kwargs": kwargs}
            )
            if error_phase == "call_tool":
                raise error
            return result

    monkeypatch.setattr(streamable_http, "streamablehttp_client", FakeTransport)
    monkeypatch.setattr(mcp_session, "ClientSession", FakeSession)
    monkeypatch.setattr(mcp, "ClientSession", FakeSession)
    monkeypatch.setattr(client_module, "streamablehttp_client", FakeTransport, raising=False)
    monkeypatch.setattr(client_module, "ClientSession", FakeSession, raising=False)


def _new_state():
    return {
        "transport": None,
        "transport_entered": 0,
        "transport_exited": 0,
        "session_constructor": None,
        "session_entered": 0,
        "session_exited": 0,
        "initialize_calls": 0,
        "tool_calls": [],
    }


def _client_module():
    return importlib.import_module("ai_service.mcp_client")


def _assert_client_error(exc_info, code):
    error = exc_info.value
    assert isinstance(error.code, str)
    assert error.code == code
    assert isinstance(error.message, str)
    assert error.message
    assert "SECRET" not in error.message
    assert "password" not in error.message.lower()
    assert "traceback" not in error.message.lower()


def test_public_client_surface_and_signatures_are_stable():
    module = _client_module()
    assert hasattr(module, "MCPClient")
    assert hasattr(module, "MCPClientError")
    assert issubclass(module.MCPClientError, RuntimeError)
    error = module.MCPClientError("MCP_ERROR", "safe message")
    assert error.code == "MCP_ERROR"
    assert error.message == "safe message"
    assert list(inspect.signature(module.MCPClient).parameters) == [
        "product_mcp_url",
        "stock_mcp_url",
        "timeout_seconds",
    ]
    constructor_parameters = inspect.signature(module.MCPClient).parameters
    assert constructor_parameters["product_mcp_url"].default is None
    assert constructor_parameters["stock_mcp_url"].default is None
    assert constructor_parameters["timeout_seconds"].default == 5.0
    assert list(inspect.signature(module.MCPClient.call_product_tool).parameters) == [
        "self",
        "tool_name",
        "arguments",
    ]
    assert list(inspect.signature(module.MCPClient.call_stock_tool).parameters) == [
        "self",
        "tool_name",
        "arguments",
    ]
    assert inspect.signature(module.MCPClient.call_product_tool).parameters[
        "arguments"
    ].default is None
    assert inspect.signature(module.MCPClient.call_stock_tool).parameters[
        "arguments"
    ].default is None
    assert inspect.iscoroutinefunction(module.MCPClient.call_product_tool)
    assert inspect.iscoroutinefunction(module.MCPClient.call_stock_tool)


@pytest.mark.parametrize("path", ["", "/", "/mcp"])
@pytest.mark.parametrize("target", ["product", "stock"])
def test_valid_urls_are_canonicalized_to_the_mcp_endpoint(monkeypatch, path, target):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))

    client = module.MCPClient(
        product_mcp_url=f"https://product.example{path}",
        stock_mcp_url=f"http://stock.example{path}",
    )
    if target == "product":
        _run(client.call_product_tool("list_products"))
        expected_url = "https://product.example/mcp"
    else:
        _run(client.call_stock_tool("list_branch_stock"))
        expected_url = "http://stock.example/mcp"

    assert state["transport"]["url"] == expected_url


def test_explicit_urls_take_precedence_over_environment(monkeypatch):
    module = _client_module()
    monkeypatch.setenv("PRODUCT_MCP_URL", "https://wrong-product.example/bad")
    monkeypatch.setenv("STOCK_MCP_URL", "https://wrong-stock.example/bad")
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))

    client = module.MCPClient(PRODUCT_URL, STOCK_URL)
    _run(client.call_product_tool("list_products"))

    assert state["transport"]["url"] == "https://product.example/mcp"


def test_environment_urls_are_used_when_explicit_urls_are_absent(monkeypatch):
    module = _client_module()
    monkeypatch.setenv("PRODUCT_MCP_URL", PRODUCT_URL)
    monkeypatch.setenv("STOCK_MCP_URL", STOCK_URL)
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))

    client = module.MCPClient()
    _run(client.call_stock_tool("list_branch_stock", {"branch_id": 2}))

    assert state["transport"]["url"] == "http://stock.example/mcp"


@pytest.mark.parametrize(
    "product_url",
    [
        None,
        "",
        "product.example/mcp",
        "ftp://product.example/mcp",
        "http:///mcp",
        "https://user:password@product.example/mcp",
        "https://product.example/mcp?token=secret",
        "https://product.example/mcp#fragment",
        "https://product.example/not-mcp",
    ],
)
def test_invalid_product_url_is_rejected_during_construction(monkeypatch, product_url):
    module = _client_module()
    monkeypatch.delenv("PRODUCT_MCP_URL", raising=False)
    monkeypatch.delenv("STOCK_MCP_URL", raising=False)
    with pytest.raises(ValueError):
        module.MCPClient(product_url, STOCK_URL)


@pytest.mark.parametrize(
    "stock_url",
    [
        None,
        "",
        "stock.example/mcp",
        "ftp://stock.example/mcp",
        "http:///mcp",
        "https://user:password@stock.example/mcp",
        "https://stock.example/mcp?token=secret",
        "https://stock.example/mcp#fragment",
        "https://stock.example/not-mcp",
    ],
)
def test_invalid_stock_url_is_rejected_during_construction(monkeypatch, stock_url):
    module = _client_module()
    monkeypatch.delenv("PRODUCT_MCP_URL", raising=False)
    monkeypatch.delenv("STOCK_MCP_URL", raising=False)
    with pytest.raises(ValueError):
        module.MCPClient(PRODUCT_URL, stock_url)


@pytest.mark.parametrize("timeout", [True, False, 0, -1, math.inf, -math.inf, math.nan, "5", None])
def test_invalid_timeout_is_rejected_during_construction(timeout):
    module = _client_module()
    with pytest.raises(ValueError):
        module.MCPClient(PRODUCT_URL, STOCK_URL, timeout_seconds=timeout)


def test_finite_positive_integer_timeout_is_accepted(monkeypatch):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))

    client = module.MCPClient(PRODUCT_URL, STOCK_URL, timeout_seconds=3)
    _run(client.call_product_tool("list_products"))

    timeout_values = dict(state["transport"]["kwargs"])
    if state["transport"]["args"]:
        timeout_values["timeout"] = state["transport"]["args"][0]
        if len(state["transport"]["args"]) > 1:
            timeout_values["sse_read_timeout"] = state["transport"]["args"][1]
    assert timeout_values["timeout"] == 3
    assert timeout_values["sse_read_timeout"] == 3
    read_timeout = state["session_constructor"]["kwargs"].get("read_timeout_seconds")
    if read_timeout is None and state["session_constructor"]["args"]:
        read_timeout = state["session_constructor"]["args"][0]
    assert read_timeout == timedelta(seconds=3)


def test_default_timeout_is_transmitted_as_five_seconds(monkeypatch):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))

    client = module.MCPClient(PRODUCT_URL, STOCK_URL)
    _run(client.call_product_tool("list_products"))

    timeout_values = dict(state["transport"]["kwargs"])
    if state["transport"]["args"]:
        timeout_values["timeout"] = state["transport"]["args"][0]
        if len(state["transport"]["args"]) > 1:
            timeout_values["sse_read_timeout"] = state["transport"]["args"][1]
    assert type(timeout_values["timeout"]) is float
    assert timeout_values["timeout"] == 5.0
    assert type(timeout_values["sse_read_timeout"]) is float
    assert timeout_values["sse_read_timeout"] == 5.0

    read_timeout = state["session_constructor"]["kwargs"].get("read_timeout_seconds")
    if read_timeout is None and state["session_constructor"]["args"]:
        read_timeout = state["session_constructor"]["args"][0]
    assert read_timeout == timedelta(seconds=5.0)


def test_ai_runtime_manifest_contains_only_the_approved_dependency():
    manifest = Path(__file__).parents[1] / "ai_service" / "requirements.txt"
    with manifest.open(encoding="utf-8") as manifest_file:
        dependencies = [line.strip() for line in manifest_file if line.strip()]
    assert dependencies == ["mcp>=1.27,<2"]


@pytest.mark.parametrize("target, tool_name", [("product", name) for name in PRODUCT_TOOLS] + [("stock", name) for name in STOCK_TOOLS])
def test_each_approved_tool_is_called_on_its_matching_mcp(monkeypatch, target, tool_name):
    module = _client_module()
    state = _new_state()
    envelope = {"status": "success", "data": {"value": tool_name}}
    _patch_sdk(monkeypatch, module, state, result=_result(envelope))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL, timeout_seconds=2.5)

    arguments = {
        "external_product_id": "SKU-1",
        "metadata": {"tags": ["contract-test"]},
    }
    arguments_before = copy.deepcopy(arguments)
    if target == "product":
        returned = _run(client.call_product_tool(tool_name, arguments))
        expected_url = "https://product.example/mcp"
    else:
        returned = _run(client.call_stock_tool(tool_name, arguments))
        expected_url = "http://stock.example/mcp"

    assert returned == envelope
    assert state["tool_calls"][0]["arguments"] == arguments_before
    assert state["transport"]["url"] == expected_url
    assert state["tool_calls"][0]["name"] == tool_name
    assert arguments == arguments_before


@pytest.mark.parametrize("method_name", ["call_product_tool", "call_stock_tool"])
@pytest.mark.parametrize("arguments", [4, True, "arguments", [], ()])
def test_non_dictionary_arguments_are_rejected_before_transport(
    monkeypatch, method_name, arguments
):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)
    tool_name = "list_products" if method_name == "call_product_tool" else "list_branch_stock"

    with pytest.raises(ValueError):
        _run(getattr(client, method_name)(tool_name, arguments))
    assert state["transport"] is None
    assert state["transport_entered"] == 0
    assert state["tool_calls"] == []


@pytest.mark.parametrize("method_name, tool_name", [("call_product_tool", "not_allowed"), ("call_stock_tool", "list_products")])
def test_tool_names_outside_each_target_allowlist_are_rejected_before_transport(
    monkeypatch, method_name, tool_name
):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    with pytest.raises(ValueError):
        _run(getattr(client, method_name)(tool_name))
    assert state["transport"] is None
    assert state["transport_entered"] == 0
    assert state["tool_calls"] == []


def test_none_arguments_are_passed_as_none_without_mutation(monkeypatch):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    _run(client.call_product_tool("list_products"))

    assert state["tool_calls"][0]["arguments"] is None


def test_call_uses_identical_transport_and_session_timeouts_and_closes_contexts(monkeypatch):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result({"status": "success", "data": {}}))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL, timeout_seconds=2.5)

    _run(client.call_product_tool("list_products", {"page": 1}))

    transport = state["transport"]
    timeout_values = dict(transport["kwargs"])
    if transport["args"]:
        timeout_values["timeout"] = transport["args"][0]
        if len(transport["args"]) > 1:
            timeout_values["sse_read_timeout"] = transport["args"][1]
    assert timeout_values["timeout"] == 2.5
    assert timeout_values["sse_read_timeout"] == 2.5
    session = state["session_constructor"]
    read_timeout = session["kwargs"].get("read_timeout_seconds")
    if read_timeout is None and session["args"]:
        read_timeout = session["args"][0]
    assert read_timeout == timedelta(seconds=2.5)
    assert state["initialize_calls"] == 1
    assert len(state["tool_calls"]) == 1
    assert state["transport_entered"] == 1
    assert state["transport_exited"] == 1
    assert state["session_entered"] == 1
    assert state["session_exited"] == 1


@pytest.mark.parametrize(
    ("method_name", "tool_name", "arguments"),
    [
        ("call_product_tool", "list_products", {"page": 1}),
        ("call_stock_tool", "list_branch_stock", {"branch_id": 7}),
    ],
)
def test_identical_calls_on_one_instance_are_not_cached(
    monkeypatch, method_name, tool_name, arguments
):
    module = _client_module()
    state = _new_state()
    envelope = {"status": "success", "data": {"call": "fresh"}}
    _patch_sdk(monkeypatch, module, state, result=_result(envelope))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    first = _run(getattr(client, method_name)(tool_name, arguments))
    second = _run(getattr(client, method_name)(tool_name, arguments))

    assert first == envelope
    assert second == envelope
    assert state["transport_entered"] == 2
    assert state["transport_exited"] == 2
    assert state["session_entered"] == 2
    assert state["session_exited"] == 2
    assert state["initialize_calls"] == 2
    assert state["tool_calls"] == [
        {"name": tool_name, "arguments": arguments, "args": (), "kwargs": {}},
        {"name": tool_name, "arguments": arguments, "args": (), "kwargs": {}},
    ]


@pytest.mark.parametrize(
    "envelope",
    [
        {"status": "success", "data": {"items": []}, "trace_id": "success-preserved"},
        {"status": "not_found", "data": None, "trace_id": "not-found-preserved"},
        {
            "status": "error",
            "error": {"code": "MCP_DOWNSTREAM", "message": "Unavailable."},
            "trace_id": "preserved",
        },
    ],
)
def test_valid_mcp_envelopes_are_returned_without_mutation(monkeypatch, envelope):
    module = _client_module()
    state = _new_state()
    envelope_before = copy.deepcopy(envelope)
    _patch_sdk(monkeypatch, module, state, result=_result(envelope))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    returned = _run(client.call_product_tool("list_products"))

    assert returned == envelope_before
    assert envelope == envelope_before


@pytest.mark.parametrize(
    "envelope",
    [
        None,
        [],
        {"status": "success"},
        {"status": "not_found"},
        {"status": "not_found", "data": {}},
        {"status": "error"},
        {"status": "error", "error": {}},
        {"status": "error", "error": {"code": 1, "message": "message"}},
        {"status": "error", "error": {"code": "code", "message": None}},
        {"status": "error", "error": {"code": "", "message": "message"}},
        {"status": "error", "error": {"code": "code", "message": ""}},
        {"status": "other", "data": None},
    ],
)
def test_invalid_structured_content_raises_mcp_error(monkeypatch, envelope):
    module = _client_module()
    state = _new_state()
    _patch_sdk(monkeypatch, module, state, result=_result(envelope))
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    with pytest.raises(module.MCPClientError) as exc_info:
        _run(client.call_product_tool("list_products"))
    _assert_client_error(exc_info, "MCP_ERROR")


def test_is_error_result_raises_mcp_error_even_with_a_valid_envelope(monkeypatch):
    module = _client_module()
    state = _new_state()
    _patch_sdk(
        monkeypatch,
        module,
        state,
        result=_result({"status": "success", "data": {}}, is_error=True),
    )
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    with pytest.raises(module.MCPClientError) as exc_info:
        _run(client.call_product_tool("list_products"))
    _assert_client_error(exc_info, "MCP_ERROR")


@pytest.mark.parametrize(
    "phase",
    [
        "transport_construct",
        "transport_enter",
        "session_construct",
        "session_enter",
        "initialize",
        "call_tool",
    ],
)
def test_timeout_errors_from_transport_or_session_map_to_upstream_timeout(monkeypatch, phase):
    module = _client_module()
    state = _new_state()
    _patch_sdk(
        monkeypatch,
        module,
        state,
        result=_result({"status": "success", "data": {}}),
        error_phase=phase,
        error=TimeoutError("SECRET upstream password traceback"),
    )
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    with pytest.raises(module.MCPClientError) as exc_info:
        _run(client.call_product_tool("list_products"))
    _assert_client_error(exc_info, "UPSTREAM_TIMEOUT")
    assert state["transport_exited"] == (
        0 if phase in {"transport_construct", "transport_enter"} else 1
    )
    assert state["session_exited"] == (1 if phase in {"initialize", "call_tool"} else 0)


@pytest.mark.parametrize(
    "phase",
    [
        "transport_construct",
        "transport_enter",
        "session_construct",
        "session_enter",
        "initialize",
        "call_tool",
    ],
)
def test_other_transport_or_session_errors_map_to_mcp_unavailable(monkeypatch, phase):
    module = _client_module()
    state = _new_state()
    _patch_sdk(
        monkeypatch,
        module,
        state,
        result=_result({"status": "success", "data": {}}),
        error_phase=phase,
        error=RuntimeError("SECRET password https://user:password@example.test traceback"),
    )
    client = module.MCPClient(PRODUCT_URL, STOCK_URL)

    with pytest.raises(module.MCPClientError) as exc_info:
        _run(client.call_product_tool("list_products"))
    _assert_client_error(exc_info, "MCP_UNAVAILABLE")
    assert state["transport_exited"] == (
        0 if phase in {"transport_construct", "transport_enter"} else 1
    )
    assert state["session_exited"] == (1 if phase in {"initialize", "call_tool"} else 0)


@pytest.mark.parametrize(
    ("exception_type", "expected_code"),
    [
        (TimeoutError, "UPSTREAM_TIMEOUT"),
        (RuntimeError, "MCP_UNAVAILABLE"),
    ],
)
def test_upstream_error_messages_are_constant_and_safe(
    monkeypatch, exception_type, expected_code
):
    module = _client_module()
    messages = []
    for detail in (
        "SECRET password traceback from first upstream",
        "another private URL https://user:password@example.test",
    ):
        state = _new_state()
        _patch_sdk(
            monkeypatch,
            module,
            state,
            result=_result({"status": "success", "data": {}}),
            error_phase="call_tool",
            error=exception_type(detail),
        )
        client = module.MCPClient(PRODUCT_URL, STOCK_URL)
        with pytest.raises(module.MCPClientError) as exc_info:
            _run(client.call_product_tool("list_products"))
        _assert_client_error(exc_info, expected_code)
        messages.append(exc_info.value.message)

    assert messages[0] == messages[1]
