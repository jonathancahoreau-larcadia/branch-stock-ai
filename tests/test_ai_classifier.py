"""Contract tests for the deterministic public AI question classifier."""

from __future__ import annotations

import inspect
import importlib
import socket

import pytest


EXPECTED_TYPES = (
    "product_details",
    "product_availability",
    "branch_inventory",
    "shopping_list",
)


@pytest.fixture(autouse=True)
def forbid_real_sockets(monkeypatch):
    def fail_if_socket_is_opened(*_args, **_kwargs):
        raise AssertionError("AI classifier tests must not open a real socket")

    monkeypatch.setattr(socket, "socket", fail_if_socket_is_opened)


@pytest.fixture
def classifier():
    return importlib.import_module("ai_service.classifier")


def test_public_classifier_surface_is_stable(classifier):
    assert classifier.SUPPORTED_QUESTION_TYPES == EXPECTED_TYPES
    assert isinstance(classifier.SUPPORTED_QUESTION_TYPES, tuple)
    assert inspect.signature(classifier.classify_question).parameters.keys() == {
        "question"
    }


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Give me details about product XX.",
            "product_details",
        ),
        (
            "Which branch has stock of product X?",
            "product_availability",
        ),
        (
            "What products are available in branch Y?",
            "branch_inventory",
        ),
        (
            "Where can I find 3 units of X, 2 units of Y, and 4 units of Z?",
            "shopping_list",
        ),
    ],
)
def test_documented_question_examples_are_classified(classifier, question, expected):
    assert classifier.classify_question(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Donne-moi les détails du produit HB-MON-2102.", "product_details"),
        ("Dans quelle succursale reste-t-il des écrans ?", "product_availability"),
        ("Quels produits sont disponibles dans la succursale 2 ?", "branch_inventory"),
        ("Où trouver 2 unités de X et 3 unités de Y ?", "shopping_list"),
        ("Il reste combien de HB-MON-2102 ?", "product_availability"),
        ("Quelle agence possède ce produit ?", "product_availability"),
    ],
)
def test_french_question_families_accept_accents_apostrophes_and_sku_hyphens(
    classifier, question, expected
):
    assert classifier.classify_question(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("  GIVE\tME details\nabout product xx!!! ", "product_details"),
        ("Which—branch has STOCK of product x?!", "product_availability"),
        ("WHAT PRODUCTS are available in branch y…", "branch_inventory"),
        ("Ｗｈｅｒｅ　ｃａｎ　Ｉ　ｆｉｎｄ　３　ｕｎｉｔｓ　ｏｆ　Ｘ，２　ｕｎｉｔｓ　ｏｆ　Ｙ？", "shopping_list"),
    ],
)
def test_classification_normalizes_case_spacing_unicode_and_punctuation(
    classifier, question, expected
):
    assert classifier.classify_question(question) == expected


@pytest.mark.parametrize("question", [None, 4, True, [], {}, "", " \t\n"])
def test_non_string_or_empty_question_raises_the_contract_error(classifier, question):
    with pytest.raises(ValueError, match=r"^question must be a non-empty string$"):
        classifier.classify_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "hello there",
        "how are sales today",
        "tell me a joke",
        "what is the weather",
    ],
)
def test_questions_outside_the_four_families_are_unsupported(classifier, question):
    assert classifier.classify_question(question) == "unsupported"


@pytest.mark.parametrize(
    "question",
    [
        "shopping list: what products are available in branch Y; 2 units of X, 3 units of Y",
        "Which branch has stock of product X? 2 units of X and 4 units of Y",
        "Tell me about product details: 2 units of X, 3 units of Y",
    ],
)
def test_shopping_list_has_priority_over_other_matching_families(classifier, question):
    assert classifier.classify_question(question) == "shopping_list"


def test_branch_inventory_has_priority_over_availability_and_details(classifier):
    question = (
        "What products are available in branch Y? "
        "Which branch has stock of product X; tell me about product details"
    )
    assert classifier.classify_question(question) == "branch_inventory"


def test_product_availability_has_priority_over_product_details(classifier):
    question = "Tell me about which branch has stock of product X"
    assert classifier.classify_question(question) == "product_availability"


@pytest.mark.parametrize(
    "question",
    [
        "2 units of X",
        "one unit of X",
        "1 unit of X and no second item",
    ],
)
def test_a_single_or_non_numeric_item_does_not_make_a_shopping_list(classifier, question):
    assert classifier.classify_question(question) == "unsupported"


def test_shopping_list_phrase_is_supported_without_numeric_items(classifier):
    assert classifier.classify_question("Please show my shopping list") == "shopping_list"


@pytest.mark.parametrize(
    "question",
    [
        "2 units of X and 3 units of Y",
        "2 X, 3 Y",
        "10 units of long-product-name and 1 Z",
    ],
)
def test_two_non_overlapping_numeric_items_are_a_shopping_list(classifier, question):
    assert classifier.classify_question(question) == "shopping_list"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("what products", "branch_inventory"),
        ("which products", "branch_inventory"),
        ("products available in branch", "branch_inventory"),
        ("products are available in branch", "branch_inventory"),
        ("branch inventory", "branch_inventory"),
        ("inventory in branch", "branch_inventory"),
        ("inventory at branch", "branch_inventory"),
        ("which branch", "product_availability"),
        ("which store", "product_availability"),
        ("where can i find", "product_availability"),
        ("stock of", "product_availability"),
        ("in stock", "product_availability"),
        ("product availability", "product_availability"),
        ("product details", "product_details"),
        ("details about", "product_details"),
        ("details for", "product_details"),
        ("information about", "product_details"),
        ("information on", "product_details"),
        ("tell me about", "product_details"),
    ],
)
def test_each_contract_keyword_family_is_supported(classifier, phrase, expected):
    assert classifier.classify_question(f"Please {phrase} item X") == expected
