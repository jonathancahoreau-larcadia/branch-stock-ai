"""Health endpoint for the Backoffice service."""

from flask import Blueprint, Response, jsonify

health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health")
def health() -> tuple[Response, int]:
    """Report that the Backoffice process is available."""
    return jsonify(status="ok"), 200
