"""Contract tests for the public AI Query Service HTTP adapter."""

from __future__ import annotations

import importlib
import inspect
import socket
import sys

import pytest


class FakeQuestionService:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else {
            "status": "success",
            "answer": "Grounded answer.",
            "data": {"source": "fake"},
        }
        self.error = error
        self.calls = []

    async def answer_question(self, question):
        self.calls.append(question)
        if self.error is not None:
            raise self.error
        return self.result


class FakeApplicationError(RuntimeError):
    def __init__(self, code, message="safe public message"):
        super().__init__("internal detail must not leak")
        self.code = code
        self.message = message


def server_module():
    return importlib.import_module("ai_service.server")


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("AI server tests must not use a real network")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket, "create_connection", fail)


def test_public_surface_is_importable_without_starting_a_server():
    module = server_module()

    assert callable(module.create_app)
    assert callable(module.main)
    assert list(inspect.signature(module.create_app).parameters) == [
        "question_service",
        "test_config",
    ]
    assert list(inspect.signature(module.main).parameters) == []


def test_fresh_import_does_not_start_server_or_open_network(monkeypatch):
    module_name = "ai_service.server"
    sys.modules.pop(module_name, None)

    def fail_if_io(*_args, **_kwargs):
        raise AssertionError("import must not start a server or use a socket")

    monkeypatch.setattr(socket.socket, "bind", fail_if_io)
    monkeypatch.setattr(socket.socket, "listen", fail_if_io)
    monkeypatch.setattr(socket.socket, "connect", fail_if_io)
    monkeypatch.setattr(socket, "create_connection", fail_if_io)

    module = importlib.import_module(module_name)

    assert callable(module.create_app)
    assert callable(module.main)


def test_create_app_uses_injected_service_and_default_construction_is_local(monkeypatch):
    module = server_module()
    service = FakeQuestionService()
    app = module.create_app(service, {"TESTING": True})
    assert app.testing is True

    constructed = []

    class FakeMCPClient:
        def __init__(self):
            constructed.append("mcp")

    class FakeService:
        def __init__(self, client):
            constructed.append(("service", client))

    monkeypatch.setattr(module, "MCPClient", FakeMCPClient)
    monkeypatch.setattr(module, "QuestionService", FakeService)
    module.create_app(test_config={"TESTING": True})
    assert constructed == ["mcp", ("service", constructed[1][1])]


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {},
        {"data": "not-json", "content_type": "text/plain"},
        {"data": "{bad", "content_type": "application/json"},
    ],
)
def test_invalid_json_is_a_stable_400_and_does_not_call_service(request_kwargs):
    service = FakeQuestionService()
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.post("/questions", **request_kwargs)

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "INVALID_JSON",
            "message": "Request body must be valid JSON.",
            "details": {},
        }
    }
    assert service.calls == []


@pytest.mark.parametrize(
    "payload",
    [[], "question", {}, {"question": None}, {"question": 4},
     {"question": ""}, {"question": "   "}, {"question": "x" * 1001}],
)
def test_invalid_question_is_a_stable_400_and_does_not_call_service(payload):
    service = FakeQuestionService()
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.post("/questions", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "The question must be a non-empty string of at most 1000 characters.",
            "details": {},
        }
    }
    assert service.calls == []


def test_json_null_is_a_validation_error_and_does_not_call_service():
    service = FakeQuestionService()
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.post(
        "/questions", data="null", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "The question must be a non-empty string of at most 1000 characters.",
            "details": {},
        }
    }
    assert service.calls == []


def test_valid_question_is_stripped_called_once_and_response_is_not_mutated():
    result = {"status": "partial", "answer": "Answer.", "data": {"x": 1}}
    service = FakeQuestionService(result=result)
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.post("/questions", json={"question": "  Where?  ", "extra": True})

    assert response.status_code == 200
    assert response.get_json() == result
    assert service.calls == ["Where?"]


@pytest.mark.parametrize("status", ["success", "partial", "unavailable", "unsupported"])
def test_all_business_statuses_return_http_200_without_an_envelope(status):
    result = {"status": status, "answer": "Safe.", "data": {}}
    service = FakeQuestionService(result=result)
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.post("/questions", json={"question": "Question"})

    assert response.status_code == 200
    assert response.get_json() == result


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [("MCP_ERROR", 502), ("MCP_UNAVAILABLE", 503),
     ("AI_PROVIDER_UNAVAILABLE", 503), ("UPSTREAM_TIMEOUT", 504),
     ("UNKNOWN_CODE", 500)],
)
def test_application_errors_have_stable_status_and_safe_error_shape(code, expected_status):
    service = FakeQuestionService(error=FakeApplicationError(code))
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.post("/questions", json={"question": "Question"})

    assert response.status_code == expected_status
    assert response.get_json() == {
        "error": {
            "code": code if code != "UNKNOWN_CODE" else "INTERNAL_ERROR",
            "message": "safe public message" if code != "UNKNOWN_CODE" else "An unexpected error occurred.",
            "details": {},
        }
    }
    assert "internal detail must not leak" not in response.get_data(as_text=True)


