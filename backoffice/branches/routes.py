"""Read-only HTTP routes for branch consultation."""

from flask import Blueprint, jsonify, request

from backoffice.api_errors import error_response
from backoffice.auth.decorators import (
    current_user,
    protected_token_required,
)
from backoffice.database.models import ACCESS_TOKEN_TYPE

from .services import (
    BranchServiceError,
    get_accessible_branch,
    list_accessible_branches,
    serialize_branch,
)

branches_blueprint = Blueprint(
    "branches", __name__, url_prefix="/api/v1/branches"
)


def _service_error(error: BranchServiceError):
    return error_response(error.code, error.status)


@branches_blueprint.get("")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def branches_list():
    """List all branches visible to the current database user."""
    unexpected = sorted(request.args.keys())
    if unexpected:
        return error_response(
            "VALIDATION_ERROR",
            400,
            details={"fields": {"unexpected": unexpected}},
        )

    try:
        branches = list_accessible_branches(current_user())
    except BranchServiceError as error:
        return _service_error(error)
    return (
        jsonify(
            data=[serialize_branch(branch) for branch in branches],
            meta={"count": len(branches)},
        ),
        200,
    )


@branches_blueprint.get("/<int:branch_id>")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def branches_get(branch_id: int):
    """Return one branch within the current database user's scope."""
    try:
        branch = get_accessible_branch(current_user(), branch_id)
    except BranchServiceError as error:
        return _service_error(error)
    return jsonify(data=serialize_branch(branch)), 200
