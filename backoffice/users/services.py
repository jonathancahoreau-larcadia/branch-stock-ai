"""Business rules and transactions for Backoffice user management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import bcrypt
from flask import current_app
from sqlalchemy.exc import IntegrityError

from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    User,
)
from backoffice.extensions import db

from . import repositories
from .schemas import (
    CreateUserData,
    PasswordUpdateData,
    UpdateUserData,
    UserListFilters,
)


class UserServiceError(RuntimeError):
    """A stable user-management business error."""

    code = "INTERNAL_ERROR"
    status = 500


class UserNotFoundError(UserServiceError):
    code = "USER_NOT_FOUND"
    status = 404


class BranchNotFoundError(UserServiceError):
    code = "BRANCH_NOT_FOUND"
    status = 404


class UsernameAlreadyExistsError(UserServiceError):
    code = "USERNAME_ALREADY_EXISTS"
    status = 409


class ReservedUsernameError(UserServiceError):
    code = "RESERVED_USERNAME"
    status = 422


class UserTargetForbiddenError(UserServiceError):
    code = "FORBIDDEN"
    status = 403


def _bcrypt_rounds() -> int:
    try:
        rounds = int(current_app.config.get("BCRYPT_ROUNDS"))
    except (TypeError, ValueError) as exc:
        raise UserServiceError from exc
    if not 4 <= rounds <= 31:
        raise UserServiceError
    return rounds


def hash_password(password: str) -> str:
    """Hash an already validated password with the configured bcrypt cost."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=_bcrypt_rounds()),
    ).decode("utf-8")


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_integrity_error(error: IntegrityError) -> None:
    db.session.rollback()
    constraint = _constraint_name(error)
    if constraint == "uq_users_username":
        raise UsernameAlreadyExistsError from error
    if constraint == "fk_users_branch_id":
        raise BranchNotFoundError from error
    if constraint in {
        "ck_users_admin_username",
        "ck_users_reserved_admin_username",
        "uq_users_single_admin",
    }:
        raise ReservedUsernameError from error
    raise error


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError as error:
        _raise_integrity_error(error)


def _require_assignable_branch(branch_id: int) -> Branch:
    branch = repositories.get_branch(branch_id)
    if branch is None:
        raise BranchNotFoundError
    return branch


def _validate_available_username(
    username: str,
    *,
    exclude_user_id: int | None = None,
) -> None:
    if username == "admin":
        raise ReservedUsernameError
    if repositories.username_exists(
        username,
        exclude_user_id=exclude_user_id,
    ):
        raise UsernameAlreadyExistsError


def _mutable_common_user(user_id: int) -> User:
    user = repositories.get_user(user_id, for_update=True)
    if user is None or user.deleted_at is not None:
        raise UserNotFoundError
    if user.role == ADMIN_ROLE:
        raise UserTargetForbiddenError
    return user


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _serialize_branch(branch: Branch | None) -> dict[str, Any] | None:
    if branch is None:
        return None
    return {"id": branch.id, "name": branch.name}


def serialize_user(user: User) -> dict[str, Any]:
    """Serialize only fields explicitly allowed by the API contract."""
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "branch": _serialize_branch(user.branch),
        "is_active": user.is_active,
        "deleted_at": _serialize_datetime(user.deleted_at),
    }


def list_users(filters: UserListFilters) -> list[User]:
    """Return users matching the validated list filters."""
    return repositories.list_users(
        status=filters.status,
        branch_id=filters.branch_id,
    )


def get_user(user_id: int) -> User:
    """Return an active, inactive, deleted, or admin user by identifier."""
    user = repositories.get_user(user_id)
    if user is None:
        raise UserNotFoundError
    return user


def create_user(data: CreateUserData) -> User:
    """Create exactly one active common user."""
    _validate_available_username(data.username)
    branch = _require_assignable_branch(data.branch_id)
    password_hash = hash_password(data.password)
    user = User(
        username=data.username,
        password_hash=password_hash,
        role=COMMON_USER_ROLE,
        branch=branch,
        is_active=True,
        deleted_at=None,
        token_version=0,
    )
    db.session.add(user)
    _commit()
    return user


def update_user(user_id: int, data: UpdateUserData) -> User:
    """Update only the username and/or branch of a common user."""
    user = _mutable_common_user(user_id)
    branch = None

    if data.username_provided:
        _validate_available_username(
            data.username,
            exclude_user_id=user.id,
        )
    if data.branch_id_provided:
        branch = _require_assignable_branch(data.branch_id)

    if data.username_provided:
        user.username = data.username
    if data.branch_id_provided:
        user.branch = branch
    _commit()
    return user


def update_password(
    user_id: int,
    data: PasswordUpdateData,
) -> None:
    """Replace a common user's password and invalidate all prior JWTs."""
    password_hash = hash_password(data.new_password)
    user = _mutable_common_user(user_id)
    user.password_hash = password_hash
    user.token_version += 1
    _commit()


def soft_delete_user(user_id: int) -> None:
    """Soft-delete a common user, preserving all associated rows."""
    user = repositories.get_user(user_id, for_update=True)
    if user is None:
        raise UserNotFoundError
    if user.role == ADMIN_ROLE:
        raise UserTargetForbiddenError
    if user.deleted_at is not None:
        return
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    _commit()


__all__ = [
    "BranchNotFoundError",
    "ReservedUsernameError",
    "UserNotFoundError",
    "UserServiceError",
    "UserTargetForbiddenError",
    "UsernameAlreadyExistsError",
    "create_user",
    "get_user",
    "hash_password",
    "list_users",
    "serialize_user",
    "soft_delete_user",
    "update_password",
    "update_user",
]
