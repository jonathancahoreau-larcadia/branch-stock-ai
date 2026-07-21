# Product MCP Server — Design Document

- **Component:** Product MCP Server
- **Owner:** Person 2 (Alexander)
- **Framework:** FastMCP + httpx (async)
- **Transport:** stdio (production), SSE optional for local debugging
- **Status:** design — not yet implemented

External contracts: `docs/api_contracts.md` §9–10.

---

## 1. Purpose

Bridge between the AI agent and the external Product API. Exposes 2 read-only MCP tools. No PostgreSQL access, no local caching of product data.

```
AI Query Service → Product MCP Server → External Product API (Docker)
```

---

## 2. Directory Structure

```
product_mcp_server/
├── server.py              # FastMCP entrypoint + tool definitions
├── product_client.py      # httpx async client → Product API
├── models.py              # Pydantic models for API responses
├── errors.py              # Typed exceptions
├── config.py              # env-based settings
├── health.py              # GET /health (SSE mode only)
├── requirements.txt
└── tests/
    ├── conftest.py
    ├── test_server.py
    └── test_product_client.py
```

---

## 3. MCP Tools

### 3.1 `list_products() -> dict`

Calls `GET {PRODUCT_API_BASE_URL}/products`. Empty list is valid (not an error).

```json
// Success
{"status": "success", "data": {"products": [{"external_product_id": "...", "name": "..."}]}}

// Errors
{"status": "error", "error": {"code": "PRODUCT_API_UNAVAILABLE", "message": "..."}}
{"status": "error", "error": {"code": "PRODUCT_API_TIMEOUT", "message": "..."}}
{"status": "error", "error": {"code": "PRODUCT_API_ERROR", "message": "..."}}
{"status": "error", "error": {"code": "PRODUCT_API_INVALID_RESPONSE", "message": "..."}}
```

### 3.2 `get_product_details(external_product_id: str) -> dict`

Validates ID is non-empty, then calls `GET {PRODUCT_API_BASE_URL}/products/{id}`. Returns `not_found` for 404.

```json
// Success
{"status": "success", "data": {"external_product_id": "...", "name": "...", "description": "...", "price": 12.99}}

// Not found (product doesn't exist)
{"status": "not_found", "data": null}

// Validation
{"status": "error", "error": {"code": "INVALID_EXTERNAL_PRODUCT_ID", "message": "..."}}
```

---

## 4. Product Client (`product_client.py`)

```python
class ProductClient:
    def __init__(self, base_url: str, timeout: float = 5.0): ...
    async def list_products(self) -> list[dict]: ...
    async def get_product(self, external_product_id: str) -> dict: ...
```

**Retry policy:** max 2 retries on timeout + 5xx (exponential backoff 1s/2s). 4xx never retried. All GETs are idempotent.

**Exceptions:** `ProductAPIError`, `ProductAPITimeout`, `ProductAPIUnavailable`, `ProductAPIInvalidResponse` — caught by tools and mapped to structured error responses.

---

## 5. Configuration

| Variable | Required | Default |
|---|---|---|
| `PRODUCT_API_BASE_URL` | Yes | — |
| `PRODUCT_API_TIMEOUT` | No | `5` |
| `PRODUCT_MCP_LOG_LEVEL` | No | `INFO` |
| `PRODUCT_MCP_TRANSPORT` | No | `stdio` |
| `PRODUCT_MCP_PORT` | No | `8100` |

---

## 6. Health

SSE mode only (`GET /health`). Returns `{"status": "ok", "dependencies": {"product_api": "ok"}}` or `degraded`. In stdio mode Docker monitors the process directly.

---

## 7. Logging

Per tool call: tool name, duration, status, error code. Never logged: full API responses, keys, connection strings.

---

## 8. Docker Compose

```yaml
product_mcp_server:
  build: ./product_mcp_server
  environment:
    - PRODUCT_API_BASE_URL=http://product_api:8080
    - PRODUCT_API_TIMEOUT=5
  depends_on:
    product_api:
      condition: service_healthy
```

---

## 9. Dependencies

```
mcp>=1.0.0
httpx>=0.27.0
pydantic>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 10. Definition of Done

- [ ] `list_products` returns structured results from real Product API
- [ ] `get_product_details` handles found, not-found, and all error states
- [ ] Timeouts and retries work correctly
- [ ] No product data stored locally
- [ ] Health endpoint reports Product API status
- [ ] Tests pass with real Product API container
- [ ] MCP Inspector session demonstrates both tools
- [ ] Reviewed by Person 1 or Person 3
