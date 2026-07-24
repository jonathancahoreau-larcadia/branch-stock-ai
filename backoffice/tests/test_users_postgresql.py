"""PostgreSQL integration tests for administrator user management."""

from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import func, select

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    RevokedToken,
    Stock,
    User,
)
from backoffice.extensions import db

ADMIN_PASSWORD = "postgres-admin-password"
USER_PASSWORD = "postgres-user-password"


def _hash(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")


def _prepare_database(*, include_user=False):
    toulon = Branch(name="Toulon")
    marseille = Branch(name="Marseille")
    db.session.add_all([toulon, marseille])
    db.session.flush()
    admin = User(
        username="admin",
        password_hash=_hash(ADMIN_PASSWORD),
        role=ADMIN_ROLE,
        branch_id=None,
        is_active=True,
        token_version=0,
    )
    db.session.add(admin)
    user = None
    if include_user:
        user = User(
            username="alice",
            password_hash=_hash(USER_PASSWORD),
            role=COMMON_USER_ROLE,
            branch_id=toulon.id,
            is_active=True,
            token_version=0,
        )
        db.session.add(user)
    db.session.commit()
    return admin, user, toulon, marseille


def _login(client, username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _assert_no_private_user_data(response):
    body = response.get_data(as_text=True)
    assert "password_hash" not in body
    assert "token_version" not in body
    assert "revoked_tokens" not in body


def test_postgresql_admin_access_and_common_user_forbidden(
    clean_postgres_app,
):
    _prepare_database(include_user=True)
    client = clean_postgres_app.test_client()
    admin_token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]
    user_token = _login(client, "alice", USER_PASSWORD)["access_token"]

    allowed = client.get(
        "/api/v1/users",
        headers=_bearer(admin_token),
    )
    forbidden = client.get(
        "/api/v1/users",
        headers=_bearer(user_token),
    )

    assert allowed.status_code == 200
    assert [item["username"] for item in allowed.get_json()["data"]] == [
        "admin",
        "alice",
    ]
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"]["code"] == "FORBIDDEN"


def test_postgresql_create_common_user_is_normalized_hashed_and_safe(
    clean_postgres_app,
):
    _, _, toulon, _ = _prepare_database()
    client = clean_postgres_app.test_client()
    token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]
    password = "  exact user password  "

    response = client.post(
        "/api/v1/users",
        json={
            "username": "  Alice  ",
            "password": password,
            "branch_id": toulon.id,
        },
        headers=_bearer(token),
    )

    assert response.status_code == 201
    user = db.session.scalar(select(User).where(User.username == "alice"))
    assert user.role == COMMON_USER_ROLE
    assert user.branch_id == toulon.id
    assert user.is_active is True
    assert user.deleted_at is None
    assert user.token_version == 0
    assert user.password_hash != password
    assert bcrypt.checkpw(
        password.encode("utf-8"),
        user.password_hash.encode("utf-8"),
    )
    assert response.get_json()["data"]["username"] == "alice"
    _assert_no_private_user_data(response)
    assert password not in response.get_data(as_text=True)


def test_postgresql_create_reports_reserved_duplicate_and_missing_branch(
    clean_postgres_app,
):
    _, user, toulon, _ = _prepare_database(include_user=True)
    client = clean_postgres_app.test_client()
    token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]

    reserved = client.post(
        "/api/v1/users",
        json={
            "username": " ADMIN ",
            "password": "password",
            "branch_id": toulon.id,
        },
        headers=_bearer(token),
    )
    duplicate = client.post(
        "/api/v1/users",
        json={
            "username": " ALICE ",
            "password": "password",
            "branch_id": toulon.id,
        },
        headers=_bearer(token),
    )
    missing_branch = client.post(
        "/api/v1/users",
        json={
            "username": "bob",
            "password": "password",
            "branch_id": 999999,
        },
        headers=_bearer(token),
    )

    assert reserved.status_code == 422
    assert reserved.get_json()["error"]["code"] == "RESERVED_USERNAME"
    assert duplicate.status_code == 409
    assert (
        duplicate.get_json()["error"]["code"]
        == "USERNAME_ALREADY_EXISTS"
    )
    assert missing_branch.status_code == 404
    assert (
        missing_branch.get_json()["error"]["code"]
        == "BRANCH_NOT_FOUND"
    )

    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    deleted_duplicate = client.post(
        "/api/v1/users",
        json={
            "username": "alice",
            "password": "password",
            "branch_id": toulon.id,
        },
        headers=_bearer(token),
    )
    assert deleted_duplicate.status_code == 409


