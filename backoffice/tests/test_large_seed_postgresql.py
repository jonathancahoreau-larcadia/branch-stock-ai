"""PostgreSQL integration tests for the additive large demo seed."""

from __future__ import annotations

import bcrypt
import pytest
from sqlalchemy import func, select

from backoffice.database import large_seed as large_seed_module
from backoffice.database.large_seed import (
    LARGE_SEED_BRANCH_PREFIX,
    LargeSeedConflictError,
    seed_large_database,
)
from backoffice.database.models import (
    ADMIN_ROLE,
    Branch,
    Stock,
    User,
)
from backoffice.extensions import db

from .test_large_seed import DEMO_PASSWORD, FakePagedProductClient

ADMIN_PASSWORD = "existing-admin-password"


def _hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),
    ).decode("utf-8")


def _seed_small_manual_data() -> tuple[int, int, int]:
    toulon = Branch(name="Toulon")
    db.session.add(toulon)
    db.session.flush()
    admin = User(
        username="admin",
        password_hash=_hash(ADMIN_PASSWORD),
        role=ADMIN_ROLE,
        branch_id=None,
        is_active=True,
        token_version=0,
    )
    manual = User(
        username="manual-user",
        password_hash=_hash("manual-password"),
        role="common_user",
        branch_id=toulon.id,
        is_active=True,
        token_version=0,
    )
    stock = Stock(
        branch_id=toulon.id,
        external_product_id="HB-MANUAL-0001",
        quantity=9,
    )
    db.session.add_all([admin, manual, stock])
    db.session.commit()
    return admin.id, manual.id, stock.id


def _run_large_seed(
    *,
    branches=15,
    users_per_branch=3,
    seed=42,
    products=40,
    dry_run=False,
):
    return seed_large_database(
        app_environment="test",
        user_password=DEMO_PASSWORD,
        branches=branches,
        users_per_branch=users_per_branch,
        seed=seed,
        product_client=FakePagedProductClient(products),
        dry_run=dry_run,
    )


def test_postgresql_default_volume_preserves_admin_manual_and_small_seed(
    clean_postgres_app,
):
    with clean_postgres_app.app_context():
        admin_id, manual_id, manual_stock_id = _seed_small_manual_data()

        result = _run_large_seed()

        assert result.branches_created == 15
        assert result.users_created == 45
        assert result.users_soft_deleted == 4
        assert result.products_fetched == 40
        assert result.stocks_created == 600
        assert db.session.get(User, admin_id).username == "admin"
        assert db.session.get(User, manual_id).username == "manual-user"
        assert db.session.get(Stock, manual_stock_id).quantity == 9
        assert db.session.scalar(
            select(func.count())
            .select_from(Branch)
            .where(Branch.name.like(f"{LARGE_SEED_BRANCH_PREFIX}%"))
        ) == 15
        assert db.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.username.like("demo-%"))
        ) == 45
        assert db.session.scalar(
            select(func.count())
            .select_from(Stock)
            .join(Branch)
            .where(Branch.name.like(f"{LARGE_SEED_BRANCH_PREFIX}%"))
        ) == 600
        quantities = list(
            db.session.scalars(
                select(Stock.quantity)
                .join(Branch)
                .where(
                    Branch.name.like(f"{LARGE_SEED_BRANCH_PREFIX}%")
                )
            )
        )
        assert min(quantities) == 0
        assert all(quantity >= 0 for quantity in quantities)


def test_postgresql_dry_run_validates_but_writes_nothing(
    clean_postgres_app,
):
    with clean_postgres_app.app_context():
        result = _run_large_seed(
            branches=2,
            users_per_branch=2,
            products=3,
            dry_run=True,
        )

        assert result.dry_run is True
        assert result.branches_created == 2
        assert result.users_created == 4
        assert result.stocks_created == 6
        assert db.session.scalar(
            select(func.count()).select_from(Branch)
        ) == 0
        assert db.session.scalar(
            select(func.count()).select_from(User)
        ) == 0
        assert db.session.scalar(
            select(func.count()).select_from(Stock)
        ) == 0


