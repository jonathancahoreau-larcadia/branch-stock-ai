"""Product MCP tools for the HBntory project.

This module exposes the two mandatory product tool functions:
list_products and get_product_details, which interface with the
external Product API and return structured results.
"""

from .product_api import list_products as api_list_products, get_product_details as api_get_product_details


async def list_products():
    """Fetch the list of all products from the external API.

    Returns:
        A structured result dictionary with data or error information.
    """
    return await api_list_products()


async def get_product_details(external_product_id: str):
    """Fetch details for a specific product by ID from the external API.

    Args:
        external_product_id: The unique identifier of the product in the external system.

    Returns:
        A structured result dictionary with data or error information.
    """
    return await api_get_product_details(external_product_id)
