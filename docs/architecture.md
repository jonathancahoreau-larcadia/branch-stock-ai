# HBntory — System Architecture

## 1. Document Status

- **Project:** HBntory — Inventory Management Platform
- **Team size:** 3
- **Architecture style:** service-oriented system with a modular monolithic Backoffice
- **Status:** approved baseline after review of Tasks 0–8
- **Last updated:** July 2026

This document defines service boundaries, communication flows, technical decisions, trade-offs, MVP scope, and integration rules.

---

## 2. Architecture Goals

The architecture must:

- satisfy every mandatory functional requirement;
- keep product details outside the local database;
- enforce user and branch permissions in backend code;
- provide controlled read-only data access to the AI agent;
- let three team members work in parallel;
- remain realistic for the project timeframe;
- start through one Docker Compose command.

---

## 3. System Diagram

```mermaid
flowchart LR
    BO_USER[Admin or Common User]
    BO_UI[Backoffice HTML/CSS/JS]
    BO_API[Flask Backoffice REST API]
    DB[(PostgreSQL)]
    PRODUCT_API[External Product API<br/>Read-only container]

    PUBLIC_USER[Anonymous Visitor]
    CLIENT[Client Web Interface]
    AI[Flask AI Query Service]
    PRODUCT_MCP[Product MCP Server]
    STOCK_MCP[Stock MCP Server<br/>Read-only]

    BO_USER --> BO_UI
    BO_UI -->|REST + JWT Bearer| BO_API
    BO_API -->|SQLAlchemy| DB
    BO_API -->|HTTP REST| PRODUCT_API

    PUBLIC_USER --> CLIENT
    CLIENT -->|POST /questions| AI
    AI -->|MCP over internal network| PRODUCT_MCP
    AI -->|MCP over internal network| STOCK_MCP
    PRODUCT_MCP -->|HTTP REST| PRODUCT_API
    STOCK_MCP -->|SELECT only| DB
```

---

## 4. Component Responsibilities

### 4.1 Backoffice Interface

Responsibilities:

- display the login form;
- store JWTs in `sessionStorage` for the MVP;
- add the access token to protected API requests;
- refresh the access token when required;
- display the current user's branch clearly;
- provide stock screens for common users;
- provide user-management screens for the administrator;
- hide irrelevant actions without treating hiding as authorization.

Restrictions:

- no direct database access;
- no authorization decisions trusted by the backend;
- no storage of product details.

### 4.2 Backoffice Service

Technology:

```text
Python + Flask + SQLAlchemy
```

Responsibilities:

- expose REST endpoints;
- authenticate users;
- issue and validate JWTs;
- hash and verify passwords with bcrypt;
- enforce roles and branch scope;
- manage common users;
- manage stock transactions;
- call the Product API;
- expose health information;
- return stable JSON errors.

Architecture:

```text
modular monolith
```

Modules:

```text
auth
users
branches
stocks
products
database
```

### 4.3 PostgreSQL

Stores:

- users;
- branches;
- stock records;
- revoked JWT identifiers.

It is the source of truth for:

- current account state;
- current role;
- current branch assignment;
- stock quantities.

It is not the source of truth for product details.

### 4.4 External Product API

Responsibilities:

- list products;
- return product details by identifier.

It is read-only and is the source of truth for product information.

### 4.5 Product MCP Server

Responsibilities:

- expose `list_products`;
- expose `get_product_details`;
- normalize Product API responses;
- return clear errors.

It does not access PostgreSQL.

### 4.6 Stock MCP Server

Responsibilities:

- expose controlled stock-query tools;
- read branch and stock data;
- solve the shopping-list branch-selection problem deterministically.

It uses a dedicated PostgreSQL read-only account.

It cannot access:

- `users.password_hash`;
- `users.token_version`;
- `revoked_tokens`;
- private employee data;
- write operations.

### 4.7 AI Query Service

Technology:

```text
Python + Flask
```

Responsibilities:

- expose `POST /questions`;
- classify supported question types;
- invoke MCP tools;
- combine structured results;
- generate grounded responses;
- expose tool-call information for debugging;
- reject unsupported requests clearly.

It has no direct PostgreSQL credentials.

