"""Deterministic classification of supported stock and product questions."""

from __future__ import annotations

import re
import unicodedata


SUPPORTED_QUESTION_TYPES: tuple[str, ...] = (
    "product_details",
    "product_availability",
    "branch_inventory",
    "shopping_list",
)

_SHOPPING_ITEM_PATTERN = re.compile(
    r"\b\d+\s+(?:(?:units?|unites?)\s+(?:of|de)\s+)?[\w-]+\b"
)
_BRANCH_INVENTORY_PHRASES = (
    "what products",
    "which products",
    "products available in branch",
    "products are available in branch",
    "branch inventory",
    "inventory in branch",
    "inventory at branch",
    "quels produits",
    "produits disponibles dans la succursale",
    "produits sont disponibles dans la succursale",
    "inventaire de la succursale",
)
_PRODUCT_AVAILABILITY_PHRASES = (
    "which branch",
    "which store",
    "where can i find",
    "stock of",
    "in stock",
    "product availability",
    "quelle succursale",
    "quelle agence",
    "ou trouver",
    "reste t il",
    "reste combien",
    "disponibilite du produit",
)
_PRODUCT_DETAILS_PHRASES = (
    "product details",
    "details about",
    "details of",
    "details for",
    "information about",
    "information on",
    "tell me about",
    "details du produit",
    "details sur",
    "informations sur",
    "donne moi les details",
)


def _normalize(question: str) -> str:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(character)
    )
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(without_punctuation.split())


def classify_question(question: str) -> str:
    """Return the supported family for a question, or ``unsupported``."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")

    normalized = _normalize(question)

    if (
        "shopping list" in normalized
        or len(_SHOPPING_ITEM_PATTERN.findall(normalized)) >= 2
    ):
        return "shopping_list"

    if any(phrase in normalized for phrase in _BRANCH_INVENTORY_PHRASES):
        return "branch_inventory"

    if any(phrase in normalized for phrase in _PRODUCT_AVAILABILITY_PHRASES):
        return "product_availability"

    if any(phrase in normalized for phrase in _PRODUCT_DETAILS_PHRASES):
        return "product_details"

    return "unsupported"
