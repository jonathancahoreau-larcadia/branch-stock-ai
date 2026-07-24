"""HTTP unit tests for administrator-only user-management routes."""

import bcrypt
import pytest

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    User,
)
from backoffice.extensions import db

ADMIN_PASSWORD = "admin-password"
USER_PASSWORD = "user-password"


@pytest.fixture()
def users_app(sqlite_database_app):
    return sqlite_database_app


@pytest.fixture()
def users_client(users_app):
    return users_app.test_client()


def _hash(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")


def _add_admin(app):
    with app.app_context():
        db.session.add(
            User(
                id=1,
                username="admin",
                password_hash=_hash(ADMIN_PASSWORD),
                role=ADMIN_ROLE,
                branch_id=None,
                is_active=True,
                token_version=0,
            )
        )
        db.session.commit()


def _add_branch(app, branch_id, name):
    with app.app_context():
        db.session.add(Branch(id=branch_id, name=name))
        db.session.commit()


def _add_common_user(
    app,
    *,
    user_id=12,
    username="alice",
    branch_id=2,
    password=USER_PASSWORD,
):
    with app.app_context():
        db.session.add(
            User(
                id=user_id,
                username=username,
                password_hash=_hash(password),
                role=COMMON_USER_ROLE,
                branch_id=branch_id,
                is_active=True,
                token_version=0,
            )
        )
        db.session.commit()


def _login(client, username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]["access_token"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _prepare_admin_and_user(app):
    _add_branch(app, 2, "Toulon")
    _add_admin(app)
    _add_common_user(app)


def test_admin_can_list_and_consult_admin_and_common_user(
    users_app,
    users_client,
):
    _prepare_admin_and_user(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    listed = users_client.get(
        "/api/v1/users",
        headers=_bearer(token),
    )
    detail = users_client.get(
        "/api/v1/users/1",
        headers=_bearer(token),
    )

    assert listed.status_code == 200
    assert listed.get_json()["meta"] == {"count": 2}
    assert [user["id"] for user in listed.get_json()["data"]] == [1, 12]
    assert detail.status_code == 200
    assert detail.get_json()["data"]["branch"] is None
    assert "password_hash" not in listed.get_data(as_text=True)
    assert "token_version" not in listed.get_data(as_text=True)


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/api/v1/users", None),
        (
            "post",
            "/api/v1/users",
            {"username": "bob", "password": "secret", "branch_id": 2},
        ),
        ("get", "/api/v1/users/12", None),
        ("patch", "/api/v1/users/12", {"username": "bob"}),
        (
            "patch",
            "/api/v1/users/12/password",
            {"new_password": "replacement"},
        ),
        ("delete", "/api/v1/users/12", None),
    ],
)
def test_common_user_is_forbidden_on_every_user_route(
    users_app,
    users_client,
    method,
    path,
    json,
):
    _prepare_admin_and_user(users_app)
    token = _login(users_client, "alice", USER_PASSWORD)

    response = getattr(users_client, method)(
        path,
        json=json,
        headers=_bearer(token),
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_create_rejects_extra_fields_and_returns_whitelisted_user(
    users_app,
    users_client,
    monkeypatch,
):
    _add_branch(users_app, 2, "Toulon")
    _add_admin(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    forbidden = users_client.post(
        "/api/v1/users",
        json={
            "username": "bob",
            "password": "secret",
            "branch_id": 2,
            "role": "admin",
        },
        headers=_bearer(token),
    )
    assert forbidden.status_code == 400
    assert forbidden.get_json()["error"]["code"] == "VALIDATION_ERROR"

    created_user = User(
        id=13,
        username="bob",
        password_hash="never-return",
        role=COMMON_USER_ROLE,
        branch=Branch(id=2, name="Toulon"),
        is_active=True,
        deleted_at=None,
        token_version=0,
    )
    monkeypatch.setattr(
        "backoffice.users.routes.create_user",
        lambda data: created_user,
    )

    created = users_client.post(
        "/api/v1/users",
        json={
            "username": "  BOB  ",
            "password": "secret",
            "branch_id": 2,
        },
        headers=_bearer(token),
    )

    assert created.status_code == 201
    assert created.get_json()["data"] == {
        "id": 13,
        "username": "bob",
        "role": "common_user",
        "branch": {"id": 2, "name": "Toulon"},
        "is_active": True,
        "deleted_at": None,
    }
    assert "never-return" not in created.get_data(as_text=True)


def test_user_mutation_distinguishes_invalid_json_from_invalid_payload(
    users_app,
    users_client,
):
    _add_admin(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    wrong_content_type = users_client.post(
        "/api/v1/users",
        data='{"username": "alice"}',
        content_type="text/plain",
        headers=_bearer(token),
    )
    malformed_json = users_client.post(
        "/api/v1/users",
        data="{",
        content_type="application/json",
        headers=_bearer(token),
    )
    invalid_payload = users_client.patch(
        "/api/v1/users/999",
        json={},
        headers=_bearer(token),
    )

    assert wrong_content_type.status_code == malformed_json.status_code == 400
    assert (
        wrong_content_type.get_json()["error"]["code"]
        == "INVALID_JSON"
    )
    assert malformed_json.get_json()["error"]["code"] == "INVALID_JSON"
    assert invalid_payload.status_code == 400
    assert (
        invalid_payload.get_json()["error"]["code"]
        == "VALIDATION_ERROR"
    )


def test_create_reports_reserved_duplicate_and_missing_branch(
    users_app,
    users_client,
):
    _prepare_admin_and_user(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    reserved = users_client.post(
        "/api/v1/users",
        json={
            "username": " ADMIN ",
            "password": "secret",
            "branch_id": 2,
        },
        headers=_bearer(token),
    )
    duplicate = users_client.post(
        "/api/v1/users",
        json={
            "username": " ALICE ",
            "password": "secret",
            "branch_id": 2,
        },
        headers=_bearer(token),
    )
    missing_branch = users_client.post(
        "/api/v1/users",
        json={
            "username": "bob",
            "password": "secret",
            "branch_id": 999,
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


def test_patch_updates_username_and_branch_without_changing_token_version(
    users_app,
    users_client,
):
    _prepare_admin_and_user(users_app)
    _add_branch(users_app, 3, "Marseille")
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    response = users_client.patch(
        "/api/v1/users/12",
        json={"username": "  Alice.New  ", "branch_id": 3},
        headers=_bearer(token),
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["username"] == "alice.new"
    assert response.get_json()["data"]["branch"]["id"] == 3
    with users_app.app_context():
        user = db.session.get(User, 12)
        assert user.token_version == 0


def test_password_change_increments_version_and_returns_empty_204(
    users_app,
    users_client,
):
    _prepare_admin_and_user(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)
    new_password = "  replacement password  "

    response = users_client.patch(
        "/api/v1/users/12/password",
        json={"new_password": new_password},
        headers=_bearer(token),
    )

    assert response.status_code == 204
    assert response.data == b""
    with users_app.app_context():
        user = db.session.get(User, 12)
        assert user.token_version == 1
        assert bcrypt.checkpw(
            new_password.encode("utf-8"),
            user.password_hash.encode("utf-8"),
        )


def test_delete_is_idempotent_and_deleted_user_remains_readable(
    users_app,
    users_client,
):
    _prepare_admin_and_user(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    first = users_client.delete(
        "/api/v1/users/12",
        headers=_bearer(token),
    )
    second = users_client.delete(
        "/api/v1/users/12",
        headers=_bearer(token),
    )
    detail = users_client.get(
        "/api/v1/users/12",
        headers=_bearer(token),
    )
    active = users_client.get(
        "/api/v1/users?status=active",
        headers=_bearer(token),
    )
    deleted = users_client.get(
        "/api/v1/users?status=deleted",
        headers=_bearer(token),
    )

    assert first.status_code == second.status_code == 204
    assert first.data == second.data == b""
    assert detail.status_code == 200
    assert detail.get_json()["data"]["is_active"] is False
    assert detail.get_json()["data"]["deleted_at"].endswith("Z")
    assert [item["id"] for item in active.get_json()["data"]] == [1]
    assert [item["id"] for item in deleted.get_json()["data"]] == [12]

    rejected = users_client.patch(
        "/api/v1/users/12",
        json={"username": "other"},
        headers=_bearer(token),
    )
    assert rejected.status_code == 404
    assert rejected.get_json()["error"]["code"] == "USER_NOT_FOUND"


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("patch", "/api/v1/users/1", {"username": "other"}),
        (
            "patch",
            "/api/v1/users/1/password",
            {"new_password": "replacement"},
        ),
        ("delete", "/api/v1/users/1", None),
    ],
)
def test_admin_target_cannot_be_mutated(
    users_app,
    users_client,
    method,
    path,
    json,
):
    _add_admin(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    response = getattr(users_client, method)(
        path,
        json=json,
        headers=_bearer(token),
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_list_filters_branch_and_validates_query(users_app, users_client):
    _prepare_admin_and_user(users_app)
    token = _login(users_client, "admin", ADMIN_PASSWORD)

    branch = users_client.get(
        "/api/v1/users?status=all&branch_id=2",
        headers=_bearer(token),
    )
    nonexistent = users_client.get(
        "/api/v1/users?branch_id=999",
        headers=_bearer(token),
    )
    invalid = users_client.get(
        "/api/v1/users?status=inactive",
        headers=_bearer(token),
    )

    assert [item["id"] for item in branch.get_json()["data"]] == [12]
    assert nonexistent.get_json() == {"data": [], "meta": {"count": 0}}
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "VALIDATION_ERROR"
