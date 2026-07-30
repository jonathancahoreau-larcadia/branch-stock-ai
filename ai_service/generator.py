"""Deterministic responses grounded exclusively in validated MCP results."""

from __future__ import annotations

import math as _math
import typing as _typing

from ai_service.classifier import SUPPORTED_QUESTION_TYPES


__all__ = ["SUPPORTED_QUESTION_TYPES", "generate_grounded_response"]

_PARTIAL_ANSWER = (
    "Some MCP information is available, but it is insufficient for a complete "
    "grounded answer."
)
_UNAVAILABLE_RESPONSE = {
    "status": "unavailable",
    "answer": "I do not have enough information to answer this question.",
    "data": {},
}
_EXPECTED_TOOLS = {
    "product_details": ("get_product_details",),
    "product_availability": (
        "get_product_details",
        "get_stock_for_product",
    ),
    "branch_inventory": ("list_products", "list_branch_stock"),
    "shopping_list": (
        "list_products",
        "find_branches_for_shopping_list",
    ),
}


def _is_non_empty_string(value: _typing.Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_integer(value: _typing.Any, *, minimum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= minimum
    )


def _is_number(
    value: _typing.Any, *, minimum: float, maximum: float | None = None
) -> bool:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not _math.isfinite(value)
        or value < minimum
    ):
        return False
    return maximum is None or value <= maximum


def _project_product_details(data: _typing.Any) -> dict[str, _typing.Any] | None:
    if not isinstance(data, dict):
        return None

    external_product_id = data.get("external_product_id")
    name = data.get("name")
    if not _is_non_empty_string(external_product_id) or not _is_non_empty_string(
        name
    ):
        return None

    projection: dict[str, _typing.Any] = {
        "external_product_id": external_product_id,
        "name": name,
    }
    public_fields = {
        "description",
        "category",
        "brand",
        "supplier",
        "unit_price",
        "currency",
        "discontinued",
        "weight_kg",
        "tags",
        "updated_at",
    }
    present_fields = public_fields.intersection(data)
    if not present_fields:
        return projection
    if present_fields != public_fields:
        return None

    supplier = data["supplier"]
    tags = data["tags"]
    if (
        not all(
            _is_non_empty_string(data[field])
            for field in ("description", "category", "brand", "currency")
        )
        or not isinstance(supplier, dict)
        or not all(
            _is_non_empty_string(supplier.get(field))
            for field in ("id", "name", "country")
        )
        or not _is_integer(supplier.get("lead_time_days"), minimum=0)
        or not _is_number(
            supplier.get("reliability_score"), minimum=0, maximum=1
        )
        or not _is_number(data["unit_price"], minimum=0)
        or not isinstance(data["discontinued"], bool)
        or not _is_number(data["weight_kg"], minimum=0)
        or not isinstance(tags, list)
        or not all(_is_non_empty_string(tag) for tag in tags)
        or not _is_non_empty_string(data["updated_at"])
    ):
        return None

    projection.update(
        {
            "description": data["description"],
            "category": data["category"],
            "brand": data["brand"],
            "supplier": {
                "id": supplier["id"],
                "name": supplier["name"],
                "country": supplier["country"],
                "lead_time_days": supplier["lead_time_days"],
                "reliability_score": supplier["reliability_score"],
            },
            "unit_price": data["unit_price"],
            "currency": data["currency"],
            "discontinued": data["discontinued"],
            "weight_kg": data["weight_kg"],
            "tags": list(tags),
            "updated_at": data["updated_at"],
        }
    )
    return projection


def _project_list_products(data: _typing.Any) -> dict[str, _typing.Any] | None:
    if not isinstance(data, dict):
        return None

    products = data.get("products")
    if not isinstance(products, list):
        return None

    projected_products = []
    for product in products:
        if not isinstance(product, dict):
            return None
        external_product_id = product.get("external_product_id")
        name = product.get("name")
        if not _is_non_empty_string(
            external_product_id
        ) or not _is_non_empty_string(name):
            return None
        projected_products.append(
            {
                "external_product_id": external_product_id,
                "name": name,
            }
        )

    return {"products": projected_products}


