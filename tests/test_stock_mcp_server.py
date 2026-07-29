"""Public contract tests for the Stock MCP protocol adapter."""

from __future__ import annotations

import ast
import importlib
import inspect
import runpy
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import pytest


def _load_server():
    return importlib.import_module("stock_mcp_server.server")


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            imported.add(node.module)
            imported.update(
                f"{node.module}.{alias.name}" for alias in node.names
            )

    return imported


def _dynamic_import_calls(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    calls: list[ast.Call] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            calls.append(node)
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
        ):
            calls.append(node)

    return calls


def _decorated_tool_names(source: str) -> set[str]:
    tree = ast.parse(source)
    decorated: set[str] = set()

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr != "tool":
                continue
            if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "mcp":
                decorated.add(node.name)

    return decorated


def _strict_annotation(function: Any, parameter_name: str) -> None:
    annotation = get_type_hints(function, include_extras=True)[parameter_name]
    assert get_origin(annotation) is Annotated
    base_type, *metadata = get_args(annotation)
    assert base_type is int
    assert any(
        getattr(item, "strict", None) is True
        for field_info in metadata
        for item in getattr(field_info, "metadata", (field_info,))
    )


def test_public_wrappers_have_the_contract_signatures_and_strict_integers():
    server = _load_server()

    expected_parameters = {
        "list_branch_stock": {"branch_id": Annotated[int, ...]},
        "get_stock_for_product": {"external_product_id": str},
        "find_branches_with_stock": {
            "external_product_id": str,
            "quantity": Annotated[int, ...],
        },
        "find_branches_for_shopping_list": {"items": list[dict]},
    }

    for function_name, parameters in expected_parameters.items():
        function = getattr(server, function_name)
        signature = inspect.signature(function)
        assert list(signature.parameters) == list(parameters)
        assert inspect.iscoroutinefunction(function) is False
        hints = get_type_hints(function, include_extras=True)
        assert hints["return"] == dict[str, Any]
        for parameter_name, expected_type in parameters.items():
            if get_origin(expected_type) is Annotated:
                _strict_annotation(function, parameter_name)
            else:
                assert hints[parameter_name] == expected_type


def test_each_public_wrapper_is_registered_with_mcp_tool_decorator():
    server_path = Path(__file__).parents[1] / "stock_mcp_server" / "server.py"
    source = server_path.read_text(encoding="utf-8")

    assert _decorated_tool_names(source) == {
        "list_branch_stock",
        "get_stock_for_product",
        "find_branches_with_stock",
        "find_branches_for_shopping_list",
    }


@pytest.mark.parametrize(
    ("function_name", "args"),
    [
        ("list_branch_stock", (7,)),
        ("get_stock_for_product", (" SKU-1 / blue ",)),
        (
            "find_branches_with_stock",
            ("SKU-1", 0),
        ),
        (
            "find_branches_for_shopping_list",
            ([{"external_product_id": "SKU-1", "quantity": 2}],),
        ),
    ],
)
@pytest.mark.parametrize(
    "envelope",
    [
        {"status": "success", "data": {"value": "kept"}},
        {"status": "not_found", "data": None},
        {
            "status": "error",
            "error": {"code": "STOCK_DATABASE_ERROR", "message": "safe"},
        },
    ],
)
def test_each_wrapper_delegates_once_and_returns_the_exact_envelope(
    monkeypatch: pytest.MonkeyPatch,
    function_name: str,
    args: tuple[Any, ...],
    envelope: dict[str, Any],
):
    server = _load_server()
    stock_tools = importlib.import_module("stock_mcp_server.tools")
    calls: list[tuple[Any, ...]] = []

    def fake_tool(*received: Any) -> dict[str, Any]:
        calls.append(received)
        return envelope

    monkeypatch.setattr(stock_tools, function_name, fake_tool)
    wrapper = getattr(server, function_name)

    result = wrapper(*args)

    assert result is envelope
    assert len(calls) == 1
    assert calls == [args]
    if function_name == "find_branches_for_shopping_list":
        assert calls[0][0] is args[0]


def test_server_configuration_and_mcp_routes_are_public():
    server = _load_server()
    from mcp.server.fastmcp import FastMCP

    assert isinstance(server.mcp, FastMCP)
    assert server.mcp.name == "Stock MCP Server"
    settings = server.mcp.settings
    assert settings.host == "0.0.0.0"
    assert settings.port == 8200
    assert settings.streamable_http_path == "/mcp"
    assert settings.stateless_http is True
    assert settings.json_response is True

    app = server.mcp.streamable_http_app()
    routes_by_path = {}
    for route in app.routes:
        routes_by_path.setdefault(route.path, []).append(route)

    assert set(routes_by_path) == {"/mcp", "/health"}
    assert len(routes_by_path["/mcp"]) == 1
    assert len(routes_by_path["/health"]) == 1
    assert routes_by_path["/health"][0].methods <= {"GET", "HEAD"}
    assert "GET" in routes_by_path["/health"][0].methods


def test_server_does_not_expose_direct_database_or_network_dependencies():
    server_path = Path(__file__).parents[1] / "stock_mcp_server" / "server.py"
    source = server_path.read_text(encoding="utf-8")
    imported = _imported_module_names(source)

    forbidden_modules = {
        "os",
        "psycopg",
        "requests",
        "httpx",
        "urllib",
        "urllib.request",
        "urllib3",
        "aiohttp",
        "socket",
        "websockets",
        "importlib",
    }
    forbidden_roots = {module.split(".", 1)[0] for module in forbidden_modules}

    assert not {
        module
        for module in imported
        if module in forbidden_modules
        or module.split(".", 1)[0] in forbidden_roots
    }
    assert not {
        module
        for module in imported
        if module == "stock_mcp_server.repository"
        or module.startswith("stock_mcp_server.repository.")
    }
    assert "STOCK_MCP_DATABASE_URL" not in source
    assert "execute_sql" not in source
    assert _dynamic_import_calls(source) == []

    server = _load_server()
    assert not hasattr(server, "STOCK_MCP_DATABASE_URL")
    assert not hasattr(server, "execute_sql")


def test_runtime_manifest_contains_exactly_the_approved_dependencies():
    manifest = Path(__file__).parents[1] / "stock_mcp_server" / "requirements.txt"

    assert manifest.read_text(encoding="utf-8").splitlines() == [
        "mcp>=1.27,<2",
        "psycopg[binary]>=3.2,<4.0",
    ]


def test_main_selects_only_streamable_http_transport(monkeypatch: pytest.MonkeyPatch):
    server = _load_server()
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(server.mcp, "run", fake_run)

    server.main()

    assert calls == [{"transport": "streamable-http"}]


def test_direct_execution_guard_calls_main_without_starting_network(
    monkeypatch: pytest.MonkeyPatch,
):
    from mcp.server.fastmcp import FastMCP

    calls: list[dict[str, Any]] = []

    def fake_run(_self: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(FastMCP, "run", fake_run)

    runpy.run_module("stock_mcp_server.server", run_name="__main__")

    assert calls == [{"transport": "streamable-http"}]
