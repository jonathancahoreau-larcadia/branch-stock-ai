"""PostgreSQL queries used by branch-scoped stock services."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from backoffice.database.models import Branch, Stock
from backoffice.extensions import db


def get_branch(branch_id: int) -> Branch | None:
    """Load the current user's branch."""
    return db.session.get(Branch, branch_id)


def list_stocks(
    branch_id: int,
    *,
    available_only: bool,
) -> list[Stock]:
    """List a branch's stock rows in deterministic contract order."""
    statement = select(Stock).where(Stock.branch_id == branch_id)
    if available_only:
        statement = statement.where(Stock.quantity > 0)
    statement = statement.order_by(
        Stock.external_product_id.asc(),
        Stock.id.asc(),
    )
    return list(db.session.scalars(statement).all())


def get_stock(
    branch_id: int,
    external_product_id: str,
    *,
    for_update: bool = False,
) -> Stock | None:
    """Load one branch/product stock row, optionally locking it."""
    statement = select(Stock).where(
        Stock.branch_id == branch_id,
        Stock.external_product_id == external_product_id,
    )
    if for_update:
        statement = statement.with_for_update(of=Stock)
    return db.session.scalar(statement)


def add_stock(
    branch_id: int,
    external_product_id: str,
    quantity: int,
) -> Stock:
    """Atomically create or increment a stock row in PostgreSQL."""
    statement = insert(Stock).values(
        branch_id=branch_id,
        external_product_id=external_product_id,
        quantity=quantity,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_stocks_branch_product",
        set_={
            "quantity": Stock.quantity + statement.excluded.quantity,
            "updated_at": func.now(),
        },
    ).returning(Stock)
    return db.session.execute(statement).scalar_one()


__all__ = [
    "add_stock",
    "get_branch",
    "get_stock",
    "list_stocks",
]
