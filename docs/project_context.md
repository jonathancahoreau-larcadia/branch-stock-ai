# HBntory — Project Context

## 1. Project Overview

HBntory is an inventory management platform for a fictional retail company with several physical branches.

The system has two user-facing areas:

1. an authenticated internal Backoffice for stock and user management;
2. a public Client Web Interface where anonymous users ask natural-language questions about products and stock.

Product details are managed by a read-only external Product API supplied as a Docker container. The local database stores only external product identifiers and stock quantities.

---

## 2. Mandatory Objectives

The project must allow:

- a common user to consult and modify stock only for their assigned branch;
- the unique administrator account, `admin`, to manage common users;
- an anonymous visitor to ask questions about products and availability;
- an AI agent to answer from real product and stock data;
- all required services to run together through Docker Compose.

The project must not:

- store product names, descriptions, prices, images, categories, or metadata in the Backoffice database;
- store plain-text passwords;
- allow the AI agent to modify stock;
- rely only on hidden interface buttons for authorization;
- expose unrestricted SQL execution to the AI agent;
- store conversation history for the public interface.

---

## 3. Confirmed Architecture

HBntory uses a hybrid service-oriented architecture.

### 3.1 Main Components

- **Backoffice Interface:** lightweight HTML/CSS/JavaScript interface.
- **Backoffice Service:** Flask REST API organized as a modular monolith.
- **PostgreSQL Database:** local source of truth for users, branches, stock, and revoked JWT identifiers.
- **External Product API:** read-only source of truth for product information.
- **Product MCP Server:** controlled bridge between the AI service and the Product API.
- **Stock MCP Server:** custom, strictly read-only bridge between the AI service and PostgreSQL.
- **AI Query Service:** independent Flask service containing one or more AI agents.
- **Client Web Interface:** public HTML/CSS/JavaScript search-style interface.

### 3.2 Simplified Flow

```text
Authenticated employee
        |
        v
Backoffice Interface
        |
        | REST + JWT Bearer
        v
Backoffice Service
        |
        +--> PostgreSQL
        |
        +--> External Product API


Anonymous visitor
        |
        v
Client Web Interface
        |
        | POST /questions
        v
AI Query Service
        |
        +--> Product MCP Server --> External Product API
        |
        +--> Stock MCP Server --> PostgreSQL, read-only
```

---

## 4. Backoffice Communication Strategy

The Backoffice uses a Flask REST API with a lightweight HTML/CSS/JavaScript interface.

### Selected option

```text
REST API + lightweight frontend
```

### Main benefit

JWT Bearer tokens can be added explicitly to API calls through the HTTP `Authorization` header.

### Main trade-off

The frontend requires more JavaScript than a fully server-rendered application and must manage token storage and refresh behavior carefully.

A fully server-side rendered interface was not selected because normal browser page navigation does not automatically attach a JWT Bearer token to the `Authorization` header.

---

## 5. Public Client Communication Strategy

The Client Web Interface communicates with the AI Query Service through REST.

### Selected option

```http
POST /questions
```

### Main benefit

Each question is independent, so one request naturally maps to one response. REST is simpler to implement, test, document, and integrate.

### Main trade-off

The first version does not stream partial responses and does not provide continuous real-time communication.

WebSockets are outside the MVP because conversation history and streaming are not required.

---

## 6. Authentication

The Backoffice uses JWT Bearer authentication.

After a successful login, the API returns:

- an access token valid for 30 minutes;
- a refresh token valid for 7 days.

The client sends the required token in:

```http
Authorization: Bearer <token>
```

For the MVP, the Backoffice frontend stores both tokens in `sessionStorage`.

This choice:

- survives page reloads in the same browser tab;
- clears the tokens when the tab or browser session is closed;
- avoids long-term persistence in `localStorage`.

Known limitation:

- `sessionStorage` remains accessible to JavaScript, so an XSS vulnerability could steal the tokens.

