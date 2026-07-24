"""HTTP tests for the authenticated read-only products API."""

from datetime import datetime, timezone

import bcrypt
import pytest
from sqlalchemy import event

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    User,
)
from backoffice.extensions import db
from backoffice.products.services import (
    ProductInvalidResponseServiceError,
    ProductListResult,
    ProductNotFoundServiceError,
    ProductTimeoutServiceError,
    ProductUnavailableServiceError,
)

ADMIN_PASSWORD = "admin-password"
USER_PASSWORD = "user-password"
SUMMARY = {
    "external_product_id": "HB-MON-2102",
    "name": "24 inch Compact Monitor",
    "category": "Displays",
    "brand": "LabForge",
    "unit_price": 169.99,
    "currency": "USD",
    "discontinued": False,
}
DETAIL = {
    **SUMMARY,
    "description": "A compact display.",
    "supplier": {
        "id": "SUP-LAB-002",
        "name": "LabForge Supplies",
        "country": "UY",
        "lead_time_days": 7,
        "reliability_score": 0.94,
    },
    "weight_kg": 3.9,
    "tags": ["display", "compact"],
    "updated_at": "2026-05-22T12:00:00Z",
}


@pytest.fixture()
def products_app(sqlite_database_app):
    return sqlite_database_app


@pytest.fixture()
def products_client(products_app):
    return products_app.test_client()


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
                    branch_id=None,
                    is_active=True,
                    token_version=0,
                ),
                User(
                    id=12,
                    username="alice",
                    password_hash=_hash(USER_PASSWORD),
                    role=COMMON_USER_ROLE,
                    branch_id=branch.id,
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


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("admin", ADMIN_PASSWORD),
        ("alice", USER_PASSWORD),
    ],
)
def test_admin_and_common_user_can_list_products(
    products_app,
    products_client,
    monkeypatch,
    username,
    password,
):
    _prepare_database(products_app)
    received = []

    def fake_list(query):
        received.append(query)
        return ProductListResult(
            data=[SUMMARY],
            total=40,
            limit=query.limit,
            offset=query.offset,
        )

    monkeypatch.setattr(
        "backoffice.products.routes.list_products",
        fake_list,
    )
    token = _login(products_client, username, password)["access_token"]

    response = products_client.get(
        "/api/v1/products"
        "?q=monitor&category=Displays"
        "&supplier_id=SUP-LAB-002"
        "&include_discontinued=false"
        "&min_price=50&max_price=200"
        "&limit=1&offset=0&sort=-unit_price",
        headers=_bearer(token),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "data": [SUMMARY],
        "meta": {
            "count": 1,
            "total": 40,
            "limit": 1,
            "offset": 0,
        },
    }
    assert received[0].params == {
        "q": "monitor",
        "category": "Displays",
        "supplier_id": "SUP-LAB-002",
        "include_discontinued": "false",
        "min_price": "50",
        "max_price": "200",
        "limit": "1",
        "offset": "0",
        "sort": "-unit_price",
    }


def test_empty_product_list_uses_zero_page_count(
    products_app,
    products_client,
    monkeypatch,
):
    _prepare_database(products_app)
    monkeypatch.setattr(
        "backoffice.products.routes.list_products",
        lambda query: ProductListResult(
            data=[],
            total=0,
            limit=20,
            offset=0,
        ),
    )
    token = _login(
        products_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]

    response = products_client.get(
        "/api/v1/products",
        headers=_bearer(token),
    )

    assert response.get_json() == {
        "data": [],
        "meta": {
            "count": 0,
            "total": 0,
            "limit": 20,
            "offset": 0,
        },
    }


@pytest.mark.parametrize("identifier", ["4", "HB-MON-2102"])
def test_product_detail_accepts_numeric_id_or_sku(
    products_app,
    products_client,
    monkeypatch,
    identifier,
):
    _prepare_database(products_app)
    received = []

    def fake_get(value):
        received.append(value)
        return DETAIL

    monkeypatch.setattr(
        "backoffice.products.routes.get_product",
        fake_get,
    )
    token = _login(
        products_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]

    response = products_client.get(
        f"/api/v1/products/{identifier}",
        headers=_bearer(token),
    )

    assert response.status_code == 200
    assert response.get_json() == {"data": DETAIL}
    assert received == [identifier]
    body = response.get_data(as_text=True)
    assert "contact_email" not in body
    assert "supplier_id" not in body
    assert "supplier_name" not in body