def test_postgresql_patch_reloads_username_and_branch_without_version_bump(
    clean_postgres_app,
):
    _, user, _, marseille = _prepare_database(include_user=True)
    client = clean_postgres_app.test_client()
    admin_token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]
    user_token = _login(client, "alice", USER_PASSWORD)["access_token"]

    response = client.patch(
        f"/api/v1/users/{user.id}",
        json={"username": " Alice.New ", "branch_id": marseille.id},
        headers=_bearer(admin_token),
    )

    assert response.status_code == 200
    db.session.refresh(user)
    assert user.username == "alice.new"
    assert user.branch_id == marseille.id
    assert user.token_version == 0

    current = client.get(
        "/api/v1/auth/me",
        headers=_bearer(user_token),
    )
    assert current.status_code == 200
    assert current.get_json()["data"]["username"] == "alice.new"
    assert current.get_json()["data"]["branch"]["id"] == marseille.id
    _assert_no_private_user_data(response)


def test_postgresql_password_change_invalidates_access_and_refresh_tokens(
    clean_postgres_app,
):
    _, user, _, _ = _prepare_database(include_user=True)
    client = clean_postgres_app.test_client()
    admin_token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]
    old_tokens = _login(client, "alice", USER_PASSWORD)
    new_password = "  replacement password  "

    changed = client.patch(
        f"/api/v1/users/{user.id}/password",
        json={"new_password": new_password},
        headers=_bearer(admin_token),
    )

    assert changed.status_code == 204
    assert changed.data == b""
    db.session.refresh(user)
    assert user.token_version == 1
    assert bcrypt.checkpw(
        new_password.encode("utf-8"),
        user.password_hash.encode("utf-8"),
    )

    old_access = client.get(
        "/api/v1/auth/me",
        headers=_bearer(old_tokens["access_token"]),
    )
    old_refresh = client.post(
        "/api/v1/auth/refresh",
        headers=_bearer(old_tokens["refresh_token"]),
    )
    assert old_access.status_code == old_refresh.status_code == 401
    assert (
        old_access.get_json()["error"]["code"]
        == "TOKEN_VERSION_INVALID"
    )
    assert (
        old_refresh.get_json()["error"]["code"]
        == "TOKEN_VERSION_INVALID"
    )
    assert _login(client, "alice", new_password)["access_token"]

    changed_again = client.patch(
        f"/api/v1/users/{user.id}/password",
        json={"new_password": new_password},
        headers=_bearer(admin_token),
    )
    assert changed_again.status_code == 204
    db.session.refresh(user)
    assert user.token_version == 2


