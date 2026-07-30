"""Browser-contract tests for the anonymous Client Web UI.

Node executes the native browser script with a local DOM and Fetch double.
No HTTP server, socket, browser storage, or external service is used.
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


def run_node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def browser_script(
    scenario: str = "success",
    action: str = "submit",
    question: str = "  Donne-moi les détails du produit HB-MON-2102.  ",
) -> str:
    return f"""
(async () => {{
const vm = require("vm");
const appSource = {json.dumps(APP)};
const scenario = {json.dumps(scenario)};
const action = {json.dumps(action)};
const suppliedQuestion = {json.dumps(question)};

class Element {{
  constructor(tag, id = "") {{
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.children = [];
    this.parentNode = null;
    this.listeners = {{}};
    this.attributes = {{}};
    this.dataset = {{}};
    this.className = "";
    this.hidden = false;
    this.value = "";
    this.disabled = false;
    this.required = false;
    this.maxLength = 0;
    this.type = "";
    this.dateTime = "";
    this.focused = false;
    this._text = "";
    this.classList = {{
      add: (...names) => {{
        const current = this.className.split(/\\s+/).filter(Boolean);
        this.className = [...new Set([...current, ...names])].join(" ");
      }},
      remove: (...names) => {{
        this.className = this.className.split(/\\s+/)
          .filter(name => name && !names.includes(name)).join(" ");
      }},
    }};
  }}
  set textContent(value) {{
    this._text = String(value);
    this.children = [];
  }}
  get textContent() {{
    return this._text + this.children.map(child => child.textContent || "").join("");
  }}
  setAttribute(name, value) {{ this.attributes[name] = String(value); }}
  getAttribute(name) {{ return this.attributes[name] ?? null; }}
  append(...nodes) {{
    for (const node of nodes) {{
      node.parentNode = this;
      this.children.push(node);
    }}
  }}
  appendChild(node) {{ this.append(node); return node; }}
  addEventListener(name, callback) {{
    (this.listeners[name] ||= []).push(callback);
  }}
  dispatch(name, extra = {{}}) {{
    const event = {{
      preventDefault() {{ this.defaultPrevented = true; }},
      defaultPrevented: false,
      target: this,
      currentTarget: this,
      ...extra,
    }};
    return (this.listeners[name] || []).map(callback => callback(event));
  }}
  requestSubmit() {{ this.dispatch("submit"); }}
  remove() {{
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(
      child => child !== this
    );
    this.parentNode = null;
  }}
  focus() {{
    allElements.forEach(element => {{ element.focused = false; }});
    this.focused = true;
  }}
  scrollIntoView() {{}}
  querySelectorAll(selector) {{
    const results = [];
    const className = selector.startsWith(".") ? selector.slice(1) : null;
    const visit = node => {{
      for (const child of node.children) {{
        if (
          className &&
          child.className.split(/\\s+/).includes(className)
        ) results.push(child);
        visit(child);
      }}
    }};
    visit(this);
    return results;
  }}
}}

const selectors = new Map();
const allElements = [];
function register(selector, tag) {{
  const element = new Element(tag, selector.startsWith("#") ? selector.slice(1) : "");
  selectors.set(selector, element);
  allElements.push(element);
  return element;
}}

const form = register("#question-form", "form");
const question = register("#question", "textarea");
const submit = register("#submit-button", "button");
const clear = register("#clear-button", "button");
const log = register("#conversation-log", "div");
const empty = register("#empty-state", "div");
const counter = register("#character-count", "span");
const status = register("#request-status", "p");
const errorLive = register("#error-live", "p");
const service = register("#service-status", "p");
const serviceText = register("#service-status-text", "span");
log.append(empty);
question.required = true;
question.maxLength = 1000;

const exampleQuestions = [
  "Donne-moi les détails du produit HB-MON-2102.",
  "Dans quelle succursale reste-t-il des écrans ?",
  "Quels produits sont disponibles dans la succursale 2 ?",
  "Où trouver 2 unités de HB-MON-2102 ?",
];
const examples = exampleQuestions.map(text => {{
  const element = new Element("button");
  element.className = "example-button";
  element.dataset.question = text;
  allElements.push(element);
  return element;
}});

const created = [];
const document = {{
  querySelector(selector) {{
    const element = selectors.get(selector);
    if (!element) throw new Error("missing selector: " + selector);
    return element;
  }},
  querySelectorAll(selector) {{
    if (selector === ".example-button") return examples;
    return [];
  }},
  createElement(tag) {{
    const element = new Element(tag);
    created.push(element);
    allElements.push(element);
    return element;
  }},
}};
globalThis.document = document;
globalThis.window = globalThis;

function deepFreeze(value) {{
  if (value && typeof value === "object") {{
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }}
  return value;
}}

const successPayload = deepFreeze({{
  status: "success",
  answer: "<b>Réponse externe sûre</b>",
  data: {{
    question_type: "product_availability",
    tool_results: {{
      get_product_details: {{
        external_product_id: "HB-MON-2102",
        name: "24 inch Compact Monitor",
        description: "A compact business display.",
        category: "Displays",
        brand: "HB",
        supplier: {{
          id: "SUP-LAB-002",
          name: "LabForge Supplies",
          country: "US",
          lead_time_days: 4,
          reliability_score: 0.9,
        }},
        unit_price: 169.99,
        currency: "USD",
        discontinued: false,
        weight_kg: 3.2,
        tags: ["business"],
        updated_at: "2026-01-01",
      }},
      get_stock_for_product: {{
        external_product_id: "HB-MON-2102",
        branches: [{{branch_id: 2, branch_name: "Toulon", quantity: 8}}],
      }},
    }},
  }},
}});
const originalSnapshot = JSON.stringify(successPayload);
let pendingResolve;
const calls = [];
globalThis.fetch = (url, options) => {{
  calls.push({{url, options}});
  if (url === "/health") {{
    if (scenario === "health-error") return Promise.reject(new Error("offline"));
    return Promise.resolve({{
      ok: scenario !== "health-invalid",
      status: scenario === "health-invalid" ? 503 : 200,
      json: async () => scenario === "health-invalid" ? {{status: "down"}} : {{status: "ok"}},
    }});
  }}
  if (scenario === "network-error") return Promise.reject(new Error("private network detail"));
  if (scenario === "pending") {{
    return new Promise(resolve => {{ pendingResolve = resolve; }});
  }}
  if (scenario === "http-error") return Promise.resolve({{
    ok: false,
    status: 503,
    json: async () => ({{
      error: {{
        code: "MCP_UNAVAILABLE",
        message: "secret http://internal.example",
        details: {{}},
      }},
    }}),
  }});
  if (scenario === "http-unknown") return Promise.resolve({{
    ok: false,
    status: 500,
    json: async () => ({{error: {{code: "PRIVATE", message: "trace secret"}}}}),
  }});
  if (scenario === "invalid-json") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => {{ throw new Error("invalid"); }},
  }});
  if (scenario === "invalid-payload") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => ({{status: "success"}}),
  }});
  if (scenario === "empty-answer") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => ({{status: "success", answer: "", data: {{}}}}),
  }});
  if (scenario === "unsupported") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => ({{
      status: "unsupported",
      answer: "Question unsupported.",
      data: {{supported_question_types: [
        "product_details", "product_availability", "branch_inventory", "shopping_list"
      ]}},
    }}),
  }});
  if (scenario === "branch-inventory") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => ({{
      status: "success",
      answer: "Inventaire disponible.",
      data: {{
        question_type: "branch_inventory",
        tool_results: {{
          list_products: {{products: [
            {{external_product_id: "HB-MON-2102", name: "Compact Monitor"}},
            {{external_product_id: "HB-OTHER-1", name: "Original English Name"}},
          ]}},
          list_branch_stock: {{
            branch_id: 2,
            branch_name: "Toulon",
            stocks: [
              {{external_product_id: "HB-MON-2102", quantity: 4}},
              {{external_product_id: "HB-OTHER-1", quantity: 2}},
            ],
          }},
        }},
      }},
    }}),
  }});
  if (scenario === "shopping") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => ({{
      status: "success",
      answer: "Plan disponible.",
      data: {{
        question_type: "shopping_list",
        tool_results: {{
          list_products: {{products: []}},
          find_branches_for_shopping_list: {{
            complete: true,
            strategy: "single_branch",
            visits: [{{
              branch_id: 2,
              branch_name: "Toulon",
              items: [{{
                external_product_id: "HB-MON-2102",
                requested_quantity: 2,
                available_quantity: 8,
              }}],
            }}],
            missing_items: [],
          }},
        }},
      }},
    }}),
  }});
  if (scenario === "unknown-product") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => ({{
      status: "success",
      answer: "English answer preserved.",
      data: {{
        question_type: "product_details",
        tool_results: {{
          get_product_details: {{
            external_product_id: "HB-UNKNOWN-1",
            name: "Original English Name",
            description: "Unmapped English description.",
            category: "Unmapped category",
          }},
        }},
      }},
    }}),
  }});
  if (scenario === "partial" || scenario === "unavailable") return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => ({{
      status: scenario,
      answer: scenario === "partial" ? "Réponse incomplète." : "Aucune information.",
      data: {{}},
    }}),
  }});
  return Promise.resolve({{
    ok: true,
    status: 200,
    json: async () => successPayload,
  }});
}};

