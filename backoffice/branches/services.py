"""Authorization and serialization rules for branch consultation."""

from __future__ import annotations

from typing import Any

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    User,
)

from . import repositories


class BranchServiceError(RuntimeError):
    """A stable branch-consultation business error."""

    code = "INTERNAL_ERROR"
    status = 500


class BranchNotFoundError(BranchServiceError):
    code = "BRANCH_NOT_FOUND"
    status = 404


class BranchAccessForbiddenError(BranchServiceError):
    code = "BRANCH_ACCESS_FORBIDDEN"
    status = 403


class BranchRoleForbiddenError(BranchServiceError):
    code = "FORBIDDEN"
    status = 403


def serialize_branch(branch: Branch) -> dict[str, Any]:
    """Serialize only fields explicitly exposed by the API contract."""
    return {"id": branch.id, "name": branch.name}


def list_accessible_branches(user: User) -> list[Branch]:
    """List every branch visible to the user's current database role."""
    if user.role == ADMIN_ROLE:
        return repositories.list_branches()
    if user.role != COMMON_USER_ROLE:
        raise BranchRoleForbiddenError
    if user.branch_id is None:
        raise BranchNotFoundError

    branch = repositories.get_branch(user.branch_id)
    if branch is None:
        raise BranchNotFoundError
    return [branch]


def get_accessible_branch(user: User, branch_id: int) -> Branch:
    """Return one branch after enforcing the user's current branch scope."""
    if user.role == COMMON_USER_ROLE:
        if user.branch_id != branch_id:
            raise BranchAccessForbiddenError
    elif user.role != ADMIN_ROLE:
        raise BranchRoleForbiddenError

    branch = repositories.get_branch(branch_id)
    if branch is None:
        raise BranchNotFoundError
    return branch


__all__ = [
    "BranchAccessForbiddenError",
    "BranchNotFoundError",
    "BranchRoleForbiddenError",
    "BranchServiceError",
    "get_accessible_branch",
    "list_accessible_branches",
    "serialize_branch",
]
