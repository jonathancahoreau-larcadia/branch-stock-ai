"""Contract tests for Python-controlled Ollama/MCP orchestration."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import socket

import pytest


def run(awaitable):
    return asyncio.run(awaitable)


def envelope(data, *, status="success"):
    return {"status": status, "data": data}


def public_product_detail(external_product_id="product-1", name="Widget"):
    """Complete public Product API detail payload used by success fixtures."""
    return {
        "external_product_id": external_product_id,
        "name": name,
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


class FakeProviderError(RuntimeError):
    def __init__(self, code, message="safe"):
        super().__init__(message)
        self.code = code
        self.message = message


class FakeMCP:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    async def call_product_tool(self, tool_name, arguments=None):
        self.calls.append(("product", tool_name, arguments))
        return self.responses.get(("product", tool_name), envelope({}))

    async def call_stock_tool(self, tool_name, arguments=None):
        self.calls.append(("stock", tool_name, arguments))
        return self.responses.get(("stock", tool_name), envelope({}))


class FakeOllama:
    def __init__(
        self,
        intent=None,
        reformulated=None,
        error=None,
        intent_error=None,
        reformulation_error=None,
    ):
        self.intent = intent
        self.reformulated = reformulated
        self.error = error
        self.intent_error = intent_error
        self.reformulation_error = reformulation_error
        self.intent_calls = []
        self.reformulation_calls = []

    async def generate_intent(self, question):
        self.intent_calls.append(question)
        if self.intent_error is not None:
            raise self.intent_error
        if self.error is not None:
            raise self.error
        return self.intent

    async def reformulate(self, question, grounded_response):
        self.reformulation_calls.append((question, grounded_response))
        if self.reformulation_error is not None:
            raise self.reformulation_error
        if self.error is not None:
            raise self.error
        return self.reformulated


def module_under_test():
    return importlib.import_module("ai_service.question_service")


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("question-service tests must not use a real network")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket, "create_connection", fail)


def install_grounding_spy(monkeypatch, module, *, status="success", answer="Product product-1 has stock.", data=None):
    calls = []
    if data is None:
        data = {"grounded": True}
    deterministic = {"status": status, "answer": answer, "data": data}

    def fake_generator(question_type, mcp_results):
        calls.append((question_type, mcp_results))
        return deterministic

    monkeypatch.setattr(module, "generate_grounded_response", fake_generator)
    return calls, deterministic


def make_service(module, mcp, ollama, *, enabled=True):
    return module.QuestionService(mcp, ollama_client=ollama, ollama_enabled=enabled)


def test_public_surface_and_async_signature_are_stable():
    module = module_under_test()
    assert issubclass(module.QuestionServiceError, RuntimeError)
    error = module.QuestionServiceError("VALIDATION_ERROR", "safe")
    assert error.code == "VALIDATION_ERROR"
    assert error.message == "safe"
    assert list(inspect.signature(module.QuestionService).parameters) == [
        "mcp_client",
        "ollama_client",
        "ollama_enabled",
    ]
    assert list(inspect.signature(module.QuestionService.answer_question).parameters) == [
        "self",
        "question",
    ]
    assert inspect.iscoroutinefunction(module.QuestionService.answer_question)


def test_french_fallback_question_is_classified_and_answered_without_ollama(
    monkeypatch,
):
    module = module_under_test()
    mcp = FakeMCP(
        {
            ("product", "get_product_details"): envelope(
                public_product_detail("HB-MON-2102", "Écran compact")
            )
        }
    )
    service = module.QuestionService(mcp, ollama_enabled=False)

    result = run(service.answer_question("Donne-moi les détails du produit HB-MON-2102."))

    assert result["status"] == "success"
    assert result["data"]["question_type"] == "product_details"
    assert "HB-MON-2102" in result["answer"]
    assert "Produit" in result["answer"] or "produit" in result["answer"]
    assert "Product " not in result["answer"]
    assert mcp.calls == [
        ("product", "get_product_details", {"external_product_id": "HB-MON-2102"})
    ]


def test_french_anaphora_never_invents_a_product_identifier():
    module = module_under_test()
    mcp = FakeMCP()
    service = module.QuestionService(mcp, ollama_enabled=False)

    result = run(service.answer_question("Quelle agence possède ce produit ?"))

    assert result["status"] in {"unsupported", "unavailable"}
    assert mcp.calls == []


def test_public_service_never_reformulates_with_ollama_even_when_enabled(monkeypatch):
    module = module_under_test()
    mcp = FakeMCP(
        {
            ("product", "get_product_details"): envelope(
                public_product_detail("product-123", "Écran compact")
            )
        }
    )
    ollama = FakeOllama(
        intent={
            "question_type": "product_details",
            "parameters": {"product": "product-123"},
        },
        reformulated="hallucinated answer",
    )
    service = module.QuestionService(mcp, ollama_client=ollama, ollama_enabled=True)

    result = run(service.answer_question("Give me the details of product product-123."))

    assert result["status"] == "success"
    assert "hallucinated answer" not in result["answer"]
    assert ollama.reformulation_calls == []


@pytest.mark.parametrize(
    ("question", "expected_type", "expected_calls"),
    [
        (
            "DONNE-MOI les détails du produit HB-MON-2102 !!!",
            "product_details",
            [("product", "get_product_details", {"external_product_id": "HB-MON-2102"})],
        ),
        (
            "Dans quelle succursale reste-t-il du produit HB-MON-2102 ?",
            "product_availability",
            [
                ("product", "get_product_details", {"external_product_id": "HB-MON-2102"}),
                ("stock", "get_stock_for_product", {"external_product_id": "HB-MON-2102"}),
            ],
        ),
        (
            "Quels produits sont disponibles dans la succursale 2 ?",
            "branch_inventory",
            [
                ("product", "list_products", None),
                ("stock", "list_branch_stock", {"branch_id": 2}),
            ],
        ),
        (
            "OÙ trouver 2 unités de HB-MON-2102 et 3 unités de HB-KEY-1001 ?",
            "shopping_list",
            [
                ("product", "list_products", None),
                (
                    "stock",
                    "find_branches_for_shopping_list",
                    {
                        "items": [
                            {"external_product_id": "HB-MON-2102", "quantity": 2},
                            {"external_product_id": "HB-KEY-1001", "quantity": 3},
                        ]
                    },
                ),
            ],
        ),
    ],
)
def test_french_public_service_covers_all_four_families_without_reformulation(
    question, expected_type, expected_calls
):
    module = module_under_test()
    mcp = FakeMCP(
        {
            ("product", "list_products"): envelope(
                {"products": [
                    {"external_product_id": "HB-MON-2102", "name": "Écran compact"},
                    {"external_product_id": "HB-KEY-1001", "name": "Clavier compact"},
                ]}
            ),
            ("product", "get_product_details"): envelope(
                public_product_detail("HB-MON-2102", "Écran compact")
            ),
            ("stock", "get_stock_for_product"): envelope(
                {
                    "external_product_id": "HB-MON-2102",
                    "branches": [{"branch_id": 2, "branch_name": "Toulon", "quantity": 4}],
                }
            ),
            ("stock", "list_branch_stock"): envelope(
                {
                    "branch_id": 2,
                    "branch_name": "Toulon",
                    "stocks": [{"external_product_id": "HB-MON-2102", "quantity": 4}],
                }
            ),
            ("stock", "find_branches_for_shopping_list"): envelope(
                {
                    "complete": True,
                    "strategy": "single_branch",
                    "visits": [
                        {
                            "branch_id": 2,
                            "branch_name": "Toulon",
                            "items": [
                                {
                                    "external_product_id": "HB-MON-2102",
                                    "requested_quantity": 2,
                                    "available_quantity": 4,
                                },
                                {
                                    "external_product_id": "HB-KEY-1001",
                                    "requested_quantity": 3,
                                    "available_quantity": 3,
                                },
                            ],
                        }
                    ],
                    "missing_items": [],
                }
            ),
        }
    )
    ollama = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    result = run(module.QuestionService(mcp, ollama_client=ollama, ollama_enabled=False).answer_question(question))

    assert result["data"]["question_type"] == expected_type
    assert result["status"] == "success"
    assert mcp.calls == expected_calls
    assert result["answer"]
    assert "Product " not in result["answer"]
    assert "product-1" not in result["answer"]
    assert ollama.reformulation_calls == []


@pytest.mark.parametrize(
    ("question", "expected_status"),
    [
        ("Parle-moi de la météo.", "unsupported"),
        ("Donne-moi les détails du produit HB-MON-2102.", "unavailable"),
    ],
)
def test_french_public_service_keeps_deterministic_unavailable_and_unsupported_statuses(
    question, expected_status
):
    module = module_under_test()
    mcp = FakeMCP({("product", "get_product_details"): envelope(None, status="error")})
    result = run(module.QuestionService(mcp, ollama_enabled=False).answer_question(question))
    assert result["status"] == expected_status
    assert result["answer"]


def test_english_public_service_keeps_the_english_deterministic_surface():
    module = module_under_test()
    mcp = FakeMCP(
        {
            ("product", "get_product_details"): envelope(
                public_product_detail("HB-MON-2102", "Compact Monitor")
            )
        }
    )
    result = run(
        module.QuestionService(mcp, ollama_enabled=False).answer_question(
            "Give me the details of product HB-MON-2102."
        )
    )
    assert result["status"] == "success"
    assert "HB-MON-2102" in result["answer"]
    assert "Product" in result["answer"]
    assert "Produit" not in result["answer"]


@pytest.mark.parametrize(
    ("question", "mcp", "expected_status", "expected_message"),
    [
        (
            "Parle-moi de la météo, s’il te plaît !",
            FakeMCP(),
            "unsupported",
            "Cette question ne fait pas partie du périmètre d’inventaire pris en charge.",
        ),
        (
            "Donne-moi les détails du produit HB-MON-2102.",
            FakeMCP({("product", "get_product_details"): envelope(None, status="error")}),
            "unavailable",
            "Je ne dispose pas d’assez d’informations pour répondre à cette question.",
        ),
    ],
)
def test_french_public_service_uses_exact_safe_status_messages(
    question, mcp, expected_status, expected_message
):
    module = module_under_test()
    result = run(module.QuestionService(mcp, ollama_enabled=False).answer_question(question))
    assert result["status"] == expected_status
    assert result["answer"] == expected_message


def test_french_public_service_reports_no_positive_stock_without_leaking_zero_rows():
    module = module_under_test()
    mcp = FakeMCP(
        {
            ("product", "get_product_details"): envelope(
                public_product_detail("HB-MON-2102", "Écran compact")
            ),
            ("stock", "get_stock_for_product"): envelope(
                {
                    "external_product_id": "HB-MON-2102",
                    "branches": [
                        {"branch_id": 2, "branch_name": "Toulon", "quantity": 0}
                    ],
                }
            ),
        }
    )
    result = run(
        module.QuestionService(mcp, ollama_enabled=False).answer_question(
            "Dans quelle succursale reste-t-il du HB-MON-2102 ?"
        )
    )
    assert result["status"] == "success"
    assert result["answer"] == (
        "Le produit Écran compact (HB-MON-2102) n’est disponible dans aucune succursale."
    )
    assert "Toulon" not in result["answer"]


def test_french_public_service_localizes_partial_grounding_message(monkeypatch):
    module = module_under_test()
    mcp = FakeMCP(
        {
            ("product", "list_products"): envelope(
                {"products": [{"external_product_id": "HB-MON-2102", "name": "Écran compact"}]}
            ),
            ("stock", "list_branch_stock"): envelope(None, status="error"),
        }
    )
    result = run(
        module.QuestionService(mcp, ollama_enabled=False).answer_question(
            "Quels produits sont disponibles dans la succursale 2 ?"
        )
    )
    assert result["status"] == "partial"
    assert result["answer"] == (
        "Certaines informations MCP sont disponibles, mais elles ne suffisent pas "
        "pour fournir une réponse complète et vérifiable."
    )


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "On"])
def test_ollama_enabled_accepts_only_documented_true_values(monkeypatch, value):
    module = module_under_test()
    monkeypatch.setenv("OLLAMA_ENABLED", value)
    mcp = FakeMCP()
    ollama = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    service = module.QuestionService(mcp, ollama_client=ollama)
    run(service.answer_question("What is unrelated?"))
    assert ollama.intent_calls == ["What is unrelated?"]


@pytest.mark.parametrize("value", ["false", "0", "no", "OFF"])
def test_ollama_enabled_accepts_documented_false_values(monkeypatch, value):
    module = module_under_test()
    monkeypatch.setenv("OLLAMA_ENABLED", value)
    mcp = FakeMCP()
    ollama = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    service = module.QuestionService(mcp, ollama_client=ollama)
    result = run(service.answer_question("What is unrelated?"))
    assert result["status"] == "unsupported"
    assert ollama.intent_calls == []


def test_invalid_ollama_enabled_value_is_rejected(monkeypatch):
    module = module_under_test()
    monkeypatch.setenv("OLLAMA_ENABLED", "sometimes")
    with pytest.raises(ValueError):
        module.QuestionService(FakeMCP(), ollama_client=FakeOllama())


def test_ollama_enabled_argument_has_precedence_and_absence_defaults_to_disabled(
    monkeypatch,
):
    module = module_under_test()

    monkeypatch.setenv("OLLAMA_ENABLED", "false")
    enabled_client = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    run(
        module.QuestionService(
            FakeMCP(), ollama_client=enabled_client, ollama_enabled=True
        ).answer_question("unrelated")
    )
    assert enabled_client.intent_calls == ["unrelated"]

    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    disabled_client = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    run(
        module.QuestionService(
            FakeMCP(), ollama_client=disabled_client, ollama_enabled=False
        ).answer_question("unrelated")
    )
    assert disabled_client.intent_calls == []

    monkeypatch.delenv("OLLAMA_ENABLED", raising=False)
    absent_client = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    run(module.QuestionService(FakeMCP(), ollama_client=absent_client).answer_question("unrelated"))
    assert absent_client.intent_calls == []


def test_enabled_service_constructs_a_default_client_only_when_needed(monkeypatch):
    module = module_under_test()
    constructed = []

    class ConstructedClient(FakeOllama):
        def __init__(self):
            super().__init__(intent={"question_type": "unsupported", "parameters": {}})

    def factory():
        constructed.append(True)
        return ConstructedClient()

    monkeypatch.setattr(module, "OllamaClient", factory)
    module.QuestionService(FakeMCP(), ollama_enabled=True)
    assert constructed == [True]

    disabled_constructed = []
    monkeypatch.setattr(
        module, "OllamaClient", lambda: disabled_constructed.append(True)
    )
    module.QuestionService(FakeMCP(), ollama_enabled=False)
    assert disabled_constructed == []


@pytest.mark.parametrize("question", [None, "", "   ", "x" * 1001])
def test_question_validation_is_stable_and_precedes_any_backend_call(question):
    module = module_under_test()
    mcp = FakeMCP()
    ollama = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    service = make_service(module, mcp, ollama)
    with pytest.raises(module.QuestionServiceError) as exc_info:
        run(service.answer_question(question))
    assert exc_info.value.code == "VALIDATION_ERROR"
    assert not mcp.calls
    assert not ollama.intent_calls


@pytest.mark.parametrize(
    ("question_type", "parameters", "expected_calls"),
    [
        (
            "product_details",
            {"product": "product-1"},
            [("product", "get_product_details", {"external_product_id": "product-1"})],
        ),
        (
            "product_availability",
            {"product": "product-1"},
            [
                ("product", "get_product_details", {"external_product_id": "product-1"}),
                ("stock", "get_stock_for_product", {"external_product_id": "product-1"}),
            ],
        ),
        (
            "branch_inventory",
            {"branch_id": 7},
            [
                ("product", "list_products", None),
                ("stock", "list_branch_stock", {"branch_id": 7}),
            ],
        ),
        (
            "shopping_list",
            {
                "items": [
                    {"product": "Widget", "requested_quantity": 2},
                    {"product": "Gadget", "requested_quantity": 3},
                ]
            },
            [
                ("product", "list_products", None),
                (
                    "stock",
                    "find_branches_for_shopping_list",
                    {
                        "items": [
                            {"external_product_id": "product-1", "quantity": 2},
                            {"external_product_id": "product-2", "quantity": 3},
                        ]
                    },
                ),
            ],
        ),
        ("unsupported", {}, []),
    ],
)
def test_supported_intents_use_exact_sequential_read_only_mcp_calls(
    monkeypatch, question_type, parameters, expected_calls
):
    module = module_under_test()
    products = envelope(
        {
            "products": [
                {"external_product_id": "product-1", "name": "Widget"},
                {"external_product_id": "product-2", "name": "Gadget"},
            ]
        }
    )
    mcp = FakeMCP(
        {
            ("product", "list_products"): products,
            ("product", "get_product_details"): envelope(public_product_detail()),
            ("stock", "get_stock_for_product"): envelope({"external_product_id": "product-1", "branches": []}),
            ("stock", "list_branch_stock"): envelope({"branch_id": 7, "branch_name": "Central", "stocks": []}),
            ("stock", "find_branches_for_shopping_list"): envelope({"complete": True, "visits": []}),
        }
    )
    ollama = FakeOllama(
        intent={"question_type": question_type, "parameters": parameters},
        reformulated="Product product-1 has stock.",
    )
    calls, deterministic = install_grounding_spy(monkeypatch, module)

    result = run(make_service(module, mcp, ollama).answer_question("question"))

    assert mcp.calls == expected_calls
    assert len(calls) == 1
    assert result["status"] == deterministic["status"]
    assert result["data"] is deterministic["data"]
    assert ollama.reformulation_calls == []


def test_product_resolution_is_casefolded_and_deduplicates_id_and_name_match(monkeypatch):
    module = module_under_test()
    mcp = FakeMCP(
        {
            ("product", "list_products"): envelope(
                {
                    "products": [
                        {"external_product_id": "product-1", "name": "Cafe Widget"},
                        {"external_product_id": "product-2", "name": "Other"},
                    ]
                }
            ),
            ("product", "get_product_details"): envelope(public_product_detail("product-1", "Café Widget")),
        }
    )
    ollama = FakeOllama(
        intent={
            "question_type": "product_details",
            "parameters": {"product": "  Ｃａｆｅ　Ｗｉｄｇｅｔ "},
        },
        reformulated="Product product-1 has stock.",
    )
    calls, _ = install_grounding_spy(monkeypatch, module)
    run(make_service(module, mcp, ollama).answer_question("question"))
    assert mcp.calls == [
        ("product", "list_products", None),
        ("product", "get_product_details", {"external_product_id": "product-1"}),
    ]
    assert calls[0][1] == {
        "get_product_details": envelope(public_product_detail("product-1", "Café Widget"))
    }


@pytest.mark.parametrize(
    ("question_type", "parameters", "expected_calls"),
    [
        (
            "product_availability",
            {"product": "  Ｗｉｄｇｅｔ  "},
            [
                ("product", "list_products", None),
                (
                    "product",
                    "get_product_details",
                    {"external_product_id": "product-1"},
                ),
                (
                    "stock",
                    "get_stock_for_product",
                    {"external_product_id": "product-1"},
                ),
            ],
        ),
        (
            "product_availability",
            {"product": "product-1"},
            [
                (
                    "product",
                    "get_product_details",
                    {"external_product_id": "product-1"},
                ),
                (
                    "stock",
                    "get_stock_for_product",
                    {"external_product_id": "product-1"},
                ),
            ],
        ),
        (
            "shopping_list",
            {
                "items": [
                    {"product": "  Ｗｉｄｇｅｔ ", "requested_quantity": 2},
                    {"product": "product-2", "requested_quantity": 3},
                ]
            },
            [
                ("product", "list_products", None),
                (
                    "stock",
                    "find_branches_for_shopping_list",
                    {
                        "items": [
                            {"external_product_id": "product-1", "quantity": 2},
                            {"external_product_id": "product-2", "quantity": 3},
                        ]
                    },
                ),
            ],
        ),
    ],
)
def test_product_resolution_covers_availability_and_shopping_list(
    monkeypatch, question_type, parameters, expected_calls
):
    module = module_under_test()
    products = envelope(
        {
            "products": [
                {"external_product_id": "product-1", "name": "Widget"},
                {"external_product_id": "product-2", "name": "Gadget"},
            ]
        }
    )
    mcp = FakeMCP(
        {
            ("product", "list_products"): products,
            (
                "product",
                "get_product_details",
            ): envelope({"external_product_id": "product-1", "name": "Widget"}),
            (
                "stock",
                "get_stock_for_product",
            ): envelope({"external_product_id": "product-1", "branches": []}),
            (
                "stock",
                "find_branches_for_shopping_list",
            ): envelope({"complete": True, "visits": []}),
        }
    )
    ollama = FakeOllama(
        intent={"question_type": question_type, "parameters": parameters},
        reformulated="Product product-1 has stock.",
    )
    install_grounding_spy(monkeypatch, module)

    run(make_service(module, mcp, ollama).answer_question("question"))

    assert mcp.calls == expected_calls


@pytest.mark.parametrize(
    ("products", "items"),
    [
        (
            [],
            [
                {"product": "Widget", "requested_quantity": 1},
                {"product": "Gadget", "requested_quantity": 2},
            ],
        ),
        (
            [
                {"external_product_id": "product-1", "name": "Widget"},
                {"external_product_id": "product-2", "name": "Widget"},
            ],
            [{"product": "Widget", "requested_quantity": 1}],
        ),
    ],
)
def test_shopping_list_unknown_or_ambiguous_resolution_stops_before_stock(
    monkeypatch, products, items
):
    module = module_under_test()
    mcp = FakeMCP({("product", "list_products"): envelope({"products": products})})
    ollama = FakeOllama(
        intent={"question_type": "shopping_list", "parameters": {"items": items}},
        reformulated="Invented product-1 availability.",
    )
    calls, deterministic = install_grounding_spy(
        monkeypatch, module, status="unavailable", answer="No grounded data."
    )

    result = run(make_service(module, mcp, ollama).answer_question("question"))

    assert mcp.calls == [("product", "list_products", None)]
    assert calls == [("shopping_list", {})]
    assert result == deterministic
    assert ollama.reformulation_calls == []


@pytest.mark.parametrize(
    ("reference", "expected_list_call"),
    [
        ("product-ABC", False),
        ("Product-ABC", True),
        ("external-ABC", True),
    ],
)
def test_direct_product_resolution_requires_the_exact_external_id_shape(
    monkeypatch, reference, expected_list_call
):
    module = module_under_test()
    products = envelope(
        {
            "products": [
                {"external_product_id": "Product-ABC", "name": "Widget"},
                {"external_product_id": "external-ABC", "name": "Other"},
            ]
        }
    )
    mcp = FakeMCP(
        {
            ("product", "list_products"): products,
            ("product", "get_product_details"): envelope(
                public_product_detail(reference, "Widget")
            ),
        }
    )
    ollama = FakeOllama(
        intent={
            "question_type": "product_details",
            "parameters": {"product": reference},
        },
        reformulated=None,
    )
    install_grounding_spy(monkeypatch, module)

    run(make_service(module, mcp, ollama).answer_question("question"))

    if expected_list_call:
        assert mcp.calls[0] == ("product", "list_products", None)
    else:
        assert mcp.calls[0] == (
            "product",
            "get_product_details",
            {"external_product_id": reference},
        )


@pytest.mark.parametrize(
    "products",
    [
        [],
        [
            {"external_product_id": "product-1", "name": "Widget"},
            {"external_product_id": "product-2", "name": "Widget"},
        ],
    ],
)
def test_unknown_or_ambiguous_product_stops_downstream_calls_without_invention(
    monkeypatch, products
):
    module = module_under_test()
    mcp = FakeMCP({("product", "list_products"): envelope({"products": products})})
    ollama = FakeOllama(
        intent={"question_type": "product_details", "parameters": {"product": "Widget"}},
        reformulated="invented product-1",
    )
    calls, deterministic = install_grounding_spy(
        monkeypatch, module, status="unavailable", answer="No grounded data."
    )
    result = run(make_service(module, mcp, ollama).answer_question("question"))
    assert mcp.calls == [("product", "list_products", None)]
    assert calls == [("product_details", {})]
    assert result == deterministic
    assert ollama.reformulation_calls == []


def test_invalid_intent_uses_deterministic_fallback_and_never_reformulates(monkeypatch):
    module = module_under_test()
    mcp = FakeMCP({("product", "get_product_details"): envelope(public_product_detail())})
    ollama = FakeOllama(
        intent={"question_type": "product_details", "parameters": {"product": ""}},
        reformulated="must not be used",
    )
    calls, _ = install_grounding_spy(monkeypatch, module)
    run(make_service(module, mcp, ollama).answer_question("Tell me about product product-1"))
    assert mcp.calls == [
        ("product", "get_product_details", {"external_product_id": "product-1"})
    ]
    assert len(calls) == 1
    assert ollama.reformulation_calls == []


@pytest.mark.parametrize(
    ("question", "expected_calls"),
    [
        (
            "Tell me about product product-1",
            [("product", "get_product_details", {"external_product_id": "product-1"})],
        ),
        (
            "Where can I find product product-1?",
            [
                ("product", "get_product_details", {"external_product_id": "product-1"}),
                ("stock", "get_stock_for_product", {"external_product_id": "product-1"}),
            ],
        ),
        (
            "What products are available in branch 7?",
            [
                ("product", "list_products", None),
                ("stock", "list_branch_stock", {"branch_id": 7}),
            ],
        ),
        (
            "shopping list: 2 units of Widget, and 3 Gadget.",
            [
                ("product", "list_products", None),
                (
                    "stock",
                    "find_branches_for_shopping_list",
                    {
                        "items": [
                            {"external_product_id": "product-1", "quantity": 2},
                            {"external_product_id": "product-2", "quantity": 3},
                        ]
                    },
                ),
            ],
        ),
        (
            "2 Widget and 3 Gadget",
            [
                ("product", "list_products", None),
                (
                    "stock",
                    "find_branches_for_shopping_list",
                    {
                        "items": [
                            {"external_product_id": "product-1", "quantity": 2},
                            {"external_product_id": "product-2", "quantity": 3},
                        ]
                    },
                ),
            ],
        ),
        (
            "where can I find: 2 Widget, and 3 units of Gadget?",
            [
                ("product", "list_products", None),
                (
                    "stock",
                    "find_branches_for_shopping_list",
                    {
                        "items": [
                            {"external_product_id": "product-1", "quantity": 2},
                            {"external_product_id": "product-2", "quantity": 3},
                        ]
                    },
                ),
            ],
        ),
        (
            "shopping list 2 Widget and 3 Gadget",
            [
                ("product", "list_products", None),
                (
                    "stock",
                    "find_branches_for_shopping_list",
                    {
                        "items": [
                            {"external_product_id": "product-1", "quantity": 2},
                            {"external_product_id": "product-2", "quantity": 3},
                        ]
                    },
                ),
            ],
        ),
    ],
)
def test_provider_failure_uses_each_exact_deterministic_fallback_grammar(
    monkeypatch, question, expected_calls
):
    module = module_under_test()
    products = envelope(
        {
            "products": [
                {"external_product_id": "product-1", "name": "Widget"},
                {"external_product_id": "product-2", "name": "Gadget"},
            ]
        }
    )
    mcp = FakeMCP(
        {
            ("product", "list_products"): products,
            ("product", "get_product_details"): envelope(public_product_detail()),
            ("stock", "get_stock_for_product"): envelope({"external_product_id": "product-1", "branches": []}),
            ("stock", "list_branch_stock"): envelope({"branch_id": 7, "branch_name": "Central", "stocks": []}),
            ("stock", "find_branches_for_shopping_list"): envelope({"complete": True, "visits": []}),
        }
    )
    ollama = FakeOllama(intent_error=FakeProviderError("AI_PROVIDER_UNAVAILABLE"))
    calls, _ = install_grounding_spy(monkeypatch, module)

    run(make_service(module, mcp, ollama).answer_question(question))

    assert mcp.calls == expected_calls
    assert calls[0][0] in {
        "product_details",
        "product_availability",
        "branch_inventory",
        "shopping_list",
    }
    assert ollama.reformulation_calls == []


@pytest.mark.parametrize(
    "question",
    [
        "Tell me about product",
        "Tell me about product Widget and product Gadget",
        "What products are available in branch 0?",
        "What products are available in branch 7 and branch 8?",
        "shopping list: 2 Widget",
        "shopping list: 0 Widget and 2 Gadget",
        "shopping list: Widget and 2 Gadget",
        "shopping list: 2 Widget and 2 widget",
        "shopping list: 2 Widget and 3 Gadget extra",
    ],
)
def test_failed_deterministic_extraction_returns_provider_code_without_mcp(
    monkeypatch, question
):
    module = module_under_test()
    ollama = FakeOllama(intent_error=FakeProviderError("AI_PROVIDER_UNAVAILABLE"))
    mcp = FakeMCP()
    install_grounding_spy(monkeypatch, module)

    with pytest.raises(module.QuestionServiceError) as exc_info:
        run(make_service(module, mcp, ollama).answer_question(question))

    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert not mcp.calls
    assert ollama.reformulation_calls == []


def test_disabled_ollama_returns_the_official_provider_code_when_fallback_needs_parameters(
    monkeypatch,
):
    module = module_under_test()
    mcp = FakeMCP()
    ollama = FakeOllama()
    install_grounding_spy(monkeypatch, module)

    with pytest.raises(module.QuestionServiceError) as exc_info:
        run(
            module.QuestionService(mcp, ollama_client=ollama, ollama_enabled=False)
            .answer_question("Tell me about product")
        )

    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert not mcp.calls
    assert ollama.intent_calls == []


@pytest.mark.parametrize(
    "question",
    [
        "Tell me about product product-1",
        "Which branch has product product-1?",
        "What products are available in branch 7?",
        "2 units of Widget and 3 units of Gadget",
    ],
)
def test_disabled_ollama_uses_only_deterministic_fallback(monkeypatch, question):
    module = module_under_test()
    products = envelope(
        {
            "products": [
                {"external_product_id": "product-1", "name": "Widget"},
                {"external_product_id": "product-2", "name": "Gadget"},
            ]
        }
    )
    mcp = FakeMCP({("product", "list_products"): products})
    ollama = FakeOllama(intent={"question_type": "unsupported", "parameters": {}})
    install_grounding_spy(monkeypatch, module)
    result = run(module.QuestionService(mcp, ollama_client=ollama, ollama_enabled=False).answer_question(question))
    assert ollama.intent_calls == []
    assert ollama.reformulation_calls == []
    assert set(result) == {"status", "answer", "data"}


def test_fallback_failure_preserves_official_provider_error_code_and_makes_no_mcp_call(monkeypatch):
    module = module_under_test()
    error = FakeProviderError("UPSTREAM_TIMEOUT", "safe timeout")
    ollama = FakeOllama(error=error)
    mcp = FakeMCP()
    install_grounding_spy(monkeypatch, module)
    service = make_service(module, mcp, ollama)

    with pytest.raises(module.QuestionServiceError) as exc_info:
        run(service.answer_question("Tell me about product"))
    assert exc_info.value.code == "UPSTREAM_TIMEOUT"
    assert not mcp.calls


@pytest.mark.parametrize("status", ["unavailable", "unsupported"])
def test_unavailable_or_unsupported_never_invokes_second_ollama_call(monkeypatch, status):
    module = module_under_test()
    mcp = FakeMCP()
    ollama = FakeOllama(
        intent={"question_type": "unsupported", "parameters": {}},
        reformulated="must not be called",
    )
    install_grounding_spy(monkeypatch, module, status=status, answer="No data.")
    run(make_service(module, mcp, ollama).answer_question("unrelated question"))
    assert ollama.reformulation_calls == []


class RaisingMCP(FakeMCP):
    def __init__(self, error):
        super().__init__()
        self.error = error

    async def call_product_tool(self, tool_name, arguments=None):
        self.calls.append(("product", tool_name, arguments))
        raise self.error


def test_mcp_failure_is_not_reclassified_by_question_service(monkeypatch):
    module = module_under_test()
    mcp_error = RuntimeError("MCP error")
    mcp = RaisingMCP(mcp_error)
    ollama = FakeOllama(
        intent={
            "question_type": "product_details",
            "parameters": {"product": "product-1"},
        }
    )
    install_grounding_spy(monkeypatch, module)

    with pytest.raises(RuntimeError) as exc_info:
        run(make_service(module, mcp, ollama).answer_question("question"))

    assert exc_info.value is mcp_error


@pytest.mark.parametrize(
    "bad_intent",
    [
        {"question_type": "product_details", "parameters": {"product": ""}},
        {"question_type": "product_details", "parameters": {"product": "x"}, "extra": 1},
        {"question_type": "branch_inventory", "parameters": {"branch_id": True}},
        {"question_type": "branch_inventory", "parameters": {"branch_id": 0}},
        {"question_type": "shopping_list", "parameters": {"items": []}},
        {
            "question_type": "shopping_list",
            "parameters": {
                "items": [
                    {"product": "Widget", "requested_quantity": 1},
                    {"product": " widget ", "requested_quantity": 2},
                ]
            },
        },
        {"question_type": "unsupported", "parameters": {"product": "x"}},
    ],
)
def test_invalid_intention_schemas_fall_back_instead_of_reaching_mcp(monkeypatch, bad_intent):
    module = module_under_test()
    ollama = FakeOllama(intent=bad_intent)
    mcp = FakeMCP()
    install_grounding_spy(monkeypatch, module, status="unsupported", answer="Unsupported.")
    run(make_service(module, mcp, ollama).answer_question("What is unrelated?"))
    assert not mcp.calls
    assert ollama.reformulation_calls == []


def test_no_persistence_or_direct_database_or_product_api_access_is_introduced():
    module = module_under_test()
    source = inspect.getsource(module)
    assert "psycopg" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "product_api" not in source
    assert "postgres" not in source.lower()
