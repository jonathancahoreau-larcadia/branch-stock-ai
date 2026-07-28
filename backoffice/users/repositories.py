"""SQLAlchemy queries used by user-management services."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backoffice.database.models import Branch, User
from backoffice.extensions import db


def get_user(user_id: int, *, for_update: bool = False) -> User | None:
    """Load one user and its branch, optionally locking the row."""
    statement = (
        select(User)
        .options(joinedload(User.branch))
        .where(User.id == user_id)
    )
    if for_update:
        statement = statement.with_for_update(of=User)
    return db.session.scalar(statement)


def get_branch(branch_id: int) -> Branch | None:
    """Load an assignable branch by identifier."""
    return db.session.get(Branch, branch_id)


def username_exists(
    username: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    """Return whether the normalized username is already reserved."""
    statement = select(User.id).where(User.username == username)
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return db.session.scalar(statement) is not None


def list_users(*, status: str, branch_id: int | None) -> list[User]:
    """List users using the documented state and branch filters."""
    statement = select(User).options(joinedload(User.branch))
    if status == "active":
        statement = statement.where(
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    elif status == "deleted":
        statement = statement.where(User.deleted_at.is_not(None))
    if branch_id is not None:
        statement = statement.where(User.branch_id == branch_id)
    statement = statement.order_by(User.id.asc())
    return list(db.session.scalars(statement).all())


__all__ = [
    "get_branch",
    "get_user",
    "list_users",
    "username_exists",
]
