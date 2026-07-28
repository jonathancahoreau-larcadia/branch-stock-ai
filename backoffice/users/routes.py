"""HTTP routes for administrator-only common-user management."""

from collections.abc import Callable
from typing import Any

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import BadRequest

from backoffice.api_errors import error_response
from backoffice.auth.decorators import admin_required

from .schemas import (
    UserValidationError,
    validate_create_user,
    validate_list_filters,
    validate_password_update,
    validate_update_user,
)
from .services import (
    UserServiceError,
    create_user,
    get_user,
    list_users,
    serialize_user,
    soft_delete_user,
    update_password,
    update_user,
)

users_blueprint = Blueprint("users", __name__, url_prefix="/api/v1/users")


def _validated_json(
    validator: Callable[[object], Any],
) -> tuple[Any | None, tuple[Response, int] | None]:
    if not request.is_json:
        return None, error_response("INVALID_JSON", 400)
    try:
        payload = request.get_json()
    except BadRequest:
        return None, error_response("INVALID_JSON", 400)
    try:
        return validator(payload), None
    except UserValidationError as error:
        return (
            None,
            error_response(
                "VALIDATION_ERROR",
                400,
                details=error.details,
            ),
        )


def _service_error(error: UserServiceError):
    return error_response(error.code, error.status)


@users_blueprint.get("")
@admin_required
def users_list():
    """List users using the documented state and branch filters."""
    try:
        filters = validate_list_filters(
            request.args.to_dict(flat=False)
        )
    except UserValidationError as error:
        return error_response(
            "VALIDATION_ERROR",
            400,
            details=error.details,
        )

    users = list_users(filters)
    return (
        jsonify(
            data=[serialize_user(user) for user in users],
            meta={"count": len(users)},
        ),
        200,
    )


@users_blueprint.post("")
@admin_required
def users_create():
    """Create one active common user."""
    data, validation_error = _validated_json(validate_create_user)
    if validation_error is not None:
        return validation_error
    try:
        user = create_user(data)
    except UserServiceError as error:
        return _service_error(error)
    return jsonify(data=serialize_user(user)), 201


@users_blueprint.get("/<int:user_id>")
@admin_required
def users_get(user_id: int):
    """Return one user, including an admin or soft-deleted user."""
    try:
        user = get_user(user_id)
    except UserServiceError as error:
        return _service_error(error)
    return jsonify(data=serialize_user(user)), 200


@users_blueprint.patch("/<int:user_id>")
@admin_required
def users_update(user_id: int):
    """Update one common user's username and/or branch."""
    data, validation_error = _validated_json(validate_update_user)
    if validation_error is not None:
        return validation_error
    try:
        user = update_user(user_id, data)
    except UserServiceError as error:
        return _service_error(error)
    return jsonify(data=serialize_user(user)), 200


@users_blueprint.patch("/<int:user_id>/password")
@admin_required
def users_update_password(user_id: int):
    """Replace one common user's password and invalidate its JWTs."""
    data, validation_error = _validated_json(validate_password_update)
    if validation_error is not None:
        return validation_error
    try:
        update_password(user_id, data)
    except UserServiceError as error:
        return _service_error(error)
    return Response(status=204)


@users_blueprint.delete("/<int:user_id>")
@admin_required
def users_delete(user_id: int):
    """Soft-delete one common user idempotently."""
    try:
        soft_delete_user(user_id)
    except UserServiceError as error:
        return _service_error(error)
    return Response(status=204)
