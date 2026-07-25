"""PostgreSQL integration tests for the read-only branches API."""

import bcrypt
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
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


def _prepare_database():
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
    user = User(
        username="alice",
        password_hash=_hash(USER_PASSWORD),
        role=COMMON_USER_ROLE,
        branch_id=toulon.id,
        is_active=True,
        token_version=0,
    )
    stock = Stock(
        branch_id=toulon.id,
        external_product_id="HB-MON-2102",
        quantity=7,
    )
    db.session.add_all([admin, user, stock])
    db.session.commit()
    return admin, user, toulon, marseille, stock


def _login(client, username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]["access_token"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_postgresql_role_scopes_order_and_whitelist(clean_postgres_app):
    _, _, toulon, marseille, _ = _prepare_database()
    client = clean_postgres_app.test_client()
    admin_token = _login(client, "admin", ADMIN_PASSWORD)
    user_token = _login(client, "alice", USER_PASSWORD)

    admin_list = client.get(
        "/api/v1/branches",
        headers=_bearer(admin_token),
    )
    user_list = client.get(
        "/api/v1/branches",
        headers=_bearer(user_token),
    )
    user_detail = client.get(
        f"/api/v1/branches/{toulon.id}",
        headers=_bearer(user_token),
    )

    assert admin_list.status_code == user_list.status_code == 200
    assert admin_list.get_json() == {
        "data": [
            {"id": marseille.id, "name": "Marseille"},
            {"id": toulon.id, "name": "Toulon"},
        ],
        "meta": {"count": 2},
    }
    assert user_list.get_json() == {
        "data": [{"id": toulon.id, "name": "Toulon"}],
        "meta": {"count": 1},
    }
    assert user_detail.get_json() == {
        "data": {"id": toulon.id, "name": "Toulon"}
    }
    for response in (admin_list, user_list, user_detail):
        body = response.get_data(as_text=True)
        assert "created_at" not in body
        assert "updated_at" not in body
        assert "users" not in body
        assert "stocks" not in body
        assert "password_hash" not in body


def test_postgresql_existing_token_uses_current_branch_assignment(
    clean_postgres_app,
):
    _, user, toulon, marseille, _ = _prepare_database()
    client = clean_postgres_app.test_client()
    token = _login(client, "alice", USER_PASSWORD)

    user.branch_id = marseille.id
    db.session.commit()

    listed = client.get(
        "/api/v1/branches",
        headers=_bearer(token),
    )
    previous = client.get(
        f"/api/v1/branches/{toulon.id}",
        headers=_bearer(token),
    )
    current = client.get(
        f"/api/v1/branches/{marseille.id}",
        headers=_bearer(token),
    )

    assert listed.get_json() == {
        "data": [{"id": marseille.id, "name": "Marseille"}],
        "meta": {"count": 1},
    }
    assert previous.status_code == 403
    assert (
        previous.get_json()["error"]["code"]
        == "BRANCH_ACCESS_FORBIDDEN"
    )
    assert current.status_code == 200


def test_postgresql_foreign_scope_does_not_reveal_existence(
    clean_postgres_app,
):
    _, _, _, marseille, _ = _prepare_database()
    client = clean_postgres_app.test_client()
    user_token = _login(client, "alice", USER_PASSWORD)
    admin_token = _login(client, "admin", ADMIN_PASSWORD)

    existing_foreign = client.get(
        f"/api/v1/branches/{marseille.id}",
        headers=_bearer(user_token),
    )
    missing_foreign = client.get(
        "/api/v1/branches/999999",
        headers=_bearer(user_token),
    )
    admin_missing = client.get(
        "/api/v1/branches/999999",
        headers=_bearer(admin_token),
    )

    assert existing_foreign.status_code == missing_foreign.status_code == 403
    assert existing_foreign.get_json() == missing_foreign.get_json()
    assert admin_missing.status_code == 404
    assert admin_missing.get_json()["error"]["code"] == "BRANCH_NOT_FOUND"


def test_postgresql_referenced_branch_delete_is_restricted_and_rolls_back(
    clean_postgres_app,
):
    _, _, toulon, _, stock = _prepare_database()
    branch_id = toulon.id
    stock_id = stock.id

    with pytest.raises(IntegrityError):
        db.session.execute(
            delete(Branch).where(Branch.id == branch_id)
        )
        db.session.commit()
    db.session.rollback()

    assert db.session.get(Branch, branch_id) is not None
    assert db.session.get(Stock, stock_id) is not None
    assert db.session.scalar(
        select(User.id).where(User.branch_id == branch_id)
    ) is not None

    client = clean_postgres_app.test_client()
    token = _login(client, "admin", ADMIN_PASSWORD)
    response = client.get(
        f"/api/v1/branches/{branch_id}",
        headers=_bearer(token),
    )
    assert response.status_code == 200
