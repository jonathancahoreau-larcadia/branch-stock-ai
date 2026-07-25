"""HTTP tests for the read-only branches API."""

from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from flask_jwt_extended import decode_token

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    RevokedToken,
    User,
)
from backoffice.extensions import db

ADMIN_PASSWORD = "admin-password"
USER_PASSWORD = "user-password"


@pytest.fixture()
def branches_app(sqlite_database_app):
    return sqlite_database_app


@pytest.fixture()
def branches_client(branches_app):
    return branches_app.test_client()


def _hash(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")


def _prepare_database(app):
    with app.app_context():
        marseille = Branch(id=3, name="Marseille")
        toulon = Branch(id=2, name="Toulon")
        db.session.add_all([toulon, marseille])
        db.session.add_all(
            [
                User(
                    id=1,
                    username="admin",
                    password_hash=_hash(ADMIN_PASSWORD),
                    role=ADMIN_ROLE,
                    branch_id=None,
                    is_active=True,
                    token_version=0,
                ),
                User(
                    id=12,
                    username="alice",
                    password_hash=_hash(USER_PASSWORD),
                    role=COMMON_USER_ROLE,
                    branch_id=toulon.id,
                    is_active=True,
                    token_version=0,
                ),
            ]
        )
        db.session.commit()


def _login(client, username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_lists_and_consults_all_branches(
    branches_app,
    branches_client,
):
    _prepare_database(branches_app)
    token = _login(
        branches_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    listed = branches_client.get(
        "/api/v1/branches",
        headers=_bearer(token),
    )
    detail = branches_client.get(
        "/api/v1/branches/2",
        headers=_bearer(token),
    )

    assert listed.status_code == 200
    assert listed.get_json() == {
        "data": [
            {"id": 3, "name": "Marseille"},
            {"id": 2, "name": "Toulon"},
        ],
        "meta": {"count": 2},
    }
    assert detail.status_code == 200
    assert detail.get_json() == {
        "data": {"id": 2, "name": "Toulon"}
    }


def test_common_user_lists_and_consults_only_their_branch(
    branches_app,
    branches_client,
):
    _prepare_database(branches_app)
    token = _login(
        branches_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]

    listed = branches_client.get(
        "/api/v1/branches",
        headers=_bearer(token),
    )
    own = branches_client.get(
        "/api/v1/branches/2",
        headers=_bearer(token),
    )
    foreign = branches_client.get(
        "/api/v1/branches/3",
        headers=_bearer(token),
    )
    unknown_foreign = branches_client.get(
        "/api/v1/branches/999",
        headers=_bearer(token),
    )

    assert listed.get_json() == {
        "data": [{"id": 2, "name": "Toulon"}],
        "meta": {"count": 1},
    }
    assert own.status_code == 200
    assert foreign.status_code == unknown_foreign.status_code == 403
    assert (
        foreign.get_json()
        == unknown_foreign.get_json()
        == {
            "error": {
                "code": "BRANCH_ACCESS_FORBIDDEN",
                "message": "You cannot access this branch.",
                "details": {},
            }
        }
    )


def test_admin_unknown_branch_returns_structured_not_found(
    branches_app,
    branches_client,
):
    _prepare_database(branches_app)
    token = _login(
        branches_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    response = branches_client.get(
        "/api/v1/branches/999",
        headers=_bearer(token),
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "BRANCH_NOT_FOUND"


def test_list_rejects_every_undocumented_query_parameter(
    branches_app,
    branches_client,
):
    _prepare_database(branches_app)
    token = _login(
        branches_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    response = branches_client.get(
        "/api/v1/branches?status=active&branch_id=2",
        headers=_bearer(token),
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request data is invalid.",
            "details": {
                "fields": {
                    "unexpected": ["branch_id", "status"],
                }
            },
        }
    }


def test_access_token_is_required_and_refresh_token_is_rejected(
    branches_app,
    branches_client,
):
    _prepare_database(branches_app)
    tokens = _login(branches_client, "alice", USER_PASSWORD)

    missing = branches_client.get("/api/v1/branches")
    wrong_type = branches_client.get(
        "/api/v1/branches",
        headers=_bearer(tokens["refresh_token"]),
    )

    assert missing.status_code == 401
    assert missing.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert wrong_type.status_code == 401
    assert wrong_type.get_json()["error"]["code"] == "WRONG_TOKEN_TYPE"


@pytest.mark.parametrize("state", ["inactive", "deleted", "obsolete"])
def test_current_account_state_is_checked_on_branch_routes(
    branches_app,
    branches_client,
    state,
):
    _prepare_database(branches_app)
    token = _login(
        branches_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]
    with branches_app.app_context():
        user = db.session.get(User, 12)
        if state == "inactive":
            user.is_active = False
        elif state == "deleted":
            user.is_active = False
            user.deleted_at = datetime.now(timezone.utc)
        else:
            user.token_version += 1
        db.session.commit()

    response = branches_client.get(
        "/api/v1/branches",
        headers=_bearer(token),
    )

    if state == "obsolete":
        assert response.status_code == 401
        assert (
            response.get_json()["error"]["code"]
            == "TOKEN_VERSION_INVALID"
        )
    else:
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_revoked_access_token_is_rejected(
    branches_app,
    branches_client,
):
    _prepare_database(branches_app)
    token = _login(
        branches_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]
    with branches_app.app_context():
        claims = decode_token(token)
        db.session.add(
            RevokedToken(
                id=1,
                user_id=12,
                jti=claims["jti"],
                token_type="access",
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=30),
                reason="test",
            )
        )
        db.session.commit()

    response = branches_client.get(
        "/api/v1/branches",
        headers=_bearer(token),
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "TOKEN_REVOKED"


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_branch_crud_routes_do_not_exist(
    branches_app,
    branches_client,
    method,
):
    _prepare_database(branches_app)
    token = _login(
        branches_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    response = getattr(branches_client, method)(
        "/api/v1/branches/2",
        json={"name": "Other"},
        headers=_bearer(token),
    )

    assert response.status_code == 405