vm.runInThisContext(appSource);
await new Promise(resolve => setTimeout(resolve, 0));

const result = {{
  initialSubmitDisabled: submit.disabled,
  initialClearDisabled: clear.disabled,
  initialCounter: counter.textContent,
  initialEmptyVisible: !empty.hidden,
  healthState: service.dataset.state,
  healthText: serviceText.textContent,
  exampleCount: examples.length,
}};

if (action === "example") {{
  examples[1].dispatch("click");
  result.exampleValue = question.value;
  result.exampleFocused = question.focused;
  result.submitEnabled = !submit.disabled;
}} else {{
  question.value = suppliedQuestion;
  question.dispatch("input");
  result.counterAfterInput = counter.textContent;
  result.submitEnabled = !submit.disabled;
  if (action === "keyboard") {{
    question.dispatch("keydown", {{key: "Enter", ctrlKey: true}});
  }} else {{
    form.dispatch("submit");
  }}
  await Promise.resolve();
  result.loadingSubmitDisabled = submit.disabled;
  result.loadingCount = log.querySelectorAll(".loading-message").length;
  result.questionCallsWhileLoading = calls.filter(call => call.url === "/questions").length;

  if (scenario === "pending") {{
    form.dispatch("submit");
    result.doubleSubmitQuestionCalls = calls.filter(call => call.url === "/questions").length;
    pendingResolve({{ok: true, status: 200, json: async () => successPayload}});
  }}
  await new Promise(resolve => setTimeout(resolve, 0));
  await Promise.resolve();

  result.questionCalls = calls.filter(call => call.url === "/questions").map(call => ({{
    url: call.url,
    method: call.options.method,
    credentials: call.options.credentials,
    headers: call.options.headers,
    body: JSON.parse(call.options.body),
  }}));
  result.messageCount = log.querySelectorAll(".message").length;
  result.loadingFinalCount = log.querySelectorAll(".loading-message").length;
  result.logText = log.textContent;
  result.statusText = status.textContent;
  result.errorText = errorLive.textContent;
  result.serviceStateFinal = service.dataset.state;
  result.finalSubmitDisabled = submit.disabled;
  result.finalClearDisabled = clear.disabled;
  result.payloadUnchanged = JSON.stringify(successPayload) === originalSnapshot;
  result.createdTags = created.map(element => element.tagName);

  if (action === "clear") {{
    clear.dispatch("click");
    result.clearedMessageCount = log.querySelectorAll(".message").length;
    result.clearedEmptyVisible = !empty.hidden;
    result.clearedFocused = question.focused;
    result.clearedAnnouncement = status.textContent;
    result.clearedButtonDisabled = clear.disabled;
  }} else if (action === "retry") {{
    const retries = log.querySelectorAll(".retry-button");
    result.retryButtonCount = retries.length;
    retries[0].dispatch("click");
    await new Promise(resolve => setTimeout(resolve, 0));
    result.retryQuestionCalls = calls.filter(
      call => call.url === "/questions"
    ).length;
  }}
}}

