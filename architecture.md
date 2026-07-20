# Architecture of the Backoffice Stock & AI Project

## 1. General Information

- **Project name:** Backoffice Stock & AI
- **Architecture type:** service-oriented architecture with a modular monolithic Backoffice
- **Team:** three people
- **Document status:** initial version to be approved by the team
- **Primary owner of this document:** the entire team
- **Last updated:** July 2026

This document describes the project’s technical organization, the responsibilities of each component, communication flows, technology choices, and integration rules.

It does not replace the other documents in the `docs/` directory:

- `project_context.md` describes the business need and general rules;
- `database_schema.md` describes tables, fields, constraints, and relationships;
- `api_contracts.md` describes HTTP routes, parameters, JSON responses, and errors;
- `security_rules.md` describes detailed security rules;
- `testing_strategy.md` describes test levels and scenarios.

---

## 2. Architecture Objective

The architecture must make it possible to:

- manage users, branches, and stock quantities;
- ensure that each user acts only within their authorized scope;
- retrieve product information from an external Product API;
- allow a public interface to submit questions in natural language;
- allow an AI agent to consult product and stock data without modifying it;
- prevent the AI agent from accessing the database directly or executing unrestricted SQL;
- run all components together with Docker Compose;
- allow the three team members to work in parallel using shared integration contracts.

---

## 3. Overview

The project is composed of the following elements:

1. **Backoffice Service**
   - manages authentication;
   - manages users;
   - manages branches;
   - manages stock quantities;
   - enforces authorization rules;
   - accesses the database;
   - calls the external Product API whenever product information must be displayed.

2. **Backoffice Interface**
   - allows employees to log in;
   - allows users to view the stock they are authorized to access;
   - allows common users to add or remove stock;
   - allows the administrator to manage users and branches.

3. **Public Interface**
   - allows a visitor to ask a question in natural language;
   - displays the response from the AI service;
   - never accesses the database directly.

4. **AI Query Service**
   - receives questions from the public interface;
   - analyzes each question independently;
   - selects the required MCP tools;
   - combines product and stock data;
   - returns a structured and cautious response.

5. **Product MCP Server**
   - exposes product lookup tools;
   - calls only the external Product API;
   - does not read the local database.

6. **Stock MCP Server**
   - exposes stock lookup tools;
   - accesses only the data required for read operations;
   - cannot add or remove stock;
   - cannot access passwords or private employee data.

7. **Relational Database**
   - stores users;
   - stores branches;
   - stores stock quantities;
   - does not store product names, descriptions, or other business product details.

8. **Provided Product API**
   - is provided as a read-only Docker container;
   - is the source of truth for product information;
   - provides detailed product information;
   - must be queried whenever product information is required;
   - must be queried before a product is added to stock.

---

## 4. General Diagram

```mermaid
flowchart LR
    BO_UI[Backoffice Interface]
    PUBLIC_UI[Public Interface]
    BACKOFFICE[Flask Backoffice Service]
    AI[AI Query Service]
    PRODUCT_MCP[Product MCP Server]
    STOCK_MCP[Stock MCP Server]
    PRODUCT_API[Provided Product API<br/>Read-only Docker container]
    DB[(Relational Database)]

    BO_UI -->|HTTP/REST| BACKOFFICE
    PUBLIC_UI -->|POST /questions| AI

    BACKOFFICE -->|SQLAlchemy| DB
    BACKOFFICE -->|HTTP/REST| PRODUCT_API

    AI -->|MCP| PRODUCT_MCP
    AI -->|MCP| STOCK_MCP

    PRODUCT_MCP -->|HTTP/REST| PRODUCT_API
    STOCK_MCP -->|Read-only| DB
```

---

## 5. Architecture Principles

### 5.1 Separation of Responsibilities

Each component has a clear responsibility.

- The Backoffice manages business write operations and internal security.
- The Product MCP retrieves product data.
- The Stock MCP retrieves stock data.
- The AI service orchestrates MCP tools.
- The interfaces display data and forward user actions.
- The database must be accessible only to explicitly authorized components.

### 5.2 Principle of Least Privilege

Each service receives only the permissions it needs.

- The Backoffice can read and modify authorized business data.
- The Stock MCP has read-only access.
- The Product MCP does not access the local database.
- The AI service has no direct database access.
- The interfaces never access the database directly.

### 5.3 Single Source of Truth

- The relational database is the source of truth for users, branches, and stock quantities.
- The external Product API is the source of truth for product information.
- Product details must not be permanently duplicated in the local database.

