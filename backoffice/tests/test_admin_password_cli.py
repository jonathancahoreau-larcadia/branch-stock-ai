"""Public contract tests for the transactional ``admin-password`` command."""

from __future__ import annotations

import bcrypt
import pytest
import re
from sqlalchemy import select

from backoffice.database.models import ADMIN_ROLE, User
from backoffice.extensions import db


def _assert_safe_cli_output(output: str, *secrets: str) -> None:
    assert not any(secret and secret in output for secret in secrets)
    assert not re.search(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{20,}", output)
    assert not re.search(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", output)


def _create_admin(password: str = "old-admin-password", *, token_version: int = 4) -> User:
    admin = User(
        id=1,
        username="admin",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode(),
        role=ADMIN_ROLE,
        branch_id=None,
        is_active=True,
        token_version=token_version,
    )
    db.session.add(admin)
    db.session.commit()
    return admin


def test_admin_password_cli_rotates_hash_and_token_version_without_leaking_secrets(
    sqlite_database_app, monkeypatch
):
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "new-admin-password")
    with sqlite_database_app.app_context():
        admin = _create_admin()
        original_hash = admin.password_hash
        original_version = admin.token_version

    client = sqlite_database_app.test_client()
    before = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "old-admin-password"},
    )
    assert before.status_code == 200
    old_tokens = before.get_json()["data"]

    result = sqlite_database_app.test_cli_runner().invoke(args=["admin-password"])

    assert result.exit_code == 0, result.output
    assert result.output.strip()
    _assert_safe_cli_output(result.output, "new-admin-password", "old-admin-password")
    with sqlite_database_app.app_context():
        refreshed = db.session.scalar(select(User).where(User.username == "admin"))
        assert refreshed.password_hash != original_hash
        assert bcrypt.checkpw(
            b"new-admin-password", refreshed.password_hash.encode()
        )
        assert not bcrypt.checkpw(
            b"old-admin-password", refreshed.password_hash.encode()
        )
        assert refreshed.token_version == original_version + 1

    old_access = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {old_tokens['access_token']}"},
    )
    old_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {old_tokens['refresh_token']}"},
    )
    assert old_access.status_code == 401
    assert old_refresh.status_code == 401


def test_admin_password_cli_requires_an_existing_coherent_admin_and_rolls_back(
    sqlite_database_app, monkeypatch
):
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "new-admin-password")
    result = sqlite_database_app.test_cli_runner().invoke(args=["admin-password"])
    assert result.exit_code != 0
    _assert_safe_cli_output(result.output, "new-admin-password")
    with sqlite_database_app.app_context():
        assert db.session.scalar(select(User).where(User.username == "admin")) is None


@pytest.mark.parametrize("configured_password", [None, "", "replace-with-secret", "${ADMIN_INITIAL_PASSWORD}"])
def test_admin_password_cli_rejects_absent_or_placeholder_without_leaking_configuration(
    sqlite_database_app, monkeypatch, configured_password
):
    private_database_url = "postgresql://private-sentinel:password@database.internal/hbntory"
    monkeypatch.setenv("DATABASE_URL", private_database_url)
    if configured_password is None:
        monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", configured_password)
    with sqlite_database_app.app_context():
        admin = _create_admin()
        original = (admin.password_hash, admin.token_version)

    result = sqlite_database_app.test_cli_runner().invoke(args=["admin-password"])

    assert result.exit_code != 0
    assert "ADMIN_INITIAL_PASSWORD" in result.output
    _assert_safe_cli_output(
        result.output,
        configured_password or "",
        "old-admin-password",
        private_database_url,
        "private-sentinel",
    )
    with sqlite_database_app.app_context():
        admin = db.session.scalar(select(User).where(User.username == "admin"))
        assert (admin.password_hash, admin.token_version) == original


