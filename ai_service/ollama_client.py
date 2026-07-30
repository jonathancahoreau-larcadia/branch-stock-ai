"""Asynchronous standard-library client for the configured Ollama runtime."""

from __future__ import annotations

import asyncio as _asyncio
import json as _json
import math as _math
import os as _os
import threading as _threading
import unicodedata as _unicodedata
import urllib.request as _urllib_request
from urllib.parse import urlsplit as _urlsplit


__all__ = ["OllamaClient", "OllamaClientError"]

_INTENT_SYSTEM_PROMPT = (
    "You are the HBntory intent parser. Return one JSON object only with "
    "exactly question_type and parameters. question_type must be "
    "product_details, product_availability, branch_inventory, shopping_list, "
    "or unsupported. parameters must follow the requested type: product for "
    "product_details or product_availability, branch_id for branch_inventory, "
    "items with product and requested_quantity for shopping_list, and an "
    "empty object for unsupported. Never choose or name an MCP tool."
)
_REFORMULATION_SYSTEM_PROMPT = (
    "You reformulate one grounded HBntory response. Return one JSON object "
    "only with exactly answer. Do not add, remove, calculate, or change any "
    "product, identifier, branch, price, quantity, or stock fact. Answer in "
    "the user's language when possible."
)
_ERROR_MESSAGES = {
    "AI_PROVIDER_UNAVAILABLE": "The AI provider is unavailable.",
    "UPSTREAM_TIMEOUT": "The AI provider timed out.",
}
_QUESTION_TYPES = frozenset(
    {
        "product_details",
        "product_availability",
        "branch_inventory",
        "shopping_list",
        "unsupported",
    }
)


