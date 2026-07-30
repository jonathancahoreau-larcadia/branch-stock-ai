"""Browser-contract tests for the anonymous Client Web UI.

Node executes the browser script with a tiny local DOM and a fake Fetch.  No
HTTP server, socket, browser storage, or external service is used.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "client_web" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "client_web" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "client_web" / "styles.css").read_text(encoding="utf-8")


def run_node(script):
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def browser_script(scenario="success"):
    return f"""
(async () => {{
const vm = require("vm");
const appSource = {json.dumps(APP)};
const scenario = {json.dumps(scenario)};

class Element {{
  constructor(tag, id) {{
    this.tagName = tag.toUpperCase();
    this.id = id || "";
    this.children = [];
    this.listeners = {{}};
    this.attributes = {{}};
    this.style = {{}};
    this.className = "";
    this.dataset = {{}};
    this.classList = {{
      add: (...names) => {{ this.className = [...new Set(`${{this.className}} ${{names.join(" ")}}`.trim().split(/\\s+/).filter(Boolean))].join(" "); }},
      remove: (...names) => {{ this.className = this.className.split(/\\s+/).filter(name => name && !names.includes(name)).join(" "); }},
      toggle: (name, force) => {{
        const present = this.className.split(/\\s+/).includes(name);
        if (force === undefined ? !present : force) this.classList.add(name);
        else this.classList.remove(name);
        return force === undefined ? !present : force;
      }},
    }};
    this.value = "";
    this.disabled = false;
    this.required = false;
    this.maxLength = 0;
    this.textContent = "";
  }}
  setAttribute(name, value) {{ this.attributes[name] = String(value); }}
  getAttribute(name) {{ return this.attributes[name] ?? null; }}
  append(...nodes) {{ this.children.push(...nodes); }}
  appendChild(node) {{ this.children.push(node); return node; }}
  replaceChildren(...nodes) {{ this.children = nodes; }}
  addEventListener(name, callback) {{
    (this.listeners[name] ||= []).push(callback);
  }}
  dispatch(name, extra = {{}}) {{
    const event = {{ preventDefault() {{}}, target: this, currentTarget: this, ...extra }};
    for (const callback of (this.listeners[name] || [])) callback(event);
  }}
}}

const elements = new Map([
  ["#question-form", new Element("form", "question-form")],
  ["#question", new Element("input", "question")],
  ["#submit-button", new Element("button", "submit-button")],
  ["#request-status", new Element("p", "request-status")],
  ["#answer-output", new Element("div", "answer-output")],
  ["#data-output", new Element("pre", "data-output")],
]);
elements.get("#question").required = true;
elements.get("#question").maxLength = 1000;
const document = {{
  querySelector(selector) {{
    const element = elements.get(selector);
    if (!element) throw new Error("missing selector: " + selector);
    return element;
  }},
  createElement(tag) {{ return new Element(tag); }},
  createTextNode(text) {{ const node = new Element("text"); node.textContent = String(text); return node; }},
}};
globalThis.document = document;
globalThis.window = globalThis;

let pendingResolve;
let pendingReject;
const calls = [];
globalThis.fetch = (url, options) => {{
  calls.push({{url, options}});
  if (scenario === "fetch-error") return Promise.reject(new Error("network unavailable"));
  if (scenario === "invalid-json") return Promise.resolve({{ok: true, status: 200, json: async () => {{ throw new Error("bad json"); }}}});
  if (scenario === "invalid-payload") return Promise.resolve({{ok: true, status: 200, json: async () => ({{status: "success"}})}});
  if (scenario === "invalid-answer") return Promise.resolve({{ok: true, status: 200, json: async () => ({{status: "success", answer: 7, data: {{}}}})}});
  if (scenario === "invalid-data") return Promise.resolve({{ok: true, status: 200, json: async () => ({{status: "success", answer: "ok", data: []}})}});
  if (scenario === "http-error") return Promise.resolve({{ok: false, status: 503, json: async () => ({{status: "error", error: {{code: "UPSTREAM", message: "Service unavailable"}}}})}});
  if (scenario === "http-error-unstructured") return Promise.resolve({{ok: false, status: 502, json: async () => ({{status: "error"}})}});
  if (scenario === "http-error-invalid") return Promise.resolve({{ok: false, status: 500, json: async () => ({{status: "error", error: {{code: 7, message: "<script>secret</script>"}}}})}});
  if (scenario === "concurrency") return new Promise((resolve, reject) => {{ pendingResolve = resolve; pendingReject = reject; }});
  const status = scenario;
  return Promise.resolve({{ok: true, status: 200, json: async () => ({{status, answer: "<b>safe answer</b>", data: {{value: "<script>unsafe</script>"}}}})}});
}};
globalThis.localStorage = new Proxy({{}}, {{ get() {{ throw new Error("localStorage forbidden"); }} }});
globalThis.sessionStorage = new Proxy({{}}, {{ get() {{ throw new Error("sessionStorage forbidden"); }} }});
Object.defineProperty(document, "cookie", {{ get() {{ throw new Error("cookie forbidden"); }} }});

vm.runInThisContext(appSource);
const form = elements.get("#question-form");
const question = elements.get("#question");
const button = elements.get("#submit-button");
const status = elements.get("#request-status");
question.value = "  Product product-1  ";
question.dispatch("input");

const first = {{
  initialDisabled: button.disabled,
  maxLength: question.maxLength,
  required: question.required,
}};
form.dispatch("submit");
await Promise.resolve();
first.callCount = calls.length;
first.loadingText = status.textContent;
first.request = calls[0] && {{
  url: calls[0].url,
  method: calls[0].options.method,
  credentials: calls[0].options.credentials,
  headers: calls[0].options.headers,
  body: JSON.parse(calls[0].options.body),
}};
first.loadingDisabled = button.disabled;

if (scenario === "concurrency") {{
  form.dispatch("submit");
  first.concurrentCallCount = calls.length;
  pendingResolve({{ok: true, status: 200, json: async () => ({{status: "success", answer: "done", data: {{}}}})}});
}}
await new Promise(resolve => setTimeout(resolve, 0));
first.statusText = status.textContent;
first.statusClass = status.className;
first.statusState = status.dataset.state || status.dataset.status || "";
first.statusStyle = {{...status.style}};
first.answer = elements.get("#answer-output").textContent;
first.data = elements.get("#data-output").textContent;
first.finalDisabled = button.disabled;
console.log(JSON.stringify(first));
}})();
"""


def test_html_has_anonymous_accessible_contract_and_four_examples():
    for marker in (
        'id="question-form"',
        'id="question"',
        'id="submit-button"',
        'id="request-status"',
        'id="answer-output"',
        'id="data-output"',
        'maxlength="1000"',
        'required',
        'role="status"',
        'aria-live="polite"',
    ):
        assert marker in HTML
    lowered = HTML.lower()
    assert all(
        term in lowered
        for term in ("product", "branch", "stock", "shopping")
    )
    assert sum(
        marker in lowered
        for marker in ("details", "availability", "branch", "shopping")
    ) == 4


def test_examples_use_french_public_questions_and_real_demo_identifiers():
    folded = HTML.casefold()
    expected_examples = (
        "donne-moi les détails du produit hb-mon-2102",
        "dans quelle succursale reste-t-il du hb-mon-2102",
        "quels produits sont disponibles dans la succursale 2",
        "où trouver 2 unités de hb-mon-2102 et 3 unités de hb-key-1001",
    )
    assert all(example in folded for example in expected_examples)
    assert folded.count("hb-mon-2102") >= 3
    assert "hb-key-1001" in folded
    assert all(identifier not in folded for identifier in ("product-1", "widget", "gadget"))


def test_client_posts_trimmed_question_with_exact_anonymous_fetch_options():
    result = run_node(browser_script())
    assert result["request"] == {
        "url": "/questions",
        "method": "POST",
        "credentials": "omit",
        "headers": {"Content-Type": "application/json"},
        "body": {"question": "Product product-1"},
    }
    assert result["callCount"] == 1
    assert result["finalDisabled"] is False


def test_empty_question_is_not_sent_and_loading_disables_submission():
    script = browser_script().replace('question.value = "  Product product-1  ";', 'question.value = "   ";')
    result = run_node(script)
    assert result["callCount"] == 0
    assert result["initialDisabled"] is True


def test_concurrent_submission_creates_only_one_fetch_and_disables_button():
    result = run_node(browser_script("concurrency"))
    assert result["callCount"] == 1
    assert result["concurrentCallCount"] == 1
    assert result["loadingDisabled"] is True
    assert result["finalDisabled"] is False


def test_each_public_status_is_announced_and_rendered():
    observed = {}
    visual_rules = {}
    for status in ("success", "partial", "unavailable", "unsupported"):
        result = run_node(browser_script(status))
        observed[status] = result["statusClass"] + "|" + result["statusState"]
        assert status in result["statusText"].lower()
        assert result["answer"] == "<b>safe answer</b>"
        assert "<script>unsafe</script>" in result["data"]
        declarations = []
        for class_name in result["statusClass"].split():
            for selector, block in re.findall(r"([^{}]+)\{([^{}]*)\}", STYLES):
                if not re.search(
                    rf"\.{re.escape(class_name)}(?:[^\w-]|$)", selector
                ):
                    continue
                block = block.lower()
                declarations.extend(
                    line.strip()
                    for line in block.split(";")
                    if re.match(
                        r"(?:color|background|border|outline|font-weight|text-decoration)\s*:",
                        line.strip(),
                    )
                )
        declarations.extend(
            f"{key}:{value}"
            for key, value in result["statusStyle"].items()
            if key in {"color", "background", "border", "outline", "fontWeight", "textDecoration"}
        )
        assert declarations, result["statusClass"]
        visual_rules[status] = tuple(sorted(set(declarations)))
    assert len(set(observed.values())) == 4
    assert len(set(visual_rules.values())) == 4


def test_loading_state_is_textual_and_button_is_disabled_before_completion():
    result = run_node(browser_script("concurrency"))
    assert result["loadingText"]
    assert result["loadingDisabled"] is True


def test_structured_http_error_displays_only_its_safe_message():
    result = run_node(browser_script("http-error"))
    assert result["statusText"] == "Service unavailable"
    assert "UPSTREAM" not in result["statusText"]


def test_success_payload_requires_a_string_answer_and_object_data():
    for scenario in ("invalid-payload", "invalid-answer", "invalid-data"):
        result = run_node(browser_script(scenario))
        assert result["statusText"]
        assert "Service unavailable" not in result["statusText"]


def test_http_fetch_json_and_payload_failures_are_technical_visible_errors():
    for scenario in ("http-error", "fetch-error", "invalid-json", "invalid-payload"):
        result = run_node(browser_script(scenario))
        assert result["statusText"]
        assert result["finalDisabled"] is False
        assert "secret" not in result["statusText"].lower()


def test_unknown_success_status_is_rejected_as_a_technical_error():
    result = run_node(browser_script("future-status"))
    assert result["statusText"]
    assert "future-status" not in result["statusText"]
    assert result["answer"] == ""


@pytest.mark.parametrize("scenario", ["http-error-unstructured", "http-error-invalid"])
def test_invalid_http_error_payload_is_rejected_without_remote_details(scenario):
    result = run_node(browser_script(scenario))
    assert result["statusText"]
    assert "secret" not in result["statusText"].lower()
    assert "script" not in result["statusText"].lower()


def test_client_source_forbids_persistence_unsafe_html_and_authorization():
    lowered = APP.lower()
    for forbidden in (
        "innerhtml",
        "localstorage",
        "sessionstorage",
        "document.cookie",
        "indexeddb",
        "authorization",
    ):
        assert forbidden not in lowered
