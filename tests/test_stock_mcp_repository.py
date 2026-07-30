"""Contract tests for the read-only Stock MCP PostgreSQL repository."""

from __future__ import annotations

import importlib
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest


DSN_ONE = "postgresql://stock_reader:secret-one@database/hbntory"
DSN_TWO = "postgresql://stock_reader:secret-two@database/hbntory"
RAW_DRIVER_MESSAGE = "driver detail: password=do-not-leak; SELECT secret"


@dataclass
class QueryResult:
    one: Any = None
    all: list[Any] | None = None


class FakeCursor:
    def __init__(
        self,
        results: list[QueryResult],
        *,
        execute_error: BaseException | None = None,
    ) -> None:
        self._results = iter(results)
        self._current: QueryResult | None = None
        self.execute_error = execute_error
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
        self.executions.append((statement, tuple(params)))
        if self.execute_error is not None:
            raise self.execute_error
        self._current = next(self._results)

    def fetchone(self) -> Any:
        assert self._current is not None
        return self._current.one

    def fetchall(self) -> list[Any]:
        assert self._current is not None
        return list(self._current.all or [])


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_value = cursor

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_value


def _load_repository():
    return importlib.import_module("stock_mcp_server.repository")


def _install_connections(
    monkeypatch: pytest.MonkeyPatch,
    repository: Any,
    connections: list[FakeConnection],
) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_connect(database_url: str, **kwargs: Any) -> FakeConnection:
        calls.append((database_url, kwargs))
        return connections.pop(0)

    monkeypatch.setattr(repository.psycopg, "connect", fake_connect)
    return calls


def _assert_read_only_parameterized(executions: list[tuple[str, tuple[Any, ...]]]) -> None:
    assert executions
    allowed_tables = {"branches", "stocks"}
    for statement, params in executions:
        normalized = " ".join(statement.split())
        assert normalized.upper().startswith("SELECT")
        assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP)\b", normalized, re.I)
        assert not re.search(r"\bFOR\s+UPDATE\b", normalized, re.I)
        referenced_tables = {
            name.lower()
            for name in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", normalized, re.I)
        }
        assert referenced_tables <= allowed_tables
        assert "%s" in statement
        assert params


def _normalized(statement: str) -> str:
    return " ".join(statement.split())


def _assert_branch_lookup(statement: str) -> None:
    normalized = _normalized(statement)
    assert re.search(r"\bFROM\s+branches\b", normalized, re.I)
    assert re.search(r"\bWHERE\s+(?:branches\.)?id\s*=\s*%s\b", normalized, re.I)


def _assert_branch_stock_query(statement: str) -> None:
    normalized = _normalized(statement)
    assert re.search(r"\bFROM\s+stocks\b", normalized, re.I)
    assert re.search(
        r"\bWHERE\s+(?:stocks\.)?branch_id\s*=\s*%s\b", normalized, re.I
    )
    assert re.search(r"\b(?:stocks\.)?quantity\s*>\s*0\b", normalized, re.I)
    assert re.search(
        r"\bORDER\s+BY\s+(?:stocks\.)?external_product_id(?:\s+ASC)?\s*,\s*"
        r"stocks\.id(?:\s+ASC)?\b",
        normalized,
        re.I,
    )


def _assert_product_stock_query(statement: str) -> None:
    normalized = _normalized(statement)
    assert re.search(
        r"\bFROM\s+stocks\s+JOIN\s+branches\s+ON\s+"
        r"(?:branches\.id\s*=\s*stocks\.branch_id|"
        r"stocks\.branch_id\s*=\s*branches\.id)\b",
        normalized,
        re.I,
    )
    assert re.search(
        r"\bWHERE\s+(?:stocks\.)?external_product_id\s*=\s*%s\b",
        normalized,
        re.I,
    )
    assert re.search(
        r"\bORDER\s+BY\s+branches\.name(?:\s+ASC)?\s*,\s*"
        r"branches\.id(?:\s+ASC)?\b",
        normalized,
        re.I,
    )


def test_repository_import_does_not_require_database_configuration(monkeypatch):
    monkeypatch.delenv("STOCK_MCP_DATABASE_URL", raising=False)
    repository = _load_repository()

    assert repository is not None


