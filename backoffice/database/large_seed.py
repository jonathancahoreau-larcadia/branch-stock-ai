"""Large, deterministic and additive demonstration seed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import random
import time

import bcrypt
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from backoffice.config import validate_runtime_value
from backoffice.database.models import (
    COMMON_USER_ROLE,
    Branch,
    Stock,
    User,
)
from backoffice.extensions import db
from backoffice.products.client import (
    ProductClient,
    ProductClientError,
)
from backoffice.users.services import hash_password

LARGE_SEED_BRANCH_PREFIX = "Démo Large — "
LARGE_SEED_USERNAME_PREFIX = "demo-"
LOCAL_ENVIRONMENTS = frozenset({"development", "local", "demo", "test"})
PRODUCT_PAGE_LIMIT = 100
SOFT_DELETE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)

BRANCH_SITES: tuple[tuple[str, str], ...] = (
    ("Marseille Centre", "marseille"),
    ("Toulon Centre", "toulon"),
    ("Lyon Part-Dieu", "lyon"),
    ("Paris Centre", "paris"),
    ("Bordeaux Centre", "bordeaux"),
    ("Lille Centre", "lille"),
    ("Nantes Centre", "nantes"),
    ("Toulouse Centre", "toulouse"),
    ("Montpellier Centre", "montpellier"),
    ("Nice Centre", "nice"),
    ("Rennes Centre", "rennes"),
    ("Strasbourg Centre", "strasbourg"),
    ("Grenoble Centre", "grenoble"),
    ("Rouen Centre", "rouen"),
    ("Dijon Centre", "dijon"),
)


class LargeSeedError(RuntimeError):
    """Base class for safe large-seed failures."""


class LargeSeedConfigurationError(LargeSeedError):
    """The command configuration is missing or unsafe."""


class LargeSeedConflictError(LargeSeedError):
    """Existing reserved demonstration data is incompatible."""


class LargeSeedProductError(LargeSeedError):
    """The complete external catalogue could not be validated."""


@dataclass(frozen=True)
class BranchPlan:
    """One deterministically named demonstration branch."""

    name: str
    slug: str


@dataclass(frozen=True)
class UserPlan:
    """One deterministic common user and its expected state."""

    username: str
    branch_name: str
    deleted: bool


@dataclass(frozen=True)
class StockPlan:
    """One permitted external identifier and deterministic quantity."""

    branch_name: str
    external_product_id: str
    quantity: int


@dataclass(frozen=True)
class LargeSeedPlan:
    """The complete logical dataset built before database writes."""

    branches: tuple[BranchPlan, ...]
    users: tuple[UserPlan, ...]
    product_ids: tuple[str, ...]
    stocks: tuple[StockPlan, ...]
    seed: int


@dataclass(frozen=True)
class LargeSeedResult:
    """Safe counts returned by a dry-run or committed execution."""

    branches_total: int
    branches_created: int
    users_total: int
    users_created: int
    users_soft_deleted: int
    products_fetched: int
    stocks_total: int
    stocks_created: int
    seed: int
    dry_run: bool

    @property
    def already_complete(self) -> bool:
        """Return whether no row needed to be added."""
        return not any(
            (
                self.branches_created,
                self.users_created,
                self.stocks_created,
            )
        )


def _validate_environment(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LargeSeedConfigurationError(
            "APP_ENV must explicitly identify a local environment."
        )
    normalized = value.strip().casefold()
    if normalized not in LOCAL_ENVIRONMENTS:
        raise LargeSeedConfigurationError(
            "seed-large is allowed only in development, local, demo, or "
            "test environments."
        )
    return normalized


def _validate_password(value: object) -> str:
    try:
        password = validate_runtime_value(
            "LARGE_SEED_USER_PASSWORD",
            value,
        )
    except RuntimeError as exc:
        raise LargeSeedConfigurationError(str(exc)) from None
    try:
        encoded = password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise LargeSeedConfigurationError(
            "LARGE_SEED_USER_PASSWORD must contain valid UTF-8 text."
        ) from exc
    if len(encoded) > 72:
        raise LargeSeedConfigurationError(
            "LARGE_SEED_USER_PASSWORD cannot exceed 72 UTF-8 bytes."
        )
    return password


def _validate_options(
    branches: object,
    users_per_branch: object,
    seed: object,
) -> tuple[int, int, int]:
    if (
        isinstance(branches, bool)
        or not isinstance(branches, int)
        or not 1 <= branches <= len(BRANCH_SITES)
    ):
        raise LargeSeedConfigurationError(
            "branches must be an integer between 1 and 15."
        )
    if (
        isinstance(users_per_branch, bool)
        or not isinstance(users_per_branch, int)
        or users_per_branch <= 0
    ):
        raise LargeSeedConfigurationError(
            "users-per-branch must be a strictly positive integer."
        )
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise LargeSeedConfigurationError("seed must be an integer.")
    return branches, users_per_branch, seed


def _derived_random(seed: int, *parts: str) -> random.Random:
    """Return a stable RNG isolated from catalogue ordering changes."""
    material = "\x1f".join((str(seed), *parts))
    return random.Random(material)


def _branch_plans(count: int) -> tuple[BranchPlan, ...]:
    return tuple(
        BranchPlan(
            name=f"{LARGE_SEED_BRANCH_PREFIX}{site_name}",
            slug=slug,
        )
        for site_name, slug in BRANCH_SITES[:count]
    )


def _user_plans(
    branches: tuple[BranchPlan, ...],
    users_per_branch: int,
    seed: int,
) -> tuple[UserPlan, ...]:
    candidates: list[tuple[str, str]] = []
    for branch in branches:
        for sequence in range(1, users_per_branch + 1):
            username = (
                f"{LARGE_SEED_USERNAME_PREFIX}{branch.slug}-{sequence:02d}"
            )
            candidates.append((username, branch.name))

    deletion_order = list(candidates)
    random.Random(seed).shuffle(deletion_order)
    target_deleted = round(len(candidates) * 0.10)
    active_by_branch = {
        branch.name: users_per_branch
        for branch in branches
    }
    deleted_usernames: set[str] = set()
    for username, branch_name in deletion_order:
        if len(deleted_usernames) >= target_deleted:
            break
        if active_by_branch[branch_name] <= 1:
            continue
        deleted_usernames.add(username)
        active_by_branch[branch_name] -= 1

    return tuple(
        UserPlan(
            username=username,
            branch_name=branch_name,
            deleted=username in deleted_usernames,
        )
        for username, branch_name in candidates
    )


def _stock_quantity(
    seed: int,
    branch_name: str,
    external_product_id: str,
) -> int:
    rng = _derived_random(
        seed,
        "stock",
        branch_name,
        external_product_id.casefold(),
    )
    bucket = rng.random()
    if bucket < 0.20:
        return 0
    if bucket < 0.40:
        return rng.randint(1, 5)
    return rng.randint(6, 200)


def fetch_all_product_ids(
    product_client: ProductClient,
) -> tuple[str, ...]:
    """Fetch every validated page and return unique SKUs in API order."""
    offset = 0
    total: int | None = None
    seen_ids: set[int] = set()
    seen_skus: set[str] = set()
    product_ids: list[str] = []

    while total is None or offset < total:
        page = product_client.list_products(
            {
                "limit": str(PRODUCT_PAGE_LIMIT),
                "offset": str(offset),
            }
        )
        if page.limit != PRODUCT_PAGE_LIMIT or page.offset != offset:
            raise LargeSeedProductError(
                "Product API pagination is inconsistent."
            )
        if total is None:
            total = page.total
        elif page.total != total:
            raise LargeSeedProductError(
                "Product API count changed during pagination."
            )

        for product in page.products:
            normalized_sku = product.sku.strip()
            folded_sku = normalized_sku.casefold()
            if len(normalized_sku) > 255:
                raise LargeSeedProductError(
                    "Product API returned an identifier that is too long."
                )
            if product.id in seen_ids or folded_sku in seen_skus:
                raise LargeSeedProductError(
                    "Product API returned a duplicate product."
                )
            seen_ids.add(product.id)
            seen_skus.add(folded_sku)
            product_ids.append(normalized_sku)

        next_offset = offset + page.limit
        if next_offset <= offset:
            raise LargeSeedProductError(
                "Product API pagination did not make progress."
            )
        offset = next_offset

    if total is None or len(product_ids) != total:
        raise LargeSeedProductError(
            "Product API catalogue size is inconsistent."
        )
    return tuple(product_ids)


def build_large_seed_plan(
    *,
    branches: int,
    users_per_branch: int,
    seed: int,
    product_client: ProductClient,
) -> LargeSeedPlan:
    """Validate the full catalogue and build deterministic logical rows."""
    branch_count, user_count, normalized_seed = _validate_options(
        branches,
        users_per_branch,
        seed,
    )
    branch_plans = _branch_plans(branch_count)
    user_plans = _user_plans(
        branch_plans,
        user_count,
        normalized_seed,
    )
    product_ids = fetch_all_product_ids(product_client)
    stocks = tuple(
        StockPlan(
            branch_name=branch.name,
            external_product_id=product_id,
            quantity=_stock_quantity(
                normalized_seed,
                branch.name,
                product_id,
            ),
        )
        for branch in branch_plans
        for product_id in product_ids
    )
    return LargeSeedPlan(
        branches=branch_plans,
        users=user_plans,
        product_ids=product_ids,
        stocks=stocks,
        seed=normalized_seed,
    )


def _password_matches(password: str, password_hash: object) -> bool:
    if not isinstance(password_hash, str):
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


def _load_reserved_branches() -> list[Branch]:
    prefix = LARGE_SEED_BRANCH_PREFIX.casefold()
    return list(
        db.session.scalars(
            select(Branch).where(
                func.lower(Branch.name).like(f"{prefix}%")
            )
        ).all()
    )


def _load_reserved_users() -> list[User]:
    return list(
        db.session.scalars(
            select(User).where(
                User.username.like(f"{LARGE_SEED_USERNAME_PREFIX}%")
            )
        ).all()
    )


def _validate_existing_user(
    user: User,
    expected: UserPlan,
    branch: Branch,
    password: str,
) -> None:
    expected_active = not expected.deleted
    compatible = (
        user.role == COMMON_USER_ROLE
        and user.branch_id == branch.id
        and user.is_active is expected_active
        and ((user.deleted_at is not None) is expected.deleted)
        and isinstance(user.token_version, int)
        and not isinstance(user.token_version, bool)
        and user.token_version >= 0
        and _password_matches(password, user.password_hash)
    )
    if not compatible:
        raise LargeSeedConflictError(
            f"Existing reserved user is incompatible: {expected.username}."
        )


def apply_large_seed_plan(
    plan: LargeSeedPlan,
    *,
    password: str,
    dry_run: bool,
) -> LargeSeedResult:
    """Complete safe missing rows in one transaction, never overwriting."""
    expected_branch_names = {branch.name for branch in plan.branches}
    expected_users = {user.username: user for user in plan.users}
    expected_stocks = {
        (stock.branch_name, stock.external_product_id): stock
        for stock in plan.stocks
    }

    branches_created = 0
    users_created = 0
    stocks_created = 0

    with db.session.begin():
        reserved_branches = _load_reserved_branches()
        unexpected_branches = sorted(
            branch.name
            for branch in reserved_branches
            if branch.name not in expected_branch_names
        )
        if unexpected_branches:
            raise LargeSeedConflictError(
                "Existing reserved branches are incompatible with the "
                "requested branch count."
            )

        branches_by_name = {
            branch.name: branch
            for branch in reserved_branches
        }
        missing_branch_names = [
            branch.name
            for branch in plan.branches
            if branch.name not in branches_by_name
        ]

        reserved_users = _load_reserved_users()
        unexpected_users = sorted(
            user.username
            for user in reserved_users
            if user.username not in expected_users
        )
        if unexpected_users:
            raise LargeSeedConflictError(
                "Existing reserved users are incompatible with the "
                "requested users-per-branch value."
            )

        existing_users = {
            user.username: user
            for user in reserved_users
        }
        for username, user in existing_users.items():
            expected = expected_users[username]
            branch = branches_by_name.get(expected.branch_name)
            if branch is None:
                raise LargeSeedConflictError(
                    "Existing reserved user references an incompatible "
                    "demonstration branch."
                )
            _validate_existing_user(
                user,
                expected,
                branch,
                password,
            )

        existing_stocks: dict[tuple[str, str], Stock] = {}
        existing_branch_ids = {
            branch.id: branch.name
            for branch in reserved_branches
        }
        if existing_branch_ids:
            rows = db.session.scalars(
                select(Stock).where(
                    Stock.branch_id.in_(existing_branch_ids)
                )
            )
            for stock in rows:
                branch_name = existing_branch_ids[stock.branch_id]
                key = (branch_name, stock.external_product_id)
                expected = expected_stocks.get(key)
                if expected is not None:
                    if stock.quantity != expected.quantity:
                        raise LargeSeedConflictError(
                            "Existing reserved stock is incompatible for "
                            f"{branch_name} / {stock.external_product_id}."
                        )
                    existing_stocks[key] = stock

        missing_users = [
            user
            for user in plan.users
            if user.username not in existing_users
        ]
        missing_stocks = [
            stock
            for stock in plan.stocks
            if (
                stock.branch_name,
                stock.external_product_id,
            )
            not in existing_stocks
        ]

        branches_created = len(missing_branch_names)
        users_created = len(missing_users)
        stocks_created = len(missing_stocks)

        if not dry_run:
            for branch_plan in plan.branches:
                if branch_plan.name not in branches_by_name:
                    branch = Branch(name=branch_plan.name)
                    db.session.add(branch)
                    branches_by_name[branch_plan.name] = branch
            db.session.flush()

            for user_plan in missing_users:
                db.session.add(
                    User(
                        username=user_plan.username,
                        password_hash=hash_password(password),
                        role=COMMON_USER_ROLE,
                        branch=branches_by_name[user_plan.branch_name],
                        is_active=not user_plan.deleted,
                        token_version=0,
                        deleted_at=(
                            SOFT_DELETE_TIMESTAMP
                            if user_plan.deleted
                            else None
                        ),
                    )
                )

            for stock_plan in missing_stocks:
                db.session.add(
                    Stock(
                        branch=branches_by_name[stock_plan.branch_name],
                        external_product_id=(
                            stock_plan.external_product_id
                        ),
                        quantity=stock_plan.quantity,
                    )
                )

    return LargeSeedResult(
        branches_total=len(plan.branches),
        branches_created=branches_created,
        users_total=len(plan.users),
        users_created=users_created,
        users_soft_deleted=sum(user.deleted for user in plan.users),
        products_fetched=len(plan.product_ids),
        stocks_total=len(plan.stocks),
        stocks_created=stocks_created,
        seed=plan.seed,
        dry_run=dry_run,
    )


def seed_large_database(
    *,
    app_environment: object,
    user_password: object,
    branches: int,
    users_per_branch: int,
    seed: int,
    product_client: ProductClient,
    dry_run: bool = False,
) -> LargeSeedResult:
    """Validate configuration/catalogue, then add missing demo rows."""
    _validate_environment(app_environment)
    password = _validate_password(user_password)
    plan = build_large_seed_plan(
        branches=branches,
        users_per_branch=users_per_branch,
        seed=seed,
        product_client=product_client,
    )
    return apply_large_seed_plan(
        plan,
        password=password,
        dry_run=dry_run,
    )


def _result_message(result: LargeSeedResult, duration: float) -> str:
    mode = "dry-run" if result.dry_run else "completed"
    if result.already_complete:
        mode = f"{mode}, already complete"
    return (
        f"Large seed {mode}: "
        f"branches_total={result.branches_total}, "
        f"branches_created={result.branches_created}, "
        f"users_total={result.users_total}, "
        f"users_created={result.users_created}, "
        f"users_soft_deleted={result.users_soft_deleted}, "
        f"products_fetched={result.products_fetched}, "
        f"stocks_total={result.stocks_total}, "
        f"stocks_created={result.stocks_created}, "
        f"seed={result.seed}, "
        f"duration_seconds={duration:.3f}."
    )


@click.command("seed-large")
@click.option(
    "--branches",
    type=click.IntRange(1, len(BRANCH_SITES)),
    default=15,
    show_default=True,
)
@click.option(
    "--users-per-branch",
    type=click.IntRange(min=1),
    default=3,
    show_default=True,
)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--dry-run", is_flag=True)
@with_appcontext
def seed_large_command(
    branches: int,
    users_per_branch: int,
    seed: int,
    dry_run: bool,
) -> None:
    """Create or safely complete the deterministic large demo dataset."""
    started = time.perf_counter()
    try:
        product_client = ProductClient(
            current_app.config.get("PRODUCT_API_BASE_URL", ""),
            current_app.config.get("PRODUCT_API_TIMEOUT", ""),
        )
        result = seed_large_database(
            app_environment=current_app.config.get("APP_ENV"),
            user_password=current_app.config.get(
                "LARGE_SEED_USER_PASSWORD"
            ),
            branches=branches,
            users_per_branch=users_per_branch,
            seed=seed,
            product_client=product_client,
            dry_run=dry_run,
        )
    except (LargeSeedError, ProductClientError) as exc:
        db.session.rollback()
        raise click.ClickException(str(exc)) from exc
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise click.ClickException(
            "Large seed failed; no changes were committed."
        ) from exc
    except Exception as exc:
        db.session.rollback()
        raise click.ClickException(
            "Large seed failed; no changes were committed."
        ) from exc

    click.echo(_result_message(result, time.perf_counter() - started))


__all__ = [
    "BRANCH_SITES",
    "LARGE_SEED_BRANCH_PREFIX",
    "LARGE_SEED_USERNAME_PREFIX",
    "BranchPlan",
    "LargeSeedConfigurationError",
    "LargeSeedConflictError",
    "LargeSeedError",
    "LargeSeedPlan",
    "LargeSeedProductError",
    "LargeSeedResult",
    "StockPlan",
    "UserPlan",
    "apply_large_seed_plan",
    "build_large_seed_plan",
    "fetch_all_product_ids",
    "seed_large_command",
    "seed_large_database",
]
