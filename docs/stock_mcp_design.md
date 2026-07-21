# Stock MCP Server — Design Document

- **Component:** Stock MCP Server
- **Owner:** Person 2 (Alexander)
- **Framework:** FastMCP + SQLAlchemy 2.0 async + asyncpg
- **Database:** PostgreSQL, dedicated `stock_reader` role (SELECT only on `branches`, `stocks`)
- **Transport:** stdio (production), SSE optional for local debugging
- **Status:** design — not yet implemented

External contracts: `docs/api_contracts.md` §9, §11. DB schema: `docs/database_schema.md`.

---

## 1. Purpose

Read-only stock data access for the AI agent. Exposes 4 MCP tools. Cannot read `users`/`revoked_tokens` tables, cannot write.

```
AI Query Service → Stock MCP Server → PostgreSQL (branches + stocks, SELECT only)
```

---

## 2. Directory Structure

```
stock_mcp_server/
├── server.py              # FastMCP entrypoint + tool definitions
├── db.py                  # Async engine + session factory
├── models.py              # Read-only Branch + Stock SQLAlchemy mappings
├── queries.py             # Query functions per tool
├── shopping.py            # Shopping-list branch-selection algorithm
├── errors.py              # Typed exceptions
├── config.py              # env-based settings
├── health.py              # GET /health (SSE mode only)
├── requirements.txt
└── tests/
    ├── conftest.py
    ├── test_server.py
    ├── test_queries.py
    └── test_shopping.py
```

---

## 3. Database Models (read-only projection)

Mirrors Person 1's schema — not the source of truth. Must stay in sync.

```python
class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[int]              # BIGINT PK
    name: Mapped[str]            # VARCHAR(120) UNIQUE

class Stock(Base):
    __tablename__ = "stocks"
    id: Mapped[int]              # BIGINT PK
    branch_id: Mapped[int]       # FK → branches.id
    external_product_id: Mapped[str]  # VARCHAR(255)
    quantity: Mapped[int]        # INTEGER, DEFAULT 0, CHECK >= 0
```

---

## 4. MCP Tools

### 4.1 `list_branch_stock(branch_id: int) -> dict`

Returns branch name + all items with `quantity > 0`. Branch not found → `BRANCH_NOT_FOUND`. Invalid ID → `INVALID_BRANCH_ID`.

```json
{"status": "success", "data": {
  "branch": {"branch_id": 2, "branch_name": "Toulon"},
  "items": [{"external_product_id": "product-123", "quantity": 8}]
}}
```

### 4.2 `get_stock_for_product(external_product_id: str) -> dict`

Returns all branch-quantity pairs for a product. Empty list = product not stocked anywhere (valid, not an error).

```json
{"status": "success", "data": {
  "external_product_id": "product-123",
  "branches": [{"branch_id": 2, "branch_name": "Toulon", "available_quantity": 8}]
}}
```

### 4.3 `find_branches_with_stock(external_product_id: str, quantity: int) -> dict`

Filters to branches with `available_quantity >= quantity`. Sorted descending by quantity. Invalid quantity → `INVALID_QUANTITY`.

```json
{"status": "success", "data": {
  "external_product_id": "product-123", "requested_quantity": 3,
  "branches": [{"branch_id": 2, "branch_name": "Toulon", "available_quantity": 8}]
}}
```

### 4.4 `find_branches_for_shopping_list(items: list[dict]) -> dict`

Input: `{"items": [{"external_product_id": "...", "quantity": N}, ...]}`

**Algorithm (`shopping.py`):**
1. Validate all items (non-empty ID, positive quantity).
2. Single-branch check: any branch satisfy all items? Pick the one with most total surplus.
3. Multi-branch: try combinations of 2 branches, then 3, ... up to N. `itertools.combinations` in lexicographic order. Greedy assignment: sort items hardest-first, assign to first branch in combo with enough stock.
4. No solution: return `complete: false` with `missing_items`.

**Deterministic:** no randomness, no LLM involvement. Same input → same output always.

```json
// Complete, single branch
{"status": "success", "data": {"complete": true, "strategy": "single_branch",
  "visits": [{"branch_id": 2, "branch_name": "Toulon", "items": [
    {"external_product_id": "product-123", "requested_quantity": 3, "available_quantity": 8}
  ]}], "missing_items": []}}

// Complete, multi-branch
{"status": "success", "data": {"complete": true, "strategy": "multi_branch",
  "visits": [{"branch_id": 2, ...}, {"branch_id": 3, ...}], "missing_items": []}}

// Incomplete
{"status": "success", "data": {"complete": false, "strategy": "unavailable",
  "visits": [], "missing_items": [{"external_product_id": "product-456", "missing_quantity": 2}]}}
```

---

## 5. Database Connection

```python
engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=2)
AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
```

Read-only enforced at DB level: `stock_reader` role has `GRANT SELECT ON branches, stocks` only. No INSERT/UPDATE/DELETE/TRUNCATE. No access to `users` or `revoked_tokens`.

---

## 6. Security

- All queries use SQLAlchemy parameterized queries — no raw SQL, no `execute_sql` tool.
- Returns only: branch IDs/names, external product IDs, quantities.
- Never returns: user data, password hashes, JWT identifiers.

---

## 7. Configuration

| Variable | Required | Default |
|---|---|---|
| `STOCK_MCP_DATABASE_URL` | Yes | — |
| `STOCK_MCP_LOG_LEVEL` | No | `INFO` |
| `STOCK_MCP_TRANSPORT` | No | `stdio` |
| `STOCK_MCP_PORT` | No | `8200` |

---

## 8. Health

SSE mode: `GET /health` → `{"status": "ok", "dependencies": {"database": "ok"}}` or `degraded`.

---

## 9. Docker Compose

```yaml
stock_mcp_server:
  build: ./stock_mcp_server
  environment:
    - STOCK_MCP_DATABASE_URL=postgresql+asyncpg://stock_reader:${STOCK_MCP_DB_PASSWORD}@database:5432/hbntory
  depends_on:
    database:
      condition: service_healthy
```

---

## 10. Dependencies

```
mcp>=1.0.0
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
pydantic>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 11. Coordination With Person 1

| What | Status |
|---|---|
| `branches`/`stocks` SQLAlchemy models | Pending — use own read-only copies until merged |
| DB migrations | Pending |
| `stock_reader` PG role | Pending |
| Seed data | Pending |
| `external_product_id` format: `VARCHAR(255)` | Confirmed |

---

## 12. Definition of Done

- [ ] All 4 tools return contract-conformant responses
- [ ] Shopping-list algorithm is deterministic, minimal-visit, and correct
- [ ] `stock_reader` SELECT-only permissions verified at DB level
- [ ] No access to `users`/`revoked_tokens`, no raw SQL tool
- [ ] Integration tests pass against real PostgreSQL
- [ ] Reviewed by Person 1 or Person 3