### 5.4 Server-Side Validation

Business rules and authorization rules must always be enforced in the backend.

Hiding a button in the interface is not sufficient protection.

### 5.5 Structured Exchanges

Communication between components must use predictable formats:

- JSON for REST APIs;
- documented response structures for MCP tools;
- stable error codes;
- unambiguous technical identifiers.

### 5.6 Loose Coupling

Each service should be able to evolve without forcing internal changes on the other services, as long as the integration contracts remain unchanged.

---

## 6. Technology Choices

## 6.1 Backoffice

The Backoffice will be developed with **Flask**.

Related technologies:

- **Flask** for the web application and HTTP routes;
- **SQLAlchemy** for data access;
- **Flask-Migrate** and **Alembic** for migrations;
- **Jinja** for server-side rendered HTML pages;
- **pytest** for testing;
- **bcrypt** for secure password hashing;
- **Flask-Login** or an equivalent session mechanism for web authentication.

### Why Flask Was Chosen

Flask is suitable for the project because the Backoffice must:

- display HTML pages;
- expose HTTP routes;
- use SQLAlchemy;
- remain modular;
- allow the team to implement business rules, authentication, and authorization explicitly.

Flask provides a lightweight foundation without imposing an ORM or an overly rigid structure.

## 6.2 Database

The project uses **PostgreSQL** as its relational database management system.

PostgreSQL will be used:

- in the development environment;
- in Docker Compose;
- for integration tests;
- in the demonstration or production environment.

Migrations will be managed with **Flask-Migrate** and **Alembic**.

Unit tests may use mocks, but tests that verify constraints, transactions, locks, or SQL behavior must run against PostgreSQL so that they remain representative of the real environment.

## 6.3 MCP Servers

The MCP servers will be developed in Python.

Recommended choice:

- **FastMCP** to expose tools;
- local or network transport depending on the selected integration mode;
- structured responses returned as dictionaries or JSON-serializable objects.

## 6.4 AI Service

The AI service will be developed in Python and will expose an HTTP API.

Choices still to be approved:

- Flask or FastAPI for the AI service API;
- AI provider and model;
- orchestration library;
- connection mode for the MCP servers.

The AI service must remain independent from the technology used by the Backoffice.

## 6.5 Interfaces

The Backoffice interface may be rendered with:

- Flask;
- Jinja;
- HTML;
- CSS;
- lightweight JavaScript.

The public interface may be:

- integrated into the same web client;
- or developed as a separate interface.

The final choice must be defined with Person 3.

## 6.6 Containerization

The project will use:

- **Docker** to build the services;
- **Docker Compose** to run the complete project;
- `.env` files for local values;
- an `.env.example` file without real secrets.

## 6.7 Communication Between the Public Interface and the AI Service

The public interface will communicate with the **AI Query Service** through a **REST API**.

Each question is independent, and no conversation history is stored. An HTTP `POST /questions` request therefore maps naturally to one question and one response.

REST was selected because it is simpler to develop, test, document, and integrate for this project.

WebSocket was not selected because the system does not require:

- a persistent connection;
- continuous bidirectional communication;
- conversation history;
- real-time broadcasting or streamed responses.

This choice may be reconsidered only if a streaming or real-time requirement is added to the project.

---

## 7. Backoffice Architecture

The Backoffice is a **modular monolith**.

It is a single deployable application divided into clearly separated business modules.

Proposed structure:

```text
backoffice/
├── __init__.py
├── app.py
├── config.py
├── extensions.py
├── auth/
│   ├── __init__.py
│   ├── routes.py
│   ├── services.py
│   ├── forms.py
│   └── decorators.py
├── users/
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   └── repositories.py
├── branches/
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   └── repositories.py
├── stocks/
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   └── repositories.py
├── products/
│   ├── __init__.py
│   ├── client.py
│   └── services.py
├── database/
│   ├── __init__.py
│   └── migrations/
├── templates/
├── static/
└── tests/
```

### 7.1 Routes Layer

The `routes` layer:

- receives HTTP requests;
- validates input data;
- calls business services;
- returns an HTTP response;
- does not contain the main business logic directly.

### 7.2 Services Layer

The `services` layer:

- applies business rules;
- checks authorization;
- coordinates data access;
- starts the required transactions;
- raises explicit business errors.

### 7.3 Repositories Layer

The `repositories` layer:

- centralizes SQLAlchemy queries;
- does not contain business rules;
- avoids scattering database access throughout the application.