def test_unexpected_exception_is_internal_error_without_exception_text():
    service = FakeQuestionService(error=RuntimeError("secret URL and traceback"))
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.post("/questions", json={"question": "Question"})

    assert response.status_code == 500
    assert response.get_json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "details": {},
        }
    }
    assert "secret URL and traceback" not in response.get_data(as_text=True)


def test_each_request_is_independent():
    service = FakeQuestionService()
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    client.post("/questions", json={"question": "First"})
    client.post("/questions", json={"question": "Second"})

    assert service.calls == ["First", "Second"]


def test_health_is_public_exact_and_has_no_service_call():
    service = FakeQuestionService()
    client = server_module().create_app(service, {"TESTING": True}).test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert service.calls == []


def test_options_is_local_and_advertises_only_public_question_headers():
    service = FakeQuestionService()
    client = server_module().create_app(
        service,
        {"TESTING": True, "CLIENT_WEB_ORIGIN": "https://client.example"},
    ).test_client()

    response = client.options("/questions", headers={"Origin": "https://client.example"})

    assert response.status_code in {200, 204}
    assert service.calls == []
    assert response.headers.get("Access-Control-Allow-Methods") == "POST, OPTIONS"
    assert response.headers.get("Access-Control-Allow-Headers") == "Content-Type"
    assert "Authorization" not in response.headers.get("Access-Control-Allow-Headers", "")


def test_configured_matching_origin_gets_cors_headers():
    client = server_module().create_app(
        FakeQuestionService(),
        {"TESTING": True, "CLIENT_WEB_ORIGIN": "https://client.example"},
    ).test_client()

    response = client.post(
        "/questions", json={"question": "Question"},
        headers={"Origin": "https://client.example"},
    )

    assert response.headers["Access-Control-Allow-Origin"] == "https://client.example"
    assert response.headers["Vary"] == "Origin"
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_absent_or_nonmatching_origin_gets_no_cors_allow_origin():
    for config, origin in [({}, "https://client.example"),
                           ({"CLIENT_WEB_ORIGIN": "https://client.example"}, None),
                           ({"CLIENT_WEB_ORIGIN": "https://client.example"}, "https://other.example")]:
        client = server_module().create_app(FakeQuestionService(), {"TESTING": True, **config}).test_client()
        headers = {} if origin is None else {"Origin": origin}
        response = client.post("/questions", json={"question": "Question"}, headers=headers)
        assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.parametrize("origin", ["*", "ftp://client.example", "https://client.example/path", "https://user:pass@client.example", "https://client.example?x=1", "https://client.example#x"])
def test_invalid_client_web_origin_is_rejected(origin):
    with pytest.raises(ValueError):
        server_module().create_app(FakeQuestionService(), {"CLIENT_WEB_ORIGIN": origin})


def test_main_uses_positive_configured_port_and_does_not_open_a_real_port(monkeypatch):
    module = server_module()
    run_calls = []

    class FakeApp:
        def run(self, **kwargs):
            run_calls.append(kwargs)

    monkeypatch.setattr(module, "create_app", lambda: FakeApp())
    monkeypatch.setenv("AI_SERVICE_PORT", "8123")

    module.main()

    assert run_calls == [{"host": "0.0.0.0", "port": 8123}]


def test_main_uses_port_8000_by_default_and_does_not_open_a_real_port(monkeypatch):
    module = server_module()
    run_calls = []

    class FakeApp:
        def run(self, **kwargs):
            run_calls.append(kwargs)

    monkeypatch.delenv("AI_SERVICE_PORT", raising=False)
    monkeypatch.setattr(module, "create_app", lambda: FakeApp())

    module.main()

    assert run_calls == [{"host": "0.0.0.0", "port": 8000}]


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", " "])
def test_main_rejects_invalid_port_before_start(monkeypatch, value):
    module = server_module()
    monkeypatch.setenv("AI_SERVICE_PORT", value)
    monkeypatch.setattr(module, "create_app", lambda: pytest.fail("app must not start"))

    with pytest.raises(ValueError):
        module.main()
