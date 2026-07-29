"""Product MCP server package for the HBntory project.

This package exposes the two mandatory product tool functions:
list_products and get_product_details, which interface with the
external Product API and return structured results.
"""

from .tools import list_products, get_product_details

__all__ = ["list_products", "get_product_details"]
