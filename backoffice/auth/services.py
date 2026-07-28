"""Authentication business rules and token persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import bcrypt
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backoffice.database.models import Branch, RevokedToken, User
from backoffice.extensions import db

# A fixed valid bcrypt hash keeps an unknown username on the same expensive
# password-verification path without creating a new hash for each request.
DUMMY_PASSWORD_HASH = (
    "$2b$12$8EVlvF0jzqi4hMaJplcmZuqXYOvSSRg1bWTDB8/Lm3x7f7g/IIYem"
)


class InvalidCredentialsError(ValueError):
    """The supplied username/password pair cannot be authenticated."""


class AccountInactiveError(ValueError):
    """The credentials are correct but the account cannot authenticate."""


def _password_matches(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


def authenticate_user(username: str, password: str) -> User:
    """Verify credentials without exposing whether a username exists."""
    user = db.session.scalar(
        select(User).where(User.username == username)
    )
    password_hash = (
        user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    )
    password_matches = _password_matches(password, password_hash)

    if user is None or not password_matches:
        raise InvalidCredentialsError
    if not user.is_active or user.deleted_at is not None:
        raise AccountInactiveError
    return user


def _additional_claims(user: User) -> dict[str, int]:
    return {"token_version": user.token_version}


def issue_access_token(user: User) -> str:
    """Issue an access token containing no stale authorization data."""
    return create_access_token(
        identity=str(user.id),
        additional_claims=_additional_claims(user),
    )


def issue_token_pair(user: User) -> dict[str, str]:
    """Issue the documented access and refresh tokens."""
    claims = _additional_claims(user)
    identity = str(user.id)
    return {
        "access_token": create_access_token(
            identity=identity,
            additional_claims=claims,
        ),
        "refresh_token": create_refresh_token(
            identity=identity,
            additional_claims=claims,
        ),
    }


def _serialize_branch(branch: Branch | None) -> dict[str, Any] | None:
    if branch is None:
        return None
    return {"id": branch.id, "name": branch.name}


def serialize_user(user: User) -> dict[str, Any]:
    """Serialize only public account fields."""
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "branch": _serialize_branch(user.branch),
    }


def revoke_token(user: User, *, reason: str) -> None:
    """Persist only the current token identifier and expiration metadata."""
    claims = get_jwt()
    jti = claims["jti"]
    token_type = claims["type"]
    expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)

    existing = db.session.scalar(
        select(RevokedToken.id).where(RevokedToken.jti == jti)
    )
    if existing is not None:
        return

    db.session.add(
        RevokedToken(
            user_id=user.id,
            jti=jti,
            token_type=token_type,
            expires_at=expires_at,
            reason=reason,
        )
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = db.session.scalar(
            select(RevokedToken.id).where(RevokedToken.jti == jti)
        )
        if existing is None:
            raise


__all__ = [
    "AccountInactiveError",
    "InvalidCredentialsError",
    "authenticate_user",
    "issue_access_token",
    "issue_token_pair",
    "revoke_token",
    "serialize_user",
]