def test_admin_password_cli_rejects_incoherent_admin_without_mutation(sqlite_database_app, monkeypatch):
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "new-admin-password")
    with sqlite_database_app.app_context():
        admin = _create_admin()
        admin.is_active = False
        db.session.commit()
        original = (admin.password_hash, admin.token_version)

    result = sqlite_database_app.test_cli_runner().invoke(args=["admin-password"])

    assert result.exit_code != 0
    _assert_safe_cli_output(result.output, "new-admin-password")
    with sqlite_database_app.app_context():
        admin = db.session.scalar(select(User).where(User.username == "admin"))
        assert (admin.password_hash, admin.token_version) == original


def test_admin_password_cli_rolls_back_when_hashing_fails(sqlite_database_app, monkeypatch):
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "new-admin-password")
    with sqlite_database_app.app_context():
        admin = _create_admin()
        original = (admin.password_hash, admin.token_version)

    def fail_hash(*_args, **_kwargs):
        raise RuntimeError("hash backend unavailable")

    monkeypatch.setattr(bcrypt, "hashpw", fail_hash)
    result = sqlite_database_app.test_cli_runner().invoke(args=["admin-password"])

    assert result.exit_code != 0
    _assert_safe_cli_output(result.output, "new-admin-password")
    with sqlite_database_app.app_context():
        admin = db.session.scalar(select(User).where(User.username == "admin"))
        assert (admin.password_hash, admin.token_version) == original


@pytest.mark.parametrize("failure_stage", ["flush", "commit"])
def test_admin_password_cli_rolls_back_on_transaction_stage_failure(
    sqlite_database_app, monkeypatch, failure_stage
):
    """A database failure at either transaction boundary never persists a rotation."""
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "new-admin-password")
    with sqlite_database_app.app_context():
        admin = _create_admin()
        original = (admin.password_hash, admin.token_version)

    def fail_transaction_stage(*_args, **_kwargs):
        raise RuntimeError(f"forced {failure_stage} failure")

    # Patch only for command execution, then restore before querying the DB so
    # the assertion itself exercises the normal session path.
    with monkeypatch.context() as context:
        context.setattr(db.session, failure_stage, fail_transaction_stage)
        result = sqlite_database_app.test_cli_runner().invoke(args=["admin-password"])

    assert result.exit_code != 0
    assert "new-admin-password" not in result.output
    with sqlite_database_app.app_context():
        admin = db.session.scalar(select(User).where(User.username == "admin"))
        assert (admin.password_hash, admin.token_version) == original


def test_admin_password_cli_rotates_and_rolls_back_on_postgresql_fixture(
    clean_postgres_app, monkeypatch
):
    """The dedicated PostgreSQL fixture exercises the row-lock/transaction path."""
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "new-admin-password")
    with clean_postgres_app.app_context():
        _create_admin()
        admin = db.session.scalar(select(User).where(User.username == "admin"))
        original = (admin.password_hash, admin.token_version)

    success = clean_postgres_app.test_cli_runner().invoke(args=["admin-password"])
    assert success.exit_code == 0, success.output
    with clean_postgres_app.app_context():
        rotated = db.session.scalar(select(User).where(User.username == "admin"))
        assert rotated.token_version == original[1] + 1
        assert bcrypt.checkpw(b"new-admin-password", rotated.password_hash.encode())

    with clean_postgres_app.app_context():
        before_failure = db.session.scalar(select(User).where(User.username == "admin"))
        snapshot = (before_failure.password_hash, before_failure.token_version)

    def fail_hash(*_args, **_kwargs):
        raise RuntimeError("forced hash failure")

    monkeypatch.setattr(bcrypt, "hashpw", fail_hash)
    failed = clean_postgres_app.test_cli_runner().invoke(args=["admin-password"])
    assert failed.exit_code != 0
    _assert_safe_cli_output(failed.output, "new-admin-password")
    with clean_postgres_app.app_context():
        after_failure = db.session.scalar(select(User).where(User.username == "admin"))
        assert (after_failure.password_hash, after_failure.token_version) == snapshot
