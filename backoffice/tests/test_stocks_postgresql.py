"""PostgreSQL integration and concurrency tests for stock management."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import bcrypt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    Stock,
    User,
)
from backoffice.extensions import db
from backoffice.products.services import ProductTimeoutServiceError
from backoffice.stocks.schemas import StockMovementData
from backoffice.stocks.services import add_stock, remove_stock

ADMIN_PASSWORD = "postgres-admin-password"
USER_PASSWORD = "postgres-user-password"
SKU = "HB-MON-2102"


def _hash(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")


def _prepare_database(app, *, quantity=None, other_quantity=None):
    with app.app_context():
        toulon = Branch(name="Toulon")
        marseille = Branch(name="Marseille")
        db.session.add_all([toulon, marseille])
        db.session.flush()
        admin = User(
            username="admin",
            password_hash=_hash(ADMIN_PASSWORD),
            role=ADMIN_ROLE,
            is_active=True,
        )
        alice = User(
            username="alice",
            password_hash=_hash(USER_PASSWORD),
            role=COMMON_USER_ROLE,
            branch_id=toulon.id,
            is_active=True,
        )
        bob = User(
            username="bob",
            password_hash=_hash(USER_PASSWORD),
            role=COMMON_USER_ROLE,
            branch_id=marseille.id,
            is_active=True,
        )
        db.session.add_all([admin, alice, bob])
        db.session.flush()
        if quantity is not None:
            db.session.add(
                Stock(
                    branch_id=toulon.id,
                    external_product_id=SKU,
                    quantity=quantity,
                )
            )
        if other_quantity is not None:
            db.session.add(
                Stock(
                    branch_id=marseille.id,
                    external_product_id=SKU,
                    quantity=other_quantity,
                )
            )
        db.session.commit()
        return {
            "branch_id": toulon.id,
            "other_branch_id": marseille.id,
            "user_id": alice.id,
        }


def _login(client, username="alice", password=USER_PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _product(identifier):
    return {
        "external_product_id": SKU,
        "name": "24 inch Compact Monitor",
        "discontinued": True,
        "received_identifier": identifier,
    }


def test_postgresql_routes_create_add_remove_zero_scope_and_timestamps(
    clean_postgres_app,
    monkeypatch,
):
    identifiers = _prepare_database(
        clean_postgres_app,
        other_quantity=99,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        _product,
    )
    client = clean_postgres_app.test_client()
    access = _login(client)["access_token"]
    headers = _bearer(access)

    created = client.post(
        "/api/v1/stocks/42/add",
        json={"quantity": 5},
        headers=headers,
    )
    added = client.post(
        f"/api/v1/stocks/{SKU}/add",
        json={"quantity": 3},
        headers=headers,
    )
    removed = client.post(
        f"/api/v1/stocks/{SKU}/remove",
        json={"quantity": 8},
        headers=headers,
    )
    detail = client.get(f"/api/v1/stocks/{SKU}", headers=headers)
    default_list = client.get("/api/v1/stocks", headers=headers)
    all_list = client.get(
        "/api/v1/stocks?available_only=false",
        headers=headers,
    )

    assert (
        created.status_code
        == added.status_code
        == removed.status_code
        == 200
    )
    assert created.get_json()["data"]["quantity"] == 5
    assert added.get_json()["data"]["quantity"] == 8
    assert removed.get_json()["data"]["quantity"] == 0
    assert detail.get_json()["data"]["quantity"] == 0
    assert default_list.get_json()["data"]["items"] == []
    assert all_list.get_json()["data"]["items"] == [
        {
            "external_product_id": SKU,
            "quantity": 0,
            "product": {"name": "24 inch Compact Monitor"},
        }
    ]

    with clean_postgres_app.app_context():
        stock = db.session.scalar(
            select(Stock).where(
                Stock.branch_id == identifiers["branch_id"]
            )
        )
        assert stock.branch_id == identifiers["branch_id"]
        assert stock.external_product_id == SKU
        assert stock.quantity == 0
        assert stock.updated_at >= stock.created_at
        assert db.session.scalar(
            select(Stock.quantity).where(
                Stock.branch_id == identifiers["other_branch_id"]
            )
        ) == 99
        assert (
            db.session.scalar(select(func.count()).select_from(Stock))
            == 2
        )


def test_postgresql_admin_denied_missing_insufficient_and_product_rollback(
    clean_postgres_app,
    monkeypatch,
):
    _prepare_database(clean_postgres_app, quantity=2)
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda identifier: (
            {
                **_product(identifier),
                "external_product_id": (
                    "OTHER" if identifier == "OTHER" else SKU
                ),
            }
        ),
    )
    client = clean_postgres_app.test_client()
    user_headers = _bearer(_login(client)["access_token"])
    admin_headers = _bearer(
        _login(client, "admin", ADMIN_PASSWORD)["access_token"]
    )

    admin = client.get("/api/v1/stocks", headers=admin_headers)
    missing = client.post(
        "/api/v1/stocks/OTHER/remove",
        json={"quantity": 1},
        headers=user_headers,
    )
    insufficient = client.post(
        f"/api/v1/stocks/{SKU}/remove",
        json={"quantity": 3},
        headers=user_headers,
    )

    assert admin.get_json()["error"]["code"] == "ADMIN_STOCK_FORBIDDEN"
    assert missing.get_json()["error"]["code"] == "STOCK_NOT_FOUND"
    assert (
        insufficient.get_json()["error"]["code"]
        == "INSUFFICIENT_STOCK"
    )
    with clean_postgres_app.app_context():
        assert db.session.scalar(select(Stock).where(Stock.quantity == 2))

    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda _identifier: (_ for _ in ()).throw(
            ProductTimeoutServiceError()
        ),
    )
    failed = client.post(
        f"/api/v1/stocks/{SKU}/add",
        json={"quantity": 99},
        headers=user_headers,
    )
    assert failed.get_json()["error"]["code"] == "PRODUCT_API_TIMEOUT"
    with clean_postgres_app.app_context():
        assert db.session.scalar(select(Stock.quantity)) == 2


def _run_pair(
    app,
    monkeypatch,
    user_id,
    operations,
):
    barrier = Barrier(2)

    def synchronized_product(identifier):
        barrier.wait(timeout=5)
        return _product(identifier)

    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        synchronized_product,
    )

    def worker(operation, quantity):
        with app.app_context():
            user = db.session.get(User, user_id)
            result = operation(
                user,
                SKU,
                StockMovementData(quantity=quantity),
            )
            value = result.stock.quantity
            db.session.remove()
            return value

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(worker, operation, quantity)
            for operation, quantity in operations
        ]
        return [future.result(timeout=10) for future in futures]


def test_postgresql_stock_constraints_reject_invalid_persistence(
    clean_postgres_app,
):
    identifiers = _prepare_database(clean_postgres_app, quantity=1)
    invalid_rows = [
        Stock(
            branch_id=identifiers["branch_id"],
            external_product_id=SKU,
            quantity=2,
        ),
        Stock(
            branch_id=identifiers["branch_id"],
            external_product_id=" ",
            quantity=1,
        ),
        Stock(
            branch_id=identifiers["branch_id"],
            external_product_id="OTHER",
            quantity=-1,
        ),
    ]

    with clean_postgres_app.app_context():
        for invalid in invalid_rows:
            db.session.add(invalid)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
        assert db.session.scalar(select(func.count()).select_from(Stock)) == 1


@pytest.mark.parametrize(
    ("initial", "operations", "expected"),
    [
        (None, [(add_stock, 2), (add_stock, 3)], 5),
        (10, [(add_stock, 2), (add_stock, 3)], 15),
        (10, [(remove_stock, 4), (remove_stock, 3)], 3),
        (10, [(add_stock, 5), (remove_stock, 4)], 11),
    ],
    ids=["two-first-adds", "two-adds", "two-removes", "add-remove"],
)
def test_postgresql_concurrent_movements_do_not_lose_updates(
    clean_postgres_app,
    monkeypatch,
    initial,
    operations,
    expected,
):
    identifiers = _prepare_database(
        clean_postgres_app,
        quantity=initial,
    )

    _run_pair(
        clean_postgres_app,
        monkeypatch,
        identifiers["user_id"],
        operations,
    )

    with clean_postgres_app.app_context():
        stocks = list(db.session.scalars(select(Stock)).all())
        assert len(stocks) == 1
        assert stocks[0].quantity == expected
