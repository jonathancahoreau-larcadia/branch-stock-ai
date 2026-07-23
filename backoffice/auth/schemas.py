"""Input validation for authentication endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class LoginValidationError(ValueError):
    """The login JSON object does not match the public contract."""

    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__("Invalid login payload.")
        self.details = details


@dataclass(frozen=True)
class LoginCredentials:
    """Validated credentials with only the username normalized."""

    username: str
    password: str


def validate_login_payload(payload: object) -> LoginCredentials:
    """Validate the exact login shape without altering the password."""
    if not isinstance(payload, dict):
        raise LoginValidationError(
            {"fields": {"body": "Must be a JSON object."}}
        )

    allowed_fields = {"username", "password"}
    received_fields = set(payload)
    missing_fields = sorted(allowed_fields - received_fields)
    unexpected_fields = sorted(received_fields - allowed_fields)
    field_errors: dict[str, Any] = {}

    if missing_fields:
        field_errors["missing"] = missing_fields
    if unexpected_fields:
        field_errors["unexpected"] = unexpected_fields

    username = payload.get("username")
    password = payload.get("password")

    if not isinstance(username, str):
        field_errors["username"] = "Must be a string."
    else:
        username = username.strip().lower()
        if not username:
            field_errors["username"] = "Must not be empty."
        elif len(username) > 80:
            field_errors["username"] = (
                "Must not exceed 80 characters."
            )

    if not isinstance(password, str):
        field_errors["password"] = "Must be a string."
    elif not password:
        field_errors["password"] = "Must not be empty."
    else:
        try:
            password_bytes = password.encode("utf-8")
        except UnicodeEncodeError:
            field_errors["password"] = "Must contain valid UTF-8 text."
        else:
            if len(password_bytes) > 72:
                field_errors["password"] = (
                    "Must not exceed 72 UTF-8 bytes."
                )

    if field_errors:
        raise LoginValidationError({"fields": field_errors})

    return LoginCredentials(username=username, password=password)


__all__ = [
    "LoginCredentials",
    "LoginValidationError",
    "validate_login_payload",
]
