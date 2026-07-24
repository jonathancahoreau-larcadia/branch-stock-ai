"""Stable JSON error responses shared by Backoffice API modules."""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db

ERROR_MESSAGES = {
    "INVALID_JSON": "Request body must be valid JSON.",
    "VALIDATION_ERROR": "Request data is invalid.",
    "AUTHENTICATION_REQUIRED": "Authentication is required.",
    "INVALID_CREDENTIALS": "Invalid username or password.",
    "TOKEN_INVALID": "Token is invalid.",
    "TOKEN_EXPIRED": "Token has expired.",
    "TOKEN_REVOKED": "Token has been revoked.",
    "WRONG_TOKEN_TYPE": "Token type is not allowed for this endpoint.",
    "TOKEN_VERSION_INVALID": "Token version is no longer valid.",
    "ACCOUNT_INACTIVE": "Account is inactive.",
    "INTERNAL_ERROR": "An unexpected error occurred.",
}


def error_response(
    code: str,
    status: int,
    *,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    """Build the documented error envelope without sensitive context."""
    return (
        jsonify(
            error={
                "code": code,
                "message": ERROR_MESSAGES[code],
                "details": details or {},
            }
        ),
        status,
    )


def register_api_error_handlers(app: Flask) -> None:
    """Convert database failures into non-sensitive API responses."""

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(_error: SQLAlchemyError):
        db.session.rollback()
        return error_response("INTERNAL_ERROR", 500)


__all__ = ["error_response", "register_api_error_handlers"]
