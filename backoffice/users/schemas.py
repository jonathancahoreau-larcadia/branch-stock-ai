"""Strict request validation for Backoffice user management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class UserValidationError(ValueError):
    """A user-management request does not match its public contract."""

    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__("Invalid user-management input.")
        self.details = details


@dataclass(frozen=True)
class CreateUserData:
    """Validated fields for creating one common user."""

    username: str
    password: str
    branch_id: int


@dataclass(frozen=True)
class UpdateUserData:
    """Validated optional fields for updating one common user."""

    username: str | None
    branch_id: int | None
    username_provided: bool
    branch_id_provided: bool


@dataclass(frozen=True)
class PasswordUpdateData:
    """Validated password replacement that preserves the supplied value."""

    new_password: str


@dataclass(frozen=True)
class UserListFilters:
    """Validated list filters."""

    status: str
    branch_id: int | None


def _validate_exact_fields(
    payload: object,
    *,
    allowed: set[str],
    required: set[str],
    allow_empty: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise UserValidationError(
            {"fields": {"body": "Must be a JSON object."}}
        )

    received = set(payload)
    field_errors: dict[str, Any] = {}
    missing = sorted(required - received)
    unexpected = sorted(received - allowed)
    if missing:
        field_errors["missing"] = missing
    if unexpected:
        field_errors["unexpected"] = unexpected
    if not allow_empty and not received:
        field_errors["body"] = "Must contain at least one allowed field."
    return payload, field_errors


def _normalized_username(
    value: object,
    field_errors: dict[str, Any],
) -> str | None:
    if not isinstance(value, str):
        field_errors["username"] = "Must be a string."
        return None

    normalized = value.strip().lower()
    if not normalized:
        field_errors["username"] = "Must not be empty."
    elif len(normalized) > 80:
        field_errors["username"] = "Must not exceed 80 characters."
    return normalized


def _positive_identifier(
    value: object,
    field_errors: dict[str, Any],
    *,
    field: str,
) -> int | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        field_errors[field] = "Must be a strictly positive integer."
        return None
    return value


def _validated_password(
    value: object,
    field_errors: dict[str, Any],
    *,
    field: str,
) -> str | None:
    if not isinstance(value, str):
        field_errors[field] = "Must be a string."
        return None
    if not value or not value.strip():
        field_errors[field] = "Must not be empty or blank."
        return None

    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        field_errors[field] = "Must contain valid UTF-8 text."
        return None
    if len(encoded) > 72:
        field_errors[field] = "Must not exceed 72 UTF-8 bytes."
    return value


def validate_create_user(payload: object) -> CreateUserData:
    """Validate the exact common-user creation payload."""
    payload, errors = _validate_exact_fields(
        payload,
        allowed={"username", "password", "branch_id"},
        required={"username", "password", "branch_id"},
        allow_empty=True,
    )
    username = _normalized_username(payload.get("username"), errors)
    password = _validated_password(
        payload.get("password"),
        errors,
        field="password",
    )
    branch_id = _positive_identifier(
        payload.get("branch_id"),
        errors,
        field="branch_id",
    )
    if errors:
        raise UserValidationError({"fields": errors})
    return CreateUserData(
        username=username,
        password=password,
        branch_id=branch_id,
    )


def validate_update_user(payload: object) -> UpdateUserData:
    """Validate a partial username and/or branch update."""
    payload, errors = _validate_exact_fields(
        payload,
        allowed={"username", "branch_id"},
        required=set(),
    )
    username_provided = "username" in payload
    branch_id_provided = "branch_id" in payload
    username = (
        _normalized_username(payload.get("username"), errors)
        if username_provided
        else None
    )
    branch_id = (
        _positive_identifier(
            payload.get("branch_id"),
            errors,
            field="branch_id",
        )
        if branch_id_provided
        else None
    )
    if errors:
        raise UserValidationError({"fields": errors})
    return UpdateUserData(
        username=username,
        branch_id=branch_id,
        username_provided=username_provided,
        branch_id_provided=branch_id_provided,
    )


def validate_password_update(payload: object) -> PasswordUpdateData:
    """Validate an exact password-reset payload."""
    payload, errors = _validate_exact_fields(
        payload,
        allowed={"new_password"},
        required={"new_password"},
        allow_empty=True,
    )
    new_password = _validated_password(
        payload.get("new_password"),
        errors,
        field="new_password",
    )
    if errors:
        raise UserValidationError({"fields": errors})
    return PasswordUpdateData(new_password=new_password)


def validate_list_filters(
    query: dict[str, list[str]],
) -> UserListFilters:
    """Validate the exact query parameters accepted by the list route."""
    allowed = {"status", "branch_id"}
    errors: dict[str, Any] = {}
    unexpected = sorted(set(query) - allowed)
    if unexpected:
        errors["unexpected"] = unexpected

    for field in allowed:
        if len(query.get(field, [])) > 1:
            errors[field] = "Must be provided at most once."

    status_values = query.get("status", [])
    status = status_values[0] if status_values else "active"
    if status not in {"active", "deleted", "all"}:
        errors["status"] = "Must be active, deleted, or all."

    branch_id = None
    branch_values = query.get("branch_id", [])
    if branch_values:
        raw_branch_id = branch_values[0]
        try:
            branch_id = int(raw_branch_id)
        except (TypeError, ValueError):
            errors["branch_id"] = "Must be a strictly positive integer."
        else:
            if branch_id <= 0 or str(branch_id) != raw_branch_id:
                errors["branch_id"] = (
                    "Must be a strictly positive integer."
                )

    if errors:
        raise UserValidationError({"fields": errors})
    return UserListFilters(status=status, branch_id=branch_id)


__all__ = [
    "CreateUserData",
    "PasswordUpdateData",
    "UpdateUserData",
    "UserListFilters",
    "UserValidationError",
    "validate_create_user",
    "validate_list_filters",
    "validate_password_update",
    "validate_update_user",
]