### 7.4 Models Layer

The `models` layer:

- defines SQLAlchemy models;
- defines relationships;
- defines database constraints;
- does not replace business validation performed by the services.

### 7.5 Product Client

The `products/client.py` module:

- calls the external Product API;
- manages timeouts;
- converts network errors into application errors;
- does not permanently store product information.

---

## 8. Main Business Model

The main Backoffice resources are:

### 8.1 User

A user represents a person authorized to access the Backoffice.

Planned roles:

- `admin`;
- `user`.

Main rules:

- the application has exactly one administrator, whose username is `admin`;
- the `admin` account is created during application initialization;
- no route or interface allows another administrator to be created;
- the administrator may create common users only;
- a common user’s role cannot be changed to administrator;
- a common user is assigned to exactly one branch;
- an administrator is not allowed to modify stock quantities;
- a disabled user can no longer log in;
- passwords are hashed with bcrypt and are never stored in plain text;
- deleting a common user is implemented as a soft delete.

### 8.2 Branch

A branch represents a location where stock may be available.

Main rules:

- each branch has a unique identifier;
- a common user belongs to exactly one branch;
- a branch may contain several stock records.

### 8.3 Stock

A stock record represents the available quantity of a product in a branch.

Minimum business fields:

- `branch_id`;
- `product_id`;
- `quantity`.

Main rules:

- the `branch_id + product_id` combination is unique;
- `quantity` is always greater than or equal to zero;
- an added or removed quantity is a strictly positive integer;
- a removal greater than the available stock is rejected;
- a stock record is kept when its quantity reaches zero;
- stock changes are performed inside a transaction;
- the product must exist in the external Product API before the first stock addition.

The complete model will be defined in `database_schema.md`.

---

## 9. Authentication and Authorization

## 9.1 Authentication

The Backoffice uses server-side session authentication.

General flow:

1. the user submits a username and password;
2. the backend searches for an active user;
3. the backend verifies the hashed password;
4. an authenticated session is created;
5. subsequent requests use this session;
6. logging out invalidates the session.

Passwords will be hashed with **bcrypt**.

bcrypt is designed for password storage. It automatically applies a unique salt and a configurable cost factor, which slows down brute-force attempts. Plain-text passwords must never be stored, written to logs, or returned by an API.

## 9.2 Authorization

Authorization is checked on the server for every sensitive operation.

### Administrator

The administrator may:

- list users;
- create common users;
- modify a common user’s information;
- change a common user’s password;
- change the branch assigned to a common user;
- soft-delete a common user;
- manage branches according to the approved rules;
- view information required for administration.

The administrator may not:

- add stock;
- remove stock.

### Common User

A common user may:

- view the stock of their branch;
- add a quantity to the stock of their branch;
- remove a quantity from the stock of their branch.

A common user may not:

- view or modify the stock of another branch;
- manage user accounts;
- modify their role;
- freely choose another branch in a request.

The authorized branch is determined from the authenticated user, not from a value freely supplied by the browser.

---

## 10. Product MCP Server Architecture

The Product MCP Server provides product lookup tools.

Proposed structure:

```text
product_mcp_server/
├── __init__.py
├── server.py
├── product_client.py
├── schemas.py
└── tests/
```

Minimum tools:

```text
list_products()
get_product_details(product_id)
```

Responsibilities:

- call the external Product API;
- validate and normalize responses;
- return simple, usable data;
- handle unknown products;
- handle timeouts;
- handle Product API unavailability;
- avoid inventing data.

The Product MCP Server must not:

- access the local database;
- modify stock;
- keep a permanent business copy of product data;
- expose connection secrets.

---

## 11. Stock MCP Server Architecture

The Stock MCP Server exposes read-only tools.

Proposed structure:

```text
stock_mcp_server/
├── __init__.py
├── server.py
├── repositories.py
├── schemas.py
└── tests/
```

Proposed tools:

```text
list_branch_stock(branch_id)
find_branches_with_stock(product_id, quantity)
get_stock_for_product(product_id)
```

Responsibilities:

- retrieve stock quantities;
- return only the required data;
- use controlled queries;
- handle unknown products or branches;
- return a structured response.

Restrictions:

- no database writes;
- no stock modifications;
- no password access;
- no access to unnecessary private data;
- no execution of SQL supplied by the agent;
- no generic tool such as `execute_sql(query)`.

### Stock Access Choice for the AI Agent

The team chose to develop a **custom, strictly read-only Stock MCP Server**.

