"""HTTP tests for authenticated, branch-scoped stock routes."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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
from backoffice.products.services import ProductTimeoutServiceError
from backoffice.stocks.services import (
    InsufficientStockError,
    StockDetailResult,
    StockListResult,
    StockNotFoundError,
)

ADMIN_PASSWORD = "admin-password"
USER_PASSWORD = "user-password"


@pytest.fixture()
def stocks_app(sqlite_database_app):
    return sqlite_database_app


@pytest.fixture()
def stocks_client(stocks_app):
    return stocks_app.test_client()


def _hash(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")


def _prepare_database(app):
    with app.app_context():
        branch = Branch(id=2, name="Toulon")
        db.session.add(branch)
        db.session.add_all(
            [
                User(
                    id=1,
                    username="admin",
                    password_hash=_hash(ADMIN_PASSWORD),
                    role=ADMIN_ROLE,
                    is_active=True,
                    token_version=0,
                ),
                User(
                    id=12,
                    username="alice",
                    password_hash=_hash(USER_PASSWORD),
                    role=COMMON_USER_ROLE,
                    branch_id=2,
                    is_active=True,
                    token_version=0,
                ),
            ]
        )
        db.session.commit()


def _login(client, username="alice", password=USER_PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _branch():
    return SimpleNamespace(id=2, name="Toulon")


def _stock(quantity=8):
    return SimpleNamespace(
        external_product_id="HB-MON-2102",
        quantity=quantity,
    )


def _product():
    return {"name": "24 inch Compact Monitor"}


def _detail(quantity=8):
    return StockDetailResult(_branch(), _stock(quantity), _product())


def test_list_default_true_false_and_empty_responses_are_exact(
    stocks_app,
    stocks_client,
    monkeypatch,
):
    _prepare_database(stocks_app)
    received = []

    def fake_list(user, filters):
        received.append((user.id, filters.available_only))
        items = (
            []
            if len(received) == 1
            else [
                {
                    "external_product_id": "HB-MON-2102",
                    "quantity": 0,
                    "product": {"name": "24 inch Compact Monitor"},
                }
            ]
        )
        return StockListResult(_branch(), items)

    monkeypatch.setattr("backoffice.stocks.routes.list_stocks", fake_list)
    token = _login(stocks_client)["access_token"]

    empty = stocks_client.get(
        "/api/v1/stocks",
        headers=_bearer(token),
    )
    with_zero = stocks_client.get(
        "/api/v1/stocks?available_only=false",
        headers=_bearer(token),
    )

    assert received == [(12, True), (12, False)]
    assert empty.get_json() == {
        "data": {
            "branch": {"id": 2, "name": "Toulon"},
            "items": [],
        },
        "meta": {"count": 0},
    }
    assert with_zero.get_json()["meta"] == {"count": 1}


@pytest.mark.parametrize(
    "query",
    [
        "available_only=TRUE",
        "available_only=1",
        "available_only=true&available_only=false",
        "branch_id=2",
    ],
)
def test_list_rejects_invalid_or_branch_selecting_query(
    stocks_app,
    stocks_client,
    query,
):
    _prepare_database(stocks_app)
    token = _login(stocks_client)["access_token"]
    response = stocks_client.get(
        f"/api/v1/stocks?{query}",
        headers=_bearer(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_detail_and_movements_return_exact_whitelist(
    stocks_app,
    stocks_client,
    monkeypatch,
):
    _prepare_database(stocks_app)
    calls = []
    monkeypatch.setattr(
        "backoffice.stocks.routes.get_stock",
        lambda user, identifier: calls.append(("get", user.id, identifier))
        or _detail(0),
    )
    monkeypatch.setattr(
        "backoffice.stocks.routes.add_stock",
        lambda user, identifier, data: calls.append(
            ("add", user.id, identifier, data.quantity)
        )
        or _detail(3),
    )
    monkeypatch.setattr(
        "backoffice.stocks.routes.remove_stock",
        lambda user, identifier, data: calls.append(
            ("remove", user.id, identifier, data.quantity)
        )
        or _detail(0),
    )
    token = _login(stocks_client)["access_token"]
    headers = _bearer(token)

    detail = stocks_client.get("/api/v1/stocks/42", headers=headers)
    added = stocks_client.post(
        "/api/v1/stocks/HB-MON-2102/add",
        json={"quantity": 3},
        headers=headers,
    )
    removed = stocks_client.post(
        "/api/v1/stocks/HB-MON-2102/remove",
        json={"quantity": 3},
        headers=headers,
    )

    assert calls == [
        ("get", 12, "42"),
        ("add", 12, "HB-MON-2102", 3),
        ("remove", 12, "HB-MON-2102", 3),
    ]
    assert (
        detail.status_code
        == added.status_code
        == removed.status_code
        == 200
    )
    assert detail.get_json() == {
        "data": {
            "branch": {"id": 2, "name": "Toulon"},
            "external_product_id": "HB-MON-2102",
            "quantity": 0,
            "product": {"name": "24 inch Compact Monitor"},
        }
    }
    forbidden = {
        "password_hash",
        "token_version",
        "created_at",
        "updated_at",
        "branch_id",
        "discontinued",
    }
    assert not forbidden.intersection(str(added.get_json()))


@pytest.mark.parametrize(
    ("payload", "content_type", "expected"),
    [
        ('{"quantity":', "application/json", "INVALID_JSON"),
        ('{"quantity": 1}', "text/plain", "INVALID_JSON"),
        ("null", "application/json", "VALIDATION_ERROR"),
        ("{}", "application/json", "VALIDATION_ERROR"),
        (
            '{"quantity": 1, "branch_id": 2}',
            "application/json",
            "VALIDATION_ERROR",
        ),
        ('{"quantity": true}', "application/json", "INVALID_QUANTITY"),
        ('{"quantity": "1"}', "application/json", "INVALID_QUANTITY"),
        ('{"quantity": 1.0}', "application/json", "INVALID_QUANTITY"),
        ('{"quantity": 0}', "application/json", "INVALID_QUANTITY"),
        ('{"quantity": -1}', "application/json", "INVALID_QUANTITY"),
    ],
)
def test_movement_validation_is_strict(
    stocks_app,
    stocks_client,
    payload,
    content_type,
    expected,
):
    _prepare_database(stocks_app)
    token = _login(stocks_client)["access_token"]
    response = stocks_client.post(
        "/api/v1/stocks/HB-MON-2102/add",
        data=payload,
        content_type=content_type,
        headers=_bearer(token),
    )
    assert response.status_code == (
        422 if expected == "INVALID_QUANTITY" else 400
    )
    assert response.get_json()["error"]["code"] == expected


def test_admin_is_denied_with_dedicated_error_before_products_call(
    stocks_app,
    stocks_client,
):
    _prepare_database(stocks_app)
    token = _login(
        stocks_client, "admin", ADMIN_PASSWORD
    )["access_token"]

    response = stocks_client.get(
        "/api/v1/stocks",
        headers=_bearer(token),
    )
    invalid_movement = stocks_client.post(
        "/api/v1/stocks/HB-MON-2102/add",
        data="not-json",
        content_type="text/plain",
        headers=_bearer(token),
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "ADMIN_STOCK_FORBIDDEN"
    assert invalid_movement.status_code == 403
    assert (
        invalid_movement.get_json()["error"]["code"]
        == "ADMIN_STOCK_FORBIDDEN"
    )


def test_stock_and_product_errors_are_structured(
    stocks_app,
    stocks_client,
    monkeypatch,
):
    _prepare_database(stocks_app)
    token = _login(stocks_client)["access_token"]
    headers = _bearer(token)
    monkeypatch.setattr(
        "backoffice.stocks.routes.get_stock",
        lambda *_args: (_ for _ in ()).throw(StockNotFoundError()),
    )
    missing = stocks_client.get(
        "/api/v1/stocks/HB-MON-2102",
        headers=headers,
    )
    monkeypatch.setattr(
        "backoffice.stocks.routes.remove_stock",
        lambda *_args: (_ for _ in ()).throw(InsufficientStockError()),
    )
    insufficient = stocks_client.post(
        "/api/v1/stocks/HB-MON-2102/remove",
        json={"quantity": 9},
        headers=headers,
    )
    monkeypatch.setattr(
        "backoffice.stocks.routes.list_stocks",
        lambda *_args: (_ for _ in ()).throw(
            ProductTimeoutServiceError()
        ),
    )
    timeout = stocks_client.get("/api/v1/stocks", headers=headers)

    assert (missing.status_code, missing.get_json()["error"]["code"]) == (
        404,
        "STOCK_NOT_FOUND",
    )
    assert (
        insufficient.status_code,
        insufficient.get_json()["error"]["code"],
    ) == (422, "INSUFFICIENT_STOCK")
    assert (timeout.status_code, timeout.get_json()["error"]["code"]) == (
        504,
        "PRODUCT_API_TIMEOUT",
    )


def test_access_token_state_is_rechecked_for_every_stock_route(
    stocks_app,
    stocks_client,
    monkeypatch,
):
    _prepare_database(stocks_app)
    monkeypatch.setattr(
        "backoffice.stocks.routes.list_stocks",
        lambda *_args: StockListResult(_branch(), []),
    )
    tokens = _login(stocks_client)
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    endpoints = [
        ("GET", "/api/v1/stocks", None),
        ("GET", "/api/v1/stocks/HB-MON-2102", None),
        ("POST", "/api/v1/stocks/HB-MON-2102/add", {"quantity": 1}),
        (
            "POST",
            "/api/v1/stocks/HB-MON-2102/remove",
            {"quantity": 1},
        ),
    ]
    for method, url, payload in endpoints:
        missing = stocks_client.open(method=method, path=url, json=payload)
        wrong_type = stocks_client.open(
            method=method,
            path=url,
            json=payload,
            headers=_bearer(refresh),
        )
        assert missing.status_code == 401
        assert wrong_type.get_json()["error"]["code"] == "WRONG_TOKEN_TYPE"
    with stocks_app.app_context():
        claims = decode_token(access)
        db.session.add(
            RevokedToken(
                id=1,
                user_id=12,
                jti=claims["jti"],
                token_type="access",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
        db.session.commit()
    revoked = stocks_client.get(
        "/api/v1/stocks",
        headers=_bearer(access),
    )

    assert revoked.get_json()["error"]["code"] == "TOKEN_REVOKED"


@pytest.mark.parametrize("state", ["version", "inactive", "deleted"])
def test_changed_account_state_blocks_existing_stock_token(
    stocks_app,
    stocks_client,
    monkeypatch,
    state,
):
    _prepare_database(stocks_app)
    monkeypatch.setattr(
        "backoffice.stocks.routes.list_stocks",
        lambda *_args: StockListResult(_branch(), []),
    )
    token = _login(stocks_client)["access_token"]
    with stocks_app.app_context():
        user = db.session.get(User, 12)
        if state == "version":
            user.token_version += 1
        elif state == "inactive":
            user.is_active = False
        else:
            user.is_active = False
            user.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

    response = stocks_client.get(
        "/api/v1/stocks",
        headers=_bearer(token),
    )

    expected = (
        "TOKEN_VERSION_INVALID"
        if state == "version"
        else "ACCOUNT_INACTIVE"
    )
    assert response.get_json()["error"]["code"] == expected
