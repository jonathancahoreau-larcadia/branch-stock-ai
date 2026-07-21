# Testing Strategy — HBntory

## 1. Objective

The testing strategy verifies the mandatory Tasks 0–8 flows and provides evidence for the final manual QA review.

Testing combines:

- automated unit tests;
- PostgreSQL integration tests;
- service integration tests;
- end-to-end browser tests or documented manual scripts;
- manual MCP test evidence;
- final demonstration rehearsal.

---

## 2. Test Environments

### Unit

Mocks or fakes may replace external dependencies.

### Integration

Use PostgreSQL, not SQLite, for:

- constraints;
- migrations;
- transactions;
- row locking;
- partial indexes;
- read-only database permissions.

### Full System

Use:

```bash
docker compose up --build
```

All mandatory services must be running.

---

## 3. Backoffice Authentication Tests

- valid login returns access and refresh tokens;
- invalid credentials return `401`;
- unknown and wrong-password responses do not reveal account existence;
- soft-deleted user cannot log in;
- inactive user cannot log in;
- access token expires after 30 minutes;
- refresh token expires after 7 days;
- valid refresh creates a new access token;
- access token is rejected on the refresh route;
- refresh token is rejected on a business route;
- revoked token is rejected;
- old `token_version` is rejected;
- missing or malformed Bearer header is rejected;
- password is stored as bcrypt, not plain text;
- full JWT values are not stored or logged.

---

## 4. Authorization Tests

### Common User

- can view their branch;
- can list current stock in their branch;
- can add stock in their branch;
- can remove stock in their branch;
- cannot manage users;
- cannot use another branch ID;
- backend ignores or rejects foreign branch scope;
- branch shown in UI matches current database assignment.

### Admin

- can list users;
- can create a common user;
- can assign a branch;
- can modify username and branch;
- can change a password;
- can soft-delete a common user;
- cannot create another admin;
- cannot modify the admin through common-user routes;
- cannot add or remove stock;
- cannot use the common-user stock interface.

---

## 5. Database and Initialization Tests

- migrations apply to an empty PostgreSQL database;
- initialization is idempotent;
- admin exists exactly once;
- at least two branches exist;
- sample stock exists;
- sample product IDs are validated through the Product API;
- unavailable Product API causes no partial sample-stock commit;
- unique username constraint works;
- one-admin partial index works;
- common user requires a branch;
- admin has no branch;
- stock branch/product pair is unique;
- negative stock is rejected;
- blocklist `jti` is unique.

---

## 6. Stock Tests

- positive integer addition succeeds;
- positive integer removal succeeds;
- zero addition is rejected;
- zero removal is rejected;
- negative quantity is rejected;
- decimal quantity is rejected;
- unknown product addition is rejected;
- removal greater than available stock is rejected;
- stock never becomes negative;
- row remains when quantity reaches zero;
- default list excludes zero quantities;
- product-specific query can return zero;
- rollback leaves no partial change;
- two concurrent removals do not oversell;
- concurrent first additions do not create duplicates.

---

## 7. Product API Integration Tests

- product list succeeds;
- existing product detail succeeds;
- unknown product is handled clearly;
- connection failure is handled clearly;
- timeout is handled clearly;
- invalid external response is handled;
- no product detail is persisted locally;
- Backoffice selector or search uses external data.

---

## 8. Product MCP Manual Tests

Document commands or inspector steps for:

1. `list_products`;
2. `get_product_details` with a valid ID;
3. `get_product_details` with an invalid ID;
4. Product API stopped or unreachable.

Evidence may include:

- command output;
- screenshots;
- saved Markdown transcript.

Expected behavior:

- structured success;
- `not_found`;
- clear error;
- no silent failure.

---

## 9. Stock MCP Tests

- `list_branch_stock` returns positive stock;
- unknown branch handled;
- `get_stock_for_product` returns all branch quantities;
- empty stock list is not an error;
- `find_branches_with_stock` filters by requested quantity;
- invalid quantity rejected;
- shopping list solved by one branch;
- shopping list solved by multiple branches;
- unavailable shopping list returns missing items;
- minimal visit count is deterministic;
- MCP account cannot insert, update, or delete;
- MCP account cannot read users or revoked tokens;
- no arbitrary SQL tool exists.

---

## 10. AI Query Service Tests

Supported types:

- product details;
- product availability;
- branch inventory;
- shopping list.

Scenarios:

- grounded answer from Product MCP;
- grounded answer from Stock MCP;
- combined answer;
- unknown product;
- information unavailable;
- unsupported question;
- Product MCP failure;
- Stock MCP failure;
- AI provider failure;
- no invented product name;
- no invented branch;
- no invented quantity;
- requests are independent;
- tool-call logs show tool name and status without secrets.

---

## 11. Client Web Interface Tests

- page loads anonymously;
- text input visible;
- submit button visible;
- response area visible;
- empty question cannot be submitted;
- submit disabled while loading;
- loading indicator appears;
- successful answer displayed;
- partial/unavailable/unsupported response displayed clearly;
- technical error displayed clearly;
- no conversation history required;
- realistic examples work.

---

## 12. Complete Critical Scenarios

The final integrated test must demonstrate:

1. Product API running.
2. Database initialized.
3. Backoffice login.
4. Common user adds valid stock.
5. Common user removes valid stock.
6. Insufficient removal rejected.
7. Other-branch operation rejected.
8. Admin creates a common user.
9. Admin changes branch and password.
10. Admin soft-deletes a user.
11. Deleted user cannot log in.
12. Admin stock operation rejected.
13. Product details come from the external API.
14. Product MCP tools work.
15. AI locates a product.
16. AI lists products in a branch.
17. AI solves a shopping list.
18. AI handles unknown or unavailable information.
19. Public interface displays the answer.
20. Docker Compose restarts successfully.

---

## 13. README Verification

A team member who did not write the setup section must verify that the README allows them to:

- configure `.env`;
- build services;
- initialize the database;
- open the Backoffice;
- use the public client;
- run tests;
- identify known limitations.

---

## 14. Presentation Rehearsal

Before review:

- run the 10-minute demonstration;
- assign speaking sections to all three members;
- verify demo data;
- prepare failure recovery steps;
- confirm architecture diagram readability;
- prepare answers about JWT, bcrypt, REST, MCP, database boundaries, and trade-offs.

---

## 15. Evidence Checklist

Store evidence in a documented location such as:

```text
docs/test_evidence/
```

Possible evidence:

- pytest output;
- MCP manual transcript;
- screenshots;
- demo checklist;
- Docker Compose health output.

---

## 16. Exit Criteria

The project is ready for manual QA review when:

- mandatory automated tests pass;
- manual MCP tests are documented;
- critical end-to-end scenarios pass;
- README setup is independently verified;
- no secrets are committed;
- the final demonstration has been rehearsed;
- the team requests the required manual QA review.
