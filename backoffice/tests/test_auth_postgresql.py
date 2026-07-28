"""PostgreSQL integration tests for JWT authentication and revocation."""

import bcrypt
from flask_jwt_extended import decode_token
from sqlalchemy import func, select

from backoffice.database.models import Branch, RevokedToken, User
from backoffice.extensions import db

PASSWORD = "postgres-auth-password"


def _create_common_user():
    branch = Branch(name="Toulon")
    db.session.add(branch)
    db.session.flush()
    user = User(
        username="alice",
        password_hash=bcrypt.hashpw(
            PASSWORD.encode("utf-8"),
            bcrypt.gensalt(rounds=4),
        ).decode("utf-8"),
        role="common_user",
        branch_id=branch.id,
        is_active=True,
        token_version=0,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _login(client):
    return client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": PASSWORD},
    )


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_postgresql_login_refresh_and_current_user(clean_postgres_app):
    user = _create_common_user()
    client = clean_postgres_app.test_client()

    login = _login(client)

    assert login.status_code == 200
    login_data = login.get_json()["data"]
    assert login_data["user"]["id"] == user.id
    assert "password_hash" not in login.get_data(as_text=True)

    refreshed = client.post(
        "/api/v1/auth/refresh",
        headers=_bearer(login_data["refresh_token"]),
    )
    assert refreshed.status_code == 200
    assert "refresh_token" not in refreshed.get_data(as_text=True)

    current = client.get(
        "/api/v1/auth/me",
        headers=_bearer(refreshed.get_json()["data"]["access_token"]),
    )
    assert current.status_code == 200
    assert current.get_json()["data"]["branch"]["name"] == "Toulon"


def test_postgresql_logout_stores_only_access_jti(clean_postgres_app):
    user = _create_common_user()
    client = clean_postgres_app.test_client()
    login_data = _login(client).get_json()["data"]
    access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]

    response = client.post(
        "/api/v1/auth/logout",
        headers=_bearer(access_token),
    )

    assert response.status_code == 204
    assert response.data == b""
    revoked = db.session.scalars(select(RevokedToken)).one()
    access_claims = decode_token(access_token)
    refresh_claims = decode_token(refresh_token)
    assert revoked.user_id == user.id
    assert revoked.jti == access_claims["jti"]
    assert revoked.jti != refresh_claims["jti"]
    assert revoked.token_type == "access"
    assert revoked.reason == "logout"
    assert access_token not in {
        str(revoked.id),
        str(revoked.user_id),
        revoked.jti,
        revoked.token_type,
        str(revoked.expires_at),
        str(revoked.revoked_at),
        revoked.reason,
    }
    assert db.session.scalar(
        select(func.count()).select_from(RevokedToken)
    ) == 1

    rejected = client.get(
        "/api/v1/auth/me",
        headers=_bearer(access_token),
    )
    refresh_still_valid = client.post(
        "/api/v1/auth/refresh",
        headers=_bearer(refresh_token),
    )
    assert rejected.status_code == 401
    assert rejected.get_json()["error"]["code"] == "TOKEN_REVOKED"
    assert refresh_still_valid.status_code == 200


def test_postgresql_refresh_logout_stores_only_refresh_jti(
    clean_postgres_app,
):
    _create_common_user()
    client = clean_postgres_app.test_client()
    login_data = _login(client).get_json()["data"]

    response = client.post(
        "/api/v1/auth/logout/refresh",
        headers=_bearer(login_data["refresh_token"]),
    )

    assert response.status_code == 204
    revoked = db.session.scalars(select(RevokedToken)).one()
    assert revoked.token_type == "refresh"
    assert revoked.jti == decode_token(login_data["refresh_token"])["jti"]

    rejected = client.post(
        "/api/v1/auth/refresh",
        headers=_bearer(login_data["refresh_token"]),
    )
    access_still_valid = client.get(
        "/api/v1/auth/me",
        headers=_bearer(login_data["access_token"]),
    )
    assert rejected.status_code == 401
    assert rejected.get_json()["error"]["code"] == "TOKEN_REVOKED"
    assert access_still_valid.status_code == 200


def test_postgresql_account_state_and_token_version_are_current(
    clean_postgres_app,
):
    user = _create_common_user()
    client = clean_postgres_app.test_client()
    first_token = _login(client).get_json()["data"]["access_token"]

    user.token_version += 1
    db.session.commit()

    obsolete = client.get(
        "/api/v1/auth/me",
        headers=_bearer(first_token),
    )
    assert obsolete.status_code == 401
    assert obsolete.get_json()["error"]["code"] == "TOKEN_VERSION_INVALID"

    current_token = _login(client).get_json()["data"]["access_token"]
    user.is_active = False
    db.session.commit()

    inactive = client.get(
        "/api/v1/auth/me",
        headers=_bearer(current_token),
    )
    assert inactive.status_code == 403
    assert inactive.get_json()["error"]["code"] == "ACCOUNT_INACTIVE"
