"""Structural contract tests for the Product MCP protocol adapter (P2-T02).

The protocol SDK and HTTP client are deliberately *not* imported here.  These
tests describe the boundary between the three Product MCP layers and can run
in a test environment where those optional runtime dependencies are absent.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "product_mcp_server"
SERVER_PATH = PACKAGE / "server.py"
TOOLS_PATH = PACKAGE / "tools.py"
PRODUCT_API_PATH = PACKAGE / "product_api.py"
REQUIREMENTS_PATH = PACKAGE / "requirements.txt"

CONTRACTUAL_TOOLS = {"list_products", "get_product_details"}
HTTP_CLIENT_ROOTS = {"httpx", "requests"}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_module_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _decorated_tool_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        ):
            names.add(node.name)
    return names


def _returns_an_awaited_call(function: ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Await)
        and isinstance(node.value.value, ast.Call)
        for node in ast.walk(function)
    )


def _tools_import_names(tree: ast.Module) -> tuple[set[str], dict[str, str]]:
    """Return module aliases and direct function aliases for ``tools.py``."""
    module_names: set[str] = set()
    function_names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            is_package_import = node.module == "product_mcp_server" or (
                node.level == 1 and node.module is None
            )
            is_tools_import = node.module == "product_mcp_server.tools" or (
                node.level == 1 and node.module == "tools"
            )
            for alias in node.names:
                if is_package_import and alias.name == "tools":
                    module_names.add(alias.asname or alias.name)
                elif is_tools_import and alias.name in CONTRACTUAL_TOOLS:
                    function_names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "product_mcp_server.tools" and alias.asname:
                    module_names.add(alias.asname)
    return module_names, function_names


def _tools_delegation(
    function: ast.AsyncFunctionDef,
    name: str,
    module_names: set[str],
    function_names: dict[str, str],
) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
            continue
        called = node.value.func
        if (
            isinstance(called, ast.Attribute)
            and isinstance(called.value, ast.Name)
            and called.value.id in module_names
            and called.attr == name
        ):
            return True
        if isinstance(called, ast.Name) and function_names.get(called.id) == name:
            return True
    return False


def _async_functions(tree: ast.Module) -> dict[str, ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    }


def _requirement_names() -> set[str]:
    names: set[str] = set()
    for raw_line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line or line.startswith(("-", ".")):
            continue
        match = re.match(r"[A-Za-z0-9_.-]+", line)
        if match:
            names.add(match.group(0).lower().replace("_", "-"))
    return names


def _has_outbound_read_call(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "get":
            return True
        if (
            node.func.attr == "request"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "GET"
        ):
            return True
    return False


def test_server_registers_exactly_the_two_contractual_mcp_tools() -> None:
    """The protocol adapter exposes no Product MCP tool beyond the contract."""
    tree = _tree(SERVER_PATH)
    functions = _async_functions(tree)

    assert _decorated_tool_names(tree) == CONTRACTUAL_TOOLS
    assert set(functions).issuperset(CONTRACTUAL_TOOLS)
    assert sum(
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and any(
            isinstance(target, ast.Name) and target.id == "mcp"
            for target in node.targets
        )
        for node in tree.body
    ) == 1

    # A Product MCP protocol adapter must not also add arbitrary ASGI routes.
    assert not any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in {"custom_route", "route", "get", "post"}
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
    )


def test_server_tool_handlers_delegate_to_the_tools_layer() -> None:
    """Each registered handler is a thin async delegation to ``tools.py``."""
    tree = _tree(SERVER_PATH)
    functions = _async_functions(tree)
    module_names, function_names = _tools_import_names(tree)
    assert module_names or function_names

    for name in CONTRACTUAL_TOOLS:
        assert _returns_an_awaited_call(functions[name])
        assert _tools_delegation(functions[name], name, module_names, function_names)


def test_server_has_no_direct_http_client_dependency() -> None:
    """HTTP belongs to ``product_api.py``, never to the MCP protocol layer."""
    tree = _tree(SERVER_PATH)

    assert not _imported_module_roots(tree).intersection(HTTP_CLIENT_ROOTS)


def test_product_api_owns_http_calls_and_tools_own_product_operations() -> None:
    """Keep transport in the adapter and the two public operations in tools."""
    product_api = _tree(PRODUCT_API_PATH)
    tools = _tree(TOOLS_PATH)
    product_api_functions = _async_functions(product_api)
    tool_functions = _async_functions(tools)

    assert _imported_module_roots(product_api).intersection(HTTP_CLIENT_ROOTS)
    assert _has_outbound_read_call(product_api)
    assert CONTRACTUAL_TOOLS.issubset(product_api_functions)
    assert CONTRACTUAL_TOOLS == set(tool_functions)
    assert not _imported_module_roots(tools).intersection(HTTP_CLIENT_ROOTS)
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "product_mcp_server.product_api"
        for node in ast.walk(tools)
    ) or any(
        isinstance(node, ast.ImportFrom)
        and node.module == "product_api"
        and node.level == 1
        for node in ast.walk(tools)
    )

    for name in CONTRACTUAL_TOOLS:
        assert _returns_an_awaited_call(tool_functions[name])


def test_mcp_sdk_is_declared_without_a_separate_fastmcp_dependency() -> None:
    """FastMCP may be provided by the approved ``mcp`` SDK, not separately."""
    requirements = _requirement_names()

    assert "mcp" in requirements
    assert "fastmcp" not in requirements


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    """Allow this dependency-free contract module to run with ``unittest``."""
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for name, test in sorted(globals().items())
        if name.startswith("test_") and callable(test)
    )