This choice exposes only precise and controlled operations to the agent, such as stock searches by product or branch. A generic database MCP was not selected because it could expose more tables or query capabilities than necessary.

The Stock MCP:

- exposes no generic SQL tool;
- never accepts SQL generated by the user or the agent;
- allows no write operation;
- does not access passwords or private employee data.

### Stock Read Mode

Two technical modes remain possible:

1. the Stock MCP accesses PostgreSQL directly using a strictly read-only SQL account that is separate from the Backoffice account;
2. the Stock MCP calls an internal read-only API exposed by the Backoffice.

The final mode must still be approved by the team and documented in `api_contracts.md` and `security_rules.md`.

---

## 12. AI Query Service Architecture

Proposed structure:

```text
ai_service/
├── __init__.py
├── app.py
├── agents/
├── prompts/
├── api/
├── schemas/
├── services/
└── tests/
```

Responsibilities:

- receive a question;
- check that the question is valid;
- identify products, branches, and quantities mentioned in the question;
- select the required MCP tools;
- call the Product MCP and Stock MCP;
- combine the results;
- produce a structured response;
- report unavailable information;
- avoid invented responses;
- process each question without conversation history.

The AI service must not:

- access the database directly;
- modify stock;
- authenticate employees;
- read passwords;
- execute unrestricted SQL;
- use data from a previous question.

Example public route:

```http
POST /questions
Content-Type: application/json
```

Example request:

```json
{
  "question": "Which branch has 3 units of product X?"
}
```

Example proposed response:

```json
{
  "answer": "Product X is available at the Central branch with 5 units.",
  "status": "success",
  "data": {
    "product_id": "X",
    "requested_quantity": 3,
    "branches": [
      {
        "branch_id": 2,
        "branch_name": "Central",
        "available_quantity": 5
      }
    ]
  }
}
```

The final format will be documented in `api_contracts.md`.

---

## 13. Main Business Flows

## 13.1 Backoffice Login

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Backoffice Interface
    participant BO as Flask Backoffice
    participant DB as Database

    U->>UI: Enters credentials
    UI->>BO: POST /auth/login
    BO->>DB: Searches for an active user
    DB-->>BO: User + hashed password
    BO->>BO: Verifies the password
    BO-->>UI: Session created or error
```

## 13.2 Adding Stock

```mermaid
sequenceDiagram
    actor U as Common User
    participant UI as Backoffice Interface
    participant BO as Flask Backoffice
    participant API as Product API
    participant DB as Database

    U->>UI: Requests a quantity addition
    UI->>BO: Add-stock request
    BO->>BO: Checks session, role, and branch
    BO->>BO: Validates the quantity
    BO->>API: Verifies that the product exists
    API-->>BO: Product found or error
    BO->>DB: Starts a transaction
    BO->>DB: Creates or updates the stock record
    BO->>DB: Commits the transaction
    BO-->>UI: Stock updated
```

## 13.3 Removing Stock

```mermaid
sequenceDiagram
    actor U as Common User
    participant UI as Backoffice Interface
    participant BO as Flask Backoffice
    participant DB as Database

    U->>UI: Requests a stock removal
    UI->>BO: Remove-stock request
    BO->>BO: Checks session, role, and branch
    BO->>BO: Validates the quantity
    BO->>DB: Locks or loads the stock inside a transaction
    DB-->>BO: Current quantity
    BO->>BO: Checks that enough stock is available
    BO->>DB: Updates the quantity
    BO->>DB: Commits the transaction
    BO-->>UI: Stock updated or error
```

## 13.4 Public Question

```mermaid
sequenceDiagram
    actor V as Visitor
    participant UI as Public Interface
    participant AI as AI Query Service
    participant PMCP as Product MCP
    participant SMCP as Stock MCP
    participant API as Product API
    participant DB as Database

    V->>UI: Asks a question
    UI->>AI: POST /questions
    AI->>PMCP: Searches for the product
    PMCP->>API: Calls the Product API
    API-->>PMCP: Product data
    PMCP-->>AI: Normalized product
    AI->>SMCP: Searches stock
    SMCP->>DB: Controlled read
    DB-->>SMCP: Available quantities
    SMCP-->>AI: Structured results
    AI-->>UI: Structured response
