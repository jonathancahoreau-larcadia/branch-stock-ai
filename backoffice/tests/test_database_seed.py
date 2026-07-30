"""PostgreSQL integration tests for the idempotent initial seed."""

from dataclasses import dataclass

import bcrypt
import pytest
from sqlalchemy import func, select, text

from backoffice.database import seed as seed_module
from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    RevokedToken,
    Stock,
    User,
)
from backoffice.database.seed import (
    SeedConfigurationError,
    SeedDataConflictError,
    SeedError,
    seed_database,
)
from backoffice.extensions import db
from backoffice.products.client import ProductValidation

ADMIN_PASSWORD = "integration-admin-password"
PRODUCT_ID = "HB-MON-2102"


@dataclass
class FakeProductClient:
    """Deterministic Product API replacement for seed integration tests."""

    product_id: str = PRODUCT_ID
    discontinued: bool = False
    calls: int = 0

    def get_product(self, identifier: str) -> ProductValidation:
        self.calls += 1
        return ProductValidation(
            id=2102,
            sku=self.product_id,
            discontinued=self.discontinued,
        )


def _run_seed(
    *,
    password=ADMIN_PASSWORD,
    product_id=PRODUCT_ID,
    rounds=4,
    product_client=None,
):
    return seed_database(
        admin_password=password,
        product_identifier=product_id,
        bcrypt_rounds=rounds,
        product_client=product_client or FakeProductClient(),
    )


def test_seed_creates_exact_mandatory_data(clean_postgres_app):
    """A fresh PostgreSQL schema receives only the required initial rows."""
    result = _run_seed()

    admin = db.session.scalar(select(User).where(User.username == "admin"))
    branches = db.session.scalars(select(Branch).order_by(Branch.name)).all()
    stocks = db.session.scalars(
        select(Stock).join(Branch).order_by(Branch.name)
    ).all()

    assert result.branches_created == 2
    assert result.admin_created is True
    assert result.stocks_created == 2
    assert admin is not None
    assert admin.role == ADMIN_ROLE
    assert admin.branch_id is None
    assert admin.is_active is True
    assert admin.token_version == 0
    assert admin.deleted_at is None
    assert admin.password_hash != ADMIN_PASSWORD
    assert bcrypt.checkpw(
        ADMIN_PASSWORD.encode("utf-8"),
        admin.password_hash.encode("utf-8"),
    )
    assert [branch.name for branch in branches] == ["Marseille", "Toulon"]
    assert {
        (stock.branch.name, stock.external_product_id, stock.quantity)
        for stock in stocks
    } == {
        ("Toulon", PRODUCT_ID, 10),
        ("Marseille", PRODUCT_ID, 5),
    }
    assert db.session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == COMMON_USER_ROLE)
    ) == 0
    assert db.session.scalar(
        select(func.count()).select_from(RevokedToken)
    ) == 0


def test_second_seed_is_strictly_without_effect(clean_postgres_app):
    """A repeat keeps identifiers, hashes, quantities, and timestamps intact."""
    _run_seed()
    first_admin = db.session.scalar(select(User).where(User.username == "admin"))
    first_branches = db.session.scalars(select(Branch).order_by(Branch.id)).all()
    first_stocks = db.session.scalars(select(Stock).order_by(Stock.id)).all()
    snapshot = {
        "admin": (
            first_admin.id,
            first_admin.password_hash,
            first_admin.created_at,
            first_admin.updated_at,
        ),
        "branches": [
            (branch.id, branch.created_at, branch.updated_at)
            for branch in first_branches
        ],
        "stocks": [
            (
                stock.id,
                stock.quantity,
                stock.created_at,
                stock.updated_at,
            )
            for stock in first_stocks
        ],
    }
    db.session.remove()

    result = _run_seed()
    second_admin = db.session.scalar(select(User).where(User.username == "admin"))
    second_branches = db.session.scalars(select(Branch).order_by(Branch.id)).all()
    second_stocks = db.session.scalars(select(Stock).order_by(Stock.id)).all()

    assert result.branches_created == 0
    assert result.admin_created is False
    assert result.stocks_created == 0
    assert (
        second_admin.id,
        second_admin.password_hash,
        second_admin.created_at,
        second_admin.updated_at,
    ) == snapshot["admin"]
    assert [
        (branch.id, branch.created_at, branch.updated_at)
        for branch in second_branches
    ] == snapshot["branches"]
    assert [
        (
            stock.id,
            stock.quantity,
            stock.created_at,
            stock.updated_at,
        )
        for stock in second_stocks
    ] == snapshot["stocks"]


def test_seed_is_idempotent_when_existing_admin_token_version_is_positive(
    clean_postgres_app,
):
    _run_seed()
    admin = db.session.scalar(select(User).where(User.username == "admin"))
    rotated_password = "rotated-admin-password"
    admin.password_hash = bcrypt.hashpw(
        rotated_password.encode("utf-8"), bcrypt.gensalt(rounds=4)
    ).decode("utf-8")
    admin.token_version = 7
    db.session.commit()

    result = _run_seed(password=rotated_password)

    db.session.refresh(admin)
    assert result.admin_created is False
    assert admin.token_version == 7
    assert bcrypt.checkpw(rotated_password.encode("utf-8"), admin.password_hash.encode("utf-8"))


