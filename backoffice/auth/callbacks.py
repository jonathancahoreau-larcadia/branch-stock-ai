"""Flask-JWT-Extended callbacks mapped to the public API contract."""

from __future__ import annotations

from flask_jwt_extended import JWTManager
from sqlalchemy import select

from backoffice.api_errors import error_response
from backoffice.database.models import RevokedToken
from backoffice.extensions import db


def register_jwt_callbacks(jwt_manager: JWTManager) -> None:
    """Register stable errors and the PostgreSQL token blocklist."""

    @jwt_manager.unauthorized_loader
    def missing_token(_reason: str):
        return error_response("AUTHENTICATION_REQUIRED", 401)

    @jwt_manager.invalid_token_loader
    def invalid_token(_reason: str):
        return error_response("TOKEN_INVALID", 401)

    @jwt_manager.expired_token_loader
    def expired_token(_header: dict, _payload: dict):
        return error_response("TOKEN_EXPIRED", 401)

    @jwt_manager.revoked_token_loader
    def revoked_token(_header: dict, _payload: dict):
        return error_response("TOKEN_REVOKED", 401)

    @jwt_manager.token_in_blocklist_loader
    def token_is_revoked(_header: dict, payload: dict) -> bool:
        jti = payload.get("jti")
        if not isinstance(jti, str):
            return False
        return (
            db.session.scalar(
                select(RevokedToken.id).where(RevokedToken.jti == jti)
            )
            is not None
        )


__all__ = ["register_jwt_callbacks"]
