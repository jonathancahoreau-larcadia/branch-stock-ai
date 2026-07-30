"""Python-controlled orchestration for independent public questions."""

from __future__ import annotations

import os as _os
import re as _re
import unicodedata as _unicodedata
from typing import Any as _Any

from ai_service.classifier import classify_question as _classify_question
from ai_service.generator import (
    generate_grounded_response,
    localize_grounded_response as _localize_grounded_response,
)
from ai_service.mcp_client import MCPClient
from ai_service.ollama_client import OllamaClient


__all__ = ["QuestionService", "QuestionServiceError"]

_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})
_SUPPORTED_TYPES = frozenset(
    {
        "product_details",
        "product_availability",
        "branch_inventory",
        "shopping_list",
    }
)
_PRODUCT_TOKEN = r"[A-Za-z0-9][A-Za-z0-9_-]*"
_ITEM = (
    r"[1-9][0-9]*\s+"
    r"(?:(?:units?|unités?)\s+(?:of|de)\s+)?"
    rf"{_PRODUCT_TOKEN}"
)
_PREFIX = (
    r"(?:(?:where\s+can\s+i\s+find|shopping\s+list|où\s+trouver)"
    r"\s*:?\s+)?"
)
_SEPARATOR = r"(?:\s*,\s*(?:(?:and|et)\s+)?|\s+(?:and|et)\s+)"
_SHOPPING_PATTERN = rf"{_PREFIX}{_ITEM}(?:{_SEPARATOR}{_ITEM})+\s*[.?!]?"
_SHOPPING_ITEM_PATTERN = _re.compile(
    (
        rf"([1-9][0-9]*)\s+"
        rf"(?:(?:units?|unités?)\s+(?:of|de)\s+)?({_PRODUCT_TOKEN})"
    ),
    flags=_re.IGNORECASE,
)
_DIRECT_PRODUCT_ID = _re.compile(
    r"(?:product-[A-Za-z0-9][A-Za-z0-9_-]*|HB-[A-Z0-9]+-[A-Z0-9]+)"
)
_DIRECT_FALLBACK_ID = _re.compile(
    r"\b(?:product-[A-Za-z0-9][A-Za-z0-9_-]*|HB-[A-Z0-9]+-[A-Z0-9]+)\b"
)
_TOKEN_PATTERN = _re.compile(r"[^\W_]+(?:-[^\W_]+)*", flags=_re.UNICODE)
_SURFACE_TOKENS = frozenset(
    {
        "an",
        "ce",
        "ces",
        "cette",
        "here",
        "la",
        "le",
        "les",
        "réponse",
        "answer",
        "the",
        "un",
        "une",
        "voici",
    }
)
_ERROR_MESSAGES = {
    "VALIDATION_ERROR": "The question must be a non-empty string of at most 1000 characters.",
    "AI_PROVIDER_UNAVAILABLE": "The AI provider could not determine the question parameters.",
    "UPSTREAM_TIMEOUT": "The AI provider timed out before the question parameters could be determined.",
}


