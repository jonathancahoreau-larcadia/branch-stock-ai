"""Unit tests for user-management hashing and serialization."""

from datetime import datetime, timezone

import bcrypt

from backoffice.database.models import ADMIN_ROLE, Branch, User
from backoffice.users.services import hash_password, serialize_user


def test_hash_password_uses_configured_bcrypt_without_plaintext(app):
    password = "  exact password  "

    with app.app_context():
        password_hash = hash_password(password)

    assert password_hash != password
    assert bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def test_user_serializer_is_an_explicit_whitelist():
    deleted_at = datetime(2026, 7, 24, 10, 30, tzinfo=timezone.utc)
    user = User(
        id=12,
        username="alice",
        password_hash="never-return",
        role="common_user",
        branch=Branch(id=2, name="Toulon"),
        is_active=False,
        deleted_at=deleted_at,
        token_version=8,
    )

    serialized = serialize_user(user)

    assert serialized == {
        "id": 12,
        "username": "alice",
        "role": "common_user",
        "branch": {"id": 2, "name": "Toulon"},
        "is_active": False,
        "deleted_at": "2026-07-24T10:30:00Z",
    }
    serialized_text = str(serialized)
    assert "password_hash" not in serialized_text
    assert "never-return" not in serialized_text
    assert "token_version" not in serialized_text
    assert "revoked_tokens" not in serialized_text


def test_admin_serializer_uses_null_branch():
    admin = User(
        id=1,
        username="admin",
        password_hash="never-return",
        role=ADMIN_ROLE,
        branch=None,
        is_active=True,
        deleted_at=None,
    )

    assert serialize_user(admin)["branch"] is None