def test_discontinued_detail_remains_consultable(
    products_app,
    products_client,
    monkeypatch,
):
    _prepare_database(products_app)
    monkeypatch.setattr(
        "backoffice.products.routes.get_product",
        lambda identifier: {**DETAIL, "discontinued": True},
    )
    token = _login(
        products_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]

    response = products_client.get(
        "/api/v1/products/HB-OLD-1301",
        headers=_bearer(token),
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["discontinued"] is True


def test_list_rejects_invalid_or_unexpected_query_before_service(
    products_app,
    products_client,
    monkeypatch,
):
    _prepare_database(products_app)

    def unexpected_service(_query):
        raise AssertionError("Invalid query must not reach the service.")

    monkeypatch.setattr(
        "backoffice.products.routes.list_products",
        unexpected_service,
    )
    token = _login(
        products_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    duplicate = products_client.get(
        "/api/v1/products?q=one&q=two",
        headers=_bearer(token),
    )
    unexpected = products_client.get(
        "/api/v1/products?force_error=true",
        headers=_bearer(token),
    )
    invalid = products_client.get(
        "/api/v1/products?limit=101",
        headers=_bearer(token),
    )

    for response in (duplicate, unexpected, invalid):
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_detail_rejects_query_parameters_before_service(
    products_app,
    products_client,
    monkeypatch,
):
    _prepare_database(products_app)
    monkeypatch.setattr(
        "backoffice.products.routes.get_product",
        lambda identifier: pytest.fail("Service must not be called."),
    )
    token = _login(
        products_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    response = products_client.get(
        "/api/v1/products/HB-MON-2102?q=monitor",
        headers=_bearer(token),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("service_error", "status", "code"),
    [
        (ProductNotFoundServiceError(), 404, "PRODUCT_NOT_FOUND"),
        (ProductTimeoutServiceError(), 504, "PRODUCT_API_TIMEOUT"),
        (
            ProductUnavailableServiceError(),
            503,
            "PRODUCT_API_UNAVAILABLE",
        ),
        (
            ProductInvalidResponseServiceError(),
            502,
            "PRODUCT_API_INVALID_RESPONSE",
        ),
    ],
)
def test_product_service_errors_use_stable_envelopes(
    products_app,
    products_client,
    monkeypatch,
    service_error,
    status,
    code,
):
    _prepare_database(products_app)

    def failing_get(_identifier):
        raise service_error

    monkeypatch.setattr(
        "backoffice.products.routes.get_product",
        failing_get,
    )
    token = _login(
        products_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    response = products_client.get(
        "/api/v1/products/HB-MON-2102",
        headers=_bearer(token),
    )

    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code
    assert response.get_json()["error"]["details"] == {}


def test_access_token_is_required_and_refresh_token_is_rejected(
    products_app,
    products_client,
):
    _prepare_database(products_app)
    tokens = _login(products_client, "alice", USER_PASSWORD)

    missing = products_client.get("/api/v1/products")
    wrong_type = products_client.get(
        "/api/v1/products",
        headers=_bearer(tokens["refresh_token"]),
    )

    assert missing.status_code == 401
    assert missing.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert wrong_type.status_code == 401
    assert wrong_type.get_json()["error"]["code"] == "WRONG_TOKEN_TYPE"


@pytest.mark.parametrize("state", ["inactive", "deleted", "obsolete"])
def test_current_account_state_is_checked_before_product_call(
    products_app,
    products_client,
    monkeypatch,
    state,
):
    _prepare_database(products_app)
    token = _login(
        products_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]
    with products_app.app_context():
        user = db.session.get(User, 12)
        if state == "inactive":
            user.is_active = False
        elif state == "deleted":
            user.is_active = False
            user.deleted_at = datetime.now(timezone.utc)
        else:
            user.token_version += 1
        db.session.commit()

    monkeypatch.setattr(
        "backoffice.products.routes.list_products",
        lambda query: pytest.fail("External API must not be called."),
    )
    response = products_client.get(
        "/api/v1/products",
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


def test_product_route_executes_no_database_write(
    products_app,
    products_client,
    monkeypatch,
):
    _prepare_database(products_app)
    token = _login(
        products_client,
        "alice",
        USER_PASSWORD,
    )["access_token"]
    statements = []

    def record_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        statements.append(statement.lstrip().upper())

    monkeypatch.setattr(
        "backoffice.products.routes.list_products",
        lambda query: ProductListResult(
            data=[SUMMARY],
            total=1,
            limit=20,
            offset=0,
        ),
    )
    event.listen(
        db.engine,
        "before_cursor_execute",
        record_statement,
    )
    try:
        response = products_client.get(
            "/api/v1/products",
            headers=_bearer(token),
        )
    finally:
        event.remove(
            db.engine,
            "before_cursor_execute",
            record_statement,
        )

    assert response.status_code == 200
    assert statements
    assert all(statement.startswith("SELECT") for statement in statements)
    assert "products" not in db.metadata.tables


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/products"),
        ("patch", "/api/v1/products/HB-MON-2102"),
        ("delete", "/api/v1/products/HB-MON-2102"),
    ],
)
def test_product_write_routes_do_not_exist(
    products_app,
    products_client,
    method,
    path,
):
    _prepare_database(products_app)
    token = _login(
        products_client,
        "admin",
        ADMIN_PASSWORD,
    )["access_token"]

    response = getattr(products_client, method)(
        path,
        json={"name": "forbidden"},
        headers=_bearer(token),
    )

    assert response.status_code == 405
