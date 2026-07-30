"""Unit and CLI tests for the additive large demonstration seed."""

from __future__ import annotations

from dataclasses import fields

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from backoffice.database import large_seed as large_seed_module
from backoffice.database.large_seed import (
    LargeSeedConfigurationError,
    LargeSeedConflictError,
    LargeSeedProductError,
    LargeSeedResult,
    build_large_seed_plan,
    fetch_all_product_ids,
    seed_large_database,
)
from backoffice.database.models import Stock
from backoffice.database.models import Branch, User
from backoffice.extensions import db
from backoffice.products.client import (
    ProductConnectionError,
    ProductData,
    ProductPage,
)

DEMO_PASSWORD = "large-demo-user-password"


@pytest.fixture()
def large_seed_sqlite_app(app):
    """Provide local transaction coverage with explicit SQLite IDs."""
    counters = {Branch: 0, User: 0, Stock: 0}

    def assign_bigint_ids(session, _flush_context, _instances):
        for model in counters:
            for instance in (
                item
                for item in session.new
                if isinstance(item, model) and item.id is None
            ):
                counters[model] += 1
                instance.id = counters[model]

    event.listen(Session, "before_flush", assign_bigint_ids)
    with app.app_context():
        connection = db.engine.raw_connection()
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)
        connection.close()
        db.create_all()
        db.session.execute(text("DROP INDEX uq_users_single_admin"))
        db.session.commit()
        try:
            yield app
        finally:
            db.session.rollback()
            db.session.remove()
            db.drop_all()
            event.remove(Session, "before_flush", assign_bigint_ids)


def _product(number: int, *, sku: str | None = None) -> ProductData:
    return ProductData(
        id=number,
        sku=sku or f"HB-DEMO-{number:04d}",
        name=f"Product {number}",
        description=f"Description {number}",
        category="Demo",
        brand="HB",
        supplier_id="supplier-1",
        supplier_name="Supplier",
        unit_price=10.0,
        currency="EUR",
        discontinued=False,
        weight_kg=1.0,
        tags=("demo",),
        updated_at="2026-01-01T00:00:00Z",
    )


class FakePagedProductClient:
    def __init__(
        self,
        count: int,
        *,
        fail_offset: int | None = None,
        duplicate_sku_at: int | None = None,
    ) -> None:
        self.products = [_product(index + 1) for index in range(count)]
        if duplicate_sku_at is not None:
            self.products[duplicate_sku_at] = _product(
                duplicate_sku_at + 1,
                sku=self.products[0].sku.lower(),
            )
        self.fail_offset = fail_offset
        self.calls: list[tuple[int, int]] = []

    def list_products(self, params):
        limit = int(params["limit"])
        offset = int(params["offset"])
        self.calls.append((limit, offset))
        if offset == self.fail_offset:
            raise ProductConnectionError("Product API is unreachable.")
        return ProductPage(
            total=len(self.products),
            limit=limit,
            offset=offset,
            products=tuple(self.products[offset : offset + limit]),
        )


def test_plan_defaults_create_expected_deterministic_volumes():
    client = FakePagedProductClient(40)

    first = build_large_seed_plan(
        branches=15,
        users_per_branch=3,
        seed=42,
        product_client=client,
    )
    second = build_large_seed_plan(
        branches=15,
        users_per_branch=3,
        seed=42,
        product_client=FakePagedProductClient(40),
    )

    assert first == second
    assert len(first.branches) == 15
    assert len(first.users) == 45
    assert sum(user.deleted for user in first.users) == 4
    assert len(first.product_ids) == 40
    assert len(first.stocks) == 600
    assert all(stock.quantity >= 0 for stock in first.stocks)
    assert any(stock.quantity == 0 for stock in first.stocks)
    assert all(
        any(
            not user.deleted and user.branch_name == branch.name
            for user in first.users
        )
        for branch in first.branches
    )


