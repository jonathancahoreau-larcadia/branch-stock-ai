# Branch Stock AI — Project Context

## 1. Project Overview

Branch Stock AI is a stock management application for a fictional company with several physical branches.

Each branch may hold different quantities of the same products.

The application includes two main parts:

1. an internal Backoffice that allows employees to manage stock;
2. a public interface that allows anonymous customers to ask questions about products and their availability.

Detailed product information must come from an external Product API provided as a Docker container.

---

## 2. Main Objective

The objective is to allow:

- employees to manage the stock of their assigned branch;
- the administrator to manage employee accounts;
- anonymous customers to ask natural-language questions about products and stock;
- an AI agent to answer only from real data obtained through MCP tools.

---

## 3. Chosen Architecture

We use a hybrid architecture.

The Backoffice is a modular monolith. It is a single application, but its code is divided into several specialized modules.

The AI Query Service is independent of the Backoffice.

The MCP servers are also separate, so that the AI agent receives limited and controlled access to data.

### Main Components

- Backoffice Interface;
- Backoffice Service;
- relational database;
- public interface;
- AI Query Service;
- Product MCP Server;
- Stock MCP Server;
- external Product API.

### Simplified View

```text
Employee or administrator
        |
        v
Backoffice Interface
        |
        v
Backoffice Service
        |
        +--> Local database
        |
        +--> External Product API


Anonymous customer
        |
        v
Public interface
        |
        v
AI Query Service
        |
        +--> Product MCP Server --> External Product API
        |
        +--> Stock MCP Server --> Local database in read-only mode
```

---

## 4. Backoffice Service

The Backoffice is an internal application that requires authentication.

It is organized into modules.

### Authentication Module

Responsibilities:

- login;
- logout;
- user identity verification;
- role verification;
- checking that the account is active;
- secure password management.

### User Module

Responsibilities:

- list users;
- create a common user;
- modify a user;
- change a user's password;
- change a user's assigned branch;
- perform a soft delete.

### Branch Module

Responsibilities:

- view branches;
- assign a common user to a branch;
- provide the information required for authorization checks.

Creating and deleting branches are not part of the mandatory scope unless the team makes a different decision.

### Stock Module

Responsibilities:

- add stock;
- remove stock;
- view stock;
- list the products available in a branch;
- prevent negative quantities;
- verify that a product exists in the external Product API.

### Data Access Layer

SQLAlchemy is used to access the relational database.

This layer manages, in particular:

- users;
- branches;
- stock records;
- database transactions.

---

## 5. Roles and Permissions

The application has two internal roles:

- `admin`;
- `common_user`.

Permissions must always be enforced by the backend.

The frontend may hide certain buttons, but this is not a security measure.

### Administrator

There is only one administrator named `admin`.

The administrator can:

- list users;
- create common users;
- modify users;
- change their passwords;
- change their assigned branches;
- deactivate users through soft deletion.

The administrator cannot:

- add stock;
- remove stock;
- manage stock for a branch.

### Common User

Each common user must be assigned to exactly one branch.

A common user can:

- view the stock of their assigned branch;
- add stock to their assigned branch;
- remove stock from their assigned branch;
- list the products available in their assigned branch.

A common user cannot:

- manage users;
- change their own assigned branch;
- view or modify the stock of another branch;
- perform an administrative action.

---

## 6. Local Data

The local database may contain only the data required for the Backoffice to operate.

### Allowed Data

- users;
- roles;
- password hashes;
- active or deactivated user status;
- branches;
- user-to-branch assignments;
- external product identifiers;
- stock quantities.

### Forbidden Product Data

The local database must never store:

- a product name;
- its description;
- its price;
- its image;
- its categories;
- its metadata;
- any other descriptive information coming from the Product API.

The local database stores only the `external_product_id` required to associate a product with a stock quantity.

---

## 7. Stock Model

A stock record represents the available quantity of an external product in a branch.

It contains at least:

```text
branch_id
external_product_id
quantity
```

The following combination must be unique:

```text
branch_id + external_product_id
```

This means that an external product can have only one stock record per branch.

`external_product_id` refers to a product managed by the external Product API. It is not a foreign key to a local product table because the local database does not store products.

### Business Rules

