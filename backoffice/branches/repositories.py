"""SQLAlchemy queries used by the branches API."""

from __future__ import annotations

from sqlalchemy import select

from backoffice.database.models import Branch
from backoffice.extensions import db


def list_branches() -> list[Branch]:
    """Return all branches in deterministic display order."""
    statement = select(Branch).order_by(Branch.name.asc(), Branch.id.asc())
    return list(db.session.scalars(statement).all())


def get_branch(branch_id: int) -> Branch | None:
    """Load one branch by its database identifier."""
    return db.session.get(Branch, branch_id)


__all__ = ["get_branch", "list_branches"]