The detailed mitigations are defined in `docs/security_rules.md`.

### 6.1 Token Revocation

Each JWT contains a unique `jti`.

A PostgreSQL blocklist stores only revoked `jti` values and their expiration metadata. Complete JWT values are never stored.

The `users.token_version` field invalidates all existing tokens for one user when their password is changed.

### 6.2 Password Storage

Passwords are hashed with bcrypt.

bcrypt is appropriate because it:

- is designed specifically for password storage;
- automatically includes a unique salt;
- is intentionally slow;
- supports a configurable work factor.

Plain SHA-256 is not sufficient by itself because it is designed to be fast, allowing attackers to test large numbers of candidate passwords quickly.

---

## 7. Roles and Permissions

The application has exactly two roles:

```text
admin
common_user
```

### 7.1 Administrator

There is exactly one administrator named `admin`.

The administrator can:

- list users;
- create common users;
- assign common users to a branch;
- modify common users;
- change a common user's password;
- change a common user's assigned branch;
- soft-delete common users;
- list branches for user assignment.

The administrator cannot:

- create another administrator;
- promote a common user to administrator;
- add stock;
- remove stock;
- use the common-user stock interface.

Creating, modifying, and deleting branches are outside the MVP.

### 7.2 Common User

A common user:

- belongs to exactly one branch;
- can add stock to that branch;
- can remove stock from that branch;
- can list products currently in stock in that branch;
- can check the quantity of one product in that branch.

A common user cannot:

- manage users;
- choose another branch in a stock request;
- operate on another branch;
- modify their role or branch assignment.

The backend obtains the branch from the authenticated user's current database record.

---

## 8. Local Data

The PostgreSQL database stores:

- users;
- password hashes;
- roles;
- active and soft-delete status;
- branch assignments;
- branches;
- external product identifiers;
- stock quantities;
- JWT token versions;
- revoked JWT identifiers and expiration metadata.

It never stores:

- product names;
- product descriptions;
- product prices;
- product images;
- product categories;
- product metadata;
- full JWT values;
- public conversation history;
- AI-generated answers.

---

## 9. Stock Rules

A stock record contains:

```text
branch_id
external_product_id
quantity
```

The combination below is unique:

```text
branch_id + external_product_id
```

Mandatory rules:

- `quantity` is an integer greater than or equal to zero;
- added and removed quantities are strictly positive integers;
- a removal greater than the available quantity is rejected;
- stock never becomes negative;
- a record remains in the database when its quantity reaches zero;
- zero means out of stock;
- stock modifications run inside PostgreSQL transactions;
- the product must exist in the Product API before the first addition;
- the branch is derived from the authenticated common user;
- an administrator cannot perform stock operations.

The stock list shown to a common user includes only quantities greater than zero by default. A product-specific consultation may still return a quantity of zero.

---

## 10. Product API Integration

The Product API is a read-only Docker service.

The Backoffice uses it to:

- populate a product selector or product search;
- display basic product details;
- validate a product identifier before adding stock.

The Product MCP Server uses it to:

- list products;
- retrieve one product's details.

Product responses may be displayed or forwarded, but they are not persisted in PostgreSQL.

If the Product API is unavailable, the system returns a clear error and does not invent data.

---

## 11. Product MCP Server

The Product MCP Server exposes only the mandatory product tools:

```python
list_products()
get_product_details(external_product_id)
```

It:

- performs read-only Product API calls;
- returns structured success, not-found, and error responses;
- handles connection errors and timeouts;
- does not access PostgreSQL;
- does not expose unnecessary Product API behavior.

---

## 12. Stock MCP Server

The team selected a custom Stock MCP Server instead of a generic database MCP.

### Main benefit

It exposes only controlled stock queries and prevents the AI agent from submitting arbitrary SQL.

### Main trade-off

The team must implement and maintain the required stock tools.

The server uses a distinct PostgreSQL account with `SELECT` permission only on the `branches` and `stocks` data required for public inventory answers.