console.log(JSON.stringify(result));
}})();
"""


def test_initial_interface_is_french_accessible_and_ready():
    result = run_node(browser_script(action="example"))
    assert result["initialSubmitDisabled"] is True
    assert result["initialClearDisabled"] is True
    assert result["initialCounter"] == "0 / 1 000"
    assert result["initialEmptyVisible"] is True
    assert result["healthState"] == "available"
    assert result["healthText"] == "Service disponible"
    assert result["exampleCount"] == 4

    required_html = (
        'lang="fr"',
        'id="conversation-log"',
        'role="log"',
        'aria-live="polite"',
        'id="error-live"',
        'role="alert"',
        'id="question-form"',
        '<textarea',
        'maxlength="1000"',
        'id="character-count"',
        'id="clear-button"',
        'id="service-status"',
    )
    assert all(marker in HTML for marker in required_html)


def test_examples_are_exact_french_clickable_questions():
    expected = (
        "Donne-moi les détails du produit HB-MON-2102.",
        "Dans quelle succursale reste-t-il des écrans ?",
        "Quels produits sont disponibles dans la succursale 2 ?",
        "Où trouver 2 unités de HB-MON-2102 ?",
    )
    assert all(f'data-question="{question}"' in HTML for question in expected)
    assert HTML.count('class="example-button"') == 4

    result = run_node(browser_script(action="example"))
    assert result["exampleValue"] == expected[1]
    assert result["exampleFocused"] is True
    assert result["submitEnabled"] is True


def test_question_is_trimmed_and_posted_with_exact_public_contract():
    result = run_node(browser_script())
    assert result["questionCalls"] == [{
        "url": "/questions",
        "method": "POST",
        "credentials": "omit",
        "headers": {"Content-Type": "application/json"},
        "body": {
            "question": "Donne-moi les détails du produit HB-MON-2102."
        },
    }]
    assert result["messageCount"] == 2
    assert result["loadingFinalCount"] == 0
    assert result["finalClearDisabled"] is False


def test_empty_question_is_blocked_and_character_limit_is_visible():
    result = run_node(browser_script(question="   "))
    assert result["submitEnabled"] is False
    assert result["questionCalls"] == []
    assert result["messageCount"] == 0
    assert result["counterAfterInput"] == "3 / 1 000"


def test_ctrl_enter_submits_the_question():
    result = run_node(browser_script(action="keyboard"))
    assert len(result["questionCalls"]) == 1


def test_loading_and_double_submission_prevention():
    result = run_node(browser_script(scenario="pending"))
    assert result["loadingSubmitDisabled"] is True
    assert result["loadingCount"] == 1
    assert result["questionCallsWhileLoading"] == 1
    assert result["doubleSubmitQuestionCalls"] == 1
    assert result["loadingFinalCount"] == 0


def test_text_and_structured_product_stock_are_rendered_safely():
    result = run_node(browser_script())
    text = result["logText"]
    for expected in (
        "<b>Réponse externe sûre</b>",
        "Écran compact 24 pouces",
        "Un écran compact pour un usage professionnel.",
        "Écrans",
        "HB-MON-2102",
        "SUP-LAB-002",
        "169.99",
        "USD",
        "Toulon",
        "8",
    ):
        assert expected in text
    assert result["payloadUnchanged"] is True
    assert "TABLE" in result["createdTags"]


def test_empty_answer_and_absent_structured_data_have_explicit_fallbacks():
    result = run_node(browser_script(scenario="empty-answer"))
    assert "Le service n’a retourné aucun texte" in result["logText"]
    assert "Aucun détail structuré supplémentaire" in result["logText"]


def test_unsupported_response_translates_supported_types():
    result = run_node(browser_script(scenario="unsupported"))
    for label in (
        "Détails d’un produit",
        "Disponibilité d’un produit",
        "Inventaire d’une succursale",
        "Liste d’achats",
    ):
        assert label in result["logText"]


def test_branch_inventory_and_unknown_english_values_are_preserved():
    result = run_node(browser_script(scenario="branch-inventory"))
    for expected in (
        "Inventaire — Toulon",
        "Écran compact",
        "HB-MON-2102",
        "Original English Name",
        "HB-OTHER-1",
        "4",
        "2",
    ):
        assert expected in result["logText"]


def test_shopping_plan_uses_exact_identifiers_and_quantities():
    result = run_node(browser_script(scenario="shopping"))
    for expected in (
        "Plan d’achat",
        "Une seule succursale",
        "Toulon — 2",
        "HB-MON-2102",
        "2",
        "8",
    ):
        assert expected in result["logText"]


def test_unknown_translation_falls_back_to_original_english_values():
    result = run_node(browser_script(scenario="unknown-product"))
    for expected in (
        "English answer preserved.",
        "Original English Name",
        "Unmapped English description.",
        "Unmapped category",
        "HB-UNKNOWN-1",
    ):
        assert expected in result["logText"]


@pytest.mark.parametrize(
    ("scenario", "label"),
    [
        ("partial", "Réponse partielle"),
        ("unavailable", "Informations indisponibles"),
    ],
)
def test_partial_and_unavailable_business_states_are_distinct(scenario, label):
    result = run_node(browser_script(scenario=scenario))
    assert label in result["logText"]
    assert result["errorText"] == ""
    assert result["serviceStateFinal"] == "available"


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (
            "http-error",
            "Les informations sur les produits ou les stocks sont indisponibles.",
        ),
        ("http-unknown", "Le service n’a pas pu traiter la question."),
        ("invalid-json", "La réponse reçue ne peut pas être affichée."),
        ("invalid-payload", "La réponse reçue ne peut pas être affichée."),
        (
            "network-error",
            "Impossible de joindre le service. Vérifiez votre connexion locale puis réessayez.",
        ),
    ],
)
def test_http_network_and_invalid_responses_are_safe_and_restore_ui(
    scenario, expected
):
    result = run_node(browser_script(scenario=scenario))
    assert expected in result["logText"]
    assert expected in result["errorText"]
    assert result["finalSubmitDisabled"] is True
    assert result["finalClearDisabled"] is False
    assert "secret" not in result["logText"].casefold()
    assert "internal.example" not in result["logText"]


@pytest.mark.parametrize("scenario", ["health-error", "health-invalid"])
def test_health_failure_is_visible_without_blocking_questions(scenario):
    result = run_node(browser_script(scenario=scenario, action="example"))
    assert result["healthState"] == "unavailable"
    assert result["healthText"] == "Service indisponible"
    assert result["submitEnabled"] is True


def test_clear_conversation_restores_initial_state_and_focus():
    result = run_node(browser_script(action="clear"))
    assert result["clearedMessageCount"] == 0
    assert result["clearedEmptyVisible"] is True
    assert result["clearedFocused"] is True
    assert result["clearedAnnouncement"] == "Conversation effacée."
    assert result["clearedButtonDisabled"] is True


def test_retry_replays_only_the_selected_independent_question():
    result = run_node(browser_script(action="retry"))
    assert result["retryButtonCount"] == 1
    assert result["retryQuestionCalls"] == 2


def test_source_uses_safe_native_dom_without_persistence_or_external_assets():
    lowered = APP.casefold()
    for forbidden in (
        "innerhtml",
        "outerhtml",
        "insertadjacenthtml",
        "eval(",
        "localstorage",
        "sessionstorage",
        "document.cookie",
        "indexeddb",
        "authorization",
    ):
        assert forbidden not in lowered
    assert "textContent" in APP
    assert "createElement" in APP
    assert 'fetch("/questions"' in APP
    assert 'fetch("/health"' in APP

    references = re.findall(
        r"""(?:src|href)=["']([^"']+)["']""",
        HTML,
        flags=re.I,
    )
    assert references == ["styles.css", "app.js", "/"]
    assert not re.search(r"""https?://|//[A-Za-z0-9]""", HTML)
    assert "@import" not in STYLES


def test_accessibility_and_responsive_motion_contracts_are_present():
    assert '<label for="question">' in HTML
    assert 'aria-describedby="composer-help character-count"' in HTML
    assert 'aria-label="Exemples et aide"' in HTML
    assert ":focus-visible" in STYLES
    assert "@media (max-width: 960px)" in STYLES
    assert "@media (max-width: 680px)" in STYLES
    assert "@media (prefers-reduced-motion: reduce)" in STYLES
