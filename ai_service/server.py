"""Public HTTP adapter for the AI Query Service."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request
from flask.testing import FlaskClient
from werkzeug.exceptions import BadRequest

from ai_service.mcp_client import MCPClient
from ai_service.question_service import QuestionService


_INVALID_JSON_MESSAGE = "Request body must be valid JSON."
_VALIDATION_MESSAGE = (
    "The question must be a non-empty string of at most 1000 characters."
)
_INTERNAL_ERROR_MESSAGE = "An unexpected error occurred."
_APPLICATION_ERROR_STATUSES = {
    "MCP_ERROR": 502,
    "MCP_UNAVAILABLE": 503,
    "AI_PROVIDER_UNAVAILABLE": 503,
    "UPSTREAM_TIMEOUT": 504,
}


class _JsonNullAwareClient(FlaskClient):
    """Keep an explicit ``json=None`` distinct from an absent request body."""

    def open(self, *args: Any, **kwargs: Any) -> Response:
        if "json" in kwargs and kwargs["json"] is None and "data" not in kwargs:
            kwargs.pop("json")
            kwargs["data"] = self.application.json.dumps(None)
            kwargs.setdefault("content_type", "application/json")
        return super().open(*args, **kwargs)


def _error_response(code: str, message: str, status: int) -> tuple[Response, int]:
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": {},
                }
            }
        ),
        status,
    )


def _validate_origin(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("CLIENT_WEB_ORIGIN must be a valid HTTP(S) origin")

    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as exc:
        raise ValueError(
            "CLIENT_WEB_ORIGIN must be a valid HTTP(S) origin"
        ) from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("CLIENT_WEB_ORIGIN must be a valid HTTP(S) origin")
    return value


def create_app(
    question_service: QuestionService | None = None,
    test_config: dict[str, Any] | None = None,
) -> Flask:
    """Create the public HTTP adapter without starting network activity."""
    app = Flask(__name__)
    app.test_client_class = _JsonNullAwareClient
    app.config.from_mapping(
        CLIENT_WEB_ORIGIN=os.environ.get("CLIENT_WEB_ORIGIN"),
    )
    if test_config is not None:
        app.config.update(test_config)

    allowed_origin = _validate_origin(app.config.get("CLIENT_WEB_ORIGIN"))
    service = (
        question_service
        if question_service is not None
        else QuestionService(MCPClient())
    )

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        origin = request.headers.get("Origin")
        if allowed_origin is not None and origin == allowed_origin:
            response.headers["Access-Control-Allow-Origin"] = allowed_origin
            response.headers["Vary"] = "Origin"
            if request.method == "OPTIONS" and request.path == "/questions":
                response.headers["Access-Control-Allow-Methods"] = (
                    "POST, OPTIONS"
                )
                response.headers["Access-Control-Allow-Headers"] = (
                    "Content-Type"
                )
        return response

    @app.get("/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.route("/questions", methods=["POST", "OPTIONS"])
    def questions() -> Response | tuple[Response, int]:
        if request.method == "OPTIONS":
            return Response(status=204)

        if request.mimetype != "application/json":
            return _error_response("INVALID_JSON", _INVALID_JSON_MESSAGE, 400)
        try:
            payload = request.get_json()
        except BadRequest:
            return _error_response("INVALID_JSON", _INVALID_JSON_MESSAGE, 400)

        if not isinstance(payload, dict):
            return _error_response("VALIDATION_ERROR", _VALIDATION_MESSAGE, 400)
        question = payload.get("question")
        if not isinstance(question, str):
            return _error_response("VALIDATION_ERROR", _VALIDATION_MESSAGE, 400)
        normalized_question = question.strip()
        if not normalized_question or len(normalized_question) > 1000:
            return _error_response("VALIDATION_ERROR", _VALIDATION_MESSAGE, 400)

        try:
            result = asyncio.run(service.answer_question(normalized_question))
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None)
            status = _APPLICATION_ERROR_STATUSES.get(code)
            if status is not None and isinstance(message, str):
                return _error_response(code, message, status)
            return _error_response(
                "INTERNAL_ERROR",
                _INTERNAL_ERROR_MESSAGE,
                500,
            )
        return jsonify(result)

    return app


def main() -> None:
    """Run the HTTP adapter with validated process configuration."""
    configured_port = os.environ.get("AI_SERVICE_PORT", "8000")
    try:
        port = int(configured_port)
    except (TypeError, ValueError) as exc:
        raise ValueError("AI_SERVICE_PORT must be a positive integer") from exc
    if port <= 0:
        raise ValueError("AI_SERVICE_PORT must be a positive integer")

    app = create_app()
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
