"""Contract tests for the native Backoffice interface.

The JavaScript scenarios run the real static application with a small local
DOM, storage, confirmation and fetch double.  They do not start a browser,
HTTP server, database, socket, or external service.  Assertions observe
requests, rendered text, accessible state and visible actions; they do not
require a particular DOM layout.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "backoffice" / "static"
ASSETS = {name: STATIC / name for name in ("index.html", "app.js", "styles.css")}


def _read(name: str) -> str:
    path = ASSETS[name]
    assert path.is_file(), f"asset absent: {path}"
    return path.read_text(encoding="utf-8")


class _HtmlParser(HTMLParser):
    """Collect only generic accessibility facts and a serialisable fixture."""

    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__()
        self.root = {"tag": "body", "attrs": {}, "children": []}
        self.stack = [self.root]
        self.controls: list[dict[str, str]] = []
        self.labels: set[str] = set()
        self.label_depth = 0
        self.wrapped_controls: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        node = {"tag": tag, "attrs": data, "children": []}
        self.stack[-1]["children"].append(node)
        if tag in {"input", "select", "textarea", "button"}:
            control = {"tag": tag, "id": data.get("id", ""), "name": data.get("name", "")}
            self.controls.append(control)
            if self.label_depth and control["id"]:
                self.wrapped_controls.add(control["id"])
        if tag == "label":
            self.label_depth += 1
            if data.get("for"):
                self.labels.add(data["for"])
        if tag not in self.void:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self.label_depth:
            self.label_depth -= 1
        if tag not in self.void and len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1]["children"].append(data)


def _fixture() -> dict:
    parser = _HtmlParser()
    parser.feed(_read("index.html"))
    return parser.root


def _run(mode: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.fail("Node.js is required for local Backoffice contract tests")

    source = json.dumps(_read("app.js"))
    fixture = json.dumps(_fixture())
    requested_mode = json.dumps(mode)
    harness = r'''
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const vm = require("vm");
const source = __SOURCE__;
const fixture = __FIXTURE__;
const mode = __MODE__;

const pending = [];
const eventPromises = [];

class Element {
  constructor(tag, attrs = {}) {
    this.tagName = String(tag).toUpperCase();
    this.attributes = {};
    this.children = [];
    this.parentElement = null;
    this.listeners = {};
    this.hidden = false;
    this.disabled = false;
    this.dataset = {};
    this.value = attrs.value ?? "";
    this.defaultValue = this.value;
    this.name = attrs.name ?? "";
    this.type = attrs.type ?? "";
    this.textContent = "";
    this.className = attrs.class ?? "";
    this.style = {};
    for (const [key, value] of Object.entries(attrs)) this.setAttribute(key, value);
    if (Object.prototype.hasOwnProperty.call(attrs, "hidden")) this.hidden = true;
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "id") this.id = String(value);
    if (name === "name") this.name = String(value);
    if (name === "type") this.type = String(value);
    if (name === "class") this.className = String(value);
    if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
    if (name === "value") { this.value = String(value); this.defaultValue = this.value; }
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name); }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...nodes) { for (const node of nodes) { if (!node || typeof node === "string") continue; node.parentElement = this; this.children.push(node); } }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  addEventListener(type, listener) { (this.listeners[type] ??= []).push(listener); }
  dispatchEvent(event) {
    event.target ??= this;
    event.currentTarget = this;
    for (const listener of this.listeners[event.type] ?? []) {
      const result = listener(event);
      if (result && typeof result.then === "function") eventPromises.push(result.catch(() => undefined));
    }
    return true;
  }
  click() { this.dispatchEvent({ type: "click", target: this }); }
  reset() { for (const field of descendants(this).filter((item) => ["INPUT", "SELECT", "TEXTAREA"].includes(item.tagName))) field.value = field.defaultValue; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  querySelectorAll(selector) { return descendants(this).filter((item) => matches(item, selector)); }
  closest(selector) { let current = this; while (current) { if (matches(current, selector)) return current; current = current.parentElement; } return null; }
  get classList() {
    return {
      contains: (name) => this.className.split(/\s+/).includes(name),
      add: (...names) => { const set = new Set(this.className.split(/\s+/).filter(Boolean)); names.forEach((name) => set.add(name)); this.className = [...set].join(" "); },
      remove: (...names) => { const set = new Set(this.className.split(/\s+/).filter(Boolean)); names.forEach((name) => set.delete(name)); this.className = [...set].join(" "); },
    };
  }
}

function descendants(root) {
  const result = [];
  for (const child of root.children ?? []) result.push(child, ...descendants(child));
  return result;
}
function matches(element, selector) {
  if (selector.includes(",")) return selector.split(",").some((part) => matches(element, part.trim()));
  if (selector.startsWith("#")) return element.id === selector.slice(1);
  const attribute = selector.match(/^([a-zA-Z]*)\[([^=\]]+)(?:=["']?([^\]"']+)["']?)?\]$/);
  if (attribute) {
    const actual = element.getAttribute(attribute[2]);
    return (!attribute[1] || element.tagName === attribute[1].toUpperCase()) && actual !== null && (attribute[3] === undefined || actual === attribute[3]);
  }
  if (selector.startsWith(".")) return element.classList.contains(selector.slice(1));
  return element.tagName === selector.toUpperCase();
}
function make(node) {
  const element = new Element(node.tag, node.attrs ?? {});
  for (const child of node.children ?? []) {
    if (typeof child === "string") element.textContent += child;
    else element.append(make(child));
  }
  return element;
}

const document = {
  body: make(fixture),
  createElement: (tag) => new Element(tag),
  getElementById: (id) => document.querySelector("#" + id),
  querySelector: (selector) => document.querySelectorAll(selector)[0] ?? null,
  querySelectorAll: (selector) => descendants(document.body).filter((item) => matches(item, selector)),
  listeners: {},
  addEventListener(type, listener) { (this.listeners[type] ??= []).push(listener); },
  dispatchEvent(event) { for (const listener of this.listeners[event.type] ?? []) listener(event); },
};
global.document = document;
global.window = global;
global.confirm = (message) => { confirmations.push(String(message)); return true; };

const confirmations = [];
const storage = new Map();
const storageKeys = [];
const seeded = !mode.startsWith("login_");
global.sessionStorage = {
  getItem: (key) => { if (!storage.has(key) && seeded) storage.set(key, storageKeys.length ? "old-refresh" : "old-access"); storageKeys.push(key); return storage.get(key) ?? null; },
  setItem: (key, value) => { storageKeys.push(key); storage.set(key, String(value)); },
  removeItem: (key) => storage.delete(key),
  clear: () => storage.clear(),
};
global.localStorage = { getItem: () => null, setItem: () => { throw new Error("localStorage is forbidden"); }, removeItem: () => {} };
global.FormData = class {
  constructor(form) { this.values = new Map(); for (const field of descendants(form).filter((item) => item.name)) this.values.set(field.name, field.value); }
  get(name) { return this.values.get(name) ?? null; }
};

const calls = [];
const snapshots = [];
const errors = [];
const applicationLogs = [];
function response(status, body, raw = undefined) {
  return { status, ok: status >= 200 && status < 300, text: async () => raw === undefined ? JSON.stringify(body) : raw };
}
function currentUser(role) { return { id: 12, username: role === "admin" ? "admin" : "alice", role, branch: { id: 2, name: "Toulon" } }; }
function roleForMode() { return mode.includes("common") || mode.includes("stock") || mode === "reads" || mode.includes("422") || mode.includes("conflict") ? "common_user" : "admin"; }
function mutation(path, method) {
  return (method === "POST" && (/\/api\/v1\/users$/.test(path) || /\/api\/v1\/stocks\/[^/]+\/(?:add|remove)$/.test(path)))
    || (method === "PATCH" && /\/api\/v1\/users\/\d+/.test(path))
    || (method === "DELETE" && /\/api\/v1\/users\/\d+$/.test(path));
}
function errorPayload(code) { return { error: { code, message: `backend ${code}` } }; }

global.fetch = async (value, options = {}) => {
  const path = String(value);
  const route = path.split("?", 1)[0];
  const method = options.method ?? "GET";
  if (!path.startsWith("/api/")) throw new Error("external network is forbidden");
  const headers = options.headers instanceof Headers ? Object.fromEntries(options.headers.entries()) : Object.fromEntries(Object.entries(options.headers ?? {}).map(([key, item]) => [key.toLowerCase(), item]));
  calls.push({ path, method, headers, body: options.body ?? null });

  if (mode.startsWith("refresh") && calls.length === 1) return response(401, errorPayload("EXPIRED"));
  if (mode === "refresh_once" && calls.length === 2) return response(200, { data: { access_token: "new-access" } });
  if (mode.startsWith("refresh_failure") && calls.length === 2) return response(401, errorPayload("REVOKED"));
  if (mode === "refresh_retry_401" && calls.length === 2) return response(200, { data: { access_token: "new-access" } });
  if (mode === "refresh_retry_401" && calls.length === 3) return response(401, errorPayload("STILL_EXPIRED"));
  if (mode === "business_refresh_once" && route === "/api/v1/branches" && method === "GET" && calls.filter((call) => call.path.split("?", 1)[0] === route).length === 1) return response(401, errorPayload("EXPIRED"));
  if (mode === "business_refresh_once" && route === "/api/v1/auth/refresh") return response(200, { data: { access_token: "business-access" } });
  if (mode.startsWith("login_error_") && path.endsWith("/auth/login")) return response(Number(mode.slice(12)), errorPayload("LOGIN_ERROR"));
  if (mode === "error_400" && method === "POST" && path.endsWith("/users")) return response(400, errorPayload("VALIDATION_ERROR"));
  if (mode === "error_403" && path.endsWith("/branches")) return response(403, errorPayload("FORBIDDEN"));
  if (mode === "error_404" && method === "GET" && /\/users\/\d+$/.test(path)) return response(404, errorPayload("USER_NOT_FOUND"));
  if (mode === "error_409" && method === "POST" && path.endsWith("/users")) return response(409, errorPayload("CONFLICT"));
  if (mode === "error_422" && method === "POST" && /\/stocks\/[^/]+\/remove$/.test(path)) return response(422, errorPayload("INSUFFICIENT_STOCK"));
  if (mode === "error_500" && path.endsWith("/branches")) return response(500, errorPayload("SERVER_ERROR"));
  if (mode === "error_non_json" && path.endsWith("/branches")) return response(500, {}, "<html>failure</html>");
  if (mode === "error_rejection" && path.endsWith("/branches")) throw new Error("transport unavailable");
  if (mode === "logout_network_rejection" && path.includes("/auth/logout")) throw new Error("network unavailable");
  if (mode === "logout_failure" && path.endsWith("/auth/logout")) return response(500, errorPayload("LOGOUT_FAILED"));
  if (mode === "logout_refresh_failure" && path.endsWith("/auth/logout/refresh")) return response(500, errorPayload("LOGOUT_REFRESH_FAILED"));
  if (mode.startsWith("mutation_success") && mutation(path, method)) return response(200, { data: { id: 42, quantity: 3 } });
  if (mode.startsWith("mutation_error") && mutation(path, method)) return response(409, errorPayload("MUTATION_REJECTED"));
  if (mode.startsWith("mutation_double") && mutation(path, method)) return new Promise((resolve) => pending.push(resolve));
  if (mode === "view_loading" && path.endsWith("/branches")) return new Promise((resolve) => pending.push(resolve));

  if (path.endsWith("/auth/login")) return response(200, { data: { access_token: "access", refresh_token: "refresh", user: currentUser(mode.includes("common") ? "common_user" : "admin") } });
  if (path.endsWith("/auth/me")) return response(200, { data: currentUser(roleForMode()) });
  if (route === "/api/v1/users" && method === "GET") return response(200, { data: [{ id: 42, username: "alice", role: "common_user", branch: { id: 2 } }], meta: { count: 17 } });
  if (/\/users\/\d+$/.test(path) && method === "GET") return response(200, { data: { id: 42, username: "alice", role: "common_user", branch: { id: 2 } } });
  if (path.endsWith("/users") && method === "POST") return response(201, { data: { id: 42 } });
  if (path.includes("/users/") && method === "PATCH") return response(200, { data: { id: 42 } });
  if (path.includes("/users/") && method === "DELETE") return response(204, {});
  if (path.endsWith("/branches") || /\/branches\/\d+$/.test(path)) return response(200, { data: [{ id: 2, name: "Toulon" }, { id: 4, name: "Paris" }] });
  if (path.endsWith("/products") || /\/products\/[^/]+$/.test(path)) return response(200, { data: [{ external_product_id: "product-123", name: "Example" }, { external_product_id: "product-456", name: "Second" }] });
  if (path.includes("/stocks") && method === "GET") return response(200, { data: { branch: { id: 2, name: "Toulon" }, items: [{ external_product_id: "product-123", available: 3 }] } });
  if (path.includes("/stocks/") && method === "POST") return response(200, { data: { quantity: 3 } });
  return response(200, { data: [] });
};

function event(type) { return { type, preventDefault() { this.defaultPrevented = true; } }; }
async function flush() { for (let index = 0; index < 30; index++) await Promise.resolve(); }
function all() { return descendants(document.body); }
function forms() { return all().filter((item) => item.tagName === "FORM"); }
function fields(form) { return descendants(form).filter((item) => item.name); }
function visible(item) { for (let current = item; current; current = current.parentElement) if (current.hidden) return false; return true; }
function visibleForms() { return forms().filter(visible); }
function field(form, name) { return fields(form).find((item) => item.name === name); }
function setField(form, name, value) { const item = field(form, name); if (item) item.value = String(value); }
function firstFormWith(name) { return visibleForms().find((form) => field(form, name)); }
function submit(form) { if (form) form.dispatchEvent(event("submit")); }
function textOf(item) { return String(item.textContent ?? "") + allChildrenText(item); }
function allChildrenText(item) { return (item.children ?? []).map(textOf).join(" "); }
function messages() { return all().filter((item) => ["status", "alert"].includes(item.getAttribute("role"))).map(textOf).join(" "); }
function buttons() { return all().filter((item) => ["BUTTON", "A"].includes(item.tagName)); }
function clickText(pattern) { const target = buttons().find((item) => visible(item) && pattern.test(textOf(item))); if (target) target.click(); return Boolean(target); }
function clickViews() { for (const pattern of [/dashboard|tableau/i, /branch|succurs/i, /produit/i, /stock/i, /utilisateur|user/i]) clickText(pattern); }
function visibleActionTexts() { return buttons().filter(visible).map(textOf).filter((value) => value.trim()); }
function loadingVisible() { return all().some((item) => visible(item) && (item.getAttribute("aria-busy") === "true" || /chargement|loading|en cours|pending/i.test(textOf(item)))); }
function finishPending() { while (pending.length) pending.shift()(response(200, { data: [] })); }
function userCreationForms() { return visibleForms().filter((form) => field(form, "username") && field(form, "password") && field(form, "branch_id")); }
function userEditForms() { return visibleForms().filter((form) => field(form, "username") && field(form, "branch_id") && !field(form, "password") && !field(form, "new_password")); }
function userPasswordForms() { return visibleForms().filter((form) => field(form, "new_password")); }
function userMutationForms() { return [...new Set([...userCreationForms(), ...userEditForms(), ...userPasswordForms(), ...userDetailForms()])]; }
function stockForm() { return firstFormWith("quantity"); }
function setCommonValues(form) {
  setField(form, "username", field(form, "password") ? "created-alice" : "changed-alice"); setField(form, "password", "created-secret"); setField(form, "new_password", "changed-secret");
  setField(form, "user_id", "42"); setField(form, "branch_id", "4"); setField(form, "product_id", "product-123"); setField(form, "external_product_id", "product-123"); setField(form, "quantity", "3");
}
function submitStock(action) {
  const form = stockForm(); if (!form) return;
  setCommonValues(form); setField(form, "action", action); const selector = field(form, "action"); if (selector) selector.dispatchEvent(event("change")); submit(form);
}
function submitVisibleUserForms() { for (const form of userMutationForms()) { setCommonValues(form); submit(form); } }
function userDetailForms() {
  return visibleForms().filter((form) => field(form, "user_id") && !field(form, "username") && !field(form, "password") && !field(form, "new_password"));
}
function submitUserDetailForms() {
  for (const form of userDetailForms()) { setField(form, "user_id", "42"); submit(form); }
}
function stockDetailForms() {
  return visibleForms().filter((form) => field(form, "external_product_id") || (field(form, "product_id") && !field(form, "quantity")));
}
function submitStockDetailForms() {
  for (const form of stockDetailForms()) {
    setField(form, "external_product_id", "product-123"); setField(form, "product_id", "product-123"); submit(form);
  }
}

global.console = {
  log: (...args) => applicationLogs.push(args.map(String).join(" ")),
  debug: (...args) => applicationLogs.push(args.map(String).join(" ")),
  info: (...args) => applicationLogs.push(args.map(String).join(" ")),
  warn: (...args) => applicationLogs.push(args.map(String).join(" ")),
  error: (...args) => applicationLogs.push(args.map(String).join(" ")),
};

vm.runInThisContext(source, { filename: "backoffice/static/app.js" });
await flush();

if (mode.startsWith("login_")) {
  const form = firstFormWith("password");
  setField(form, "username", mode.includes("common") ? "alice" : "admin"); setField(form, "password", "secret-password"); submit(form); await flush();
}
if (["logout", "logout_failure", "logout_refresh_failure", "logout_network_rejection"].includes(mode)) { clickText(/déconnect|logout/i); await flush(); }
if (mode.startsWith("nav_")) clickViews();
if (mode === "user_crud") { clickText(/utilisateur|user/i); await flush();
  for (const status of ["active", "deleted", "all"]) { const form = firstFormWith("status"); if (form) { setField(form, "status", status); const branch = field(form, "branch_id"); if (branch) branch.value = status === "all" ? "" : "2"; form.dispatchEvent(event("change")); submit(form); } }
  submitVisibleUserForms(); submitUserDetailForms();
}
if (mode === "common_forbidden") { clickText(/utilisateur|user/i); await flush(); submitVisibleUserForms(); }
if (mode === "reads") { clickViews(); await flush();
  for (const name of ["branch_id", "external_product_id", "user_id"]) { const form = firstFormWith(name); if (form) { setField(form, name, name === "user_id" ? "42" : name === "branch_id" ? "2" : "product-123"); submit(form); } }
  submitStockDetailForms();
  const stockFilter = firstFormWith("available_only"); if (stockFilter) { setField(stockFilter, "available_only", "true"); submit(stockFilter); await flush(); setField(stockFilter, "available_only", "false"); submit(stockFilter); await flush(); }
  submitStock("add"); await flush(); submitStock("remove"); await flush();
}
if (mode === "business_refresh_once") { clickText(/branch|succurs/i); await flush(); }
if (mode === "identifier_validation") {
  clickText(/utilisateur|user/i); await flush();
  const filter = firstFormWith("status");
  if (filter) { setField(filter, "branch_id", "1.5"); submit(filter); }
  for (const form of userMutationForms()) {
    setCommonValues(form);
    setField(form, "user_id", "not-a-number");
    setField(form, "branch_id", "0");
    submit(form);
  }
  await flush();
  clickText(/branch|succurs/i); await flush();
  const branch = firstFormWith("branch_id");
  if (branch) { setField(branch, "branch_id", "not-a-number"); submit(branch); }
  await flush();
}
if (mode === "reads_branches" || mode === "reads_products") { clickText(mode === "reads_branches" ? /branch|succurs/i : /produit/i); await flush(); }
if (mode === "mutation_success_stock" || mode === "mutation_success_admin") {
  clickText(mode === "mutation_success_stock" ? /stock/i : /utilisateur|user/i); await flush();
  const form = mode === "mutation_success_stock" ? stockForm() : userCreationForms()[0];
  if (form) { setCommonValues(form); submit(form); await flush(); }
}
if (mode === "stock_validation" || mode === "stock_validation_decimal" || mode === "stock_validation_negative") { clickText(/stock/i); await flush(); const form = stockForm(); if (form) { setCommonValues(form); setField(form, "quantity", mode === "stock_validation" ? "0" : mode.endsWith("decimal") ? "1.5" : "-1"); submit(form); } }
if (mode === "error_400" || mode === "error_409") { clickText(/utilisateur|user/i); await flush(); for (const form of userCreationForms()) { setCommonValues(form); submit(form); } await flush(); }
if (mode === "error_404") { clickText(/utilisateur|user/i); await flush(); submitUserDetailForms(); await flush(); }
if (mode === "error_422") { clickText(/stock/i); await flush(); submitStock("remove"); await flush(); }
if (mode === "view_loading" || mode === "error_403" || mode === "error_500" || mode === "error_non_json" || mode === "error_rejection") { clickText(/branch|succurs/i); await flush(); }
if (mode.startsWith("mutation_double")) {
  clickText(mode.includes("common") ? /stock/i : /utilisateur|user/i); await flush();
  const formsToSubmit = mode.includes("common") ? (stockForm() ? [stockForm()] : []) : userMutationForms().slice(0, 3);
  for (const form of formsToSubmit) { setCommonValues(form); const before = calls.filter((call) => mutation(call.path, call.method)).length; submit(form); const disabled = descendants(form).filter((item) => item.tagName === "BUTTON").every((item) => item.disabled); submit(form); await flush(); const count = calls.filter((call) => mutation(call.path, call.method)).length - before; if (count) { snapshots.push({ disabled, count, loading: loadingVisible() }); finishPending(); await flush(); snapshots[snapshots.length - 1].reenabled = descendants(form).filter((item) => item.tagName === "BUTTON").every((item) => !item.disabled); } }
}
if (mode.startsWith("mutation_error")) {
  clickText(mode.includes("stock") ? /stock/i : /utilisateur|user/i); await flush();
  const formsToSubmit = mode.includes("stock") ? (stockForm() ? [stockForm()] : []) : userMutationForms().slice(0, 1);
  for (const form of formsToSubmit) { setCommonValues(form); submit(form); await flush(); errors.push({ message: messages(), disabled: descendants(form).filter((item) => item.tagName === "BUTTON").every((item) => item.disabled), reenabled: descendants(form).filter((item) => item.tagName === "BUTTON").every((item) => !item.disabled) }); }
}
if (mode === "refresh_retry_401") { await flush(); }
if (mode === "finish_pending") { finishPending(); await flush(); }

process.stdout.write(JSON.stringify({
  calls, storage: Object.fromEntries(storage.entries()), storageKeys, confirmations,
  messages: messages(), messageValues: all().filter((item) => ["status", "alert"].includes(item.getAttribute("role"))).map(textOf), bodyText: textOf(document.body), visibleActions: visibleActionTexts(),
  applicationLogs,
  forms: forms().map((form) => Object.fromEntries(fields(form).map((item) => [item.name, item.value]))),
  formStates: forms().map((form) => ({
    values: Object.fromEntries(fields(form).map((item) => [item.name, item.value])),
    defaults: Object.fromEntries(fields(form).map((item) => [item.name, item.defaultValue])),
  })),
  snapshots, errors, loading: loadingVisible(),
}));
'''.replace("__SOURCE__", source).replace("__FIXTURE__", fixture).replace("__MODE__", requested_mode)

    # These are intentionally local-only process arguments; the JS double
    # rejects every URL outside the approved API prefix.
    completed = subprocess.run(
        [node, "--input-type=module", "-e", harness],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode:
        pytest.fail(f"local JavaScript harness failed: {completed.stderr.strip()}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"local JavaScript harness returned invalid JSON: {completed.stdout!r}")


def _calls(result: dict, method: str | None = None) -> list[dict]:
    return [call for call in result["calls"] if method is None or call["method"] == method]


def _path_is_allowed(path: str) -> bool:
    parsed = urlsplit(path)
    if parsed.query and parsed.path not in {"/api/v1/users", "/api/v1/stocks"}:
        return False
    parts = parsed.path.split("/")
    if parts[:3] != ["", "api", "v1"] or len(parts) < 4:
        return False
    if parts[3] == "auth":
        return "/".join(parts[4:]) in {"login", "refresh", "logout", "logout/refresh", "me"}
    if parts[3] in {"users", "branches", "products", "stocks"}:
        return True
    return False


def _request_is_allowed(call: dict) -> bool:
    parsed = urlsplit(call["path"])
    path = parsed.path
    method = call["method"]
    if parsed.query and path not in {"/api/v1/users", "/api/v1/stocks"}:
        return False
    if path in {"/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout", "/api/v1/auth/logout/refresh"}:
        return method == "POST"
    if path == "/api/v1/auth/me":
        return method == "GET"
    if path == "/api/v1/users":
        return method in {"GET", "POST"}
    if re.fullmatch(r"/api/v1/users/\d+", path):
        return method in {"GET", "PATCH", "DELETE"}
    if re.fullmatch(r"/api/v1/users/\d+/password", path):
        return method == "PATCH"
    if path in {"/api/v1/branches", "/api/v1/products", "/api/v1/stocks"}:
        return method == "GET"
    if re.fullmatch(r"/api/v1/branches/\d+", path) or re.fullmatch(r"/api/v1/products/[^/]+", path):
        return method == "GET"
    return bool(re.fullmatch(r"/api/v1/stocks/[^/]+", path) and method == "GET") or bool(
        re.fullmatch(r"/api/v1/stocks/[^/]+/(?:add|remove)", path) and method == "POST"
    )


def _protected_calls(result: dict) -> list[dict]:
    return [
        call for call in result["calls"]
        if not any(call["path"].endswith(suffix) for suffix in ("/auth/login", "/auth/refresh", "/auth/logout", "/auth/logout/refresh"))
    ]


def test_static_assets_expose_accessible_responsive_native_structure():
    html = _read("index.html")
    css = _read("styles.css")
    parser = _HtmlParser()
    parser.feed(html)
    assert re.search(r"<main\b", html, re.I)
    assert re.search(r"<form\b", html, re.I)
    assert re.search(r'<meta[^>]+name=["\']viewport', html, re.I)
    assert re.search(r'aria-live=["\'](?:polite|assertive)["\']', html, re.I)
    assert re.search(r'role=["\'](?:status|alert)["\']', html, re.I)
    labelled = [item for item in parser.controls if item["id"] and item["tag"] != "button"]
    assert labelled and all(item["id"] in parser.labels or item["id"] in parser.wrapped_controls for item in labelled)
    assert re.search(r"@media\s*\(", css) and re.search(r":focus-visible\b", css)
    assert not re.search(r'name=["\'](?:role|password_hash|is_active|deleted_at|token_version)["\']', html, re.I)


def test_global_hidden_rule_wins_over_grid_layout_for_role_panels():
    css = _read("styles.css")
    hidden = re.search(r"(?s)\[hidden\]\s*\{(?P<body>[^}]*)\}", css)
    assert hidden and re.search(r"display\s*:\s*none\s*!important", hidden.group("body"))
    assert re.search(r"\.?(?:panel|view)[^{]*\{[^}]*display\s*:\s*grid", css, re.S)


def test_logout_source_requires_fulfilled_and_ok_revocation_results_before_success():
    source = _read("app.js")
    assert "Promise.allSettled" in source
    assert re.search(r"allSettled[\s\S]{0,800}\.ok", source)


def test_static_frontend_security_boundaries_are_native_and_safe():
    assets = {name: _read(name) for name in ASSETS}
    for name, source in assets.items():
        assert "localStorage" not in source, name
        assert not re.search(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----|\b(?:sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9_-]{8,}", source), name
    assert not re.search(r"<(?:script|link|img|iframe|object|embed)\b[^>]*(?:src|href)\s*=[\"'](?:https?:)?//", assets["index.html"], re.I)
    assert not re.search(r"@import\b|url\(\s*[\"']?(?:https?:)?//", assets["styles.css"], re.I)
    javascript = assets["app.js"]
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "createContextualFragment", "document.write"):
        assert forbidden not in javascript
    assert not re.search(r"\bconsole\.(?:log|debug|info|warn|error)\s*\(", javascript)
    assert not re.search(r"\b(?:postgres(?:ql)?|psycopg|sqlalchemy|SELECT\s+.+\s+FROM)\b", javascript, re.I)
    assert not re.search(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", "\n".join(assets.values()))


def test_tokens_passwords_and_authorization_are_not_logged_or_rendered():
    results = [_run(mode) for mode in ("login_admin", "user_crud", "logout")]
    forbidden_values = {
        "access",
        "refresh",
        "old-access",
        "old-refresh",
        "secret-password",
        "created-secret",
        "changed-secret",
        "Bearer old-access",
        "Bearer old-refresh",
    }
    for result in results:
        visible_output = " ".join((result["bodyText"], result["messages"], *result["applicationLogs"]))
        assert not any(value in visible_output for value in forbidden_values)
        assert "authorization" not in visible_output.lower()
        assert result["applicationLogs"] == []


def test_observed_requests_stay_within_existing_backoffice_routes():
    observed = []
    for mode in ("login_admin", "logout", "user_crud", "reads"):
        observed.extend(_run(mode)["calls"])
    assert observed
    assert all(_path_is_allowed(call["path"]) for call in observed)
    assert all(_request_is_allowed(call) for call in observed)
    assert all(call["path"].startswith("/api/v1/") for call in observed)


def test_login_session_storage_identity_and_role_views_are_observable():
    admin = _run("login_admin")
    login = next(call for call in admin["calls"] if call["path"].endswith("/auth/login"))
    assert login["method"] == "POST" and login["path"] == "/api/v1/auth/login"
    assert login["headers"].get("content-type") == "application/json"
    assert set(json.loads(login["body"])) == {"username", "password"}
    assert sorted(admin["storage"].values()) == ["access", "refresh"]
    protected = _protected_calls(admin)
    assert protected and all(call["headers"].get("authorization", "").startswith("Bearer ") for call in protected)
    assert "admin" in admin["bodyText"] and "Toulon" in admin["bodyText"]
    admin_actions = " ".join(admin["visibleActions"]).lower()
    assert "dashboard" in admin_actions or "tableau" in admin_actions
    assert "branch" in admin_actions or "succurs" in admin_actions
    assert "produit" in admin_actions and ("user" in admin_actions or "utilisateur" in admin_actions)
    assert "stock" not in admin_actions

    common = _run("login_common")
    common_actions = " ".join(common["visibleActions"]).lower()
    assert "common_user" in common["bodyText"] and "Toulon" in common["bodyText"]
    assert "stock" in common_actions and ("user" not in common_actions and "utilisateur" not in common_actions)
    assert "branch" in common_actions or "succurs" in common_actions


def test_restore_refresh_once_failure_and_logout_are_recoverable():
    restored = _run("restore_common")
    assert any(call["path"].endswith("/auth/me") and call["method"] == "GET" for call in restored["calls"])
    refreshed = _run("refresh_once")
    refresh_calls = [call for call in refreshed["calls"] if call["path"].endswith("/auth/refresh")]
    auth_me = [index for index, call in enumerate(refreshed["calls"]) if call["path"].endswith("/auth/me")]
    assert len(refresh_calls) == 1 and auth_me[:2] == [0, 2]
    assert refresh_calls[0]["method"] == "POST" and refresh_calls[0]["headers"].get("authorization", "").startswith("Bearer ")
    failed = _run("refresh_failure")
    assert failed["storage"] == {} and failed["messages"].strip()
    assert len([call for call in failed["calls"] if call["path"].endswith("/auth/refresh")]) == 1
    retry_failed = _run("refresh_retry_401")
    assert len([call for call in retry_failed["calls"] if call["path"].endswith("/auth/refresh")]) == 1
    assert retry_failed["storage"] == {} and retry_failed["messages"].strip()
    logged_out = _run("logout")
    logout_calls = [call for call in logged_out["calls"] if "/auth/logout" in call["path"]]
    assert {urlsplit(call["path"]).path for call in logout_calls} == {"/api/v1/auth/logout", "/api/v1/auth/logout/refresh"}
    assert all(call["method"] == "POST" for call in logout_calls)
    assert next(call for call in logout_calls if call["path"].endswith("/auth/logout"))["headers"].get("authorization") == "Bearer old-access"
    assert next(call for call in logout_calls if call["path"].endswith("/auth/logout/refresh"))["headers"].get("authorization") == "Bearer old-refresh"
    assert logged_out["storage"] == {}
    assert "Vous êtes déconnecté." in logged_out["messageValues"]
    for mode in ("logout_failure", "logout_refresh_failure"):
        failed_logout = _run(mode)
        failed_calls = [call for call in failed_logout["calls"] if "/auth/logout" in call["path"]]
        assert {urlsplit(call["path"]).path for call in failed_calls} == {"/api/v1/auth/logout", "/api/v1/auth/logout/refresh"}
        assert next(call for call in failed_calls if call["path"].endswith("/auth/logout"))["headers"].get("authorization") == "Bearer old-access"
        assert next(call for call in failed_calls if call["path"].endswith("/auth/logout/refresh"))["headers"].get("authorization") == "Bearer old-refresh"
        assert failed_logout["storage"] == {}
        assert (
            "Déconnexion locale effectuée, mais la révocation serveur n’a pas pu être confirmée."
            in failed_logout["messageValues"]
        )
    rejected = _run("logout_network_rejection")
    assert rejected["storage"] == {}
    assert "Déconnexion locale effectuée, mais la révocation serveur n’a pas pu être confirmée." in rejected["messageValues"]
    assert {urlsplit(call["path"]).path for call in rejected["calls"] if "/auth/logout" in call["path"]} == {
        "/api/v1/auth/logout",
        "/api/v1/auth/logout/refresh",
    }


def test_business_request_401_refreshes_once_and_retries_the_same_request():
    result = _run("business_refresh_once")
    branch_calls = [
        (index, call)
        for index, call in enumerate(result["calls"])
        if urlsplit(call["path"]).path == "/api/v1/branches"
    ]
    refresh_calls = [call for call in result["calls"] if urlsplit(call["path"]).path == "/api/v1/auth/refresh"]
    assert len(branch_calls) == 2
    assert len(refresh_calls) == 1
    assert branch_calls[0][1]["method"] == branch_calls[1][1]["method"] == "GET"
    assert branch_calls[1][0] > branch_calls[0][0]
    assert branch_calls[1][1]["headers"].get("authorization") == "Bearer business-access"


def test_admin_user_crud_filters_and_private_fields_use_contract_payloads():
    result = _run("user_crud")
    users = [call for call in result["calls"] if "/users" in urlsplit(call["path"]).path]
    assert users
    queries = [parse_qs(urlsplit(call["path"]).query) for call in users if call["method"] == "GET" and urlsplit(call["path"]).path.endswith("/users")]
    assert {query.get("status", [None])[0] for query in queries} >= {"active", "deleted", "all"}
    for status in ("active", "deleted"):
        matching = [query for query in queries if query.get("status") == [status]]
        assert matching and all(query.get("branch_id") == ["2"] for query in matching)
    all_queries = [query for query in queries if query.get("status") == ["all"]]
    assert all_queries and all("branch_id" not in query for query in all_queries)
    created = [call for call in users if call["method"] == "POST" and urlsplit(call["path"]).path == "/api/v1/users"]
    assert created and json.loads(created[0]["body"]) == {"username": "created-alice", "password": "created-secret", "branch_id": 4}
    body_mutations = [call for call in users if call["body"] and call["method"] in {"POST", "PATCH"}]
    assert body_mutations and all(call["headers"].get("content-type") == "application/json" for call in body_mutations)
    assert any(call["method"] == "GET" and re.search(r"/users/\d+$", urlsplit(call["path"]).path) for call in users)
    edits = [call for call in users if call["method"] == "PATCH" and "/password" not in call["path"]]
    assert edits and json.loads(edits[0]["body"]) == {"username": "changed-alice", "branch_id": 4}
    password = [call for call in users if call["method"] == "PATCH" and call["path"].endswith("/password")]
    assert password and all(json.loads(call["body"]) == {"new_password": "changed-secret"} for call in password)
    deletes = [call for call in users if call["method"] == "DELETE"]
    assert deletes and all(call["body"] is None for call in deletes) and result["confirmations"]
    forbidden = {"role", "password_hash", "is_active", "deleted_at", "token_version"}
    for call in users:
        if call["body"]:
            assert not forbidden.intersection(json.loads(call["body"]))
    assert "17" in result["bodyText"] and "alice" in result["bodyText"]
    assert "created-secret" not in result["bodyText"] and "changed-secret" not in result["bodyText"]


def test_numeric_identifiers_are_validated_before_user_or_branch_requests():
    result = _run("identifier_validation")
    invalid_user_or_branch = [
        call for call in result["calls"]
        if urlsplit(call["path"]).path.startswith("/api/v1/users/")
        or re.fullmatch(r"/api/v1/branches/[^/]+", urlsplit(call["path"]).path)
    ]
    assert not invalid_user_or_branch
    assert not any(
        call["method"] in {"POST", "PATCH", "DELETE"}
        and urlsplit(call["path"]).path in {"/api/v1/users", "/api/v1/branches"}
        for call in result["calls"]
    )
    assert result["messages"].strip()


def test_common_user_cannot_submit_admin_user_mutations():
    result = _run("common_forbidden")
    assert not any(call["method"] in {"POST", "PATCH", "DELETE"} and "/users" in call["path"] for call in result["calls"])


def test_reads_stock_filters_and_movements_use_public_routes_and_payloads():
    branches = _run("reads_branches")
    branch_list = [
        call for call in branches["calls"]
        if call["method"] == "GET" and urlsplit(call["path"]).path == "/api/v1/branches"
    ]
    assert branch_list and "Toulon" in branches["bodyText"] and "Paris" in branches["bodyText"]

    products = _run("reads_products")
    product_list = [
        call for call in products["calls"]
        if call["method"] == "GET" and urlsplit(call["path"]).path == "/api/v1/products"
    ]
    assert product_list and "product-123" in products["bodyText"] and "Example" in products["bodyText"]

    result = _run("reads")
    calls = result["calls"]
    assert any(call["method"] == "GET" and "/branches/" in urlsplit(call["path"]).path for call in calls)
    assert any(call["method"] == "GET" and "/products/" in urlsplit(call["path"]).path for call in calls)
    stocks = [call for call in calls if "/stocks" in urlsplit(call["path"]).path]
    stock_lists = [call for call in stocks if call["method"] == "GET" and urlsplit(call["path"]).path == "/api/v1/stocks"]
    assert stock_lists and {parse_qs(urlsplit(call["path"]).query).get("available_only", [None])[0] for call in stock_lists} >= {"true", "false"}
    assert parse_qs(urlsplit(stock_lists[0]["path"]).query).get("available_only") == ["true"]
    assert any(call["method"] == "GET" and urlsplit(call["path"]).path == "/api/v1/stocks/product-123" for call in stocks)
    assert "Toulon" in result["bodyText"]
    movements = [call for call in stocks if call["method"] == "POST"]
    assert {urlsplit(call["path"]).path.rsplit("/", 1)[-1] for call in movements} >= {"add", "remove"}
    assert movements and all(json.loads(call["body"]) == {"quantity": 3} for call in movements)
    assert all("branch_id" not in json.loads(call["body"]) for call in movements)
    stock_forms = [form for form in result["forms"] if "product_id" in form and "quantity" in form]
    assert stock_forms and all("branch_id" not in form for form in stock_forms)
    assert all(call["headers"].get("content-type") == "application/json" for call in movements)


def test_validation_loading_and_http_or_transport_errors_are_accessible():
    for mode in ("stock_validation", "stock_validation_decimal", "stock_validation_negative"):
        result = _run(mode)
        assert not any(call["method"] == "POST" and "/stocks/" in call["path"] for call in result["calls"])
        assert result["messages"].strip()
    loading = _run("view_loading")
    assert loading["loading"]
    for mode in ("error_400", "error_403", "error_404", "error_409", "error_422", "error_500", "error_non_json", "error_rejection"):
        result = _run(mode)
        assert result["messages"].strip()
        assert not any(call["path"].endswith("/auth/refresh") for call in result["calls"])
        if mode in {"error_400", "error_409"}:
            assert any(call["method"] == "POST" and urlsplit(call["path"]).path == "/api/v1/users" for call in result["calls"])
        elif mode == "error_404":
            assert any(call["method"] == "GET" and re.fullmatch(r"/api/v1/users/\d+", urlsplit(call["path"]).path) for call in result["calls"])
        elif mode == "error_422":
            assert any(call["method"] == "POST" and re.fullmatch(r"/api/v1/stocks/[^/]+/remove", urlsplit(call["path"]).path) for call in result["calls"])
    for status in (400, 401, 403):
        result = _run(f"login_error_{status}")
        assert result["messages"].strip() and any(call["path"].endswith("/auth/login") for call in result["calls"])


def test_mutations_are_single_submission_disabled_and_reenabled():
    for mode in ("mutation_double_admin", "mutation_double_common"):
        result = _run(mode)
        assert result["snapshots"]
        assert all(item["count"] == 1 and item["disabled"] and item["reenabled"] for item in result["snapshots"])
    for mode in ("mutation_error_create", "mutation_error_stock"):
        result = _run(mode)
        assert result["errors"] and all(item["disabled"] and item["reenabled"] and item["message"].strip() for item in result["errors"])


def test_successful_mutations_reset_forms_announce_success_and_reload_views():
    stock = _run("mutation_success_stock")
    stock_posts = [
        index for index, call in enumerate(stock["calls"])
        if call["method"] == "POST" and re.fullmatch(r"/api/v1/stocks/[^/]+/(?:add|remove)", urlsplit(call["path"]).path)
    ]
    assert stock_posts and stock["messages"].strip()
    assert any(
        index > stock_posts[0]
        and call["method"] == "GET"
        and urlsplit(call["path"]).path == "/api/v1/stocks"
        for index, call in enumerate(stock["calls"])
    )
    stock_state = next(
        item for item in stock["formStates"]
        if "quantity" in item["values"] and "product_id" in item["values"]
    )
    assert stock_state["values"] == stock_state["defaults"]

    admin = _run("mutation_success_admin")
    user_posts = [
        index for index, call in enumerate(admin["calls"])
        if call["method"] == "POST" and urlsplit(call["path"]).path == "/api/v1/users"
    ]
    assert user_posts and admin["messages"].strip()
    assert any(
        index > user_posts[0]
        and call["method"] == "GET"
        and urlsplit(call["path"]).path == "/api/v1/users"
        for index, call in enumerate(admin["calls"])
    )
    creation_state = next(
        item for item in admin["formStates"]
        if {"username", "password", "branch_id"}.issubset(item["values"])
    )
    assert creation_state["values"] == creation_state["defaults"]
    assert "created-secret" not in admin["bodyText"]