### 4.8 Client Web Interface

Responsibilities:

- accept an anonymous question;
- send it to the AI Query Service;
- show loading feedback;
- display the response;
- display clear technical errors.

It stores no conversation history.

---

## 5. Architecture Decisions

### ADR-001 — Backoffice REST API and Lightweight Frontend

**Selected option:** Flask REST API + HTML/CSS/JavaScript.

**Benefit:** compatible with JWT Bearer headers and easy API testing.

**Trade-off:** requires frontend JavaScript and explicit token lifecycle management.

**Rejected option:** full Server-Side Rendering, because standard page navigation cannot attach the selected JWT Bearer header reliably.

### ADR-002 — REST for the Public Client

**Selected option:** `POST /questions`.

**Benefit:** each question is independent and maps cleanly to one HTTP request.

**Trade-off:** no streaming or persistent connection.

### ADR-003 — PostgreSQL

**Selected option:** PostgreSQL in development, integration tests, and Docker Compose.

**Benefit:** reliable relational constraints, transactions, locking, partial indexes, and production-like integration tests.

**Trade-off:** heavier setup than SQLite.

### ADR-004 — JWT Bearer Authentication

**Selected option:**

```text
Access token: 30 minutes
Refresh token: 7 days
Transport: Authorization header
Frontend storage: sessionStorage
Revocation: PostgreSQL blocklist
```

**Benefit:** explicit stateless-style API authentication and reduced classic cookie-based CSRF exposure.

**Trade-off:** XSS can expose JavaScript-readable tokens, and revocation adds database state.

### ADR-005 — bcrypt

**Selected option:** bcrypt for password hashing.

**Benefit:** salted, intentionally slow, and designed for password storage.

**Trade-off:** authentication consumes more CPU than a general-purpose fast hash, which is intentional.

### ADR-006 — Custom Stock MCP

**Selected option:** custom Stock MCP with a read-only PostgreSQL account.

**Benefit:** least privilege and no arbitrary SQL supplied by the agent.

**Trade-off:** the team must implement each required query.

### ADR-007 — Deterministic Shopping-List Tool

**Selected option:** the Stock MCP computes the branch plan.

**Benefit:** stock selection is reproducible and based on data, not language-model guesses.

**Trade-off:** additional backend logic and tests are required.

### ADR-008 — No Local Product Table

**Selected option:** store only `external_product_id` in stock records.

**Benefit:** respects the external Product API as the single source of truth.

**Trade-off:** product display depends on Product API availability.

---

## 6. Backoffice Internal Structure

```text
backoffice/
├── app.py
├── config.py
├── extensions.py
├── auth/
│   ├── routes.py
│   ├── services.py
│   ├── decorators.py
│   └── schemas.py
├── users/
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   └── repositories.py
├── branches/
│   ├── models.py
│   ├── routes.py
│   └── repositories.py
├── stocks/
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   └── repositories.py
├── products/
│   ├── client.py
│   └── services.py
├── database/
│   ├── models.py
│   ├── seed.py
│   └── migrations/
├── static/
├── templates/
└── tests/
```

Layer responsibilities:

- **routes:** HTTP parsing and response mapping;
- **services:** business rules, authorization, and transactions;
- **repositories:** SQLAlchemy queries;
- **models:** schema mapping and database constraints;
- **product client:** Product API calls and error normalization.

---

## 7. Authentication Flow

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Backoffice UI
    participant API as Backoffice API
    participant DB as PostgreSQL

    U->>UI: Submit username and password
    UI->>API: POST /api/v1/auth/login
    API->>DB: Load active user
    DB-->>API: User and bcrypt hash
    API->>API: Verify password
    API-->>UI: Access token + refresh token
    UI->>UI: Save tokens in sessionStorage
    UI->>API: Protected request with Bearer access token
    API->>DB: Verify blocklist and current user state
    DB-->>API: Current role, branch, token_version
    API-->>UI: Authorized response