```

---

## 14. Communication Between Components

| Source | Destination | Protocol | Purpose |
|---|---|---|---|
| Backoffice Interface | Backoffice Service | HTTP/REST | Authentication and business operations |
| Public Interface | AI Query Service | HTTP/REST | Submit questions |
| Backoffice Service | External Product API | HTTP/REST | Product lookup and validation |
| AI Query Service | Product MCP | MCP | Product lookup |
| AI Query Service | Stock MCP | MCP | Stock lookup |
| Backoffice Service | Database | SQLAlchemy | Read and write operations |
| Stock MCP | Database or internal API | Read-only | Stock lookup |

All network communication must define:

- a timeout;
- error handling;
- minimal logging;
- a known response format;
- a limited retry policy when necessary.

---

## 15. Data Contracts

Detailed contracts are defined in `api_contracts.md`.

Shared principles:

- UTF-8 encoded JSON;
- `snake_case` field names;
- stable identifiers;
- ISO 8601 dates;
- quantities represented as integers;
- structured errors;
- no sensitive information in responses.

Recommended error format:

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "The requested quantity exceeds the available stock.",
    "details": {}
  }
}
```

General HTTP status codes:

| Code | Usage |
|---|---|
| `200` | Successful request |
| `201` | Resource created |
| `204` | Successful request with no response body |
| `400` | Invalid input data |
| `401` | Authentication required or invalid |
| `403` | Forbidden action |
| `404` | Resource not found |
| `409` | Business conflict or uniqueness constraint |
| `422` | Data understood but invalid for the requested operation |
| `500` | Internal error |
| `502` | External service error |
| `503` | Service temporarily unavailable |

The exact choice between `400`, `409`, and `422` for each business error will be defined in `api_contracts.md`.

---

## 16. Transactions and Concurrency

All stock changes must be performed inside a transaction.

A stock removal must be atomic:

1. read the available quantity;
2. verify that it is sufficient;
3. calculate the new quantity;
4. save the new quantity;
5. commit the transaction.

If an error occurs, the entire transaction must be rolled back.

The system must prevent two simultaneous removals from using the same available quantity.

Possible methods:

- pessimistic row locking;
- conditional update;
- an appropriate isolation level;
- optimistic version control.

The final strategy will be adapted to PostgreSQL and documented in `database_schema.md`.

---

## 17. Error Management

Each component must convert technical errors into understandable errors.

Error categories:

- validation error;
- authentication error;
- authorization error;
- missing resource;
- insufficient stock;
- data conflict;
- Product API unavailability;
- timeout;
- database error;
- unexpected internal error.

Responses must never expose:

- a full Python traceback;
- an SQL query;
- a password;
- a password hash;
- an API key;
- a connection string;
- sensitive environment variables.

---

## 18. Configuration and Environment Variables

Secrets and configurable parameters must not be written directly in the code.

Proposed variables:

```text
FLASK_ENV
SECRET_KEY
DATABASE_URL
PRODUCT_API_BASE_URL
PRODUCT_API_KEY
PRODUCT_API_TIMEOUT
AI_SERVICE_URL
PRODUCT_MCP_URL
STOCK_MCP_URL
BACKOFFICE_PORT
AI_SERVICE_PORT
LOG_LEVEL
```

An `.env.example` file must contain placeholder values only:

```env
SECRET_KEY=replace_me
DATABASE_URL=postgresql://user:password@database:5432/stock_db
PRODUCT_API_BASE_URL=https://example.com/api
PRODUCT_API_KEY=replace_me
PRODUCT_API_TIMEOUT=5
BACKOFFICE_PORT=5000
AI_SERVICE_PORT=8000
LOG_LEVEL=INFO
```

The real `.env` file must be added to `.gitignore`.

---

## 19. Logging and Observability

Each service must produce useful logs.

Information that may be logged:

- service startup and shutdown;
- requested route;
- response status code;
- processing duration;
- technical error;
- external service call;
- internal request identifier;
- business operation performed.

Information that must not be logged:

- password;
- password hash;
- session cookie;
- secret token;
- API key;
- complete connection string;
- unnecessary private content.

Each important request may receive a correlation identifier so that its path can be traced across several services.

---

## 20. Deployment with Docker Compose

Planned services:

```text
backoffice
ai_service
product_mcp_server
stock_mcp_server
product_api
database
client_web
```

The `product_api` service is the read-only Docker container provided with the project specification. It is used by the Backoffice and the Product MCP Server whenever product information is required.

Optional services:

```text
reverse_proxy
```

The `docker-compose.yml` file must:

- build or use the required images;
- define ports;
- inject environment variables;
- create the internal network;
- declare dependencies;
- mount required volumes;
- preserve database data;
- add health checks;
- allow the entire project to start with a single command.

