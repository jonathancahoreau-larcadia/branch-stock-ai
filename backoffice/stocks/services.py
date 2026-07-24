"""Authorization, enrichment, and transactions for the Stocks API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    Stock,
    User,
)
from backoffice.extensions import db
from backoffice.products.services import get_product

from . import repositories
from .schemas import StockListFilters, StockMovementData


class StockServiceError(RuntimeError):
    """A stable stock business error."""

    code = "INTERNAL_ERROR"
    status = 500


class AdminStockForbiddenError(StockServiceError):
    code = "ADMIN_STOCK_FORBIDDEN"
    status = 403


class StockRoleForbiddenError(StockServiceError):
    code = "FORBIDDEN"
    status = 403


class BranchNotFoundError(StockServiceError):
    code = "BRANCH_NOT_FOUND"
    status = 404


class StockNotFoundError(StockServiceError):
    code = "STOCK_NOT_FOUND"
    status = 404


class StockConflictError(StockServiceError):
    code = "STOCK_CONFLICT"
    status = 409


class InsufficientStockError(StockServiceError):
    code = "INSUFFICIENT_STOCK"
    status = 422


@dataclass(frozen=True)
class StockListResult:
    """A branch and its product-enriched stock rows."""

    branch: Branch
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class StockDetailResult:
    """A branch and one product-enriched stock row."""

    branch: Branch
    stock: Stock
    product: dict[str, Any]


def _current_branch(user: User) -> Branch:
    authorize_stock_user(user)
    if user.branch_id is None:
        raise BranchNotFoundError
    branch = repositories.get_branch(user.branch_id)
    if branch is None:
        raise BranchNotFoundError
    return branch


def authorize_stock_user(user: User) -> None:
    """Reject every role that cannot use any stock endpoint."""
    if user.role == ADMIN_ROLE:
        raise AdminStockForbiddenError
    if user.role != COMMON_USER_ROLE:
        raise StockRoleForbiddenError


def _product(identifier: str) -> dict[str, Any]:
    """Load an already validated product through the existing service."""
    return get_product(identifier)


def _serialize_item(
    stock: Stock,
    product: dict[str, Any],
) -> dict[str, Any]:
    return {
        "external_product_id": stock.external_product_id,
        "quantity": stock.quantity,
        "product": {"name": product["name"]},
    }


def serialize_stock_list(result: StockListResult) -> dict[str, Any]:
    """Serialize only the branch, quantities, canonical SKUs, and names."""
    return {
        "branch": {"id": result.branch.id, "name": result.branch.name},
        "items": result.items,
    }


def serialize_stock_detail(result: StockDetailResult) -> dict[str, Any]:
    """Serialize the exact stock detail/movement response."""
    return {
        "branch": {"id": result.branch.id, "name": result.branch.name},
        **_serialize_item(result.stock, result.product),
    }


def list_stocks(user: User, filters: StockListFilters) -> StockListResult:
    """List only the current common user's branch stocks."""
    branch = _current_branch(user)
    stocks = repositories.list_stocks(
        branch.id,
        available_only=filters.available_only,
    )
    items = [
        _serialize_item(stock, _product(stock.external_product_id))
        for stock in stocks
    ]
    return StockListResult(branch=branch, items=items)


def get_stock(user: User, identifier: str) -> StockDetailResult:
    """Return one current-branch quantity after canonicalizing its product."""
    branch = _current_branch(user)
    product = _product(identifier)
    stock = repositories.get_stock(
        branch.id,
        product["external_product_id"],
    )
    if stock is None:
        raise StockNotFoundError
    return StockDetailResult(branch=branch, stock=stock, product=product)


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None) or getattr(
        error.orig, "pgcode", None
    )


def _is_stock_conflict(error: SQLAlchemyError) -> bool:
    if isinstance(error, DBAPIError) and _sqlstate(error) in {
        "40001",  # serialization_failure
        "40P01",  # deadlock_detected
        "55P03",  # lock_not_available
    }:
        return True
    return (
        isinstance(error, IntegrityError)
        and _constraint_name(error) == "uq_stocks_branch_product"
    )


def _rollback_database_error(error: SQLAlchemyError) -> None:
    db.session.rollback()
    if _is_stock_conflict(error):
        raise StockConflictError from error
    raise error


def add_stock(
    user: User,
    identifier: str,
    data: StockMovementData,
) -> StockDetailResult:
    """Atomically create or add stock after external product validation."""
    branch = _current_branch(user)
    product = _product(identifier)
    try:
        stock = repositories.add_stock(
            branch.id,
            product["external_product_id"],
            data.quantity,
        )
        db.session.commit()
    except SQLAlchemyError as error:
        _rollback_database_error(error)
    return StockDetailResult(branch=branch, stock=stock, product=product)


def remove_stock(
    user: User,
    identifier: str,
    data: StockMovementData,
) -> StockDetailResult:
    """Lock, validate, and decrement one stock row without deleting it."""
    branch = _current_branch(user)
    product = _product(identifier)
    try:
        stock = repositories.get_stock(
            branch.id,
            product["external_product_id"],
            for_update=True,
        )
        if stock is None:
            db.session.rollback()
            raise StockNotFoundError
        if stock.quantity < data.quantity:
            db.session.rollback()
            raise InsufficientStockError
        stock.quantity -= data.quantity
        db.session.commit()
    except StockServiceError:
        raise
    except SQLAlchemyError as error:
        _rollback_database_error(error)
    return StockDetailResult(branch=branch, stock=stock, product=product)


__all__ = [
    "AdminStockForbiddenError",
    "BranchNotFoundError",
    "InsufficientStockError",
    "StockConflictError",
    "StockDetailResult",
    "StockListResult",
    "StockNotFoundError",
    "StockRoleForbiddenError",
    "StockServiceError",
    "add_stock",
    "authorize_stock_user",
    "get_stock",
    "list_stocks",
    "remove_stock",
    "serialize_stock_detail",
    "serialize_stock_list",
]