def test_repository_reads_dsn_on_every_call_and_applies_exact_timeouts(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    first_cursor = FakeCursor([QueryResult(one=(2, "Toulon")), QueryResult(all=[])])
    second_cursor = FakeCursor([QueryResult(all=[])])
    calls = _install_connections(
        monkeypatch,
        repository,
        [FakeConnection(first_cursor), FakeConnection(second_cursor)],
    )

    assert repository.fetch_branch_stock(2) == {
        "branch_id": 2,
        "branch_name": "Toulon",
        "stocks": [],
    }
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_TWO)
    assert repository.fetch_product_stock("product-123") == []

    assert calls == [
        (
            DSN_ONE,
            {"connect_timeout": 5, "options": "-c statement_timeout=5000"},
        ),
        (
            DSN_TWO,
            {"connect_timeout": 5, "options": "-c statement_timeout=5000"},
        ),
    ]


def test_missing_configuration_is_safe_and_does_not_connect(monkeypatch):
    repository = _load_repository()
    monkeypatch.delenv("STOCK_MCP_DATABASE_URL", raising=False)
    connect_calls: list[Any] = []

    def fail_connect(*_args: Any, **_kwargs: Any) -> None:
        connect_calls.append(True)
        raise AssertionError("connect must not be called")

    monkeypatch.setattr(repository.psycopg, "connect", fail_connect)

    with pytest.raises(repository.StockRepositoryConfigurationError) as caught:
        repository.fetch_branch_stock(1)

    assert not connect_calls
    assert "STOCK_MCP_DATABASE_URL" not in str(caught.value)


@pytest.mark.parametrize(
    ("driver_error", "expected_type"),
    [
        (psycopg.errors.ConnectionTimeout(RAW_DRIVER_MESSAGE), "timeout"),
        (psycopg.errors.QueryCanceled(RAW_DRIVER_MESSAGE), "timeout"),
        (psycopg.OperationalError(RAW_DRIVER_MESSAGE), "unavailable"),
        (psycopg.DatabaseError(RAW_DRIVER_MESSAGE), "error"),
    ],
)
def test_psycopg_failures_are_mapped_without_driver_details(
    monkeypatch, driver_error, expected_type
):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)

    def fail_connect(*_args: Any, **_kwargs: Any) -> None:
        raise driver_error

    monkeypatch.setattr(repository.psycopg, "connect", fail_connect)
    expected = {
        "timeout": repository.StockRepositoryTimeoutError,
        "unavailable": repository.StockRepositoryUnavailableError,
        "error": repository.StockRepositoryError,
    }[expected_type]

    with pytest.raises(expected) as caught:
        repository.fetch_product_stock("product-123")

    assert RAW_DRIVER_MESSAGE not in str(caught.value)
    assert DSN_ONE not in str(caught.value)
    assert "SELECT" not in str(caught.value).upper()


def test_repository_errors_all_inherit_runtime_error():
    repository = _load_repository()

    for error_name in (
        "StockRepositoryConfigurationError",
        "StockRepositoryTimeoutError",
        "StockRepositoryUnavailableError",
        "StockRepositoryError",
    ):
        assert issubclass(getattr(repository, error_name), RuntimeError)


@pytest.mark.parametrize(
    "driver_error",
    [
        psycopg.errors.ConnectionTimeout(RAW_DRIVER_MESSAGE),
        psycopg.errors.QueryCanceled(RAW_DRIVER_MESSAGE),
        psycopg.OperationalError(RAW_DRIVER_MESSAGE),
        psycopg.DatabaseError(RAW_DRIVER_MESSAGE),
    ],
)
def test_query_failures_are_mapped_without_driver_details(monkeypatch, driver_error):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    cursor = FakeCursor([], execute_error=driver_error)
    _install_connections(monkeypatch, repository, [FakeConnection(cursor)])

    with pytest.raises(
        repository.StockRepositoryTimeoutError
        if isinstance(
            driver_error,
            (psycopg.errors.ConnectionTimeout, psycopg.errors.QueryCanceled),
        )
        else repository.StockRepositoryError
    ) as caught:
        repository.fetch_product_stock("product-123")

    assert RAW_DRIVER_MESSAGE not in str(caught.value)
    assert DSN_ONE not in str(caught.value)
    assert "SELECT" not in str(caught.value).upper()


def test_runtime_manifest_contains_only_the_approved_dependency():
    manifest = Path(__file__).parents[1] / "stock_mcp_server" / "requirements.txt"

    assert manifest.exists()
    assert manifest.read_text(encoding="utf-8") == (
        "mcp>=1.27,<2\n"
        "psycopg[binary]>=3.2,<4.0\n"
    )