def test_custom_options_and_seed_change_only_planned_demo_data():
    seed_42 = build_large_seed_plan(
        branches=2,
        users_per_branch=2,
        seed=42,
        product_client=FakePagedProductClient(3),
    )
    seed_7 = build_large_seed_plan(
        branches=2,
        users_per_branch=2,
        seed=7,
        product_client=FakePagedProductClient(3),
    )

    assert len(seed_42.branches) == 2
    assert len(seed_42.users) == 4
    assert len(seed_42.stocks) == 6
    assert seed_42.product_ids == seed_7.product_ids
    assert seed_42.stocks != seed_7.stocks


@pytest.mark.parametrize(
    ("branches", "users_per_branch", "seed", "message"),
    [
        (0, 3, 42, "branches"),
        (16, 3, 42, "branches"),
        (True, 3, 42, "branches"),
        (1, 0, 42, "users-per-branch"),
        (1, True, 42, "users-per-branch"),
        (1, 1, True, "seed"),
    ],
)
def test_plan_rejects_invalid_bounds(
    branches,
    users_per_branch,
    seed,
    message,
):
    with pytest.raises(LargeSeedConfigurationError, match=message):
        build_large_seed_plan(
            branches=branches,
            users_per_branch=users_per_branch,
            seed=seed,
            product_client=FakePagedProductClient(1),
        )


def test_catalogue_fetches_every_page_in_order():
    client = FakePagedProductClient(205)

    product_ids = fetch_all_product_ids(client)

    assert len(product_ids) == 205
    assert product_ids[0] == "HB-DEMO-0001"
    assert product_ids[-1] == "HB-DEMO-0205"
    assert client.calls == [(100, 0), (100, 100), (100, 200)]


def test_catalogue_propagates_an_intermediate_api_failure():
    client = FakePagedProductClient(205, fail_offset=100)

    with pytest.raises(ProductConnectionError):
        fetch_all_product_ids(client)

    assert client.calls == [(100, 0), (100, 100)]


def test_catalogue_rejects_duplicate_skus_case_insensitively():
    client = FakePagedProductClient(101, duplicate_sku_at=100)

    with pytest.raises(LargeSeedProductError, match="duplicate"):
        fetch_all_product_ids(client)


@pytest.mark.parametrize(
    "environment",
    [None, "", "production", "prod", "staging", "unknown"],
)
def test_seed_large_refuses_every_non_local_environment(environment):
    client = FakePagedProductClient(1)

    with pytest.raises(LargeSeedConfigurationError, match="environment"):
        seed_large_database(
            app_environment=environment,
            user_password=DEMO_PASSWORD,
            branches=1,
            users_per_branch=1,
            seed=42,
            product_client=client,
            dry_run=True,
        )

    assert client.calls == []


@pytest.mark.parametrize(
    "password",
    [None, "", "replace-with-demo-password", "<demo-placeholder>", "é" * 37],
)
def test_seed_large_rejects_missing_placeholder_or_long_password(password):
    client = FakePagedProductClient(1)

    with pytest.raises(
        LargeSeedConfigurationError,
        match="LARGE_SEED_USER_PASSWORD",
    ):
        seed_large_database(
            app_environment="development",
            user_password=password,
            branches=1,
            users_per_branch=1,
            seed=42,
            product_client=client,
            dry_run=True,
        )

    assert client.calls == []


def test_stock_plan_can_persist_only_the_existing_stock_columns():
    plan = build_large_seed_plan(
        branches=1,
        users_per_branch=1,
        seed=42,
        product_client=FakePagedProductClient(2),
    )
    stock_columns = set(Stock.__table__.columns.keys())

    assert {field.name for field in fields(plan.stocks[0])} == {
        "branch_name",
        "external_product_id",
        "quantity",
    }
    assert stock_columns == {
        "id",
        "branch_id",
        "external_product_id",
        "quantity",
        "created_at",
        "updated_at",
    }