def _project_product_stock(data: _typing.Any) -> dict[str, _typing.Any] | None:
    if not isinstance(data, dict):
        return None

    external_product_id = data.get("external_product_id")
    branches = data.get("branches")
    if not _is_non_empty_string(external_product_id) or not isinstance(
        branches, list
    ):
        return None

    projected_branches = []
    for branch in branches:
        if not isinstance(branch, dict):
            return None
        branch_id = branch.get("branch_id")
        branch_name = branch.get("branch_name")
        quantity = branch.get("quantity")
        if (
            not _is_integer(branch_id, minimum=1)
            or not _is_non_empty_string(branch_name)
            or not _is_integer(quantity, minimum=0)
        ):
            return None
        if quantity > 0:
            projected_branches.append(
                {
                    "branch_id": branch_id,
                    "branch_name": branch_name,
                    "quantity": quantity,
                }
            )

    return {
        "external_product_id": external_product_id,
        "branches": projected_branches,
    }


def _project_branch_stock(data: _typing.Any) -> dict[str, _typing.Any] | None:
    if not isinstance(data, dict):
        return None

    branch_id = data.get("branch_id")
    branch_name = data.get("branch_name")
    stocks = data.get("stocks")
    if (
        not _is_integer(branch_id, minimum=1)
        or not _is_non_empty_string(branch_name)
        or not isinstance(stocks, list)
    ):
        return None

    projected_stocks = []
    for stock in stocks:
        if not isinstance(stock, dict):
            return None
        external_product_id = stock.get("external_product_id")
        quantity = stock.get("quantity")
        if not _is_non_empty_string(external_product_id) or not _is_integer(
            quantity, minimum=1
        ):
            return None
        projected_stocks.append(
            {
                "external_product_id": external_product_id,
                "quantity": quantity,
            }
        )

    return {
        "branch_id": branch_id,
        "branch_name": branch_name,
        "stocks": projected_stocks,
    }


def _project_shopping_item(
    item: _typing.Any,
) -> dict[str, _typing.Any] | None:
    if not isinstance(item, dict):
        return None

    external_product_id = item.get("external_product_id")
    requested_quantity = item.get("requested_quantity")
    available_quantity = item.get("available_quantity")
    if (
        not _is_non_empty_string(external_product_id)
        or not _is_integer(requested_quantity, minimum=1)
        or not _is_integer(available_quantity, minimum=1)
        or available_quantity < requested_quantity
    ):
        return None

    return {
        "external_product_id": external_product_id,
        "requested_quantity": requested_quantity,
        "available_quantity": available_quantity,
    }


def _project_shopping_visit(
    visit: _typing.Any,
) -> dict[str, _typing.Any] | None:
    if not isinstance(visit, dict):
        return None

    branch_id = visit.get("branch_id")
    branch_name = visit.get("branch_name")
    items = visit.get("items")
    if (
        not _is_integer(branch_id, minimum=1)
        or not _is_non_empty_string(branch_name)
        or not isinstance(items, list)
        or not items
    ):
        return None

    projected_items = []
    for item in items:
        projected_item = _project_shopping_item(item)
        if projected_item is None:
            return None
        projected_items.append(projected_item)

    return {
        "branch_id": branch_id,
        "branch_name": branch_name,
        "items": projected_items,
    }


def _project_missing_item(
    item: _typing.Any,
) -> dict[str, _typing.Any] | None:
    if not isinstance(item, dict):
        return None

    external_product_id = item.get("external_product_id")
    missing_quantity = item.get("missing_quantity")
    if not _is_non_empty_string(external_product_id) or not _is_integer(
        missing_quantity, minimum=1
    ):
        return None

    return {
        "external_product_id": external_product_id,
        "missing_quantity": missing_quantity,
    }