Tools:

```python
list_branch_stock(branch_id)
get_stock_for_product(external_product_id)
find_branches_with_stock(external_product_id, quantity)
find_branches_for_shopping_list(items)
```

The shopping-list tool applies deterministic business logic outside the language model:

1. search for one branch that satisfies the entire list;
2. otherwise find a combination using the fewest branch visits;
3. return missing items when the request cannot be fully satisfied.

The Stock MCP cannot:

- insert, update, or delete data;
- access password hashes;
- access revoked tokens;
- access unnecessary employee data;
- execute SQL supplied by the user or the agent.

---

## 13. Supported AI Questions

The AI Query Service supports four mandatory question families:

1. product details;
2. product availability across branches;
3. products available in one branch;
4. a branch or minimal set of branches for a shopping list.

Examples:

```text
Give me details about product XX.
Which branch has stock of product X?
What products are available in branch Y?
Where can I find 3 units of X, 2 units of Y, and 4 units of Z?
```

A question outside this scope returns a clear `unsupported` response.

The agent must answer only from MCP tool results. It must never invent:

- products;
- product details;
- stock quantities;
- branches;
- availability.

---

## 14. Public Interface Requirements

The public interface is anonymous and contains:

- a text input;
- a submit button;
- a response area;
- loading feedback;
- clear error feedback.

The submit button is disabled when:

- the question is empty;
- a request is already in progress.

The interface distinguishes:

- a successful answer;
- a partial answer;
- unavailable data;
- an unsupported question;
- a technical service error.

---

## 15. Initial Data

The initialization process must create:

- the unique `admin` account;
- at least two branches;
- enough sample stock to test the system.

Rules:

- the admin password comes from `ADMIN_INITIAL_PASSWORD`;
- the password is hashed with bcrypt before insertion;
- no plain-text password is committed to Git;
- initialization is idempotent;
- sample stock files contain only external product identifiers and quantities;
- product identifiers are validated against the Product API before sample stock is committed;
- an unavailable Product API aborts sample-stock initialization without a partial commit.

---

## 16. Minimum Viable Product

### 16.1 Implement First

1. Docker Compose, PostgreSQL, migrations, and initialization.
2. User, branch, stock, and revoked-token models.
3. Authentication and backend authorization.
4. Common-user stock operations.
5. Admin user management.
6. Backoffice Product API integration.
7. Product MCP Server.
8. Stock MCP Server.
9. AI Query Service and `POST /questions`.
10. Public Client Web Interface.
11. Critical tests and full integration.

### 16.2 Leave for Later

- branch creation, modification, and deletion;
- refresh-token rotation;
- audit-history table;
- password-reset emails;
- conversation history;
- response streaming;
- WebSockets;
- reverse proxy;
- advanced monitoring;
- advanced UI design.

### 16.3 Optional Only If Time Allows

- richer search filters;
- improved accessibility and visual design;
- shopping-list explanations and alternative plans;
- automated cleanup job for expired blocklist records;
- recorded demonstration in addition to the live demonstration.

---

## 17. Repository Organization

```text
hbntory/
├── backoffice/
├── ai_service/
├── product_mcp_server/
├── stock_mcp_server/
├── client_web/
├── docs/
│   ├── project_context.md
│   ├── architecture.md
│   ├── database_schema.md
│   ├── api_contracts.md
│   ├── security_rules.md
│   ├── testing_strategy.md
│   ├── compliance_matrix.md
│   └── presentation_plan.md
├── seed/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 18. Definition of Done

A feature is complete when:

- it satisfies the mandatory project scope;
- backend authorization is enforced;
- input validation is implemented;
- errors are handled clearly;
- relevant automated or manual tests are documented;
- no secret or product detail is stored incorrectly;
- documentation is updated;
- another team member reviews the Pull Request;
- the integrated flow still works through Docker Compose.

The complete project is ready only after the team has requested the required manual QA review.
