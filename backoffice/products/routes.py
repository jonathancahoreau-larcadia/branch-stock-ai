"""Empty route blueprint for the future products API."""

from flask import Blueprint

products_blueprint = Blueprint(
    "products", __name__, url_prefix="/api/v1/products"
)
