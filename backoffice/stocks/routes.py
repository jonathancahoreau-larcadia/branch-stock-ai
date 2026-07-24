"""Authenticated HTTP routes for current-branch stock management."""

from collections.abc import Callable
from typing import Any

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import BadRequest

from backoffice.api_errors import error_response
from backoffice.auth.decorators import (
    current_user,
    protected_token_required,
)
from backoffice.database.models import ACCESS_TOKEN_TYPE
from backoffice.products.services import ProductServiceError

from .schemas import (
    InvalidQuantityError,
    StockValidationError,
    reject_query_parameters,
    validate_external_product_id,
    validate_list_filters,
    validate_movement_payload,
)
from .services import (
    StockServiceError,
    add_stock,
    authorize_stock_user,
    get_stock,
    list_stocks,
    remove_stock,
    serialize_stock_detail,
    serialize_stock_list,
)

stocks_blueprint = Blueprint("stocks", __name__, url_prefix="/api/v1/stocks")


def _validation_error(error: StockValidationError):
    return error_response(
        "VALIDATION_ERROR",
        400,
        details=error.details,
    )


def _validated_identifier(identifier: str):
    try:
        return validate_external_product_id(identifier), None
    except StockValidationError as error:
        return None, _validation_error(error)


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
    except InvalidQuantityError as error:
        return (
            None,
            error_response(
                "INVALID_QUANTITY",
                422,
                details=error.details,
            ),
        )
    except StockValidationError as error:
        return None, _validation_error(error)


def _service_error(error: StockServiceError | ProductServiceError):
    return error_response(error.code, error.status)


def _authorized_user():
    user = current_user()
    try:
        authorize_stock_user(user)
    except StockServiceError as error:
        return None, _service_error(error)
    return user, None


@stocks_blueprint.get("")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def stocks_list():
    """List current-branch stock with strict availability filtering."""
    user, authorization_error = _authorized_user()
    if authorization_error is not None:
        return authorization_error
    try:
        filters = validate_list_filters(request.args.to_dict(flat=False))
        result = list_stocks(user, filters)
    except StockValidationError as error:
        return _validation_error(error)
    except (StockServiceError, ProductServiceError) as error:
        return _service_error(error)
    return (
        jsonify(
            data=serialize_stock_list(result),
            meta={"count": len(result.items)},
        ),
        200,
    )


@stocks_blueprint.get("/<external_product_id>")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def stocks_get(external_product_id: str):
    """Return one current-branch quantity, including zero."""
    user, authorization_error = _authorized_user()
    if authorization_error is not None:
        return authorization_error
    try:
        reject_query_parameters(request.args.to_dict(flat=False))
    except StockValidationError as error:
        return _validation_error(error)
    identifier, validation_error = _validated_identifier(
        external_product_id
    )
    if validation_error is not None:
        return validation_error
    try:
        result = get_stock(user, identifier)
    except (StockServiceError, ProductServiceError) as error:
        return _service_error(error)
    return jsonify(data=serialize_stock_detail(result)), 200


def _movement(
    external_product_id: str,
    operation: Callable[..., Any],
):
    user, authorization_error = _authorized_user()
    if authorization_error is not None:
        return authorization_error
    try:
        reject_query_parameters(request.args.to_dict(flat=False))
    except StockValidationError as error:
        return _validation_error(error)
    identifier, validation_error = _validated_identifier(
        external_product_id
    )
    if validation_error is not None:
        return validation_error
    data, validation_error = _validated_json(validate_movement_payload)
    if validation_error is not None:
        return validation_error
    try:
        result = operation(user, identifier, data)
    except (StockServiceError, ProductServiceError) as error:
        return _service_error(error)
    return jsonify(data=serialize_stock_detail(result)), 200


@stocks_blueprint.post("/<external_product_id>/add")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def stocks_add(external_product_id: str):
    """Create or atomically increment one current-branch stock row."""
    return _movement(external_product_id, add_stock)


@stocks_blueprint.post("/<external_product_id>/remove")
@protected_token_required(token_type=ACCESS_TOKEN_TYPE)
def stocks_remove(external_product_id: str):
    """Lock and decrement one current-branch stock row."""
    return _movement(external_product_id, remove_stock)