- `quantity` must be an integer greater than or equal to zero.
- An added or removed quantity must be a strictly positive integer.
- A removal greater than the available quantity must be rejected.
- Stock must never become negative.
- A stock record is kept when its quantity reaches zero.
- A quantity of zero means that the product is currently out of stock in that branch.
- Stock records are not deleted automatically.
- The product must exist in the external Product API before stock is added.
- Stock changes must be performed inside a database transaction.
- A common user can modify only the stock of their assigned branch.
- The backend must never trust a `branch_id` freely supplied by a common user.
- For a common user, the branch used for a stock operation must come from their authenticated account.

---

## 8. External Product API

The external Product API is provided in a Docker container.

It is read-only.

At minimum, it allows the system to:

- list products;
- retrieve product details by identifier.

The Backoffice and the Product MCP Server use this API whenever product information is required.

The system must not copy the returned information into the local database.

If the Product API is unavailable, the application must return a clear error and must not invent missing information.

---

## 9. Public Interface

The public interface is accessible without authentication.

It contains at least:

- an input area for entering a question;
- a button for sending the question;
- an area for displaying the answer;
- a loading indicator;
- clear error messages.

Each question is independent.

The application does not need to store conversation history.

---

## 10. Communication With the AI Service

The public interface communicates with the AI Query Service through a REST API.

This choice is appropriate because each question is independent and no permanent connection is required.

Planned main route:

```http
POST /questions
```

Example request:

```json
{
  "question": "Which branch has three units of product X?"
}
```

Example response:

```json
{
  "answer": "The product is available at the Toulon branch.",
  "data": {
    "external_product_id": 4,
    "branches": [
      {
        "branch_id": 2,
        "branch_name": "Toulon",
        "available_quantity": 8
      }
    ]
  }
}
```

The final format will be documented in:

```text
docs/api_contracts.md
```

---

## 11. AI Query Service

The AI Query Service is independent from the Backoffice.

It receives a natural-language question, then uses an AI agent to select the required tools.

It may use:

- the Product MCP Server to obtain product information;
- the Stock MCP Server to view available quantities.

The service must:

- understand the question;
- identify the requested products;
- identify any branches mentioned;
- call the appropriate tools;
- combine the results;
- produce an understandable answer;
- clearly state when information is unavailable.

It must not modify stock.

---

## 12. Product MCP Server

The Product MCP Server acts as a bridge between the AI agent and the external Product API.

It exposes at least the following tools:

```python
list_products()
get_product_details(external_product_id)
```

It must perform read-only operations.

It must not store product information in the local database.

---

## 13. Stock MCP Server

The Stock MCP Server gives the AI agent controlled access to stock quantities.

It is read-only.

Example tools:

```python
list_branch_stock(branch_id)
find_branches_with_stock(external_product_id, quantity)
get_stock_for_product(external_product_id)
```

The Stock MCP Server may only access:

- branch identifiers;
- external product identifiers;
- available quantities;
- the public branch information required by the service.

It must never:

- add or remove stock;
- read passwords;
- read password hashes;
- access private employee data;
- modify the database;
- freely execute SQL supplied by the agent.

---

## 14. AI Agent Rules

The AI agent must answer only from results returned by the available tools.

It must never invent:

- a product;
- a description;
- a price;
- a branch;
- a quantity;
- availability information.

When the tools do not provide enough information, the agent must clearly state that the information is unavailable.

Example:

```text
I do not have enough information to answer this question.
```

The agent must not have direct and unrestricted access to the database.

---

## 15. Questions Involving Multiple Products

When a user requests several products and quantities, the system must:

1. first search for a single branch that has all requested products in the required quantities;
2. if no single branch is suitable, search for a combination of branches;
3. prefer the combination requiring the fewest visits;
4. state when the full request cannot be satisfied.

This rule must be confirmed by the team before final implementation.

---

## 16. Security

Passwords must never be stored in plain text.

They must be stored as secure hashes.

Planned mechanism:

```text
Password hashing mechanism: bcrypt
```

Secrets and sensitive configuration must be stored in environment variables.

Files containing secrets must never be committed to the Git repository.

The repository must contain only an example file:

```text
.env.example
```

Permissions must be checked on every protected backend route.

SSL/TLS is not required for this project.

---

## 17. Repository Organization

Planned structure:

