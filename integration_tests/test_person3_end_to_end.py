"""In-memory integration proofs for the Person 3 public flows.

Only public adapters and tool functions are composed here.  Product API,
PostgreSQL and MCP transports are replaced at their boundaries, so pytest
never opens a socket or contacts a service.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import bcrypt
import pytest
from sqlalchemy import event, text

from ai_service.question_service import QuestionService
from ai_service.server import create_app
from backoffice import create_app as create_backoffice_app
from backoffice.database.models import Branch, Stock, User
from backoffice.extensions import db
from backoffice.products import routes as backoffice_product_routes
from backoffice.stocks import services as backoffice_stock_services
from product_mcp_server import product_api
from product_mcp_server import tools as product_tools
from stock_mcp_server import repository as stock_repository
from stock_mcp_server import tools as stock_tools


PRODUCTS = [
    {"id": 1, "sku": "product-1", "name": "Widget"},
    {"id": 2, "sku": "product-2", "name": "Gadget"},
]


def _public_product_detail(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_product_id": product["sku"],
        "name": product["name"],
        "description": "A public catalogue product.",
        "category": "demo",
        "brand": "HB",
        "supplier": {
            "id": "supplier-demo",
            "name": "HB Supply",
            "country": "UY",
            "lead_time_days": 4,
            "reliability_score": 0.97,
        },
        "unit_price": 100.0,
        "currency": "USD",
        "discontinued": False,
        "weight_kg": 1.0,
        "tags": ["demo"],
        "updated_at": "2026-07-30T00:00:00Z",
    }
ROOT = Path(__file__).parents[1]
STOCK = {
    1: {
        "branch_id": 1,
        "branch_name": "Central",
        "stocks": [
            {"external_product_id": "product-1", "quantity": 5},
        ],
    },
    2: {
        "branch_id": 2,
        "branch_name": "North",
        "stocks": [{"external_product_id": "product-2", "quantity": 3}],
    },
}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch):
    """Make accidental network use an immediate, explicit test failure."""

    def fail(*_args: Any, **_kwargs: Any):
        raise AssertionError("P3-T05 pytest must not use a real network")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    real_run = subprocess.run

    def guarded_run(args, *rest, **kwargs):
        if list(args) and list(args)[0] == "docker":
            raise AssertionError("Docker runtime checks are not pytest tests")
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)


def _run(awaitable):
    return asyncio.run(awaitable)


def _product_page() -> dict[str, Any]:
    return {
        "count": len(PRODUCTS),
        "limit": 100,
        "offset": 0,
        "results": PRODUCTS,
    }


class InMemoryMCPRouter:
    """MCP-shaped in-memory transport backed by the real tool functions."""

    async def call_product_tool(self, name: str, arguments=None):
        arguments = arguments or {}
        if name == "list_products":
            return await product_tools.list_products()
        if name == "get_product_details":
            return await product_tools.get_product_details(
                arguments["external_product_id"]
            )
        raise AssertionError(f"unexpected Product MCP tool: {name}")

    async def call_stock_tool(self, name: str, arguments=None):
        arguments = arguments or {}
        if name == "list_branch_stock":
            return stock_tools.list_branch_stock(arguments["branch_id"])
        if name == "get_stock_for_product":
            return stock_tools.get_stock_for_product(
                arguments["external_product_id"]
            )
        if name == "find_branches_for_shopping_list":
            items = [
                {
                    "external_product_id": item["external_product_id"],
                    "quantity": item["quantity"],
                }
                for item in arguments["items"]
            ]
            return stock_tools.find_branches_for_shopping_list(
                items
            )
        raise AssertionError(f"unexpected Stock MCP tool: {name}")


@pytest.fixture
def in_memory_boundaries(monkeypatch: pytest.MonkeyPatch):
    """Install deterministic Product API and read-only PostgreSQL doubles."""

    async def fake_product_list(limit: int = 100, offset: int = 0):
        assert limit == 100
        assert offset == 0
        return {"status": "success", "data": _product_page()}

    async def fake_product_details(identifier: str):
        product = next(
            (item for item in PRODUCTS if item["sku"] == identifier), None
        )
        if product is None:
            return {"status": "not_found", "data": None}
        raw = _public_product_detail(product)
        raw.update({"id": product["id"], "sku": product["sku"]})
        return {"status": "success", "data": raw}

    def fake_branch(branch_id: int):
        return STOCK.get(branch_id)

    def fake_product_stock(product_id: str):
        return [
            {
                "branch_id": branch["branch_id"],
                "branch_name": branch["branch_name"],
                "quantity": next(
                    (
                        row["quantity"]
                        for row in branch["stocks"]
                        if row["external_product_id"] == product_id
                    ),
                    0,
                ),
            }
            for branch in STOCK.values()
        ]

    monkeypatch.setattr(product_api, "list_products", fake_product_list)
    monkeypatch.setattr(product_api, "get_product_details", fake_product_details)
    monkeypatch.setattr(stock_repository, "fetch_branch_stock", fake_branch)
    monkeypatch.setattr(stock_repository, "fetch_product_stock", fake_product_stock)


def _public_client(boundaries) -> Any:
    service = QuestionService(InMemoryMCPRouter(), ollama_enabled=False)
    return create_app(service, {"TESTING": True}).test_client()


@pytest.mark.parametrize(
    ("question", "expected_status"),
    [
        ("Give me details about product product-1.", "success"),
        ("Which branch has stock of product product-1?", "success"),
        ("What products are available in branch 1?", "success"),
        ("Where can I find 1 units of product-1 and 2 units of product-2?", "success"),
        ("Tell me a joke", "unsupported"),
    ],
)
def test_public_questions_compose_real_service_and_mcp_tools(
    in_memory_boundaries, question, expected_status
):
    response = _public_client(in_memory_boundaries).post(
        "/questions", json={"question": question}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == expected_status
    assert "error" not in payload or expected_status == "unsupported"
    assert "password" not in response.get_data(as_text=True).lower()

    if question.startswith("Give me details"):
        assert "product-1" in payload["answer"]
        assert payload["data"]["tool_results"]["get_product_details"] == _public_product_detail(PRODUCTS[0])
    elif question.startswith("Which branch"):
        assert "Widget (product-1)" in payload["answer"]
        assert "North" not in payload["answer"]
        assert payload["data"]["tool_results"]["get_stock_for_product"][
            "branches"
        ] == [{"branch_id": 1, "branch_name": "Central", "quantity": 5}]
    elif question.startswith("What products"):
        assert payload["answer"] == "Stock at Central: Widget (product-1): quantity 5."
        assert payload["data"]["tool_results"]["list_branch_stock"] == STOCK[1]
    elif question.startswith("Where can"):
        assert payload["answer"] == (
            "The shopping plan is complete with strategy multiple_branches. "
            "Visits: Central: product-1 requested 1, available 5; "
            "North: product-2 requested 2, available 3."
        )
        assert payload["data"]["tool_results"][
            "find_branches_for_shopping_list"
        ]["complete"] is True
    else:
        assert payload["answer"] == (
            "This question is outside the supported inventory scope."
        )


def test_public_questions_are_independent_and_unknown_product_is_not_invented(
    in_memory_boundaries,
):
    client = _public_client(in_memory_boundaries)
    first = client.post(
        "/questions", json={"question": "Give me details about product product-1."}
    )
    second = client.post(
        "/questions", json={"question": "Give me details about product unknown."}
    )

    assert first.get_json()["status"] == "success"
    assert second.get_json()["status"] == "unavailable"
    assert second.get_json()["data"] == {}
    assert "unknown" not in second.get_json().get("answer", "").lower()


def test_public_questions_report_partial_when_one_mcp_result_is_unavailable(
    in_memory_boundaries, monkeypatch: pytest.MonkeyPatch,
):
    def unavailable_stock(_product_id: str):
        raise stock_repository.StockRepositoryUnavailableError

    monkeypatch.setattr(stock_repository, "fetch_product_stock", unavailable_stock)
    response = _public_client(in_memory_boundaries).post(
        "/questions", json={"question": "Which branch has stock of product product-1?"}
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "partial"
    assert payload["data"]["tool_results"] == {
        "get_product_details": {
            **_public_product_detail(PRODUCTS[0]),
        }
    }
    assert "Central" not in payload["answer"]
    assert "quantity 5" not in payload["answer"]


@pytest.mark.parametrize(
    "failure",
    ["unavailable", "timeout", "invalid"],
)
def test_product_api_failures_remain_safe_public_statuses(
    monkeypatch: pytest.MonkeyPatch, failure
):
    async def failing_list(limit: int = 100, offset: int = 0):
        assert limit == 100
        assert offset == 0
        code = {
            "unavailable": "PRODUCT_API_UNAVAILABLE",
            "timeout": "PRODUCT_API_TIMEOUT",
            "invalid": "PRODUCT_API_INVALID_RESPONSE",
        }[failure]
        return {"status": "error", "error": {"code": code, "message": "safe"}}

    monkeypatch.setattr(product_api, "list_products", failing_list)
    client = _public_client(None)
    response = client.post(
        "/questions", json={"question": "Give me details about product Widget."}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "unavailable"
    assert payload["data"] == {}
    serialized = response.get_data(as_text=True).lower()
    assert "traceback" not in serialized
    assert "widget" not in serialized
    assert "product-1" not in serialized
    assert "secret" not in serialized
    assert failure.upper() not in serialized


def test_stock_mcp_boundary_is_read_only_and_exposes_no_private_data(
    in_memory_boundaries,
):
    result = stock_tools.list_branch_stock(1)

    assert result["status"] == "success"
    assert result["data"]["stocks"]
    serialized = str(result)
    assert "password_hash" not in serialized
    assert "revoked_tokens" not in serialized
    assert not hasattr(stock_repository, "execute_sql")


def test_client_web_is_anonymous_and_renders_received_data_as_text():
    source = (ROOT / "client_web" / "app.js").read_text(encoding="utf-8")
    assert 'credentials: "omit"' in source
    assert "Authorization" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "innerHTML" not in source
    assert "textContent" in source
    assert 'fetch("/questions"' in source


@pytest.fixture
def backoffice_client():
    app = create_backoffice_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "JWT_SECRET_KEY": "integration-only-secret-32-bytes-minimum",
        "BCRYPT_ROUNDS": "4",
        "PRODUCT_API_BASE_URL": "http://product-api.test",
    })
    with app.app_context():
        connection = db.engine.raw_connection()
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.create_function("char_length", 1, len)
        connection.close()
        db.create_all()
        # SQLite renders PostgreSQL's partial admin-only unique index as a
        # table-wide unique index.  Remove that dialect artifact in the
        # harness so the public common-user lifecycle remains testable here;
        # the PostgreSQL suite verifies the real partial index.
        db.session.execute(text("DROP INDEX uq_users_single_admin"))
        db.session.commit()
        db.session.add_all([
            Branch(id=1, name="Central"),
            Branch(id=2, name="North"),
            User(
                id=1,
                username="admin",
                password_hash=bcrypt.hashpw(
                    b"admin-password", bcrypt.gensalt(rounds=4)
                ).decode(),
                role="admin",
            ),
            User(
                id=2,
                username="alice",
                password_hash=bcrypt.hashpw(
                    b"alice-password", bcrypt.gensalt(rounds=4)
                ).decode(),
                role="common_user",
                branch_id=2,
            ),
        ])
        db.session.commit()
    # SQLite cannot autoincrement SQLAlchemy BigInteger primary keys.  Keep
    # this adapter local to the in-memory harness; PostgreSQL integration
    # tests exercise the native sequence behavior.
    next_user_id = iter(range(3, 1000))
    next_stock_id = iter(range(1, 1000))

    def assign_sqlite_user_id(_mapper, _connection, target):
        if target.id is None:
            target.id = next(next_user_id)

    def assign_sqlite_stock_id(_mapper, _connection, target):
        if target.id is None:
            target.id = next(next_stock_id)

    event.listen(User, "before_insert", assign_sqlite_user_id)
    event.listen(Stock, "before_insert", assign_sqlite_stock_id)
    try:
        yield app.test_client(), app
    finally:
        event.remove(User, "before_insert", assign_sqlite_user_id)
        event.remove(Stock, "before_insert", assign_sqlite_stock_id)
        with app.app_context():
            db.session.remove()
            db.drop_all()


def _login(client, username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    payload = response.get_json()
    token = (payload.get("data") or {}).get("access_token")
    return response, ({"Authorization": f"Bearer {token}"} if token else {})


def test_backoffice_admin_common_user_lifecycle_and_stock_authorization(
    backoffice_client, monkeypatch,
):
    client, app = backoffice_client
    admin_login, admin_headers = _login(client, "admin", "admin-password")
    assert admin_login.status_code == 200

    created = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"username": "bob", "password": "bob-password", "branch_id": 2},
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    bob_id = created.get_json()["data"]["id"]
    assert created.get_json()["data"]["role"] == "common_user"

    changed = client.patch(
        f"/api/v1/users/{bob_id}",
        headers=admin_headers,
        json={"username": "bob-renamed", "branch_id": 1},
    )
    assert changed.status_code == 200
    assert changed.get_json()["data"]["branch"]["id"] == 1

    old_login, _ = _login(client, "bob-renamed", "bob-password")
    assert old_login.status_code == 200
    old_access = {"Authorization": f"Bearer {old_login.get_json()['data']['access_token']}"}
    password_change = client.patch(
        f"/api/v1/users/{bob_id}/password",
        headers=admin_headers,
        json={"new_password": "new-bob-password"},
    )
    assert password_change.status_code == 204
    assert client.get("/api/v1/auth/me", headers=old_access).status_code == 401

    common_login, common_headers = _login(client, "bob-renamed", "new-bob-password")
    assert common_login.status_code == 200
    assert common_headers["Authorization"].startswith("Bearer ")

    product_calls = []

    def fake_product(identifier):
        product_calls.append(identifier)
        return {
            "id": 1,
            "external_product_id": identifier,
            "sku": identifier,
            "name": "Widget",
        }

    monkeypatch.setattr(backoffice_product_routes, "get_product", fake_product)
    monkeypatch.setattr(backoffice_stock_services, "_product", fake_product)
    product_details = client.get(
        "/api/v1/products/product-1", headers=common_headers
    )
    assert product_details.status_code == 200
    assert product_details.get_json()["data"]["name"] == "Widget"
    assert product_calls == ["product-1"]

    def add_stock_in_memory(branch_id, external_product_id, quantity):
        stock = Stock(
            branch_id=branch_id,
            external_product_id=external_product_id,
            quantity=quantity,
        )
        db.session.add(stock)
        db.session.flush()
        return stock

    monkeypatch.setattr(
        backoffice_stock_services.repositories,
        "add_stock",
        add_stock_in_memory,
    )
    added = client.post(
        "/api/v1/stocks/product-1/add",
        headers=common_headers,
        json={"quantity": 5},
    )
    assert added.status_code == 200
    assert added.get_json()["data"]["quantity"] == 5
    assert added.get_json()["data"]["product"] == {"name": "Widget"}
    removed = client.post(
        "/api/v1/stocks/product-1/remove",
        headers=common_headers,
        json={"quantity": 2},
    )
    assert removed.status_code == 200
    assert removed.get_json()["data"]["quantity"] == 3
    insufficient = client.post(
        "/api/v1/stocks/product-1/remove",
        headers=common_headers,
        json={"quantity": 4},
    )
    assert insufficient.status_code == 422
    assert insufficient.get_json()["error"]["code"] == "INSUFFICIENT_STOCK"
    foreign_scope = client.post(
        "/api/v1/stocks/product-1/add?branch_id=2",
        headers=common_headers,
        json={"quantity": 1},
    )
    assert foreign_scope.status_code == 400

    admin_stock = client.post(
        "/api/v1/stocks/product-1/add",
        headers=admin_headers,
        json={"quantity": 1},
    )
    assert admin_stock.status_code == 403
    with pytest.raises(backoffice_stock_services.AdminStockForbiddenError):
        backoffice_stock_services.authorize_stock_user(User(role="admin"))

    deleted = client.delete(f"/api/v1/users/{bob_id}", headers=admin_headers)
    assert deleted.status_code == 204
    deleted_login, _ = _login(client, "bob-renamed", "new-bob-password")
    assert deleted_login.status_code == 403
    assert "password_hash" not in json.dumps(common_login.get_json())
    assert len(product_calls) >= 3
    assert all(identifier == "product-1" for identifier in product_calls)
    assert "products" not in db.metadata.tables
    with app.app_context():
        persisted_stocks = Stock.query.all()
        assert persisted_stocks
        assert all("name" not in stock.__dict__ for stock in persisted_stocks)
        assert all(stock.external_product_id == "product-1" for stock in persisted_stocks)


def test_stock_database_double_is_select_only_and_rejects_private_or_arbitrary_sql(
    monkeypatch,
):
    class ReadOnlyPostgresDouble:
        def __init__(self):
            self.statements: list[str] = []

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters):
            normalized = " ".join(str(statement).split()).upper()
            self.statements.append(normalized)
            if not normalized.startswith("SELECT "):
                raise AssertionError("Stock MCP database double permits SELECT only")
            if any(table in normalized for table in ("USERS", "REVOKED_TOKENS")):
                raise AssertionError("Stock MCP database double exposed a private table")
            if "FROM BRANCHES" not in normalized and "FROM STOCKS" not in normalized:
                raise AssertionError("Stock MCP database double rejected only approved queries")
            if "FROM BRANCHES" in normalized:
                self.rows = [(1, "Central")]
            else:
                self.rows = []

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    database = ReadOnlyPostgresDouble()
    monkeypatch.setattr(stock_repository, "_connect", lambda: database)
    assert stock_repository.fetch_branch_stock(1) == {
        "branch_id": 1,
        "branch_name": "Central",
        "stocks": [],
    }
    assert stock_tools.list_branch_stock(1)["status"] == "success"
    assert all(statement.startswith("SELECT ") for statement in database.statements)
    with pytest.raises(AssertionError):
        database.execute("INSERT INTO stocks VALUES (%s)", (1,))
    with pytest.raises(AssertionError):
        database.execute("SELECT * FROM users", ())
    with pytest.raises(AssertionError):
        database.execute("SELECT arbitrary_sql()", ())
    assert not hasattr(stock_repository, "execute_sql")
    assert {
        "status": "success",
        "data": {"branch_id": 1, "branch_name": "Central", "stocks": []},
    } == stock_tools.list_branch_stock(1)


def test_client_web_executes_anonymously_with_flask_response_fetch_double(
    in_memory_boundaries,
):
    flask_response = _public_client(in_memory_boundaries).post(
        "/questions", json={"question": "Give me details about product product-1."}
    )
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    script = r'''
const fs = require("fs");
const vm = require("vm");

class Element {
  constructor(id = "") {
    this.id = id;
    this.value = "";
    this.disabled = false;
    this.hidden = false;
    this.dataset = {};
    this.className = "";
    this.children = [];
    this.parentNode = null;
    this.listeners = {};
    this._text = "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() {
    return this._text + this.children.map(child => child.textContent || "").join("");
  }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  dispatch(name, extra = {}) {
    const event = {preventDefault() {}, target: this, currentTarget: this, ...extra};
    for (const fn of (this.listeners[name] || [])) fn(event);
  }
  append(...nodes) {
    for (const node of nodes) { node.parentNode = this; this.children.push(node); }
  }
  setAttribute() {}
  scrollIntoView() {}
  focus() {}
  remove() {
    if (this.parentNode) {
      this.parentNode.children = this.parentNode.children.filter(child => child !== this);
      this.parentNode = null;
    }
  }
  querySelectorAll(selector) {
    const className = selector.startsWith(".") ? selector.slice(1) : null;
    const found = [];
    const visit = node => {
      for (const child of node.children) {
        if (className && child.className.split(/\s+/).includes(className)) found.push(child);
        visit(child);
      }
    };
    visit(this);
    return found;
  }
}

const ids = [
  "question-form", "question", "submit-button", "clear-button",
  "conversation-log", "empty-state", "character-count", "request-status",
  "error-live", "service-status", "service-status-text"
];
const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
elements["conversation-log"].append(elements["empty-state"]);
const calls = [];
const context = {
  document: {
    querySelector(selector) { return elements[selector.slice(1)]; },
    querySelectorAll() { return []; },
    createElement() { return new Element("created"); },
  },
  fetch: async (url, options) => {
    calls.push([url, options]);
    if (url === "/health") {
      return {ok: true, status: 200, json: async () => ({status: "ok"})};
    }
    return {ok: true, status: 200, json: async () => PAYLOAD};
  },
  console,
  setTimeout,
};

(async () => {
  vm.runInNewContext(fs.readFileSync("client_web/app.js", "utf8"), context);
  await new Promise(resolve => setTimeout(resolve, 0));
  if (elements["submit-button"].disabled !== true) {
    throw new Error("empty question was enabled");
  }
  elements.question.value = "  Where?  ";
  elements.question.dispatch("input");
  if (elements["submit-button"].disabled !== false) {
    throw new Error("valid question was disabled");
  }
  elements["question-form"].dispatch("submit");
  await new Promise(resolve => setTimeout(resolve, 0));

  const questionCalls = calls.filter(call => call[0] === "/questions");
  if (questionCalls.length !== 1) throw new Error("wrong fetch route");
  if (questionCalls[0][1].credentials !== "omit") {
    throw new Error("request was not anonymous");
  }
  if (questionCalls[0][1].headers.Authorization) {
    throw new Error("authorization leaked");
  }
  if (!elements["conversation-log"].textContent.includes(PAYLOAD.answer)) {
    throw new Error("answer not rendered");
  }
  if (elements["conversation-log"].innerHTML !== undefined) {
    throw new Error("unsafe DOM mock");
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(
        ["node", "-e", "const PAYLOAD = JSON.parse(process.env.P3_PAYLOAD);\n" + script],
        cwd=ROOT,
        env={**__import__("os").environ, "P3_PAYLOAD": json.dumps(flask_payload)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