def test_sqlite_dry_run_create_idempotence_and_conflict_are_atomic(
    large_seed_sqlite_app,
):
    with large_seed_sqlite_app.app_context():
        common = {
            "app_environment": "test",
            "user_password": DEMO_PASSWORD,
            "branches": 2,
            "users_per_branch": 2,
            "seed": 42,
        }
        dry_run = seed_large_database(
            **common,
            product_client=FakePagedProductClient(3),
            dry_run=True,
        )
        assert dry_run.branches_created == 2
        assert dry_run.users_created == 4
        assert dry_run.stocks_created == 6
        assert db.session.scalar(
            select(func.count()).select_from(Branch)
        ) == 0
        db.session.rollback()

        created = seed_large_database(
            **common,
            product_client=FakePagedProductClient(3),
        )
        repeated = seed_large_database(
            **common,
            product_client=FakePagedProductClient(3),
        )
        assert created.branches_created == 2
        assert created.users_created == 4
        assert created.stocks_created == 6
        assert repeated.already_complete is True

        stock = db.session.scalar(select(Stock))
        stock.quantity += 1
        changed_quantity = stock.quantity
        db.session.commit()
        with pytest.raises(LargeSeedConflictError):
            seed_large_database(
                **common,
                product_client=FakePagedProductClient(3),
            )
        db.session.refresh(stock)
        assert stock.quantity == changed_quantity


def test_cli_registers_defaults_and_custom_options_without_network(
    app,
    monkeypatch,
):
    captured: list[dict] = []

    def fake_seed_large_database(**kwargs):
        captured.append(kwargs)
        return LargeSeedResult(
            branches_total=kwargs["branches"],
            branches_created=kwargs["branches"],
            users_total=(
                kwargs["branches"] * kwargs["users_per_branch"]
            ),
            users_created=(
                kwargs["branches"] * kwargs["users_per_branch"]
            ),
            users_soft_deleted=0,
            products_fetched=2,
            stocks_total=kwargs["branches"] * 2,
            stocks_created=kwargs["branches"] * 2,
            seed=kwargs["seed"],
            dry_run=kwargs["dry_run"],
        )

    monkeypatch.setattr(
        large_seed_module,
        "seed_large_database",
        fake_seed_large_database,
    )
    app.config.update(
        APP_ENV="development",
        LARGE_SEED_USER_PASSWORD=DEMO_PASSWORD,
        PRODUCT_API_BASE_URL="http://product-api.test",
        PRODUCT_API_TIMEOUT="1",
    )
    runner = app.test_cli_runner()

    default = runner.invoke(args=["seed-large"])
    custom = runner.invoke(
        args=[
            "seed-large",
            "--branches",
            "2",
            "--users-per-branch",
            "4",
            "--seed",
            "7",
            "--dry-run",
        ]
    )

    assert default.exit_code == custom.exit_code == 0
    assert captured[0]["branches"] == 15
    assert captured[0]["users_per_branch"] == 3
    assert captured[0]["seed"] == 42
    assert captured[0]["dry_run"] is False
    assert captured[1]["branches"] == 2
    assert captured[1]["users_per_branch"] == 4
    assert captured[1]["seed"] == 7
    assert captured[1]["dry_run"] is True


def test_cli_error_output_never_contains_password_hash_or_private_url(
    app,
    monkeypatch,
):
    password = "private-large-seed-password"
    private_url = "postgresql://private:credentials@database/private"
    sentinel_hash = "$2b$04$privatehash"

    def fail_safely(**_kwargs):
        raise LargeSeedConflictError(
            "Existing reserved stock is incompatible."
        )

    monkeypatch.setattr(
        large_seed_module,
        "seed_large_database",
        fail_safely,
    )
    app.config.update(
        APP_ENV="development",
        LARGE_SEED_USER_PASSWORD=password,
        SQLALCHEMY_DATABASE_URI=private_url,
        PRODUCT_API_BASE_URL="http://product-api.test",
        PRODUCT_API_TIMEOUT="1",
    )

    result = app.test_cli_runner().invoke(args=["seed-large"])

    assert result.exit_code != 0
    assert "incompatible" in result.output
    assert password not in result.output
    assert private_url not in result.output
    assert sentinel_hash not in result.output


def test_cli_exposes_no_reset_or_movement_option(app):
    runner = app.test_cli_runner()

    movement = runner.invoke(args=["seed-large", "--movements", "1"])
    reset = runner.invoke(args=["seed-large", "--reset-large"])

    assert movement.exit_code == reset.exit_code == 2
    assert "No such option" in movement.output
    assert "No such option" in reset.output
