"""Functional tests for Client Web routes using a mock Backoffice client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from flask.testing import FlaskClient
from werkzeug.test import TestResponse


# ── Helpers ────────────────────────────────────────────────────


def _login(
    client: FlaskClient,
    mock_backoffice: MagicMock,
    *,
    username: str = "alice",
    role: str = "common_user",
    branch: dict[str, Any] | None = None,
) -> TestResponse:
    """Simulate a successful login via POST /login and return the response."""
    mock_backoffice.login.return_value = MagicMock(
        ok=True,
        status_code=200,
        data={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "user": {
                "id": 12,
                "username": username,
                "role": role,
                "branch": branch or {"id": 2, "name": "Toulon"},
            },
        },
    )
    return client.post(
        "/login",
        data={"username": username, "password": "secret"},
        follow_redirects=False,
    )


def _login_admin(
    client: FlaskClient,
    mock_backoffice: MagicMock,
    *,
    username: str = "admin",
) -> TestResponse:
    """Simulate a successful admin login."""
    return _login(client, mock_backoffice, username=username, role="admin")


def _assert_redirect_to_login(resp: TestResponse) -> None:
    """Assert the response redirects to the login page."""
    assert resp.status_code in (302, 307), f"Expected redirect, got {resp.status_code}"
    assert "/login" in resp.headers.get("Location", ""), resp.headers.get("Location")


# ── Unauthenticated routes ─────────────────────────────────────


class TestLogin:
    """GET /login and POST /login"""

    def test_get_login_returns_form(self, client: FlaskClient) -> None:
        resp = client.get("/login")
        assert resp.status_code == 200
        resp_text = resp.data.decode()
        assert "Connexion" in resp_text
        assert "Se connecter" in resp_text

    def test_post_login_success_redirects_to_dashboard(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        resp = _login(client, mock_backoffice)
        assert resp.status_code in (
            302,
            307,
        ), f"Expected redirect, got {resp.status_code}"
        assert "/dashboard" in resp.headers.get("Location", "")

    def test_post_login_invalid_returns_error(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        mock_backoffice.login.return_value = MagicMock(
            ok=False, status_code=401, error={"code": "INVALID_CREDENTIALS"}
        )
        resp = client.post(
            "/login",
            data={"username": "alice", "password": "wrong"},
        )
        assert resp.status_code == 200
        assert "Identifiants invalides" in resp.data.decode()

    def test_post_login_missing_fields_returns_error(
        self, client: FlaskClient
    ) -> None:
        resp = client.post("/login", data={"username": "", "password": ""})
        assert resp.status_code == 200
        assert "saisir" in resp.data.decode()

    def test_login_when_already_authenticated(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        resp = client.get("/login", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/dashboard" in resp.headers.get("Location", "")


class TestLogout:
    """GET /logout"""

    def test_logout_clears_session_and_redirects(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        mock_backoffice.logout_access = MagicMock()
        mock_backoffice.logout_refresh = MagicMock()

        resp = client.get("/logout", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers.get("Location", "")
        mock_backoffice.logout_access.assert_called_once()
        mock_backoffice.logout_refresh.assert_called_once()

    def test_logout_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/logout", follow_redirects=False)
        _assert_redirect_to_login(resp)


class TestIndex:
    """GET /"""

    def test_index_redirects_to_login_when_unauthenticated(
        self, client: FlaskClient
    ) -> None:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers.get("Location", "")

    def test_index_redirects_to_dashboard_when_authenticated(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/dashboard" in resp.headers.get("Location", "")


# ── Authenticated routes ───────────────────────────────────────


class TestDashboard:
    """GET /dashboard"""

    def test_dashboard_shows_user_info(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "alice" in html
        assert "Utilisateur" in html
        assert "Toulon" in html

    def test_dashboard_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/dashboard", follow_redirects=False)
        _assert_redirect_to_login(resp)


class TestStock:
    """GET /stock, POST /stock/add, POST /stock/remove"""

    def test_stock_shows_items(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        mock_backoffice.list_stocks.return_value = MagicMock(
            ok=True,
            status_code=200,
            data={
                "branch": {"id": 2, "name": "Toulon"},
                "items": [
                    {
                        "external_product_id": "product-123",
                        "quantity": 8,
                        "product": {"name": "Example product"},
                    }
                ],
            },
        )
        resp = client.get("/stock")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "product-123" in html
        assert "8" in html
        assert "Toulon" in html

    def test_stock_empty(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        mock_backoffice.list_stocks.return_value = MagicMock(
            ok=True,
            status_code=200,
            data={"branch": {"id": 2, "name": "Toulon"}, "items": []},
        )
        resp = client.get("/stock")
        assert resp.status_code == 200
        assert "Aucun produit" in resp.data.decode()

    def test_stock_backoffice_error(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        mock_backoffice.list_stocks.return_value = MagicMock(
            ok=False, status_code=503, error={"code": "UPSTREAM_TIMEOUT"}
        )
        resp = client.get("/stock")
        assert resp.status_code == 200
        assert "Impossible de charger" in resp.data.decode()

    def test_stock_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/stock", follow_redirects=False)
        _assert_redirect_to_login(resp)

    def test_stock_add(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        mock_backoffice.list_stocks.return_value = MagicMock(
            ok=True, status_code=200, data={"branch": {"id": 2, "name": "Toulon"}, "items": []}
        )
        mock_backoffice.add_stock.return_value = MagicMock(ok=True, status_code=200, data={"quantity": 11})

        resp = client.post(
            "/stock/add",
            data={"product_id": "product-123", "quantity": "3"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert "/stock" in resp.headers.get("Location", "")
        mock_backoffice.add_stock.assert_called_once_with("test-access-token", "product-123", 3)

    def test_stock_remove(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)
        mock_backoffice.list_stocks.return_value = MagicMock(
            ok=True, status_code=200, data={"branch": {"id": 2, "name": "Toulon"}, "items": []}
        )
        mock_backoffice.remove_stock.return_value = MagicMock(ok=True, status_code=200, data={"quantity": 5})

        resp = client.post(
            "/stock/remove",
            data={"product_id": "product-123", "quantity": "3"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert "/stock" in resp.headers.get("Location", "")
        mock_backoffice.remove_stock.assert_called_once_with("test-access-token", "product-123", 3)


class TestUsersAdmin:
    """GET /users and POST /users/* (admin only)"""

    def test_users_redirects_for_common_user(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login(client, mock_backoffice)  # common_user by default
        resp = client.get("/users", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/dashboard" in resp.headers.get("Location", "")

    def test_users_shows_list_for_admin(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login_admin(client, mock_backoffice)
        mock_backoffice.list_users.return_value = MagicMock(
            ok=True,
            status_code=200,
            data=[
                {
                    "id": 1,
                    "username": "admin",
                    "role": "admin",
                    "branch": None,
                    "is_active": True,
                    "deleted_at": None,
                },
                {
                    "id": 12,
                    "username": "alice",
                    "role": "common_user",
                    "branch": {"id": 2, "name": "Toulon"},
                    "is_active": True,
                    "deleted_at": None,
                },
            ],
        )
        mock_backoffice.list_branches.return_value = MagicMock(
            ok=True,
            status_code=200,
            data=[{"id": 1, "name": "Paris"}, {"id": 2, "name": "Toulon"}],
        )
        resp = client.get("/users")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "admin" in html
        assert "alice" in html
        assert "Toulon" in html

    def test_users_create(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login_admin(client, mock_backoffice)
        mock_backoffice.list_users.return_value = MagicMock(ok=True, status_code=200, data=[])
        mock_backoffice.list_branches.return_value = MagicMock(ok=True, status_code=200, data=[])
        mock_backoffice.create_user.return_value = MagicMock(ok=True, status_code=201, data={"id": 99})

        resp = client.post(
            "/users/create",
            data={"username": "bob", "password": "pw", "branch_id": "2"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert "/users" in resp.headers.get("Location", "")
        mock_backoffice.create_user.assert_called_once_with("test-access-token", "bob", "pw", 2)

    def test_users_delete(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login_admin(client, mock_backoffice)
        mock_backoffice.list_users.return_value = MagicMock(ok=True, status_code=200, data=[])
        mock_backoffice.list_branches.return_value = MagicMock(ok=True, status_code=200, data=[])
        mock_backoffice.delete_user.return_value = MagicMock(ok=True, status_code=204, data=None)

        resp = client.post(
            "/users/12/delete",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert "/users" in resp.headers.get("Location", "")
        mock_backoffice.delete_user.assert_called_once_with("test-access-token", 12)

    def test_users_change_password(
        self, client: FlaskClient, mock_backoffice: MagicMock
    ) -> None:
        _login_admin(client, mock_backoffice)
        mock_backoffice.list_users.return_value = MagicMock(ok=True, status_code=200, data=[])
        mock_backoffice.list_branches.return_value = MagicMock(ok=True, status_code=200, data=[])
        mock_backoffice.change_user_password.return_value = MagicMock(ok=True, status_code=204, data=None)

        resp = client.post(
            "/users/12/password",
            data={"new_password": "new-secret"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert "/users" in resp.headers.get("Location", "")
        mock_backoffice.change_user_password.assert_called_once_with(
            "test-access-token", 12, "new-secret"
        )

    def test_users_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/users", follow_redirects=False)
        _assert_redirect_to_login(resp)