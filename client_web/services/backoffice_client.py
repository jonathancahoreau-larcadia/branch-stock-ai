"""HTTP client for the Backoffice API.

Each method maps to a route documented in ``docs/api_contracts.md``.
Tokens are passed from the Flask session so the caller never handles them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from ..config import Config


@dataclass
class BackofficeResponse:
    """Normalised wrapper around a Backoffice API response."""

    ok: bool
    status_code: int
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class BackofficeClient:
    """Stateless client — all requests accept an ``access_token`` parameter."""

    def __init__(self) -> None:
        self._base_url = Config.BACKOFFICE_BASE_URL.rstrip("/")
        self._timeout = Config.BACKOFFICE_TIMEOUT

    # ── helpers ────────────────────────────────────────────────

    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _parse(self, resp: requests.Response) -> BackofficeResponse:
        try:
            body: dict[str, Any] = resp.json()
        except ValueError:
            body = {}

        if resp.ok:
            return BackofficeResponse(
                ok=True,
                status_code=resp.status_code,
                data=body.get("data"),
            )
        return BackofficeResponse(
            ok=False,
            status_code=resp.status_code,
            error=body.get("error"),
        )

    def _get(
        self, path: str, token: str | None = None, params: dict[str, Any] | None = None
    ) -> BackofficeResponse:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.get(
                url, headers=self._headers(token), params=params, timeout=self._timeout
            )
        except requests.ConnectionError:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "CONNECTION_ERROR", "message": "Cannot connect to Backoffice"})
        except requests.Timeout:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "TIMEOUT", "message": "Backoffice did not respond in time"})
        return self._parse(resp)

    def _post(
        self,
        path: str,
        token: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> BackofficeResponse:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.post(
                url,
                headers=self._headers(token),
                json=json_body,
                timeout=self._timeout,
            )
        except requests.ConnectionError:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "CONNECTION_ERROR", "message": "Cannot connect to Backoffice"})
        except requests.Timeout:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "TIMEOUT", "message": "Backoffice did not respond in time"})
        return self._parse(resp)

    def _patch(
        self, path: str, token: str, json_body: dict[str, Any] | None = None
    ) -> BackofficeResponse:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.patch(
                url,
                headers=self._headers(token),
                json=json_body,
                timeout=self._timeout,
            )
        except requests.ConnectionError:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "CONNECTION_ERROR", "message": "Cannot connect to Backoffice"})
        except requests.Timeout:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "TIMEOUT", "message": "Backoffice did not respond in time"})
        return self._parse(resp)

    def _delete(self, path: str, token: str) -> BackofficeResponse:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.delete(
                url, headers=self._headers(token), timeout=self._timeout
            )
        except requests.ConnectionError:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "CONNECTION_ERROR", "message": "Cannot connect to Backoffice"})
        except requests.Timeout:
            return BackofficeResponse(ok=False, status_code=0, error={"code": "TIMEOUT", "message": "Backoffice did not respond in time"})
        return self._parse(resp)

    # ── Auth (public, no token) ────────────────────────────────

    def login(self, username: str, password: str) -> BackofficeResponse:
        """POST /auth/login"""
        return self._post("/auth/login", json_body={"username": username, "password": password})

    def refresh_token(self, refresh_token: str) -> BackofficeResponse:
        """POST /auth/refresh"""
        return self._post("/auth/refresh", token=refresh_token)

    def get_me(self, access_token: str) -> BackofficeResponse:
        """GET /auth/me"""
        return self._get("/auth/me", token=access_token)

    # ── Token revocation ───────────────────────────────────────

    def logout_access(self, access_token: str) -> BackofficeResponse:
        """POST /auth/logout"""
        return self._post("/auth/logout", token=access_token)

    def logout_refresh(self, refresh_token: str) -> BackofficeResponse:
        """POST /auth/logout/refresh"""
        return self._post("/auth/logout/refresh", token=refresh_token)

    # ── Users (admin) ──────────────────────────────────────────

    def list_users(
        self, access_token: str, status: str | None = None, branch_id: int | None = None
    ) -> BackofficeResponse:
        """GET /users"""
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if branch_id is not None:
            params["branch_id"] = branch_id
        return self._get("/users", token=access_token, params=params or None)

    def get_user(self, access_token: str, user_id: int) -> BackofficeResponse:
        """GET /users/{user_id}"""
        return self._get(f"/users/{user_id}", token=access_token)

    def create_user(self, access_token: str, username: str, password: str, branch_id: int) -> BackofficeResponse:
        """POST /users"""
        return self._post(
            "/users",
            token=access_token,
            json_body={"username": username, "password": password, "branch_id": branch_id},
        )

    def update_user(self, access_token: str, user_id: int, **kwargs: Any) -> BackofficeResponse:
        """PATCH /users/{user_id}"""
        return self._patch(f"/users/{user_id}", token=access_token, json_body=kwargs)

    def change_user_password(self, access_token: str, user_id: int, new_password: str) -> BackofficeResponse:
        """PATCH /users/{user_id}/password"""
        return self._patch(
            f"/users/{user_id}/password",
            token=access_token,
            json_body={"new_password": new_password},
        )

    def delete_user(self, access_token: str, user_id: int) -> BackofficeResponse:
        """DELETE /users/{user_id}"""
        return self._delete(f"/users/{user_id}", token=access_token)

    # ── Branches ───────────────────────────────────────────────

    def list_branches(self, access_token: str) -> BackofficeResponse:
        """GET /branches"""
        return self._get("/branches", token=access_token)

    def get_branch(self, access_token: str, branch_id: int) -> BackofficeResponse:
        """GET /branches/{branch_id}"""
        return self._get(f"/branches/{branch_id}", token=access_token)

    # ── Products ───────────────────────────────────────────────

    def list_products(self, access_token: str) -> BackofficeResponse:
        """GET /products"""
        return self._get("/products", token=access_token)

    def get_product(self, access_token: str, external_product_id: str) -> BackofficeResponse:
        """GET /products/{external_product_id}"""
        return self._get(f"/products/{external_product_id}", token=access_token)

    # ── Stocks (common user) ───────────────────────────────────

    def list_stocks(self, access_token: str, available_only: bool = True) -> BackofficeResponse:
        """GET /stocks"""
        return self._get(
            "/stocks",
            token=access_token,
            params={"available_only": str(available_only).lower()},
        )

    def get_stock(self, access_token: str, external_product_id: str) -> BackofficeResponse:
        """GET /stocks/{external_product_id}"""
        return self._get(f"/stocks/{external_product_id}", token=access_token)

    def add_stock(self, access_token: str, external_product_id: str, quantity: int) -> BackofficeResponse:
        """POST /stocks/{external_product_id}/add"""
        return self._post(
            f"/stocks/{external_product_id}/add",
            token=access_token,
            json_body={"quantity": quantity},
        )

    def remove_stock(self, access_token: str, external_product_id: str, quantity: int) -> BackofficeResponse:
        """POST /stocks/{external_product_id}/remove"""
        return self._post(
            f"/stocks/{external_product_id}/remove",
            token=access_token,
            json_body={"quantity": quantity},
        )