def _project_shopping_plan(data: _typing.Any) -> dict[str, _typing.Any] | None:
    if not isinstance(data, dict):
        return None

    complete = data.get("complete")
    strategy = data.get("strategy")
    visits = data.get("visits")
    missing_items = data.get("missing_items")
    if (
        not isinstance(complete, bool)
        or not isinstance(strategy, str)
        or strategy
        not in ("single_branch", "multiple_branches", "unavailable")
        or not isinstance(visits, list)
        or not isinstance(missing_items, list)
    ):
        return None

    projected_visits = []
    for visit in visits:
        projected_visit = _project_shopping_visit(visit)
        if projected_visit is None:
            return None
        projected_visits.append(projected_visit)

    projected_missing_items = []
    for item in missing_items:
        projected_item = _project_missing_item(item)
        if projected_item is None:
            return None
        projected_missing_items.append(projected_item)

    if complete:
        coherent = (
            not projected_missing_items
            and (
                (strategy == "single_branch" and len(projected_visits) == 1)
                or (
                    strategy == "multiple_branches"
                    and len(projected_visits) >= 2
                )
            )
        )
    else:
        coherent = (
            strategy == "unavailable"
            and not projected_visits
            and bool(projected_missing_items)
        )
    if not coherent:
        return None

    return {
        "complete": complete,
        "strategy": strategy,
        "visits": projected_visits,
        "missing_items": projected_missing_items,
    }


_PROJECTORS = {
    "get_product_details": _project_product_details,
    "list_products": _project_list_products,
    "get_stock_for_product": _project_product_stock,
    "list_branch_stock": _project_branch_stock,
    "find_branches_for_shopping_list": _project_shopping_plan,
}


def _project_successful_result(
    result: _typing.Any,
    projector: _typing.Callable[
        [_typing.Any], dict[str, _typing.Any] | None
    ],
) -> dict[str, _typing.Any] | None:
    if not isinstance(result, dict) or result.get("status") != "success":
        return None
    return projector(result.get("data"))


def _product_details_answer(tool_results: dict[str, dict[str, _typing.Any]]) -> str:
    product = tool_results["get_product_details"]
    answer = (
        f"Product {product['name']} has identifier "
        f"{product['external_product_id']}."
    )
    if "description" not in product:
        return answer
    supplier = product["supplier"]
    return (
        f"{answer} Category: {product['category']}; brand: {product['brand']}; "
        f"supplier: {supplier['name']}; price: {product['unit_price']} "
        f"{product['currency']}. Description: {product['description']}"
    )


def _product_availability_answer(
    tool_results: dict[str, dict[str, _typing.Any]],
) -> str:
    product = tool_results["get_product_details"]
    branches = tool_results["get_stock_for_product"]["branches"]
    product_label = f"{product['name']} ({product['external_product_id']})"
    if not branches:
        return f"{product_label} has no stock in the projected branches."

    branch_summaries = [
        f"{branch['branch_name']}: quantity {branch['quantity']}"
        for branch in branches
    ]
    return f"Stock for {product_label}: {'; '.join(branch_summaries)}."


def _branch_inventory_answer(
    tool_results: dict[str, dict[str, _typing.Any]],
) -> str:
    products = tool_results["list_products"]["products"]
    branch_stock = tool_results["list_branch_stock"]
    stocks = branch_stock["stocks"]
    if not stocks:
        return (
            f"{branch_stock['branch_name']} has no stock in the projected "
            "inventory."
        )

    product_names = {
        product["external_product_id"]: product["name"] for product in products
    }
    stock_summaries = []
    for stock in stocks:
        external_product_id = stock["external_product_id"]
        name = product_names.get(external_product_id)
        product_label = (
            f"{name} ({external_product_id})" if name else external_product_id
        )
        stock_summaries.append(
            f"{product_label}: quantity {stock['quantity']}"
        )
    return (
        f"Stock at {branch_stock['branch_name']}: "
        f"{'; '.join(stock_summaries)}."
    )


