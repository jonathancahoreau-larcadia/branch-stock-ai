"""Calls the Product API — nothing else."""

import httpx


class ProductAPIError(Exception):
    pass


class ProductAPITimeout(ProductAPIError):
    pass


class ProductAPIUnavailable(ProductAPIError):
    pass


class ProductAPIInvalidResponse(ProductAPIError):
    pass


class ProductClient:
    def __init__(self, base_url, timeout=5):
        self.url = base_url.rstrip("/")
        self.timeout = timeout

    async def list_products(self):
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.get(f"{self.url}/products")
            r.raise_for_status()
            return r.json()

    async def get_product(self, pid):
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.get(f"{self.url}/products/{pid}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