def test_postgresql_is_idempotent_and_completes_only_missing_rows(
    clean_postgres_app,
):
    with clean_postgres_app.app_context():
        first = _run_large_seed(
            branches=2,
            users_per_branch=2,
            products=3,
        )
        second = _run_large_seed(
            branches=2,
            users_per_branch=2,
            products=3,
        )

        assert first.stocks_created == 6
        assert second.already_complete is True
        assert second.branches_created == 0
        assert second.users_created == 0
        assert second.stocks_created == 0

        missing_user = db.session.scalar(
            select(User).where(User.username == "demo-marseille-02")
        )
        missing_stock = db.session.scalar(
            select(Stock)
            .join(Branch)
            .where(
                Branch.name
                == f"{LARGE_SEED_BRANCH_PREFIX}Toulon Centre",
                Stock.external_product_id == "HB-DEMO-0003",
            )
        )
        db.session.delete(missing_user)
        db.session.delete(missing_stock)
        db.session.commit()

        completed = _run_large_seed(
            branches=2,
            users_per_branch=2,
            products=3,
        )

        assert completed.branches_created == 0
        assert completed.users_created == 1
        assert completed.stocks_created == 1
        assert db.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.username.like("demo-%"))
        ) == 4
        assert db.session.scalar(
            select(func.count())
            .select_from(Stock)
            .join(Branch)
            .where(Branch.name.like(f"{LARGE_SEED_BRANCH_PREFIX}%"))
        ) == 6


def test_postgresql_incompatible_parameters_rollback_without_partial_rows(
    clean_postgres_app,
):
    with clean_postgres_app.app_context():
        _run_large_seed(
            branches=2,
            users_per_branch=2,
            products=5,
        )
        counts_before = (
            db.session.scalar(select(func.count()).select_from(Branch)),
            db.session.scalar(select(func.count()).select_from(User)),
            db.session.scalar(select(func.count()).select_from(Stock)),
        )
        db.session.rollback()

        with pytest.raises(LargeSeedConflictError):
            _run_large_seed(
                branches=1,
                users_per_branch=2,
                products=5,
            )

        counts_after = (
            db.session.scalar(select(func.count()).select_from(Branch)),
            db.session.scalar(select(func.count()).select_from(User)),
            db.session.scalar(select(func.count()).select_from(Stock)),
        )
        assert counts_after == counts_before


def test_postgresql_stock_conflict_never_overwrites_manual_change(
    clean_postgres_app,
):
    with clean_postgres_app.app_context():
        _run_large_seed(
            branches=1,
            users_per_branch=2,
            products=3,
        )
        stock = db.session.scalar(
            select(Stock)
            .join(Branch)
            .where(
                Branch.name
                == f"{LARGE_SEED_BRANCH_PREFIX}Marseille Centre"
            )
        )
        stock.quantity += 1
        changed_quantity = stock.quantity
        db.session.commit()

        with pytest.raises(LargeSeedConflictError):
            _run_large_seed(
                branches=1,
                users_per_branch=2,
                products=3,
            )

        db.session.refresh(stock)
        assert stock.quantity == changed_quantity


def test_postgresql_hash_failure_rolls_back_every_created_row(
    clean_postgres_app,
    monkeypatch,
):
    calls = 0

    def failing_hash(password):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated hash failure")
        return _hash(password)

    monkeypatch.setattr(
        large_seed_module,
        "hash_password",
        failing_hash,
    )
    with clean_postgres_app.app_context():
        with pytest.raises(RuntimeError, match="simulated"):
            _run_large_seed(
                branches=2,
                users_per_branch=2,
                products=3,
            )

        assert db.session.scalar(
            select(func.count()).select_from(Branch)
        ) == 0
        assert db.session.scalar(
            select(func.count()).select_from(User)
        ) == 0
        assert db.session.scalar(
            select(func.count()).select_from(Stock)
        ) == 0


def test_postgresql_product_failure_happens_before_every_write(
    clean_postgres_app,
):
    with clean_postgres_app.app_context():
        with pytest.raises(ProductConnectionError):
            seed_large_database(
                app_environment="test",
                user_password=DEMO_PASSWORD,
                branches=2,
                users_per_branch=2,
                seed=42,
                product_client=FakePagedProductClient(
                    101,
                    fail_offset=100,
                ),
            )

        assert db.session.scalar(
            select(func.count()).select_from(Branch)
        ) == 0
        assert db.session.scalar(
            select(func.count()).select_from(User)
        ) == 0
        assert db.session.scalar(
            select(func.count()).select_from(Stock)
        ) == 0
