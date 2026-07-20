"""Empty route blueprint for the future branches API."""

from flask import Blueprint

branches_blueprint = Blueprint(
    "branches", __name__, url_prefix="/api/v1/branches"
)
