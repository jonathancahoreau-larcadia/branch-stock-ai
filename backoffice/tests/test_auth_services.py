"""Unit tests for password verification and safe user serialization."""

import bcrypt
import pytest

from backoffice.auth import services
from backoffice.database.models import ADMIN_ROLE, Branch, User


def test_password_verification_uses_bcrypt():
    password = "valid-password"
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")

    assert services._password_matches(password, password_hash) is True
    assert services._password_matches("wrong-password", password_hash) is False
    assert services._password_matches(password, "invalid-hash") is False


def test_user_serialization_excludes_private_fields():
    branch = Branch(id=2, name="Toulon")
    user = User(
        id=12,
        username="alice",
        password_hash="never-return-this",
        role="common_user",
        branch=branch,
        token_version=3,
    )

    serialized = services.serialize_user(user)

    assert serialized == {
        "id": 12,
        "username": "alice",
        "role": "common_user",
        "branch": {"id": 2, "name": "Toulon"},
    }
    assert "password_hash" not in serialized
    assert "token_version" not in serialized


def test_admin_serialization_uses_null_branch():
    admin = User(
        id=1,
        username="admin",
        password_hash="never-return-this",
        role=ADMIN_ROLE,
        branch=None,
    )

    assert services.serialize_user(admin)["branch"] is None


def test_unknown_user_still_checks_the_dummy_hash(app, monkeypatch):
    scalar_calls = []
    checked_hashes = []

    monkeypatch.setattr(
        services.db.session,
        "scalar",
        lambda statement: scalar_calls.append(statement),
    )

    def fake_checkpw(password, password_hash):
        checked_hashes.append((password, password_hash))
        return False

    monkeypatch.setattr(services.bcrypt, "checkpw", fake_checkpw)

    with app.app_context(), pytest.raises(
        services.InvalidCredentialsError
    ):
        services.authenticate_user("unknown", "wrong-password")

    assert len(scalar_calls) == 1
    assert checked_hashes == [
        (
            b"wrong-password",
            services.DUMMY_PASSWORD_HASH.encode("utf-8"),
        )
    ]