```text
branch-stock-ai/
├── backoffice/
│   ├── auth/
│   ├── users/
│   ├── branches/
│   ├── stocks/
│   ├── products/
│   ├── database/
│   └── tests/
│
├── ai_service/
│   ├── agents/
│   ├── prompts/
│   ├── api/
│   └── tests/
│
├── product_mcp_server/
│   ├── server.py
│   ├── product_client.py
│   └── tests/
│
├── stock_mcp_server/
│   ├── server.py
│   └── tests/
│
├── client_web/
│
├── docs/
│   ├── project_context.md
│   ├── architecture.md
│   ├── api_contracts.md
│   ├── database_schema.md
│   ├── security_rules.md
│   └── testing_strategy.md
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 18. Local Deployment

All components must be launchable with Docker Compose.

Target command:

```bash
docker compose up --build
```

The `docker-compose.yml` file must start at least:

- the database;
- the Backoffice;
- the AI Query Service;
- the Product MCP Server;
- the Stock MCP Server;
- the external Product API;
- optionally, the public interface if it is separate.

An API Gateway is not required for the first version.

A reverse proxy may be added later if it simplifies access to the services.

---

## 19. Required Tests

The project must test, in particular:

### Authentication

- valid login;
- invalid login;
- deactivated user;
- passwords are never stored in plain text.

### Authorization

- common user limited to their assigned branch;
- common user forbidden from managing users;
- administrator allowed to manage users;
- administrator forbidden from adding or removing stock.

### Stock

- adding a positive quantity;
- removing an available quantity;
- zero stock adjustment rejected;
- negative stock adjustment rejected;
- removal greater than available stock rejected;
- nonexistent product rejected;
- stock never becomes negative.

### Product API

- product listing;
- retrieval of an existing product;
- unknown product;
- unavailable API.

### Artificial Intelligence

- question about a product;
- question about stock in a branch;
- search for branches that have a product;
- request involving several products;
- insufficient data;
- no invented information.

### Integration

- startup with Docker Compose;
- login through the interface;
- stock modification through the browser;
- public question sent to the AI service;
- correct error display.

---

## 20. GitHub Workflow

The `main` branch is protected.

No team member should develop directly on `main`.

Each feature must follow this process:

```text
GitHub Issue
    ↓
feature/* branch
    ↓
Development and tests
    ↓
Pull request
    ↓
Review by another team member
    ↓
Merge into main
```

Branch naming convention:

```text
feature/backoffice-auth
feature/stock-management
feature/product-mcp
feature/stock-mcp
feature/ai-query-service
feature/public-interface
feature/docker-integration
```

A pull request must receive at least one approval before being merged.

---

## 21. Use of AI Assistants During Development

AI assistants may:

- propose a plan;
- explain code;
- generate a small feature;
- write tests;
- look for errors;
- review a pull request;
- propose documentation.

They must not:

- make architecture decisions on their own;
- modify several components without validation;
- add a dependency without justification;
- write or expose secrets;
- treat their own code as automatically correct;
- merge code that the team does not understand.

Before any major change, the assistant must:

1. read this document;
2. explain its plan;
3. identify the affected files;
4. restate the relevant business rules;
5. present the required tests;
6. wait for developer approval before making a major change.

---

## 22. Definition of Done

A feature is considered complete when:

- it complies with this document;
- its code is understandable;
- permissions are enforced by the backend;
- important errors are handled;
- the corresponding tests are present;
- all tests pass;
- no secrets are present in the code;
- the documentation is updated;
- another team member has reviewed the pull request;
- the pull request has been merged into `main`.

---

## 23. Decisions Still to Be Confirmed

The following decisions must still be validated by the team:

- Python framework for the Backoffice;
- Python framework for the AI Query Service;
- database engine;
- exact authentication method: session or JWT;
- AI model to be used;
- use of Ollama or a remote provider;
- whether to create an API Gateway;
- branch initialization method;
- final JSON response format;
- search algorithm for multi-product requests.

A confirmed decision must be removed from this section and added to the relevant section.

---

The exact routes will later be documented in `docs/api_contracts.md`, while the tables, relationships, and SQLAlchemy constraints will be documented in `docs/database_schema.md`. This keeps `project_context.md` as the central project overview without turning it into a huge technical manual.