```

Token claims:

```text
sub
jti
type
iat
exp
token_version
```

The backend uses `sub` to reload the user and does not trust an old role or branch claim as the current source of truth.

---

## 8. Token Refresh and Revocation

### Refresh

1. the access token expires;
2. the frontend sends the refresh token to `/api/v1/auth/refresh`;
3. the backend verifies signature, type, expiration, blocklist, user status, and `token_version`;
4. a new 30-minute access token is returned.

### Logout

The frontend revokes:

1. the current access token;
2. the refresh token.

Only their `jti` values are stored.

### Password Change

When an administrator changes a user's password:

1. the password is re-hashed;
2. `users.token_version` is incremented;
3. all previously issued access and refresh tokens fail future validation.

---

## 9. Stock Write Flow

### 9.1 Addition

```mermaid
sequenceDiagram
    actor U as Common User
    participant UI as Backoffice UI
    participant API as Backoffice API
    participant PRODUCT as Product API
    participant DB as PostgreSQL

    U->>UI: Select product and enter positive quantity
    UI->>API: POST /stocks/{external_product_id}/add
    API->>DB: Load current user and branch
    API->>PRODUCT: Verify product exists
    PRODUCT-->>API: Product found
    API->>DB: Transaction and row lock/upsert
    DB-->>API: Updated stock
    API-->>UI: Updated quantity
```

The network call occurs before the stock transaction to avoid holding database locks during a slow external request.

### 9.2 Removal

```mermaid
sequenceDiagram
    actor U as Common User
    participant UI as Backoffice UI
    participant API as Backoffice API
    participant DB as PostgreSQL

    U->>UI: Enter positive quantity
    UI->>API: POST /stocks/{external_product_id}/remove
    API->>DB: Load current user and branch
    API->>DB: SELECT stock FOR UPDATE
    API->>API: Verify sufficient quantity
    API->>DB: Update and commit
    API-->>UI: Updated quantity or error
```

---

## 10. AI Query Flow

```mermaid
sequenceDiagram
    actor V as Anonymous Visitor
    participant UI as Client Web Interface
    participant AI as AI Query Service
    participant PMCP as Product MCP
    participant SMCP as Stock MCP
    participant PRODUCT as Product API
    participant DB as PostgreSQL

    V->>UI: Ask a question
    UI->>AI: POST /questions
    AI->>AI: Classify supported question type
    AI->>PMCP: Product tool call
    PMCP->>PRODUCT: Read product data
    PRODUCT-->>PMCP: Product response
    PMCP-->>AI: Structured product data
    AI->>SMCP: Controlled stock tool call
    SMCP->>DB: Read-only query
    DB-->>SMCP: Stock data
    SMCP-->>AI: Structured stock result
    AI-->>UI: Grounded answer
```

Tool-call logs include:

- request correlation ID;
- tool name;
- duration;
- success or error code.

They exclude:

- prompts containing unnecessary private data;
- credentials;
- JWT values;
- database connection strings.

---

## 11. Supported AI Question Types

| Type | Product tools | Stock tools |
|---|---|---|
| Product details | `get_product_details` | None |
| Product availability across branches | Product lookup | `get_stock_for_product` |
| Products available in a branch | Product listing/details | `list_branch_stock` |
| Shopping list | Product validation | `find_branches_for_shopping_list` |

An unsupported request returns `status: "unsupported"`.

---

## 12. Shopping-List Strategy

Input:

```json
{
  "items": [
    {
      "external_product_id": "product-123",
      "quantity": 3
    }
  ]
}
```

Algorithm:

1. validate all quantities;
2. search for branches satisfying every item;
3. if one or more exist, select a deterministic best branch;
4. otherwise evaluate branch combinations in increasing number of visits;
5. return the first complete minimal-visit solution;
6. return missing quantities when no complete solution exists.

The model explains the structured result but does not calculate stock availability itself.

---

## 13. Database Access Boundaries

### Backoffice database account

May read and write required application tables.

It is not a PostgreSQL superuser.

### Migration account or process

May modify the schema through Alembic migrations.

### Stock MCP account

May run `SELECT` queries only on:

- branches;
- stocks.

It has no permission on:

- password hashes;
- revoked tokens;
- schema modification;
- inserts, updates, or deletes.

---

## 14. Initialization

The initialization command:

1. runs migrations;
2. creates the `admin` account if absent;
3. creates at least two branches if absent;
4. validates sample external product identifiers through the Product API;
5. inserts sample stock in one transaction;
6. can be run repeatedly without duplicating data.

Required environment variable:

```text
ADMIN_INITIAL_PASSWORD
```

Seed files may contain:

```text
branch name
external_product_id
quantity
```

They must not contain product details.

---

## 15. Error Strategy

Services convert technical failures into stable structured errors.

Categories:

- validation;
- authentication;
- authorization;
- missing resource;
- insufficient stock;
- uniqueness or concurrency conflict;
- Product API unavailable;
- MCP unavailable;
- AI provider unavailable;
- timeout;
- internal error.

Responses never expose:

- tracebacks;
- SQL;
- passwords;
- password hashes;
- JWT values;
- API keys;
- connection strings.

---

## 16. Configuration

Minimum `.env.example` values:

```env
FLASK_ENV=development
BACKOFFICE_PORT=5000
AI_SERVICE_PORT=8000