def _shopping_success_answer(
    tool_results: dict[str, dict[str, _typing.Any]],
) -> str:
    plan = tool_results["find_branches_for_shopping_list"]
    visit_summaries = []
    for visit in plan["visits"]:
        item_summaries = [
            (
                f"{item['external_product_id']} requested "
                f"{item['requested_quantity']}, available "
                f"{item['available_quantity']}"
            )
            for item in visit["items"]
        ]
        visit_summaries.append(
            f"{visit['branch_name']}: {', '.join(item_summaries)}"
        )
    return (
        f"The shopping plan is complete with strategy {plan['strategy']}. "
        f"Visits: {'; '.join(visit_summaries)}."
    )


def _shopping_incomplete_answer(
    tool_results: dict[str, dict[str, _typing.Any]],
) -> str:
    plan = tool_results["find_branches_for_shopping_list"]
    missing_summaries = [
        f"{item['external_product_id']}: quantity {item['missing_quantity']}"
        for item in plan["missing_items"]
    ]
    return (
        f"The shopping plan uses strategy {plan['strategy']}. "
        f"Missing items: {'; '.join(missing_summaries)}."
    )


def _standard_response(
    status: str,
    answer: str,
    question_type: str,
    tool_results: dict[str, dict[str, _typing.Any]],
) -> dict[str, _typing.Any]:
    return {
        "status": status,
        "answer": answer,
        "data": {
            "question_type": question_type,
            "tool_results": tool_results,
        },
    }


def generate_grounded_response(
    question_type: str,
    mcp_results: dict[str, dict[str, _typing.Any]],
) -> dict[str, _typing.Any]:
    """Generate a deterministic response from validated MCP envelopes."""
    if not isinstance(question_type, str) or question_type not in (
        *SUPPORTED_QUESTION_TYPES,
        "unsupported",
    ):
        raise ValueError("question_type is not supported")
    if not isinstance(mcp_results, dict):
        raise ValueError("mcp_results must be a dictionary")

    if question_type == "unsupported":
        if mcp_results:
            raise ValueError("unsupported questions cannot have MCP results")
        return {
            "status": "unsupported",
            "answer": "This question is outside the supported inventory scope.",
            "data": {
                "supported_question_types": list(SUPPORTED_QUESTION_TYPES),
            },
        }

    expected_tools = _EXPECTED_TOOLS[question_type]
    for tool_name in mcp_results:
        if not isinstance(tool_name, str) or tool_name not in expected_tools:
            raise ValueError("mcp_results contains an unexpected tool")

    tool_results = {}
    for tool_name in expected_tools:
        if tool_name not in mcp_results:
            continue
        projection = _project_successful_result(
            mcp_results[tool_name], _PROJECTORS[tool_name]
        )
        if projection is not None:
            tool_results[tool_name] = projection

    if question_type == "product_availability" and set(tool_results) == set(
        expected_tools
    ):
        product_id = tool_results["get_product_details"][
            "external_product_id"
        ]
        stock_product_id = tool_results["get_stock_for_product"][
            "external_product_id"
        ]
        if product_id != stock_product_id:
            del tool_results["get_stock_for_product"]
            product = tool_results["get_product_details"]
            tool_results["get_product_details"] = {
                "external_product_id": product["external_product_id"],
                "name": product["name"],
            }

    if not tool_results:
        return {
            "status": _UNAVAILABLE_RESPONSE["status"],
            "answer": _UNAVAILABLE_RESPONSE["answer"],
            "data": {},
        }

    if len(tool_results) != len(expected_tools):
        return _standard_response(
            "partial", _PARTIAL_ANSWER, question_type, tool_results
        )

    if question_type == "shopping_list":
        plan = tool_results["find_branches_for_shopping_list"]
        if not plan["complete"]:
            return _standard_response(
                "partial",
                _shopping_incomplete_answer(tool_results),
                question_type,
                tool_results,
            )
        answer = _shopping_success_answer(tool_results)
    elif question_type == "product_details":
        answer = _product_details_answer(tool_results)
    elif question_type == "product_availability":
        answer = _product_availability_answer(tool_results)
    else:
        answer = _branch_inventory_answer(tool_results)

    return _standard_response("success", answer, question_type, tool_results)