class OllamaClientError(RuntimeError):
    """Stable, safe error raised when Ollama cannot provide a valid result."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class OllamaClient:
    """Call Ollama's chat endpoint without blocking the asyncio event loop."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        keep_alive: str | None = None,
    ) -> None:
        configured_url = (
            base_url
            if base_url is not None
            else _os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        )
        configured_model = (
            model if model is not None else _os.environ.get("OLLAMA_MODEL")
        )
        configured_timeout: object = (
            timeout_seconds
            if timeout_seconds is not None
            else _os.environ.get("OLLAMA_TIMEOUT_SECONDS", "30")
        )
        configured_keep_alive = (
            keep_alive
            if keep_alive is not None
            else _os.environ.get("OLLAMA_KEEP_ALIVE", "5m")
        )

        self._base_url = self._validate_base_url(configured_url)
        self._model = self._validate_non_empty_string(
            configured_model, "model must be a non-empty string"
        )
        self._timeout_seconds = self._validate_timeout(configured_timeout)
        self._keep_alive = self._validate_non_empty_string(
            configured_keep_alive, "keep_alive must be a non-empty string"
        )

    async def generate_intent(self, question: str) -> dict[str, object]:
        """Return a strictly validated intent object."""
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")

        payload = self._payload(
            _INTENT_SYSTEM_PROMPT,
            question.strip(),
        )
        content = await self._run_off_loop(payload)
        intent = self._decode_content(content)
        if not self._is_valid_intent(intent):
            self._raise_invalid_response()
        return intent

    async def reformulate(
        self,
        question: str,
        grounded_response: dict[str, object],
    ) -> str:
        """Return the provider's strictly shaped reformulated answer."""
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        if not isinstance(grounded_response, dict):
            raise ValueError("grounded_response must be a dictionary")

        user_content = _json.dumps(
            {"grounded_response": grounded_response, "question": question},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload = self._payload(_REFORMULATION_SYSTEM_PROMPT, user_content)
        content = await self._run_off_loop(payload)
        reformulation = self._decode_content(content)
        if (
            not isinstance(reformulation, dict)
            or set(reformulation) != {"answer"}
            or not isinstance(reformulation["answer"], str)
            or not reformulation["answer"].strip()
        ):
            self._raise_invalid_response()
        return reformulation["answer"]

    def _payload(self, system_prompt: str, user_content: str) -> dict[str, object]:
        return {
            "model": self._model,
            "stream": False,
            "keep_alive": self._keep_alive,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }

    async def _run_off_loop(self, payload: dict[str, object]) -> str:
        outcome: list[object] = []

        def run() -> None:
            try:
                outcome.append(self._post(payload))
            except BaseException as exc:
                outcome.append(exc)

        worker = _threading.Thread(target=run, daemon=True)
        worker.start()
        while worker.is_alive():
            await _asyncio.sleep(0.001)
        worker.join()

        result = outcome[0]
        if isinstance(result, BaseException):
            raise result
        return result

    def _post(self, payload: dict[str, object]) -> str:
        body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = _urllib_request.Request(
            f"{self._base_url}/api/chat",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with _urllib_request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                status = response.getcode()
                if (
                    isinstance(status, bool)
                    or not isinstance(status, int)
                    or not 200 <= status < 300
                ):
                    self._raise_invalid_response()
                raw_response = response.read()
        except OllamaClientError:
            raise
        except TimeoutError as exc:
            raise OllamaClientError(
                "UPSTREAM_TIMEOUT", _ERROR_MESSAGES["UPSTREAM_TIMEOUT"]
            ) from exc
        except Exception as exc:
            raise OllamaClientError(
                "AI_PROVIDER_UNAVAILABLE",
                _ERROR_MESSAGES["AI_PROVIDER_UNAVAILABLE"],
            ) from exc

        try:
            envelope = _json.loads(raw_response.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, _json.JSONDecodeError) as exc:
            raise OllamaClientError(
                "AI_PROVIDER_UNAVAILABLE",
                _ERROR_MESSAGES["AI_PROVIDER_UNAVAILABLE"],
            ) from exc

        if not isinstance(envelope, dict):
            self._raise_invalid_response()
        message = envelope.get("message")
        if not isinstance(message, dict):
            self._raise_invalid_response()
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            self._raise_invalid_response()
        return content

    @staticmethod
    def _decode_content(content: str) -> object:
        try:
            return _json.loads(content)
        except _json.JSONDecodeError as exc:
            raise OllamaClientError(
                "AI_PROVIDER_UNAVAILABLE",
                _ERROR_MESSAGES["AI_PROVIDER_UNAVAILABLE"],
            ) from exc

    @staticmethod
    def _validate_base_url(value: object) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("base_url must be a valid HTTP(S) URL")
        try:
            parsed = _urlsplit(value)
            parsed.port
        except ValueError as exc:
            raise ValueError("base_url must be a valid HTTP(S) URL") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("base_url must be a valid HTTP(S) URL")
        return value.rstrip("/")

    @staticmethod
    def _validate_non_empty_string(value: object, message: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(message)
        return value.strip()

    @staticmethod
    def _validate_timeout(value: object) -> float:
        if isinstance(value, bool):
            raise ValueError("timeout_seconds must be a finite positive number")
        try:
            timeout = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "timeout_seconds must be a finite positive number"
            ) from exc
        if not _math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout_seconds must be a finite positive number")
        return timeout

    @classmethod
    def _is_valid_intent(cls, intent: object) -> bool:
        if not isinstance(intent, dict) or set(intent) != {
            "question_type",
            "parameters",
        }:
            return False
        question_type = intent.get("question_type")
        parameters = intent.get("parameters")
        if question_type not in _QUESTION_TYPES or not isinstance(
            parameters, dict
        ):
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
            canonical_products: set[str] = set()
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
                canonical = cls._canonical_product(product)
                if canonical in canonical_products:
                    return False
                canonical_products.add(canonical)
            return True
        return question_type == "unsupported" and not parameters

    @staticmethod
    def _canonical_product(value: str) -> str:
        normalized = _unicodedata.normalize("NFKC", value)
        return " ".join(normalized.split()).casefold()

    @staticmethod
    def _raise_invalid_response() -> None:
        raise OllamaClientError(
            "AI_PROVIDER_UNAVAILABLE",
            _ERROR_MESSAGES["AI_PROVIDER_UNAVAILABLE"],
        )
