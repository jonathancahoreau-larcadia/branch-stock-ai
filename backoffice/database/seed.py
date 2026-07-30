"""Idempotent Flask command for the mandatory initial database data."""

from __future__ import annotations

from dataclasses import dataclass

import bcrypt
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from backoffice.database.models import ADMIN_ROLE, Branch, Stock, User
from backoffice.config import validate_runtime_value
from backoffice.extensions import db
from backoffice.products.client import ProductClient, ProductClientError

BRANCH_STOCK_QUANTITIES = {
    "Toulon": 10,
    "Marseille": 5,
}


class SeedError(RuntimeError):
    """A seed precondition or existing row is incompatible."""


class SeedConfigurationError(SeedError):
    """Required seed configuration is missing or invalid."""


class SeedDataConflictError(SeedError):
    """Existing database state conflicts with the immutable seed."""


@dataclass(frozen=True)
class SeedResult:
    """Safe counts describing newly created seed rows."""

    branches_created: int
    admin_created: bool
    stocks_created: int


def _validate_password(password: object) -> bytes:
    try:
        password = validate_runtime_value("ADMIN_INITIAL_PASSWORD", password)
    except RuntimeError as exc:
        raise SeedConfigurationError(str(exc)) from None

    encoded_password = password.encode("utf-8")
    if len(encoded_password) > 72:
        raise SeedConfigurationError(
            "ADMIN_INITIAL_PASSWORD cannot exceed 72 UTF-8 bytes."
        )
    return encoded_password


def _validate_product_id(identifier: object) -> str:
    if not isinstance(identifier, str):
        raise SeedConfigurationError("SEED_PRODUCT_ID must be a string.")

    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise SeedConfigurationError(
            "SEED_PRODUCT_ID is required and cannot be empty."
        )
    if len(normalized_identifier) > 255:
        raise SeedConfigurationError(
            "SEED_PRODUCT_ID cannot exceed 255 characters."
        )
    return normalized_identifier


def _validate_bcrypt_rounds(rounds: object) -> int:
    try:
        normalized_rounds = int(rounds)
    except (TypeError, ValueError) as exc:
        raise SeedConfigurationError(
            "BCRYPT_ROUNDS must be an integer between 4 and 31."
        ) from exc

    if not 4 <= normalized_rounds <= 31:
        raise SeedConfigurationError(
            "BCRYPT_ROUNDS must be an integer between 4 and 31."
        )
    return normalized_rounds


def _load_or_create_branch(session, name: str) -> tuple[Branch, bool]:
    branch = session.scalar(
        select(Branch).where(
            func.lower(func.btrim(Branch.name)) == name.lower()
        )
    )
    if branch is None:
        branch = Branch(name=name)
        session.add(branch)
        session.flush()
        return branch, True

    if branch.name != name:
        raise SeedDataConflictError(
            f"Existing branch conflicts with required branch {name}."
        )
    return branch, False


def _load_or_create_admin(
    session,
    password: bytes,
    bcrypt_rounds: int,
) -> tuple[User, bool]:
    admin = session.scalar(select(User).where(User.username == "admin"))
    if admin is None:
        password_hash = bcrypt.hashpw(
            password,
            bcrypt.gensalt(rounds=bcrypt_rounds),
        ).decode("utf-8")
        admin = User(
            username="admin",
            password_hash=password_hash,
            role=ADMIN_ROLE,
            branch_id=None,
            is_active=True,
            token_version=0,
            deleted_at=None,
        )
        session.add(admin)
        return admin, True

    compatible_state = (
        admin.role == ADMIN_ROLE
        and admin.branch_id is None
        and admin.is_active is True
        and isinstance(admin.token_version, int)
        and not isinstance(admin.token_version, bool)
        and admin.token_version >= 0
        and admin.deleted_at is None
    )
    if not compatible_state:
        raise SeedDataConflictError(
            "Existing admin account is incompatible with the initial seed."
        )

    try:
        password_matches = bcrypt.checkpw(
            password,
            admin.password_hash.encode("utf-8"),
        )
    except (TypeError, ValueError):
        password_matches = False
    if not password_matches:
        raise SeedDataConflictError(
            "Existing admin account is incompatible with the supplied "
            "initial password."
        )
    return admin, False


def _load_or_create_stock(
    session,
    branch: Branch,
    external_product_id: str,
    quantity: int,
) -> bool:
    stock = session.scalar(
        select(Stock).where(
            Stock.branch_id == branch.id,
            Stock.external_product_id == external_product_id,
        )
    )
    if stock is None:
        session.add(
            Stock(
                branch_id=branch.id,
                external_product_id=external_product_id,
                quantity=quantity,
            )
        )
        return True

    if stock.quantity != quantity:
        raise SeedDataConflictError(
            "Existing stock is incompatible with the initial seed for "
            f"branch {branch.name}."
        )
    return False


def seed_database(
    *,
    admin_password: object,
    product_identifier: object,
    bcrypt_rounds: object,
    product_client: ProductClient,
) -> SeedResult:
    """Validate external data, then create all missing rows atomically."""
    password = _validate_password(admin_password)
    identifier = _validate_product_id(product_identifier)
    normalized_rounds = _validate_bcrypt_rounds(bcrypt_rounds)

    product = product_client.get_product(identifier)
    if not product.matches(identifier):
        raise SeedError(
            "Product API response does not match SEED_PRODUCT_ID."
        )
    if product.discontinued:
        raise SeedError("SEED_PRODUCT_ID refers to a discontinued product.")

    branches_created = 0
    stocks_created = 0
    admin_created = False

    with db.session.begin():
        branches: dict[str, Branch] = {}
        for branch_name in BRANCH_STOCK_QUANTITIES:
            branch, created = _load_or_create_branch(
                db.session,
                branch_name,
            )
            branches[branch_name] = branch
            branches_created += int(created)

        _, admin_created = _load_or_create_admin(
            db.session,
            password,
            normalized_rounds,
        )

        for branch_name, quantity in BRANCH_STOCK_QUANTITIES.items():
            created = _load_or_create_stock(
                db.session,
                branches[branch_name],
                identifier,
                quantity,
            )
            stocks_created += int(created)

    return SeedResult(
        branches_created=branches_created,
        admin_created=admin_created,
        stocks_created=stocks_created,
    )


@click.command("seed")
@with_appcontext
def seed_command() -> None:
    """Create the mandatory initial Backoffice data."""
    try:
        product_client = ProductClient(
            current_app.config.get("PRODUCT_API_BASE_URL", ""),
            current_app.config.get("PRODUCT_API_TIMEOUT", ""),
        )
        result = seed_database(
            admin_password=current_app.config.get(
                "ADMIN_INITIAL_PASSWORD"
            ),
            product_identifier=current_app.config.get("SEED_PRODUCT_ID"),
            bcrypt_rounds=current_app.config.get("BCRYPT_ROUNDS"),
            product_client=product_client,
        )
    except (ProductClientError, SeedError) as exc:
        raise click.ClickException(str(exc)) from exc
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise click.ClickException(
            "Database seed failed; no changes were committed."
        ) from exc

    click.echo(
        "Seed completed: "
        f"branches_created={result.branches_created}, "
        f"admin_created={int(result.admin_created)}, "
        f"stocks_created={result.stocks_created}."
    )


__all__ = [
    "SeedConfigurationError",
    "SeedDataConflictError",
    "SeedError",
    "SeedResult",
    "seed_command",
    "seed_database",
]
