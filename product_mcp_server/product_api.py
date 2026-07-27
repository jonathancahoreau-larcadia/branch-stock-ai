"""Product API adapter for the MCP server.

This module handles asynchronous HTTP calls to the external Product API
and normalizes responses into structured result shapes.
"""

import os
import httpx
from typing import Dict, Any, Optional

# Default timeout in seconds
DEFAULT_TIMEOUT = 10

# Retrieve base URL from environment; raise structured error if missing
PRODUCT_API_BASE_URL = os.environ.get("PRODUCT_API_BASE_URL")
if not PRODUCT_API_BASE_URL:
    raise ValueError("PRODUCT_API_BASE_URL environment variable is required.")


async def list_products() -> Dict[str, Any]:
    """Fetch the list of all products from the external API.

    Returns:
        A structured result dictionary with data or error information.
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(f"{PRODUCT_API_BASE_URL}/products")
            if response.status_code == 200:
                return {"data": response.json()}
            elif response.status_code == 404:
                return {"data": None}
            else:
                return {
                    "error": {
                        "code": "PRODUCT_API_ERROR",
                        "message": f"External API returned status code {response.status_code}",
                    }
                }
        except httpx.TimeoutException:
            return {
                "error": {
                    "code": "TIMEOUT_ERROR",
                    "message": "Timeout while fetching products from external API",
                }
            }
        except httpx.RequestError as e:
            return {
                "error": {
                    "code": "CONNECTION_ERROR",
                    "message": f"Connection error while fetching products: {str(e)}",
                }
            }


async def get_product_details(external_product_id: str) -> Dict[str, Any]:
    """Fetch details for a specific product by ID from the external API.

    Args:
        external_product_id: The unique identifier of the product in the external system.

    Returns:
        A structured result dictionary with data or error information.
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(f"{PRODUCT_API_BASE_URL}/products/{external_product_id}")
            if response.status_code == 200:
                return {"data": response.json()}
            elif response.status_code == 404:
                return {"data": None}
            else:
                return {
                    "error": {
                        "code": "PRODUCT_API_ERROR",
                        "message": f"External API returned status code {response.status_code}",
                    }
                }
        except httpx.TimeoutException:
            return {
                "error": {
                    "code": "TIMEOUT_ERROR",
                    "message": f"Timeout while fetching product details for ID {external_product_id}",
                }
            }
        except httpx.RequestError as e:
            return {
                "error": {
                    "code": "CONNECTION_ERROR",
                    "message": f"Connection error while fetching product details: {str(e)}",
                }
            }