def test_branch_stock_returns_only_positive_rows_in_contract_order(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    cursor = FakeCursor(
        [
            QueryResult(one=(2, "Toulon")),
            QueryResult(
                all=[
                    ("product-001", 8),
                    ("product-009", 2),
                ]
            ),
        ]
    )
    calls = _install_connections(monkeypatch, repository, [FakeConnection(cursor)])

    result = repository.fetch_branch_stock(2)

    assert result == {
        "branch_id": 2,
        "branch_name": "Toulon",
        "stocks": [
            {"external_product_id": "product-001", "quantity": 8},
            {"external_product_id": "product-009", "quantity": 2},
        ],
    }
    assert calls[0][0] == DSN_ONE
    assert cursor.executions[0][1] == (2,)
    assert cursor.executions[1][1] == (2,)
    _assert_branch_lookup(cursor.executions[0][0])
    _assert_branch_stock_query(cursor.executions[1][0])
    _assert_read_only_parameterized(cursor.executions)


def test_unknown_branch_skips_stock_query_and_known_empty_branch_is_success(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    unknown_cursor = FakeCursor([QueryResult(one=None)])
    empty_cursor = FakeCursor([QueryResult(one=(3, "Paris")), QueryResult(all=[])])
    _install_connections(
        monkeypatch,
        repository,
        [FakeConnection(unknown_cursor), FakeConnection(empty_cursor)],
    )

    assert repository.fetch_branch_stock(999) is None
    assert len(unknown_cursor.executions) == 1
    assert repository.fetch_branch_stock(3) == {
        "branch_id": 3,
        "branch_name": "Paris",
        "stocks": [],
    }


def test_product_stock_keeps_zero_and_orders_by_branch(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    cursor = FakeCursor(
        [
            QueryResult(
                all=[
                    (3, "Paris", 1),
                    (2, "Toulon", 0),
                    (7, "Toulon", 4),
                ]
            )
        ]
    )
    _install_connections(monkeypatch, repository, [FakeConnection(cursor)])

    assert repository.fetch_product_stock("product-123") == [
        {"branch_id": 3, "branch_name": "Paris", "quantity": 1},
        {"branch_id": 2, "branch_name": "Toulon", "quantity": 0},
        {"branch_id": 7, "branch_name": "Toulon", "quantity": 4},
    ]
    assert cursor.executions[0][1] == ("product-123",)
    _assert_product_stock_query(cursor.executions[0][0])


def test_product_without_rows_returns_empty_list(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    cursor = FakeCursor([QueryResult(all=[])])
    _install_connections(monkeypatch, repository, [FakeConnection(cursor)])

    assert repository.fetch_product_stock("missing-product") == []


def test_queries_are_select_only_and_values_are_never_interpolated(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    injected_identifier = "product-' OR 1=1 --"
    cursor = FakeCursor(
        [
            QueryResult(one=(4, "Lille")),
            QueryResult(all=[]),
        ]
    )
    _install_connections(monkeypatch, repository, [FakeConnection(cursor)])

    repository.fetch_branch_stock(4)
    product_cursor = FakeCursor([QueryResult(all=[])])
    _install_connections(monkeypatch, repository, [FakeConnection(product_cursor)])
    repository.fetch_product_stock(injected_identifier)

    executions = cursor.executions + product_cursor.executions
    _assert_read_only_parameterized(executions)
    _assert_branch_lookup(cursor.executions[0][0])
    _assert_branch_stock_query(cursor.executions[1][0])
    _assert_product_stock_query(product_cursor.executions[0][0])
    assert any(injected_identifier in params for _statement, params in product_cursor.executions)
    assert all(injected_identifier not in statement for statement, _params in executions)
    assert not hasattr(repository, "execute_sql")
    public_callables = {
        name for name, value in inspect.getmembers(repository, inspect.isfunction)
    }
    assert "execute_sql" not in public_callables


def test_malformed_database_rows_become_safe_repository_errors(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    cursor = FakeCursor([QueryResult(one=(2,)), QueryResult(all=[])])
    _install_connections(monkeypatch, repository, [FakeConnection(cursor)])

    with pytest.raises(repository.StockRepositoryError) as caught:
        repository.fetch_branch_stock(2)

    assert DSN_ONE not in str(caught.value)
    assert RAW_DRIVER_MESSAGE not in str(caught.value)


def test_malformed_product_rows_become_safe_repository_errors(monkeypatch):
    repository = _load_repository()
    monkeypatch.setenv("STOCK_MCP_DATABASE_URL", DSN_ONE)
    cursor = FakeCursor([QueryResult(all=[(2, "Toulon")])])
    _install_connections(monkeypatch, repository, [FakeConnection(cursor)])

    with pytest.raises(repository.StockRepositoryError) as caught:
        repository.fetch_product_stock("product-123")

    assert DSN_ONE not in str(caught.value)
    assert RAW_DRIVER_MESSAGE not in str(caught.value)
