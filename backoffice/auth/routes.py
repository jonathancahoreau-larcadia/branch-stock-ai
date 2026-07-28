"""HTTP routes for Backoffice JWT authentication."""

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import BadRequest

from backoffice.api_errors import error_response
from backoffice.config import (
    ACCESS_TOKEN_EXPIRES_IN,
    REFRESH_TOKEN_EXPIRES_IN,
)
from backoffice.database.models import ACCESS_TOKEN_TYPE, REFRESH_TOKEN_TYPE

from .decorators import current_user, protected_token_required
from .schemas import LoginValidationError, validate_login_payload
from .services import (
    AccountInactiveError,
    InvalidCredentialsError,
    authenticate_user,
    issue_access_token,
    issue_token_pair,
    revoke_token,
    serialize_user,
)

auth_blueprint = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_blueprint.post("/login")
def login():
    """Authenticate credentials and issue one access/refresh token pair."""
    if not request.is_json:
        return error_response("INVALID_JSON", 400)

    try:
        payload = request.get_json()
    except BadRequest:
        return error_response("INVALID_JSON", 400)

    try:
        credentials = validate_login_payload(payload)
    except LoginValidationError as exc:
        return error_response(
            "VALIDATION_ERROR",
            400,
            details=exc.details,
        )

    try:
        user = authenticate_user(
            credentials.username,
            credentials.password,
        )
    except InvalidCredentialsError:
        return error_response("INVALID_CREDENTIALS", 401)
    except AccountInactiveError:
        return error_response("ACCOUNT_INACTIVE", 403)

    tokens = issue_token_pair(user)
    return (
        jsonify(
            data={
                **tokens,
                "token_type": "Bearer",
                "access_token_expires_in": ACCESS_TOKEN_EXPIRES_IN,
                "refresh_token_expires_in": REFRESH_TOKEN_EXPIRES_IN,
                "user": serialize_user(user),
            }
        ),
        200,
    )


@auth_blueprint.post("/refresh")
@protected_token_required(token_type=REFRESH_TOKEN_TYPE)
def refresh():
    """Issue a new access token without rotating the refresh token."""
    return (
        jsonify(
            data={
                "access_token": issue_access_token(current_user()),
                "token_type": "Bearer",
                "access_token_expires_in": ACCESS_TOKEN_EXPIRES_IN,
            }
        ),
        200,
    )


@auth_blueprint.post("/logout")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def logout():
    """Revoke only the presented access token."""
    revoke_token(current_user(), reason="logout")
    return Response(status=204)


@auth_blueprint.post("/logout/refresh")
@protected_token_required(token_type=REFRESH_TOKEN_TYPE)
def logout_refresh():
    """Revoke only the presented refresh token."""
    revoke_token(current_user(), reason="logout")
    return Response(status=204)


@auth_blueprint.get("/me")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def me():
    """Return the current database representation of the account."""
    return jsonify(data=serialize_user(current_user())), 200
