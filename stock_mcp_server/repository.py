"""Read-only PostgreSQL queries used by the Stock MCP tools."""

from __future__ import annotations

import os
from typing import Any

import psycopg


_DATABASE_URL_ENV = "STOCK_MCP_DATABASE_URL"
_CONNECT_TIMEOUT_SECONDS = 5
_STATEMENT_TIMEOUT_OPTIONS = "-c statement_timeout=5000"

_BRANCH_QUERY = """
SELECT branches.id, branches.name
FROM branches
WHERE branches.id = %s
"""

_BRANCH_STOCK_QUERY = """
SELECT stocks.external_product_id, stocks.quantity
FROM stocks
WHERE stocks.branch_id = %s
  AND stocks.quantity > 0
ORDER BY stocks.external_product_id, stocks.id
"""

_PRODUCT_STOCK_QUERY = """
SELECT branches.id, branches.name, stocks.quantity
FROM stocks
JOIN branches ON branches.id = stocks.branch_id
WHERE stocks.external_product_id = %s
ORDER BY branches.name, branches.id
"""


class StockRepositoryConfigurationError(RuntimeError):
    """Raised when the Stock database configuration is absent."""


class StockRepositoryTimeoutError(RuntimeError):
    """Raised when connecting to or querying the Stock database times out."""


class StockRepositoryUnavailableError(RuntimeError):
    """Raised when the Stock database connection cannot be established."""


class StockRepositoryError(RuntimeError):
    """Raised when a Stock database query or result cannot be processed."""


def _database_url() -> str:
    database_url = os.environ.get(_DATABASE_URL_ENV)
    if database_url is None or not database_url.strip():
        raise StockRepositoryConfigurationError(
            "Stock database configuration is invalid."
        )
    return database_url


def _connect() -> Any:
    try:
        return psycopg.connect(
            _database_url(),
            connect_timeout=_CONNECT_TIMEOUT_SECONDS,
            options=_STATEMENT_TIMEOUT_OPTIONS,
        )
    except (psycopg.errors.ConnectionTimeout, psycopg.errors.QueryCanceled):
        raise StockRepositoryTimeoutError(
            "Stock database request timed out."
        ) from None
    except psycopg.OperationalError:
        raise StockRepositoryUnavailableError(
            "Stock database is unavailable."
        ) from None
    except psycopg.Error:
        raise StockRepositoryError("Stock database query failed.") from None


def _query_error() -> None:
    raise StockRepositoryError("Stock database query failed.") from None


def fetch_branch_stock(branch_id: int) -> dict[str, Any] | None:
    """Return one branch and its strictly positive stock quantities."""

    connection = _connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(_BRANCH_QUERY, (branch_id,))
                branch_row = cursor.fetchone()
                if branch_row is None:
                    return None

                branch_value, branch_name = branch_row
                cursor.execute(_BRANCH_STOCK_QUERY, (branch_id,))
                stock_rows = cursor.fetchall()

        stocks = [
            {
                "external_product_id": external_product_id,
                "quantity": quantity,
            }
            for external_product_id, quantity in stock_rows
        ]
        return {
            "branch_id": branch_value,
            "branch_name": branch_name,
            "stocks": stocks,
        }
    except (psycopg.errors.ConnectionTimeout, psycopg.errors.QueryCanceled):
        raise StockRepositoryTimeoutError(
            "Stock database request timed out."
        ) from None
    except psycopg.Error:
        _query_error()
    except Exception:
        _query_error()


def fetch_product_stock(external_product_id: str) -> list[dict[str, Any]]:
    """Return all known branch quantities for one external product."""

    connection = _connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(_PRODUCT_STOCK_QUERY, (external_product_id,))
                stock_rows = cursor.fetchall()

        return [
            {
                "branch_id": branch_id,
                "branch_name": branch_name,
                "quantity": quantity,
            }
            for branch_id, branch_name, quantity in stock_rows
        ]
    except (psycopg.errors.ConnectionTimeout, psycopg.errors.QueryCanceled):
        raise StockRepositoryTimeoutError(
            "Stock database request timed out."
        ) from None
    except psycopg.Error:
        _query_error()
    except Exception:
        _query_error()
