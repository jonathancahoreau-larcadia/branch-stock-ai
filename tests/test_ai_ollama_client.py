"""Contract tests for the standard-library Ollama adapter.

The adapter is deliberately exercised through its public async methods.  The
HTTP boundary is replaced locally, so these tests never contact Ollama or any
other network service.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import math
import socket
import urllib.request
from pathlib import Path

import pytest


BASE_URL = "http://ollama.test:11434"


def run(awaitable):
    return asyncio.run(awaitable)


class FakeResponse:
    def __init__(self, payload, *, status=200):
        self.status = status
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self):
        return self.status


def install_transport(monkeypatch, module, state, response):
    def fake_urlopen(request, *args, **kwargs):
        state["request"] = request
        state["args"] = args
        state["kwargs"] = kwargs
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            state["in_event_loop"] = False
        else:
            state["in_event_loop"] = True
        if isinstance(response, BaseException):
            raise response
        return FakeResponse(response)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    # Supporting the two common standard-library import forms keeps this test
    # at the transport boundary rather than prescribing a private helper name.
    monkeypatch.setattr(module, "urlopen", fake_urlopen, raising=False)


def request_details(state):
    request = state["request"]
    url = request.full_url if hasattr(request, "full_url") else request.get_full_url()
    headers = {key.lower(): value for key, value in request.headers.items()}
    body = request.data
    return url, request.get_method(), headers, json.loads(body.decode("utf-8"))


def response_for(content, *, status=200):
    return {"message": {"content": json.dumps(content, ensure_ascii=False)}}


def module_under_test():
    return importlib.import_module("ai_service.ollama_client")


def client(module, monkeypatch, **kwargs):
    values = {"base_url": BASE_URL, "model": "test-model", **kwargs}
    return module.OllamaClient(**values)


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("Ollama tests must not open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket, "create_connection", fail)


def test_public_surface_and_async_signatures_are_stable():
    module = module_under_test()

    assert issubclass(module.OllamaClientError, RuntimeError)
    error = module.OllamaClientError("AI_PROVIDER_UNAVAILABLE", "safe message")
    assert error.code == "AI_PROVIDER_UNAVAILABLE"
    assert error.message == "safe message"
    constructor_parameters = inspect.signature(module.OllamaClient).parameters
    assert list(constructor_parameters) == [
        "base_url",
        "model",
        "timeout_seconds",
        "keep_alive",
    ]
    assert all(
        constructor_parameters[name].default is None
        for name in ("base_url", "model", "timeout_seconds", "keep_alive")
    )
    assert list(inspect.signature(module.OllamaClient.generate_intent).parameters) == [
        "self",
        "question",
    ]
    assert list(inspect.signature(module.OllamaClient.reformulate).parameters) == [
        "self",
        "question",
        "grounded_response",
    ]
    assert inspect.iscoroutinefunction(module.OllamaClient.generate_intent)
    assert inspect.iscoroutinefunction(module.OllamaClient.reformulate)


def test_import_has_no_network_side_effect_and_model_default_is_not_hard_coded():
    module = module_under_test()
    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "qwen3.5:4b" not in source


@pytest.mark.parametrize(
    "environment",
    [
        {"OLLAMA_BASE_URL": "http://env.example:11434", "OLLAMA_MODEL": "env-model"},
        {
            "OLLAMA_BASE_URL": "http://env.example:11434/",
            "OLLAMA_MODEL": "env-model",
            "OLLAMA_TIMEOUT_SECONDS": "12.5",
            "OLLAMA_KEEP_ALIVE": "10m",
        },
    ],
)
def test_environment_configuration_is_used_and_explicit_values_take_precedence(
    monkeypatch, environment
):
    module = module_under_test()
    for name in ("OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_TIMEOUT_SECONDS", "OLLAMA_KEEP_ALIVE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    state = {}
    install_transport(monkeypatch, module, state, response_for({"question_type": "unsupported", "parameters": {}}))
    instance = module.OllamaClient()
    run(instance.generate_intent("hello"))
    url, method, headers, payload = request_details(state)

    assert url == f"{environment.get('OLLAMA_BASE_URL', 'http://env.example:11434').rstrip('/')}/api/chat"
    assert method == "POST"
    assert payload["model"] == environment["OLLAMA_MODEL"]
    assert state["kwargs"].get("timeout") == float(environment.get("OLLAMA_TIMEOUT_SECONDS", 30))

    state.clear()
    install_transport(monkeypatch, module, state, response_for({"question_type": "unsupported", "parameters": {}}))
    explicit = module.OllamaClient(
        base_url="http://explicit.example:9/",
        model="explicit-model",
        timeout_seconds=2.25,
        keep_alive="1h",
    )
    run(explicit.generate_intent("hello"))
    explicit_url, _, _, explicit_payload = request_details(state)
    assert explicit_url == "http://explicit.example:9/api/chat"
    assert explicit_payload["model"] == "explicit-model"
    assert state["kwargs"].get("timeout") == 2.25
    assert explicit_payload["keep_alive"] == "1h"


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("OLLAMA_BASE_URL", "ollama.example"),
        ("OLLAMA_BASE_URL", "ftp://ollama.example"),
        ("OLLAMA_BASE_URL", "http://user:secret@ollama.example"),
        ("OLLAMA_BASE_URL", "http://ollama.example/path?token=secret"),
        ("OLLAMA_BASE_URL", "http://ollama.example/path#fragment"),
        ("OLLAMA_MODEL", ""),
        ("OLLAMA_MODEL", "   "),
        ("OLLAMA_TIMEOUT_SECONDS", "0"),
        ("OLLAMA_TIMEOUT_SECONDS", "-1"),
        ("OLLAMA_TIMEOUT_SECONDS", "nan"),
        ("OLLAMA_TIMEOUT_SECONDS", "inf"),
        ("OLLAMA_TIMEOUT_SECONDS", "not-a-number"),
        ("OLLAMA_KEEP_ALIVE", ""),
        ("OLLAMA_KEEP_ALIVE", "   "),
    ],
)
def test_invalid_environment_configuration_is_rejected(monkeypatch, variable, value):
    module = module_under_test()
    for name in (
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "OLLAMA_TIMEOUT_SECONDS",
        "OLLAMA_KEEP_ALIVE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "configured-model")
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError):
        module.OllamaClient()


def test_default_timeout_and_keep_alive_are_sent(monkeypatch):
    module = module_under_test()
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "configured-model")
    monkeypatch.delenv("OLLAMA_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    state = {}
    install_transport(monkeypatch, module, state, response_for({"question_type": "unsupported", "parameters": {}}))

    run(module.OllamaClient().generate_intent("  hello  "))
    url, _, _, payload = request_details(state)
    assert url == "http://127.0.0.1:11434/api/chat"
    assert state["kwargs"].get("timeout") == 30.0
    assert payload["keep_alive"] == "5m"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "ollama.example"},
        {"base_url": "ftp://ollama.example"},
        {"base_url": "http://user:secret@ollama.example"},
        {"base_url": "http://ollama.example/path?token=secret"},
        {"base_url": "http://ollama.example/path#fragment"},
        {"model": ""},
        {"timeout_seconds": 0},
        {"timeout_seconds": -1},
        {"timeout_seconds": math.inf},
        {"timeout_seconds": math.nan},
        {"keep_alive": ""},
        {"keep_alive": "   "},
    ],
)
def test_invalid_configuration_is_rejected(monkeypatch, kwargs):
    module = module_under_test()
    monkeypatch.setenv("OLLAMA_MODEL", "configured-model")
    with pytest.raises(ValueError):
        module.OllamaClient(**kwargs)


def test_model_is_required_when_not_explicit_or_configured(monkeypatch):
    module = module_under_test()
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError):
        module.OllamaClient(base_url=BASE_URL)


def test_intent_request_has_exact_contract_payload(monkeypatch):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response_for({"question_type": "unsupported", "parameters": {}}))

    result = run(client(module, monkeypatch).generate_intent("  Où est le produit ?  "))
    url, method, headers, payload = request_details(state)

    assert result == {"question_type": "unsupported", "parameters": {}}
    assert url == f"{BASE_URL}/api/chat"
    assert method == "POST"
    assert headers["content-type"] == "application/json"
    assert headers["accept"] == "application/json"
    assert set(payload) == {"model", "stream", "keep_alive", "format", "messages"}
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    assert payload["messages"][1]["content"] == "Où est le produit ?"
    assert "Never choose or name an MCP tool." in payload["messages"][0]["content"]
    assert state["in_event_loop"] is False


def test_intent_request_uses_the_exact_system_prompt_and_only_contract_headers(monkeypatch):
    module = module_under_test()
    state = {}
    install_transport(
        monkeypatch,
        module,
        state,
        response_for({"question_type": "unsupported", "parameters": {}}),
    )

    run(client(module, monkeypatch).generate_intent("  question  "))
    _, _, headers, payload = request_details(state)

    assert headers == {
        "content-type": "application/json",
        "accept": "application/json",
    }
    assert payload["messages"] == [
        {
            "role": "system",
            "content": (
                "You are the HBntory intent parser. Return one JSON object only "
                "with exactly question_type and parameters. question_type must "
                "be product_details, product_availability, branch_inventory, "
                "shopping_list, or unsupported. parameters must follow the "
                "requested type: product for product_details or "
                "product_availability, branch_id for branch_inventory, items "
                "with product and requested_quantity for shopping_list, and an "
                "empty object for unsupported. Never choose or name an MCP "
                "tool."
            ),
        },
        {"role": "user", "content": "question"},
    ]


def test_reformulation_request_uses_canonical_json_and_exact_shape(monkeypatch):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response_for({"answer": "Voici product-1."}))
    grounded = {
        "status": "success",
        "answer": "Product product-1 is available.",
        "data": {"quantity": 4, "name": "Café"},
    }

    result = run(client(module, monkeypatch).reformulate("  Café ? ", grounded))
    _, method, headers, payload = request_details(state)
    expected_user = json.dumps(
        {"grounded_response": grounded, "question": "  Café ? "},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert result == "Voici product-1."
    assert method == "POST"
    assert headers["content-type"] == "application/json"
    assert headers["accept"] == "application/json"
    assert set(payload) == {"model", "stream", "keep_alive", "format", "messages"}
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["messages"][1]["content"] == expected_user
    assert "Do not add, remove, calculate, or change" in payload["messages"][0]["content"]


def test_reformulation_request_uses_the_exact_system_prompt_and_headers(monkeypatch):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response_for({"answer": "ok"}))
    grounded = {"status": "partial", "answer": "Product product-1.", "data": {}}

    run(client(module, monkeypatch).reformulate("question", grounded))
    _, _, headers, payload = request_details(state)

    assert headers == {
        "content-type": "application/json",
        "accept": "application/json",
    }
    assert payload["messages"][0] == {
        "role": "system",
        "content": (
            "You reformulate one grounded HBntory response. Return one JSON "
            "object only with exactly answer. Do not add, remove, calculate, "
            "or change any product, identifier, branch, price, quantity, or "
            "stock fact. Answer in the user's language when possible."
        ),
    }


@pytest.mark.parametrize(
    "operation, response",
    [
        ("intent", response_for({"question_type": "unsupported", "parameters": {}, "extra": True})),
        ("intent", {"message": {"content": "not-json"}}),
        ("intent", {"message": {"content": json.dumps({"wrong": True})}}),
        ("reformulate", response_for({"answer": ""})),
        ("reformulate", response_for({"answer": "ok", "extra": True})),
        ("reformulate", {"message": {"content": "not-json"}}),
    ],
)
def test_invalid_ollama_responses_are_safe_provider_errors(monkeypatch, operation, response):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response)
    instance = client(module, monkeypatch)
    call = (
        instance.generate_intent("question")
        if operation == "intent"
        else instance.reformulate("question", {"status": "success", "answer": "ok", "data": {}})
    )

    with pytest.raises(module.OllamaClientError) as exc_info:
        run(call)
    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert "ollama.test" not in exc_info.value.message
    assert "test-model" not in exc_info.value.message
    assert "not-json" not in exc_info.value.message


@pytest.mark.parametrize("error", [ConnectionError("secret endpoint"), OSError("password=secret")])
def test_transport_failures_are_safe_provider_errors(monkeypatch, error):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, error)
    with pytest.raises(module.OllamaClientError) as exc_info:
        run(client(module, monkeypatch).generate_intent("question"))
    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert "secret" not in exc_info.value.message.lower()
    assert "password" not in exc_info.value.message.lower()


def test_timeout_is_classified_separately_and_does_not_leak_details(monkeypatch):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, TimeoutError("secret timeout"))
    with pytest.raises(module.OllamaClientError) as exc_info:
        run(client(module, monkeypatch).generate_intent("question"))
    assert exc_info.value.code == "UPSTREAM_TIMEOUT"
    assert "secret" not in exc_info.value.message.lower()


def test_http_status_outside_2xx_is_a_safe_provider_error(monkeypatch):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response_for({"error": "secret"}))

    # The fake transport reports an HTTP status without running an actual
    # server; the adapter must reject it before trusting the response body.
    def fake_http_error(request, *args, **kwargs):
        state["request"] = request
        state["kwargs"] = kwargs
        return FakeResponse({"error": "secret"}, status=503)

    monkeypatch.setattr(urllib.request, "urlopen", fake_http_error)
    monkeypatch.setattr(module, "urlopen", fake_http_error, raising=False)
    with pytest.raises(module.OllamaClientError) as exc_info:
        run(client(module, monkeypatch).generate_intent("question"))
    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert "secret" not in exc_info.value.message.lower()


@pytest.mark.parametrize(
    "content",
    [
        {"question_type": "product_details", "parameters": {"product": "Widget"}},
        {"question_type": "product_availability", "parameters": {"product": "Widget"}},
        {"question_type": "branch_inventory", "parameters": {"branch_id": 7}},
        {
            "question_type": "shopping_list",
            "parameters": {"items": [{"product": "Widget", "requested_quantity": 2}]},
        },
        {"question_type": "unsupported", "parameters": {}},
    ],
)
def test_each_valid_intent_schema_is_returned_unchanged(monkeypatch, content):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response_for(content))
    assert run(client(module, monkeypatch).generate_intent("question")) == content


@pytest.mark.parametrize(
    "content",
    [
        None,
        [],
        "product_details",
        {"question_type": "unknown", "parameters": {}},
        {"question_type": 1, "parameters": {}},
        {"question_type": "product_details"},
        {"question_type": "product_details", "parameters": []},
        {"question_type": "product_details", "parameters": {"product": 1}},
        {"question_type": "product_details", "parameters": {"product": "   "}},
        {
            "question_type": "product_details",
            "parameters": {"product": "Widget", "extra": True},
        },
        {"question_type": "product_availability", "parameters": {"product": ""}},
        {"question_type": "branch_inventory", "parameters": {"branch_id": 1.0}},
        {"question_type": "branch_inventory", "parameters": {"branch_id": False}},
        {"question_type": "branch_inventory", "parameters": {"branch_id": 0}},
        {"question_type": "branch_inventory", "parameters": {"branch_id": -1}},
        {
            "question_type": "shopping_list",
            "parameters": {"items": []},
        },
        {
            "question_type": "shopping_list",
            "parameters": {"items": [{"product": "Widget"}]},
        },
        {
            "question_type": "shopping_list",
            "parameters": {
                "items": [{"product": "Widget", "requested_quantity": True}]
            },
        },
        {
            "question_type": "shopping_list",
            "parameters": {
                "items": [{"product": "Widget", "requested_quantity": 0}]
            },
        },
        {
            "question_type": "shopping_list",
            "parameters": {
                "items": [{"product": "Widget", "requested_quantity": 1.5}]
            },
        },
        {
            "question_type": "shopping_list",
            "parameters": {
                "items": [
                    {"product": "Widget", "requested_quantity": 1},
                    {"product": " widget ", "requested_quantity": 2},
                ]
            },
        },
        {
            "question_type": "shopping_list",
            "parameters": {
                "items": [
                    {"product": "Cafe Widget", "requested_quantity": 1},
                    {"product": "Ｃａｆｅ　Ｗｉｄｇｅｔ", "requested_quantity": 2},
                ]
            },
        },
        {"question_type": "unsupported", "parameters": {"unexpected": True}},
    ],
)
def test_every_invalid_intent_schema_is_rejected_as_a_provider_error(monkeypatch, content):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response_for(content))

    with pytest.raises(module.OllamaClientError) as exc_info:
        run(client(module, monkeypatch).generate_intent("question"))

    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert exc_info.value.message.strip()
    assert "ollama.test" not in exc_info.value.message
    assert "test-model" not in exc_info.value.message


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"message": None},
        {"message": {}},
        {"message": {"content": None}},
        {"message": {"content": ""}},
        {"message": {"content": 42}},
        {"message": {"content": json.dumps([])}},
        {"message": {"content": json.dumps({"answer": "ok"})}},
    ],
)
def test_invalid_ollama_envelope_shapes_are_rejected_without_detail_leaks(
    monkeypatch, response
):
    module = module_under_test()
    state = {}
    install_transport(monkeypatch, module, state, response)

    with pytest.raises(module.OllamaClientError) as exc_info:
        run(client(module, monkeypatch).generate_intent("question"))

    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert exc_info.value.message.strip()
    assert "ollama.test" not in exc_info.value.message
    assert "test-model" not in exc_info.value.message
