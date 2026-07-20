"""Empty route blueprint for the future users API."""

from flask import Blueprint

users_blueprint = Blueprint("users", __name__, url_prefix="/api/v1/users")
