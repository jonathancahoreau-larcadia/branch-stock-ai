"""Empty route blueprint for the future stocks API."""

from flask import Blueprint

stocks_blueprint = Blueprint("stocks", __name__, url_prefix="/api/v1/stocks")
