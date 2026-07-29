"""Asynchronous client for the approved Product and Stock MCP tools."""

from __future__ import annotations

import math
import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


_PRODUCT_TOOLS = frozenset(
    {
        "list_products",
        "get_product_details",
    }
)
_STOCK_TOOLS = frozenset(
    {
        "list_branch_stock",
        "get_stock_for_product",
        "find_branches_with_stock",
        "find_branches_for_shopping_list",
    }
)

_ERROR_MESSAGES = {
    "MCP_ERROR": "The MCP service returned an invalid response.",
    "MCP_UNAVAILABLE": "The MCP service is unavailable.",
    "UPSTREAM_TIMEOUT": "The MCP service timed out.",
}


class MCPClientError(RuntimeError):
    """Stable, safe error raised when an approved MCP call cannot complete."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class MCPClient:
    """Call allowlisted MCP tools over a fresh Streamable HTTP session."""

    def __init__(
        self,
        product_mcp_url: str | None = None,
        stock_mcp_url: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        product_url = (
            product_mcp_url
            if product_mcp_url is not None
            else os.environ.get("PRODUCT_MCP_URL")
        )
        stock_url = (
            stock_mcp_url
            if stock_mcp_url is not None
            else os.environ.get("STOCK_MCP_URL")
        )

        self._product_mcp_url = self._canonicalize_url(product_url)
        self._stock_mcp_url = self._canonicalize_url(stock_url)
        self._timeout_seconds = self._validate_timeout(timeout_seconds)

    async def call_product_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call one approved Product MCP tool."""
        return await self._call_tool(
            self._product_mcp_url,
            _PRODUCT_TOOLS,
            tool_name,
            arguments,
        )

    async def call_stock_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call one approved Stock MCP tool."""
        return await self._call_tool(
            self._stock_mcp_url,
            _STOCK_TOOLS,
            tool_name,
            arguments,
        )

    @staticmethod
    def _canonicalize_url(value: str | None) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("MCP URL must be a valid HTTP(S) URL")

        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("MCP URL must be a valid HTTP(S) URL") from exc

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/", "/mcp"}
        ):
            raise ValueError("MCP URL must be a valid HTTP(S) URL")

        netloc = parsed.hostname
        if ":" in netloc and not netloc.startswith("["):
            netloc = f"[{netloc}]"
        if port is not None:
            netloc = f"{netloc}:{port}"
        return urlunsplit((parsed.scheme, netloc, "/mcp", "", ""))

    @staticmethod
    def _validate_timeout(timeout_seconds: float) -> float:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        return timeout_seconds

    async def _call_tool(
        self,
        url: str,
        allowed_tools: frozenset[str],
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if tool_name not in allowed_tools:
            raise ValueError("tool_name is not approved for this MCP service")
        if arguments is not None and not isinstance(arguments, dict):
            raise ValueError("arguments must be a dictionary or None")

        try:
            async with streamablehttp_client(
                url,
                timeout=self._timeout_seconds,
                sse_read_timeout=self._timeout_seconds,
            ) as (read_stream, write_stream, _):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(
                        seconds=self._timeout_seconds
                    ),
                ) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
        except TimeoutError as exc:
            raise MCPClientError(
                "UPSTREAM_TIMEOUT",
                _ERROR_MESSAGES["UPSTREAM_TIMEOUT"],
            ) from exc
        except Exception as exc:
            raise MCPClientError(
                "MCP_UNAVAILABLE",
                _ERROR_MESSAGES["MCP_UNAVAILABLE"],
            ) from exc

        envelope = getattr(result, "structuredContent", None)
        if getattr(result, "isError", False) or not self._is_valid_envelope(
            envelope
        ):
            raise MCPClientError("MCP_ERROR", _ERROR_MESSAGES["MCP_ERROR"])
        return envelope

    @staticmethod
    def _is_valid_envelope(envelope: object) -> bool:
        if not isinstance(envelope, dict):
            return False

        status = envelope.get("status")
        if status == "success":
            return "data" in envelope
        if status == "not_found":
            return envelope.get("data", object()) is None and "data" in envelope
        if status == "error":
            error = envelope.get("error")
            if not isinstance(error, dict):
                return False
            code = error.get("code")
            message = error.get("message")
            return (
                isinstance(code, str)
                and bool(code)
                and isinstance(message, str)
                and bool(message)
            )
        return False