@pytest.mark.parametrize(
    ("password", "product_id", "rounds"),
    [
        (None, PRODUCT_ID, 4),
        ("", PRODUCT_ID, 4),
        ("   ", PRODUCT_ID, 4),
        (ADMIN_PASSWORD, "", 4),
        (ADMIN_PASSWORD, "x" * 256, 4),
        (ADMIN_PASSWORD, PRODUCT_ID, "invalid"),
        (ADMIN_PASSWORD, PRODUCT_ID, 3),
    ],
)
def test_invalid_seed_configuration_writes_nothing(
    clean_postgres_app,
    password,
    product_id,
    rounds,
):
    """Configuration errors are detected before PostgreSQL is modified."""
    client = FakeProductClient()

    with pytest.raises(SeedConfigurationError):
        _run_seed(
            password=password,
            product_id=product_id,
            rounds=rounds,
            product_client=client,
        )

    assert db.session.scalar(select(func.count()).select_from(Branch)) == 0
    assert db.session.scalar(select(func.count()).select_from(User)) == 0
    assert db.session.scalar(select(func.count()).select_from(Stock)) == 0


def test_seed_rejects_discontinued_or_mismatched_product(clean_postgres_app):
    """The Product API must confirm the exact active external identifier."""
    with pytest.raises(SeedError, match="discontinued"):
        _run_seed(product_client=FakeProductClient(discontinued=True))

    with pytest.raises(SeedError, match="does not match"):
        _run_seed(product_client=FakeProductClient(product_id="OTHER-SKU"))

    assert db.session.scalar(select(func.count()).select_from(Branch)) == 0


def test_seed_rejects_incompatible_admin_without_repair(clean_postgres_app):
    """An existing disabled admin is reported and never reactivated."""
    _run_seed()
    admin = db.session.scalar(select(User).where(User.username == "admin"))
    admin.is_active = False
    db.session.commit()

    with pytest.raises(SeedDataConflictError, match="admin account"):
        _run_seed()

    db.session.refresh(admin)
    assert admin.is_active is False


def test_seed_rejects_incompatible_password_without_rehashing(
    clean_postgres_app,
):
    """An existing admin hash is immutable across seed invocations."""
    _run_seed()
    admin = db.session.scalar(select(User).where(User.username == "admin"))
    original_hash = admin.password_hash
    db.session.remove()

    with pytest.raises(SeedDataConflictError, match="initial password"):
        _run_seed(password="different-password")

    admin = db.session.scalar(select(User).where(User.username == "admin"))
    assert admin.password_hash == original_hash


def test_seed_rejects_incompatible_branch_name(clean_postgres_app):
    """A normalized name collision is not silently renamed or duplicated."""
    db.session.add(Branch(name=" toulon "))
    db.session.commit()

    with pytest.raises(SeedDataConflictError, match="required branch Toulon"):
        _run_seed()

    assert db.session.scalars(select(Branch)).one().name == " toulon "
    assert db.session.scalar(select(func.count()).select_from(User)) == 0


def test_stock_conflict_rolls_back_every_new_seed_row(clean_postgres_app):
    """A late conflict rolls back the admin and other branch creation."""
    toulon = Branch(name="Toulon")
    db.session.add(toulon)
    db.session.flush()
    db.session.add(
        Stock(
            branch_id=toulon.id,
            external_product_id=PRODUCT_ID,
            quantity=99,
        )
    )
    db.session.commit()

    with pytest.raises(SeedDataConflictError, match="branch Toulon"):
        _run_seed()

    assert db.session.scalar(select(func.count()).select_from(User)) == 0
    assert db.session.scalar(select(func.count()).select_from(Branch)) == 1
    assert db.session.scalar(select(Stock.quantity)) == 99


def test_seed_preserves_unrelated_existing_data(clean_postgres_app):
    """Rows outside the immutable seed set are never removed or changed."""
    extra_branch = Branch(name="Nice")
    db.session.add(extra_branch)
    db.session.flush()
    extra_branch_id = extra_branch.id
    db.session.commit()
    db.session.remove()

    _run_seed()

    assert db.session.get(Branch, extra_branch_id).name == "Nice"


def test_seed_cli_leaks_no_secret_and_runs_no_migration(
    clean_postgres_app,
    monkeypatch,
):
    """The command reports safe counts and leaves Alembic untouched."""
    class FakeClientFactory(FakeProductClient):
        def __init__(self, base_url, timeout):
            super().__init__()

    monkeypatch.setattr(seed_module, "ProductClient", FakeClientFactory)
    runner = clean_postgres_app.test_cli_runner()

    with clean_postgres_app.app_context():
        before_version_table = db.session.scalar(
            text("SELECT to_regclass('alembic_version')")
        )
        db.session.rollback()

    result = runner.invoke(args=["seed"])

    assert result.exit_code == 0
    assert "Seed completed" in result.output
    assert ADMIN_PASSWORD not in result.output
    with clean_postgres_app.app_context():
        admin_hash = db.session.scalar(select(User.password_hash))
        after_version_table = db.session.scalar(
            text("SELECT to_regclass('alembic_version')")
        )
    assert admin_hash not in result.output
    assert before_version_table is None
    assert after_version_table is None
