"""Unit tests for authentication request validation."""

import pytest

from backoffice.auth.schemas import (
    LoginValidationError,
    validate_login_payload,
)


def test_login_validation_normalizes_only_username():
    password = "  Keep My Spaces  "

    credentials = validate_login_payload(
        {"username": "  Alice  ", "password": password}
    )

    assert credentials.username == "alice"
    assert credentials.password == password


@pytest.mark.parametrize("payload", [None, [], "credentials"])
def test_login_validation_requires_json_object(payload):
    with pytest.raises(LoginValidationError) as error:
        validate_login_payload(payload)

    assert error.value.details == {
        "fields": {"body": "Must be a JSON object."}
    }


def test_login_validation_reports_missing_and_unexpected_fields():
    with pytest.raises(LoginValidationError) as error:
        validate_login_payload(
            {"username": "alice", "role": "admin"}
        )

    assert error.value.details == {
        "fields": {
            "missing": ["password"],
            "unexpected": ["role"],
            "password": "Must be a string.",
        }
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("username", 12, "Must be a string."),
        ("username", "   ", "Must not be empty."),
        ("username", "x" * 81, "Must not exceed 80 characters."),
        ("password", None, "Must be a string."),
        ("password", "", "Must not be empty."),
        ("password", "é" * 37, "Must not exceed 72 UTF-8 bytes."),
    ],
)
def test_login_validation_rejects_invalid_fields(field, value, message):
    payload = {"username": "alice", "password": "secret"}
    payload[field] = value

    with pytest.raises(LoginValidationError) as error:
        validate_login_payload(payload)

    assert error.value.details["fields"][field] == message
