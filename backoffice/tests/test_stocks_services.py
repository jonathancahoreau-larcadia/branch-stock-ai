"""Unit tests for stock authorization, enrichment, and transactions."""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from backoffice.database.models import ADMIN_ROLE, COMMON_USER_ROLE
from backoffice.stocks.schemas import StockListFilters, StockMovementData
from backoffice.stocks.services import (
    AdminStockForbiddenError,
    BranchNotFoundError,
    InsufficientStockError,
    StockConflictError,
    StockNotFoundError,
    StockRoleForbiddenError,
    add_stock,
    get_stock,
    list_stocks,
    remove_stock,
    serialize_stock_detail,
)

PRODUCT = {
    "external_product_id": "HB-MON-2102",
    "name": "24 inch Compact Monitor",
    "discontinued": True,
}


def _user(role=COMMON_USER_ROLE, branch_id=2):
    return SimpleNamespace(role=role, branch_id=branch_id)


def _branch():
    return SimpleNamespace(id=2, name="Toulon")


def _stock(quantity=8):
    return SimpleNamespace(
        id=4,
        branch_id=2,
        external_product_id="HB-MON-2102",
        quantity=quantity,
    )


@pytest.mark.parametrize(
    ("user", "error"),
    [
        (_user(ADMIN_ROLE, None), AdminStockForbiddenError),
        (_user("unexpected", 2), StockRoleForbiddenError),
        (_user(COMMON_USER_ROLE, None), BranchNotFoundError),
    ],
)
def test_every_operation_enforces_current_database_role(
    monkeypatch,
    user,
    error,
):
    product_calls = []
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda value: product_calls.append(value),
    )

    with pytest.raises(error):
        list_stocks(user, StockListFilters(available_only=True))
    assert product_calls == []


def test_list_is_scoped_ordered_by_repository_and_skips_empty_enrichment(
    monkeypatch,
):
    branch = _branch()
    received = []
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_branch",
        lambda branch_id: branch,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.list_stocks",
        lambda branch_id, available_only: received.append(
            (branch_id, available_only)
        )
        or [],
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda _value: pytest.fail("empty lists must not call Products API"),
    )

    result = list_stocks(
        _user(),
        StockListFilters(available_only=False),
    )

    assert received == [(2, False)]
    assert result.items == []


def test_detail_canonicalizes_numeric_id_and_whitelists_response(monkeypatch):
    branch = _branch()
    stock = _stock(0)
    received = []
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_branch",
        lambda _branch_id: branch,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda identifier: received.append(("product", identifier))
        or PRODUCT,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_stock",
        lambda branch_id, sku: received.append(("stock", branch_id, sku))
        or stock,
    )

    result = get_stock(_user(), "42")

    assert received == [
        ("product", "42"),
        ("stock", 2, "HB-MON-2102"),
    ]
    assert serialize_stock_detail(result) == {
        "branch": {"id": 2, "name": "Toulon"},
        "external_product_id": "HB-MON-2102",
        "quantity": 0,
        "product": {"name": "24 inch Compact Monitor"},
    }


def test_detail_absence_is_stock_not_found(monkeypatch):
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_branch",
        lambda _branch_id: _branch(),
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda _identifier: PRODUCT,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_stock",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(StockNotFoundError):
        get_stock(_user(), "HB-MON-2102")


def test_add_calls_product_before_write_and_commits_once(
    app,
    monkeypatch,
):
    calls = []
    stock = _stock(11)
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_branch",
        lambda _branch_id: _branch(),
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda identifier: calls.append(("product", identifier)) or PRODUCT,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.add_stock",
        lambda branch_id, sku, quantity: calls.append(
            ("write", branch_id, sku, quantity)
        )
        or stock,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.db.session.commit",
        lambda: calls.append(("commit",)),
    )

    with app.app_context():
        result = add_stock(_user(), "42", StockMovementData(quantity=3))

    assert result.stock is stock
    assert calls == [
        ("product", "42"),
        ("write", 2, "HB-MON-2102", 3),
        ("commit",),
    ]


def test_remove_locks_row_keeps_zero_and_commits(app, monkeypatch):
    stock = _stock(3)
    received = []
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_branch",
        lambda _branch_id: _branch(),
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda _identifier: PRODUCT,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_stock",
        lambda branch_id, sku, for_update: received.append(
            (branch_id, sku, for_update)
        )
        or stock,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.db.session.commit",
        lambda: received.append("commit"),
    )

    with app.app_context():
        result = remove_stock(
            _user(),
            "HB-MON-2102",
            StockMovementData(quantity=3),
        )

    assert result.stock.quantity == 0
    assert received == [(2, "HB-MON-2102", True), "commit"]


@pytest.mark.parametrize(
    ("stock", "error"),
    [
        (None, StockNotFoundError),
        (_stock(2), InsufficientStockError),
    ],
)
def test_remove_rolls_back_business_failures(
    app,
    monkeypatch,
    stock,
    error,
):
    rollbacks = []
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_branch",
        lambda _branch_id: _branch(),
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda _identifier: PRODUCT,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_stock",
        lambda *_args, **_kwargs: stock,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.db.session.rollback",
        lambda: rollbacks.append(True),
    )

    with app.app_context(), pytest.raises(error):
        remove_stock(
            _user(),
            "HB-MON-2102",
            StockMovementData(quantity=3),
        )
    assert rollbacks == [True]


def test_known_postgresql_conflict_rolls_back_and_maps_to_409(
    app,
    monkeypatch,
):
    class DriverError(Exception):
        sqlstate = "40P01"

    error = OperationalError("statement", {}, DriverError())
    rollbacks = []
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.get_branch",
        lambda _branch_id: _branch(),
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.get_product",
        lambda _identifier: PRODUCT,
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.repositories.add_stock",
        lambda *_args: (_ for _ in ()).throw(error),
    )
    monkeypatch.setattr(
        "backoffice.stocks.services.db.session.rollback",
        lambda: rollbacks.append(True),
    )

    with app.app_context(), pytest.raises(StockConflictError):
        add_stock(_user(), "42", StockMovementData(quantity=1))
    assert rollbacks == [True]
