"""Authenticated read-only routes for the external product catalog."""

from flask import Blueprint, jsonify, request

from backoffice.api_errors import error_response
from backoffice.auth.decorators import protected_token_required
from backoffice.database.models import ACCESS_TOKEN_TYPE

from .schemas import (
    ProductValidationError,
    reject_query_parameters,
    validate_list_query,
    validate_product_identifier,
)
from .services import ProductServiceError, get_product, list_products

products_blueprint = Blueprint(
    "products", __name__, url_prefix="/api/v1/products"
)


def _validation_error(error: ProductValidationError):
    return error_response(
        "VALIDATION_ERROR",
        400,
        details=error.details,
    )


def _service_error(error: ProductServiceError):
    return error_response(error.code, error.status)


@products_blueprint.get("")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def products_list():
    """Return one filtered and paginated external catalog page."""
    try:
        query = validate_list_query(request.args.to_dict(flat=False))
    except ProductValidationError as error:
        return _validation_error(error)
    try:
        result = list_products(query)
    except ProductServiceError as error:
        return _service_error(error)
    return (
        jsonify(
            data=result.data,
            meta={
                "count": len(result.data),
                "total": result.total,
                "limit": result.limit,
                "offset": result.offset,
            },
        ),
        200,
    )


@products_blueprint.get("/<path:external_product_id>")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def products_get(external_product_id: str):
    """Return one validated product by numeric ID or SKU."""
    query = request.args.to_dict(flat=False)
    try:
        reject_query_parameters(query)
        identifier = validate_product_identifier(external_product_id)
    except ProductValidationError as error:
        return _validation_error(error)
    try:
        product = get_product(identifier)
    except ProductServiceError as error:
        return _service_error(error)
    return jsonify(data=product), 200