Target command:

```bash
docker compose up --build
```

---

## 21. Health Checks

Each HTTP service must expose a simple route:

```http
GET /health
```

Minimum response:

```json
{
  "status": "ok"
}
```

A more detailed response may distinguish between:

- service running;
- database available;
- Product API container available;
- MCP servers available.

Health checks must not expose secrets or dangerous internal details.

---

## 22. Testing Strategy in the Architecture

Detailed tests will be described in `testing_strategy.md`.

Planned levels:

### Unit Tests

- stock business rules;
- quantity validation;
- authorization;
- password hashing and verification;
- normalization of Product API responses;
- MCP tool selection.

### Integration Tests

- Backoffice with the database;
- migrations;
- transactions;
- Backoffice with a mocked Product API;
- AI service with the MCP servers;
- Stock MCP with its data source.

### End-to-End Tests

- login from the interface;
- adding and removing stock;
- user management;
- public question;
- Product API unavailability;
- full startup with Docker Compose.

### Security Tests

- unauthenticated user;
- disabled user;
- user from another branch;
- administrator attempting to modify stock;
- negative or zero quantity;
- removal greater than available stock;
- direct access to a forbidden route;
- injection of unexpected parameters.

---

## 23. Git Organization and Collaboration

The `main` branch must remain stable.

Working rule:

```text
One feature = one branch = one pull request = one review
```

Branch examples:

```text
docs/project-foundation
feature/backoffice-setup
feature/database-models
feature/authentication
feature/user-management
feature/branch-management
feature/stock-management
feature/product-mcp
feature/stock-mcp
feature/ai-query-service
feature/public-interface
feature/docker-compose
```

Before merging:

- relevant tests must pass;
- documentation must be updated;
- another team member must review the Pull Request;
- shared contracts must not be changed without team approval;
- no secret may be committed to the repository.

---

## 24. Responsibility Assignment

### Person 1 — Backoffice, Security, and Database

Responsible for:

- Flask;
- SQLAlchemy;
- migrations;
- `User`, `Branch`, and `Stock` models;
- authentication;
- authorization;
- user management;
- branch management;
- stock management;
- the Product API client used by the Backoffice;
- Backoffice tests.

### Person 2 — AI and MCP Servers

Responsible for:

- Product MCP;
- Stock MCP;
- MCP tools;
- AI agent;
- AI Query Service;
- agent tool security;
- AI and MCP tests.

### Person 3 — Interfaces and Integration

Responsible for:

- Backoffice interface;
- public interface;
- Docker Compose;
- service integration;
- end-to-end tests;
- installation documentation;
- user experience.

### Shared Responsibilities

The whole team approves:

- the data model;
- REST contracts;
- MCP contracts;
- error formats;
- the AI service response format;
- environment variables;
- security rules;
- the definition of done.

---

## 25. Decisions Still to Be Approved by the Team

The following decisions still need to be confirmed:

- whether the Stock MCP accesses the database or an internal API;
- the HTTP framework used by the AI Query Service;
- the AI provider and model;
- the MCP transport;
- the final MCP response formats;
- the final `POST /questions` format;
- the final ports;
- whether a reverse proxy will be used;
- the exact locking strategy for stock removals;
- the CSRF policy;
- the CORS policy;
- session duration;
- the rules for initial administrator creation.

No unapproved decision should be treated as final simply because it appears in this initial version.

---

## 26. Architecture Approval Criteria

The architecture will be considered approved when:

- all three members understand the role of each component;
- service boundaries are clear;
- the minimum data model is approved;
- the essential API contracts are approved;
- MCP tool formats are approved;
- the main authorization rules are approved;
- the PostgreSQL configuration is approved;
- the main environment variables are defined;
- the complete flow can be explained from the interface to the data source;
- each member can start their part without inventing a missing contract.

---

## 27. Summary

The project uses an architecture composed of several specialized services.

The Flask Backoffice is the internal business core. It manages session authentication, bcrypt password hashing, authorization, and stock changes. Internal data is stored in PostgreSQL and manipulated through SQLAlchemy. Product information remains managed by the provided read-only Product API Docker container. The AI service does not access data directly: it uses limited and controlled MCP servers. The custom Stock MCP is strictly read-only. The public interface communicates with the AI Query Service through a REST API. The entire project will be launched with Docker Compose.

Successful integration mainly depends on defining shared contracts early and integrating the three parts regularly.