def localize_grounded_response(
    response: dict[str, _typing.Any], language: str
) -> dict[str, _typing.Any]:
    """Return a deterministic French narrative over an already-grounded response."""
    if language != "fr":
        return response

    status = response.get("status")
    if status == "unsupported":
        return {
            **response,
            "answer": (
                "Cette question ne fait pas partie du périmètre d’inventaire "
                "pris en charge."
            ),
        }
    if status == "unavailable":
        return {
            **response,
            "answer": (
                "Je ne dispose pas d’assez d’informations pour répondre à "
                "cette question."
            ),
        }
    if status == "partial":
        return {
            **response,
            "answer": (
                "Certaines informations MCP sont disponibles, mais elles ne "
                "suffisent pas pour fournir une réponse complète et vérifiable."
            ),
        }
    if status != "success":
        return response

    data = response.get("data")
    if not isinstance(data, dict):
        return response
    question_type = data.get("question_type")
    tool_results = data.get("tool_results")
    if not isinstance(tool_results, dict):
        return response

    if question_type == "product_details":
        product = tool_results["get_product_details"]
        answer = (
            f"Le produit {product['name']} porte l’identifiant "
            f"{product['external_product_id']}."
        )
        if "description" in product:
            answer = (
                f"{answer} Catégorie : {product['category']} ; marque : "
                f"{product['brand']} ; fournisseur : "
                f"{product['supplier']['name']} ; prix : "
                f"{product['unit_price']} {product['currency']}. "
                f"Description : {product['description']}"
            )
    elif question_type == "product_availability":
        product = tool_results["get_product_details"]
        branches = tool_results["get_stock_for_product"]["branches"]
        product_label = f"{product['name']} ({product['external_product_id']})"
        if not branches:
            answer = (
                f"Le produit {product_label} n’est disponible dans aucune "
                "succursale."
            )
        else:
            summaries = [
                f"{branch['branch_name']} : quantité {branch['quantity']}"
                for branch in branches
            ]
            answer = f"Stock du produit {product_label} : {' ; '.join(summaries)}."
    elif question_type == "branch_inventory":
        products = tool_results["list_products"]["products"]
        branch = tool_results["list_branch_stock"]
        names = {
            product["external_product_id"]: product["name"]
            for product in products
        }
        if not branch["stocks"]:
            answer = (
                f"La succursale {branch['branch_name']} ne possède aucun "
                "stock dans l’inventaire projeté."
            )
        else:
            summaries = []
            for stock in branch["stocks"]:
                external_id = stock["external_product_id"]
                label = (
                    f"{names[external_id]} ({external_id})"
                    if external_id in names
                    else external_id
                )
                summaries.append(f"{label} : quantité {stock['quantity']}")
            answer = (
                f"Stock de la succursale {branch['branch_name']} : "
                f"{' ; '.join(summaries)}."
            )
    elif question_type == "shopping_list":
        plan = tool_results["find_branches_for_shopping_list"]
        visits = []
        for visit in plan["visits"]:
            items = [
                (
                    f"{item['external_product_id']} demandé "
                    f"{item['requested_quantity']}, disponible "
                    f"{item['available_quantity']}"
                )
                for item in visit["items"]
            ]
            visits.append(f"{visit['branch_name']} : {', '.join(items)}")
        answer = (
            f"Le plan d’achat est complet avec la stratégie "
            f"{plan['strategy']}. Visites : {' ; '.join(visits)}."
        )
    else:
        return response
    return {**response, "answer": answer}
