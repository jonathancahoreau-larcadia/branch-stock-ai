"""Authentication decorators that reload current account state."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import g
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from backoffice.api_errors import error_response
from backoffice.database.models import User
from backoffice.extensions import db

ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])


def protected_token_required(
    *,
    token_type: str,
) -> Callable[[ViewFunction], ViewFunction]:
    """Require a non-revoked token and a current active database user."""

    def decorator(function: ViewFunction) -> ViewFunction:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any):
            verify_jwt_in_request(verify_type=False)
            claims = get_jwt()

            issued_at = claims.get("iat")
            expires_at = claims.get("exp")
            jti = claims.get("jti")
            if (
                isinstance(issued_at, bool)
                or not isinstance(issued_at, int)
                or isinstance(expires_at, bool)
                or not isinstance(expires_at, int)
                or expires_at <= issued_at
                or not isinstance(jti, str)
                or not jti
            ):
                return error_response("TOKEN_INVALID", 401)

            if claims.get("type") != token_type:
                return error_response("WRONG_TOKEN_TYPE", 401)

            subject = claims.get("sub")
            if (
                not isinstance(subject, str)
                or not subject.isdecimal()
                or int(subject) <= 0
            ):
                return error_response("TOKEN_INVALID", 401)

            user = db.session.get(User, int(subject))
            if (
                user is None
                or not user.is_active
                or user.deleted_at is not None
            ):
                return error_response("ACCOUNT_INACTIVE", 403)

            token_version = claims.get("token_version")
            if (
                isinstance(token_version, bool)
                or not isinstance(token_version, int)
                or token_version != user.token_version
            ):
                return error_response("TOKEN_VERSION_INVALID", 401)

            g.authenticated_user = user
            return function(*args, **kwargs)

        return cast(ViewFunction, wrapped)

    return decorator


def current_user() -> User:
    """Return the user loaded by ``protected_token_required``."""
    return cast(User, g.authenticated_user)


__all__ = ["current_user", "protected_token_required"]