DATABASE_URL=postgresql://app_user:replace_me@database:5432/hbntory
STOCK_MCP_DATABASE_URL=postgresql://stock_reader:replace_me@database:5432/hbntory

JWT_SECRET_KEY=replace_with_a_long_random_value
JWT_ACCESS_TOKEN_MINUTES=30
JWT_REFRESH_TOKEN_DAYS=7
ADMIN_INITIAL_PASSWORD=replace_me

PRODUCT_API_BASE_URL=http://product_api:8080
PRODUCT_API_TIMEOUT=5

PRODUCT_MCP_URL=http://product_mcp_server:8100
STOCK_MCP_URL=http://stock_mcp_server:8200
AI_MODEL=replace_me
LOG_LEVEL=INFO
```

Real values remain outside Git.

---

## 17. Docker Compose Services

Mandatory services:

```text
database
product_api
backoffice
product_mcp_server
stock_mcp_server
ai_service
client_web
```

Each service uses the internal Docker network.

HTTP services expose `/health`.

The target command is:

```bash
docker compose up --build
```

---

## 18. Testing Architecture

Tests are divided into:

- unit tests for validation and service logic;
- PostgreSQL integration tests for constraints, locking, and migrations;
- Product API and MCP integration tests;
- end-to-end Backoffice tests;
- end-to-end public-query tests;
- manual MCP test evidence;
- final demonstration checklist.

Critical scenarios are defined in `docs/testing_strategy.md`.

---

## 19. MVP Delivery Order

1. project skeleton and Docker Compose;
2. database and migrations;
3. initialization;
4. authentication and authorization;
5. Backoffice stock operations;
6. admin user operations;
7. Product API integration;
8. Product MCP;
9. Stock MCP;
10. AI Query Service;
11. Client Web Interface;
12. full integration and documentation.

Integration is performed after each major component, not left until the final day.

---

## 20. Known Limitations

- no branch CRUD;
- no conversation history;
- no WebSocket or streaming;
- no refresh-token rotation;
- JWTs are stored in `sessionStorage`;
- no TLS is required by the exercise;
- product display depends on Product API availability;
- AI support is limited to documented inventory questions;
- interface design is intentionally simple.

---

## 21. Team Responsibilities

### Person 1 — Backoffice and Database

- Flask Backoffice;
- SQLAlchemy;
- migrations;
- authentication and authorization;
- user and stock management;
- Product API client;
- backend tests.

### Person 2 — AI and MCP

- Product MCP;
- Stock MCP;
- shopping-list logic;
- AI agent;
- AI Query Service;
- MCP and AI tests.

### Person 3 — Interfaces and Integration

- Backoffice frontend;
- public client;
- Docker Compose;
- end-to-end integration;
- setup documentation;
- demonstration support.

All shared contracts require team approval.

---

## 22. Architecture Acceptance Criteria

The architecture is approved when:

- mandatory services and responsibilities are understood;
- communication choices and trade-offs are documented;
- data ownership is unambiguous;
- authentication and role enforcement are documented;
- product and stock MCP contracts are stable;
- MVP and deferred features are explicit;
- the complete flow is testable with Docker Compose;
- every team member can explain the system.
