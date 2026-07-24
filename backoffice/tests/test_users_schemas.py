"""Unit tests for strict user-management request validation."""

import pytest

from backoffice.users.schemas import (
    UserValidationError,
    validate_create_user,
    validate_list_filters,
    validate_password_update,
    validate_update_user,
)


def test_create_validation_normalizes_only_username():
    password = "  Keep These Spaces  "

    data = validate_create_user(
        {
            "username": "  Alice.Dupont  ",
            "password": password,
            "branch_id": 2,
        }
    )

    assert data.username == "alice.dupont"
    assert data.password == password
    assert data.branch_id == 2


def test_create_validation_rejects_authorization_and_internal_fields():
    payload = {
        "username": "alice",
        "password": "secret",
        "branch_id": 2,
        "role": "admin",
        "is_active": True,
        "token_version": 99,
    }

    with pytest.raises(UserValidationError) as error:
        validate_create_user(payload)

    assert error.value.details["fields"]["unexpected"] == [
        "is_active",
        "role",
        "token_version",
    ]


@pytest.mark.parametrize("branch_id", [None, True, 0, -1, "2"])
def test_create_validation_requires_positive_integer_branch(branch_id):
    with pytest.raises(UserValidationError) as error:
        validate_create_user(
            {
                "username": "alice",
                "password": "secret",
                "branch_id": branch_id,
            }
        )

    assert "branch_id" in error.value.details["fields"]


@pytest.mark.parametrize(
    "password",
    ["", "   ", "é" * 37],
)
def test_create_validation_enforces_bcrypt_password_limits(password):
    with pytest.raises(UserValidationError) as error:
        validate_create_user(
            {
                "username": "alice",
                "password": password,
                "branch_id": 2,
            }
        )

    assert "password" in error.value.details["fields"]


def test_update_validation_accepts_one_or_both_fields():
    username_only = validate_update_user({"username": "  ALICE  "})
    branch_only = validate_update_user({"branch_id": 3})
    both = validate_update_user(
        {"username": "bob", "branch_id": 4}
    )

    assert username_only.username == "alice"
    assert username_only.username_provided is True
    assert username_only.branch_id_provided is False
    assert branch_only.branch_id == 3
    assert branch_only.username_provided is False
    assert both.username == "bob"
    assert both.branch_id == 4


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"password": "secret"},
        {"role": "common_user"},
        {"is_active": False},
        {"deleted_at": None},
        {"token_version": 4},
        {"password_hash": "hash"},
    ],
)
def test_update_validation_rejects_empty_or_forbidden_payloads(payload):
    with pytest.raises(UserValidationError):
        validate_update_user(payload)


def test_password_update_preserves_value_and_rejects_extra_fields():
    password = "  new password  "
    data = validate_password_update({"new_password": password})

    assert data.new_password == password

    with pytest.raises(UserValidationError):
        validate_password_update(
            {"new_password": password, "token_version": 5}
        )


@pytest.mark.parametrize("password", ["", "   ", "x" * 73])
def test_password_update_rejects_invalid_password(password):
    with pytest.raises(UserValidationError):
        validate_password_update({"new_password": password})


def test_list_filters_default_and_validate_exact_query():
    assert validate_list_filters({}).status == "active"
    assert validate_list_filters({"status": ["deleted"]}).status == (
        "deleted"
    )
    assert validate_list_filters({"status": ["all"]}).status == "all"
    assert validate_list_filters({"branch_id": ["12"]}).branch_id == 12

    for query in (
        {"status": ["inactive"]},
        {"branch_id": ["0"]},
        {"branch_id": ["01"]},
        {"branch_id": ["abc"]},
        {"status": ["active", "all"]},
        {"unknown": ["value"]},
    ):
        with pytest.raises(UserValidationError):
            validate_list_filters(query)