def test_postgresql_soft_delete_is_idempotent_and_preserves_related_data(
    clean_postgres_app,
):
    _, user, toulon, _ = _prepare_database(include_user=True)
    stock = Stock(
        branch_id=toulon.id,
        external_product_id="HB-MON-2102",
        quantity=7,
    )
    revoked = RevokedToken(
        user_id=user.id,
        jti="previously-revoked-jti",
        token_type="access",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        reason="test",
    )
    db.session.add_all([stock, revoked])
    db.session.commit()

    client = clean_postgres_app.test_client()
    admin_token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]
    user_token = _login(client, "alice", USER_PASSWORD)["access_token"]

    first = client.delete(
        f"/api/v1/users/{user.id}",
        headers=_bearer(admin_token),
    )
    second = client.delete(
        f"/api/v1/users/{user.id}",
        headers=_bearer(admin_token),
    )

    assert first.status_code == second.status_code == 204
    assert first.data == second.data == b""
    db.session.refresh(user)
    assert user.is_active is False
    assert user.deleted_at.tzinfo is not None
    assert user.token_version == 0
    assert db.session.get(Stock, stock.id) is not None
    assert db.session.get(RevokedToken, revoked.id) is not None

    rejected_token = client.get(
        "/api/v1/auth/me",
        headers=_bearer(user_token),
    )
    assert rejected_token.status_code == 403
    assert rejected_token.get_json()["error"]["code"] == "ACCOUNT_INACTIVE"

    active = client.get(
        "/api/v1/users",
        headers=_bearer(admin_token),
    )
    deleted = client.get(
        "/api/v1/users?status=deleted",
        headers=_bearer(admin_token),
    )
    all_users = client.get(
        "/api/v1/users?status=all",
        headers=_bearer(admin_token),
    )
    detail = client.get(
        f"/api/v1/users/{user.id}",
        headers=_bearer(admin_token),
    )
    assert [item["username"] for item in active.get_json()["data"]] == [
        "admin"
    ]
    assert [item["username"] for item in deleted.get_json()["data"]] == [
        "alice"
    ]
    assert [item["username"] for item in all_users.get_json()["data"]] == [
        "admin",
        "alice",
    ]
    assert detail.status_code == 200
    assert detail.get_json()["data"]["deleted_at"].endswith("Z")

    patch_deleted = client.patch(
        f"/api/v1/users/{user.id}",
        json={"username": "other"},
        headers=_bearer(admin_token),
    )
    password_deleted = client.patch(
        f"/api/v1/users/{user.id}/password",
        json={"new_password": "other-password"},
        headers=_bearer(admin_token),
    )
    assert patch_deleted.status_code == password_deleted.status_code == 404


def test_postgresql_admin_is_read_only_through_user_management(
    clean_postgres_app,
):
    admin, _, _, _ = _prepare_database()
    client = clean_postgres_app.test_client()
    token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]

    detail = client.get(
        f"/api/v1/users/{admin.id}",
        headers=_bearer(token),
    )
    patch = client.patch(
        f"/api/v1/users/{admin.id}",
        json={"username": "other"},
        headers=_bearer(token),
    )
    password = client.patch(
        f"/api/v1/users/{admin.id}/password",
        json={"new_password": "replacement"},
        headers=_bearer(token),
    )
    delete = client.delete(
        f"/api/v1/users/{admin.id}",
        headers=_bearer(token),
    )

    assert detail.status_code == 200
    assert detail.get_json()["data"]["branch"] is None
    assert patch.status_code == password.status_code == delete.status_code == 403


def test_postgresql_unique_race_rolls_back_create_and_patch(
    clean_postgres_app,
    monkeypatch,
):
    _, alice, toulon, marseille = _prepare_database(include_user=True)
    bob = User(
        username="bob",
        password_hash=_hash(USER_PASSWORD),
        role=COMMON_USER_ROLE,
        branch_id=toulon.id,
        is_active=True,
        token_version=0,
    )
    db.session.add(bob)
    db.session.commit()

    client = clean_postgres_app.test_client()
    token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]
    monkeypatch.setattr(
        "backoffice.users.repositories.username_exists",
        lambda username, exclude_user_id=None: False,
    )

    create_conflict = client.post(
        "/api/v1/users",
        json={
            "username": "bob",
            "password": "password",
            "branch_id": toulon.id,
        },
        headers=_bearer(token),
    )
    patch_conflict = client.patch(
        f"/api/v1/users/{alice.id}",
        json={"username": "bob", "branch_id": marseille.id},
        headers=_bearer(token),
    )

    assert create_conflict.status_code == patch_conflict.status_code == 409
    assert db.session.scalar(
        select(func.count()).select_from(User)
    ) == 3
    db.session.refresh(alice)
    assert alice.username == "alice"
    assert alice.branch_id == toulon.id


def test_postgresql_branch_filter_unknown_is_empty(clean_postgres_app):
    _prepare_database(include_user=True)
    client = clean_postgres_app.test_client()
    token = _login(client, "admin", ADMIN_PASSWORD)["access_token"]

    response = client.get(
        "/api/v1/users?status=all&branch_id=999999",
        headers=_bearer(token),
    )

    assert response.status_code == 200
    assert response.get_json() == {"data": [], "meta": {"count": 0}}
