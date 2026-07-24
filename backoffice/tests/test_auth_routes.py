"""HTTP tests for JWT authentication independent of PostgreSQL semantics."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt as pyjwt
import pytest
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

from backoffice.database.models import (
    ADMIN_ROLE,
    Branch,
    RevokedToken,
    User,
)
from backoffice.extensions import db

PASSWORD = "correct-password"


@pytest.fixture()
def auth_app(app):
    with app.app_context():
        connection = db.engine.raw_connection()
        connection.create_function(
            "btrim",
            1,
            lambda value: value.strip(),
        )
        connection.create_function("char_length", 1, len)
        connection.close()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def auth_client(auth_app):
    return auth_app.test_client()


def _password_hash(password=PASSWORD):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")


def _create_user(
    app,
    *,
    user_id=12,
    username="alice",
    role="common_user",
    is_active=True,
    deleted_at=None,
    token_version=0,
):
    with app.app_context():
        branch = None
        branch_id = None
        if role != ADMIN_ROLE:
            branch = Branch(id=2, name="Toulon")
            db.session.add(branch)
            branch_id = branch.id
        user = User(
            id=user_id,
            username=username,
            password_hash=_password_hash(),
            role=role,
            branch_id=branch_id,
            is_active=is_active,
            deleted_at=deleted_at,
            token_version=token_version,
        )
        db.session.add(user)
        db.session.commit()
        return user_id


def _login(client, username="alice", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_documented_tokens_and_minimal_claims(
    auth_app,
    auth_client,
):
    _create_user(auth_app)

    response = _login(auth_client, username="  ALICE  ")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["token_type"] == "Bearer"
    assert data["access_token_expires_in"] == 1800
    assert data["refresh_token_expires_in"] == 604800
    assert "Set-Cookie" not in response.headers
    assert data["user"] == {
        "id": 12,
        "username": "alice",
        "role": "common_user",
        "branch": {"id": 2, "name": "Toulon"},
    }
    assert "password_hash" not in response.get_data(as_text=True)

    with auth_app.app_context():
        access_claims = decode_token(data["access_token"])
        refresh_claims = decode_token(data["refresh_token"])

    for claims, token_type, lifetime in (
        (access_claims, "access", 1800),
        (refresh_claims, "refresh", 604800),
    ):
        assert claims["sub"] == "12"
        assert claims["type"] == token_type
        assert claims["token_version"] == 0
        assert claims["exp"] - claims["iat"] == lifetime
        assert isinstance(claims["jti"], str)
        assert "username" not in claims
        assert "role" not in claims
        assert "branch_id" not in claims
        assert "user_id" not in claims


def test_unknown_username_and_wrong_password_are_indistinguishable(
    auth_app,
    auth_client,
):
    _create_user(auth_app)

    wrong_password = _login(auth_client, password="wrong-password")
    unknown_user = _login(
        auth_client,
        username="unknown",
        password="wrong-password",
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.get_json() == unknown_user.get_json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "Invalid username or password.",
            "details": {},
        }
    }


@pytest.mark.parametrize(
    ("is_active", "deleted_at"),
    [
        (False, None),
        (False, datetime.now(timezone.utc)),
    ],
)
def test_correct_credentials_for_unavailable_account_return_inactive(
    auth_app,
    auth_client,
    is_active,
    deleted_at,
):
    _create_user(
        auth_app,
        is_active=is_active,
        deleted_at=deleted_at,
    )

    response = _login(auth_client)

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_wrong_password_for_inactive_account_remains_invalid_credentials(
    auth_app,
    auth_client,
):
    _create_user(auth_app, is_active=False)

    response = _login(auth_client, password="wrong-password")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_invalid_json_and_invalid_payload_are_distinct(auth_client):
    wrong_content_type = auth_client.post(
        "/api/v1/auth/login",
        data='{"username": "alice"}',
        content_type="text/plain",
    )
    malformed_json = auth_client.post(
        "/api/v1/auth/login",
        data="{",
        content_type="application/json",
    )
    unexpected_field = auth_client.post(
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": PASSWORD,
            "role": "admin",
        },
    )

    assert wrong_content_type.status_code == 400
    assert malformed_json.status_code == 400
    assert wrong_content_type.get_json()["error"]["code"] == "INVALID_JSON"
    assert malformed_json.get_json()["error"]["code"] == "INVALID_JSON"
    assert unexpected_field.status_code == 400
    assert (
        unexpected_field.get_json()["error"]["code"]
        == "VALIDATION_ERROR"
    )


def test_missing_and_malformed_bearer_are_structured(auth_client):
    missing = auth_client.get("/api/v1/auth/me")
    malformed = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Basic credentials"},
    )

    assert missing.status_code == malformed.status_code == 401
    assert missing.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert (
        malformed.get_json()["error"]["code"]
        == "AUTHENTICATION_REQUIRED"
    )


def test_me_reloads_current_database_account(auth_app, auth_client):
    _create_user(auth_app)
    login_data = _login(auth_client).get_json()["data"]

    with auth_app.app_context():
        user = db.session.get(User, 12)
        user.username = "alice.current"
        db.session.commit()

    response = auth_client.get(
        "/api/v1/auth/me",
        headers=_bearer(login_data["access_token"]),
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["username"] == "alice.current"


def test_refresh_returns_only_a_new_access_token(auth_app, auth_client):
    _create_user(auth_app)
    login_data = _login(auth_client).get_json()["data"]

    response = auth_client.post(
        "/api/v1/auth/refresh",
        headers=_bearer(login_data["refresh_token"]),
    )

    assert response.status_code == 200
    assert set(response.get_json()["data"]) == {
        "access_token",
        "token_type",
        "access_token_expires_in",
    }
    assert "refresh_token" not in response.get_data(as_text=True)


def test_wrong_token_types_are_rejected(auth_app, auth_client):
    _create_user(auth_app)
    login_data = _login(auth_client).get_json()["data"]

    access_on_refresh = auth_client.post(
        "/api/v1/auth/refresh",
        headers=_bearer(login_data["access_token"]),
    )
    refresh_on_me = auth_client.get(
        "/api/v1/auth/me",
        headers=_bearer(login_data["refresh_token"]),
    )

    assert access_on_refresh.status_code == refresh_on_me.status_code == 401
    assert (
        access_on_refresh.get_json()["error"]["code"]
        == "WRONG_TOKEN_TYPE"
    )
    assert refresh_on_me.get_json()["error"]["code"] == "WRONG_TOKEN_TYPE"


def test_expired_and_obsolete_tokens_are_rejected(auth_app, auth_client):
    _create_user(auth_app, token_version=2)
    with auth_app.app_context():
        expired_token = create_access_token(
            identity="12",
            additional_claims={"token_version": 2},
            expires_delta=timedelta(seconds=-1),
        )
        obsolete_token = create_access_token(
            identity="12",
            additional_claims={"token_version": 1},
        )

    expired = auth_client.get(
        "/api/v1/auth/me",
        headers=_bearer(expired_token),
    )
    obsolete = auth_client.get(
        "/api/v1/auth/me",
        headers=_bearer(obsolete_token),
    )

    assert expired.status_code == 401
    assert expired.get_json()["error"]["code"] == "TOKEN_EXPIRED"
    assert obsolete.status_code == 401
    assert (
        obsolete.get_json()["error"]["code"]
        == "TOKEN_VERSION_INVALID"
    )


def test_missing_required_jti_is_rejected(auth_app, auth_client):
    _create_user(auth_app)
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {
            "sub": "12",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "token_version": 0,
        },
        auth_app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    response = auth_client.get(
        "/api/v1/auth/me",
        headers=_bearer(token),
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "TOKEN_INVALID"


def test_revoked_token_is_rejected(auth_app, auth_client):
    _create_user(auth_app)
    with auth_app.app_context():
        token = create_access_token(
            identity="12",
            additional_claims={"token_version": 0},
        )
        claims = decode_token(token)
        db.session.add(
            RevokedToken(
                id=1,
                user_id=12,
                jti=claims["jti"],
                token_type="access",
                expires_at=datetime.fromtimestamp(
                    claims["exp"],
                    tz=timezone.utc,
                ),
            )
        )
        db.session.commit()

    response = auth_client.get(
        "/api/v1/auth/me",
        headers=_bearer(token),
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "TOKEN_REVOKED"


def test_logout_responses_have_no_body(auth_app, auth_client, monkeypatch):
    _create_user(auth_app)
    login_data = _login(auth_client).get_json()["data"]
    revoked_types = []

    def fake_revoke(_user, *, reason):
        revoked_types.append(reason)

    monkeypatch.setattr(
        "backoffice.auth.routes.revoke_token",
        fake_revoke,
    )

    access_response = auth_client.post(
        "/api/v1/auth/logout",
        headers=_bearer(login_data["access_token"]),
    )
    refresh_response = auth_client.post(
        "/api/v1/auth/logout/refresh",
        headers=_bearer(login_data["refresh_token"]),
    )

    assert access_response.status_code == refresh_response.status_code == 204
    assert access_response.data == refresh_response.data == b""
    assert revoked_types == ["logout", "logout"]


def test_authentication_logs_contain_no_credentials_or_tokens(
    auth_app,
    auth_client,
    caplog,
):
    _create_user(auth_app)

    login_data = _login(auth_client).get_json()["data"]
    auth_client.get(
        "/api/v1/auth/me",
        headers=_bearer(login_data["access_token"]),
    )

    assert PASSWORD not in caplog.text
    assert login_data["access_token"] not in caplog.text
    assert login_data["refresh_token"] not in caplog.text
    assert "Authorization" not in caplog.text