class QuestionServiceError(RuntimeError):
    """Stable, safe orchestration error for a public question."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class QuestionService:
    """Validate intent, select approved read tools, and ground the response."""

    def __init__(
        self,
        mcp_client: MCPClient,
        ollama_client: OllamaClient | None = None,
        ollama_enabled: bool | None = None,
    ) -> None:
        self._mcp_client = mcp_client
        self._ollama_enabled = self._resolve_enabled(ollama_enabled)
        if self._ollama_enabled:
            self._ollama_client = (
                ollama_client if ollama_client is not None else OllamaClient()
            )
        else:
            self._ollama_client = ollama_client

    async def answer_question(self, question: str) -> dict[str, object]:
        """Answer one independent question from validated MCP results."""
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question.strip()) > 1000
        ):
            raise QuestionServiceError(
                "VALIDATION_ERROR", _ERROR_MESSAGES["VALIDATION_ERROR"]
            )
        normalized_question = question.strip()

        fallback_code = "AI_PROVIDER_UNAVAILABLE"
        deterministic_intent = self._fallback_intent(normalized_question)
        intent = (
            deterministic_intent
            if (
                deterministic_intent is not None
                and deterministic_intent["question_type"] != "unsupported"
            )
            else None
        )

        if intent is None and self._ollama_enabled:
            try:
                candidate = await self._ollama_client.generate_intent(
                    normalized_question
                )
            except Exception as exc:
                if getattr(exc, "code", None) == "UPSTREAM_TIMEOUT":
                    fallback_code = "UPSTREAM_TIMEOUT"
            else:
                if self._is_valid_intent(candidate):
                    if candidate["question_type"] != "unsupported":
                        intent = candidate
                    elif deterministic_intent is not None:
                        intent = deterministic_intent
                    else:
                        intent = candidate

        if intent is None:
            intent = deterministic_intent
            if intent is None:
                raise QuestionServiceError(
                    fallback_code, _ERROR_MESSAGES[fallback_code]
                )

        question_type = intent["question_type"]
        parameters = intent["parameters"]
        mcp_results = await self._collect_mcp_results(
            question_type, parameters
        )
        grounded = generate_grounded_response(question_type, mcp_results)
        return _localize_grounded_response(
            grounded, self._question_language(normalized_question)
        )

    async def _collect_mcp_results(
        self,
        question_type: str,
        parameters: dict[str, object],
    ) -> dict[str, dict[str, _Any]]:
        if question_type == "unsupported":
            return {}

        if question_type in {"product_details", "product_availability"}:
            reference = parameters["product"]
            resolved_id: str | None
            if _DIRECT_PRODUCT_ID.fullmatch(reference.strip()):
                resolved_id = reference.strip()
            else:
                products_result = await self._mcp_client.call_product_tool(
                    "list_products"
                )
                resolved_id = self._resolve_product(
                    reference, products_result
                )
            if resolved_id is None:
                return {}

            details = await self._mcp_client.call_product_tool(
                "get_product_details",
                {"external_product_id": resolved_id},
            )
            results = {"get_product_details": details}
            if question_type == "product_availability":
                stock = await self._mcp_client.call_stock_tool(
                    "get_stock_for_product",
                    {"external_product_id": resolved_id},
                )
                results["get_stock_for_product"] = stock
            return results

        products = await self._mcp_client.call_product_tool("list_products")
        if question_type == "branch_inventory":
            stock = await self._mcp_client.call_stock_tool(
                "list_branch_stock",
                {"branch_id": parameters["branch_id"]},
            )
            return {
                "list_products": products,
                "list_branch_stock": stock,
            }

        resolved_items = []
        for item in parameters["items"]:
            resolved_id = self._resolve_product(item["product"], products)
            if resolved_id is None:
                return {}
            resolved_items.append(
                {
                    "external_product_id": resolved_id,
                    "quantity": item["requested_quantity"],
                }
            )
        plan = await self._mcp_client.call_stock_tool(
            "find_branches_for_shopping_list",
            {"items": resolved_items},
        )
        return {
            "list_products": products,
            "find_branches_for_shopping_list": plan,
        }

    @staticmethod
    def _resolve_enabled(explicit: bool | None) -> bool:
        if explicit is not None:
            if not isinstance(explicit, bool):
                raise ValueError("ollama_enabled must be a boolean or None")
            return explicit
        configured = _os.environ.get("OLLAMA_ENABLED")
        if configured is None:
            return False
        canonical = configured.casefold()
        if canonical in _TRUE_VALUES:
            return True
        if canonical in _FALSE_VALUES:
            return False
        raise ValueError("OLLAMA_ENABLED has an invalid boolean value")

    @classmethod
    def _is_valid_intent(cls, intent: object) -> bool:
        if not isinstance(intent, dict) or set(intent) != {
            "question_type",
            "parameters",
        }:
            return False
        question_type = intent.get("question_type")
        parameters = intent.get("parameters")
        if not isinstance(parameters, dict):
            return False
        if question_type in {"product_details", "product_availability"}:
            return (
                set(parameters) == {"product"}
                and isinstance(parameters.get("product"), str)
                and bool(parameters["product"].strip())
            )
        if question_type == "branch_inventory":
            branch_id = parameters.get("branch_id")
            return (
                set(parameters) == {"branch_id"}
                and isinstance(branch_id, int)
                and not isinstance(branch_id, bool)
                and branch_id > 0
            )
        if question_type == "shopping_list":
            if set(parameters) != {"items"}:
                return False
            items = parameters.get("items")
            if not isinstance(items, list) or not items:
                return False
            seen: set[str] = set()
            for item in items:
                if not isinstance(item, dict) or set(item) != {
                    "product",
                    "requested_quantity",
                }:
                    return False
                product = item.get("product")
                quantity = item.get("requested_quantity")
                if (
                    not isinstance(product, str)
                    or not product.strip()
                    or not isinstance(quantity, int)
                    or isinstance(quantity, bool)
                    or quantity <= 0
                ):
                    return False
                canonical = cls._canon(product)
                if canonical in seen:
                    return False
                seen.add(canonical)
            return True
        return question_type == "unsupported" and not parameters

    @classmethod
    def _fallback_intent(
        cls, question: str
    ) -> dict[str, object] | None:
        question_type = _classify_question(question)
        normalized = _unicodedata.normalize("NFKC", question).strip()

        if question_type == "unsupported":
            return {"question_type": "unsupported", "parameters": {}}
        if question_type in {"product_details", "product_availability"}:
            direct_ids = _DIRECT_FALLBACK_ID.findall(normalized)
            if len(direct_ids) == 1:
                products = direct_ids
            else:
                products = _re.findall(
                    rf"\b(?:product|produit)\s+({_PRODUCT_TOKEN})\b",
                    normalized,
                    flags=_re.IGNORECASE,
                )
            if len(products) != 1:
                if (
                    not products
                    and _re.search(
                        r"\b(?:ce|cet|cette)\s+produit\b",
                        normalized,
                        flags=_re.IGNORECASE,
                    )
                ):
                    return {"question_type": "unsupported", "parameters": {}}
                return None
            return {
                "question_type": question_type,
                "parameters": {"product": products[0].strip()},
            }
        if question_type == "branch_inventory":
            branches = _re.findall(
                r"\b(?:branch|succursale|agence)\s+([1-9][0-9]*)\b",
                normalized,
                flags=_re.IGNORECASE,
            )
            if len(branches) != 1:
                return None
            return {
                "question_type": question_type,
                "parameters": {"branch_id": int(branches[0])},
            }
        if not _re.fullmatch(
            _SHOPPING_PATTERN, normalized, flags=_re.IGNORECASE
        ):
            return None
        items = [
            {
                "product": match.group(2),
                "requested_quantity": int(match.group(1)),
            }
            for match in _SHOPPING_ITEM_PATTERN.finditer(normalized)
        ]
        seen: set[str] = set()
        for item in items:
            canonical = cls._canon(item["product"])
            if canonical in seen:
                return None
            seen.add(canonical)
        return {
            "question_type": "shopping_list",
            "parameters": {"items": items},
        }

    @classmethod
    def _resolve_product(
        cls,
        reference: str,
        products_result: object,
    ) -> str | None:
        if not isinstance(products_result, dict):
            return None
        if products_result.get("status") != "success":
            return None
        data = products_result.get("data")
        if not isinstance(data, dict):
            return None
        products = data.get("products")
        if not isinstance(products, list):
            return None

        canonical_reference = cls._canon(reference)
        matches = []
        for product in products:
            if not isinstance(product, dict):
                continue
            external_id = product.get("external_product_id")
            name = product.get("name")
            if not isinstance(external_id, str) or not external_id.strip():
                continue
            fields = [
                value
                for value in (external_id, name)
                if isinstance(value, str) and value.strip()
            ]
            if any(cls._canon(value) == canonical_reference for value in fields):
                matches.append(external_id)
        if len(matches) != 1:
            return None
        return matches[0]

    @staticmethod
    def _canon(value: str) -> str:
        normalized = _unicodedata.normalize("NFKC", value)
        return " ".join(normalized.split()).casefold()

    @staticmethod
    def _question_language(question: str) -> str:
        canonical = _unicodedata.normalize("NFKD", question).casefold()
        canonical = "".join(
            character
            for character in canonical
            if not _unicodedata.combining(character)
        )
        canonical = " ".join(
            _re.sub(r"[^\w]+", " ", canonical, flags=_re.UNICODE).split()
        )
        french_markers = (
            "agence",
            "combien",
            "dans quelle",
            "details du",
            "donne moi",
            "inventaire",
            "meteo",
            "ou trouver",
            "parle moi",
            "produit",
            "produits",
            "quels produits",
            "reste t il",
            "succursale",
            "unite",
            "unites",
        )
        return (
            "fr"
            if any(marker in canonical for marker in french_markers)
            else "en"
        )

    @classmethod
    def _tokens(cls, value: str) -> tuple[str, ...]:
        return tuple(_TOKEN_PATTERN.findall(cls._canon(value)))

    @classmethod
    def _is_safe_reformulation(
        cls, deterministic_answer: object, candidate_answer: object
    ) -> bool:
        if (
            not isinstance(deterministic_answer, str)
            or not isinstance(candidate_answer, str)
            or not candidate_answer.strip()
            or len(candidate_answer.strip()) > 4000
        ):
            return False
        deterministic_tokens = cls._tokens(deterministic_answer)
        candidate_tokens = cls._tokens(candidate_answer)
        allowed_tokens = set(deterministic_tokens) | set(_SURFACE_TOKENS)
        if any(token not in allowed_tokens for token in candidate_tokens):
            return False
        deterministic_sequence = tuple(
            token
            for token in deterministic_tokens
            if token not in _SURFACE_TOKENS
        )
        candidate_sequence = tuple(
            token for token in candidate_tokens if token not in _SURFACE_TOKENS
        )
        return candidate_sequence == deterministic_sequence
