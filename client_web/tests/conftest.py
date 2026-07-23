"""Pytest fixtures for the Client Web tests."""

from __future__ import annotations

from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient

from ..app import create_app


@pytest.fixture
def app() -> Flask:
    """Create a Client Web application instance configured for testing."""
    application = create_app(
        test_config={
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "BACKOFFICE_BASE_URL": "http://test-backoffice:5000/api/v1",
            "BACKOFFICE_TIMEOUT": 1,
        }
    )
    return application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide a test HTTP client for the Flask application."""
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def mock_backoffice(monkeypatch: Any) -> Generator[MagicMock, None, None]:
    """Replace the module-level ``BackofficeClient`` with a MagicMock.

    The mock is applied to ``client_web.app.client`` so that every method
    (``login``, ``list_stocks``, …) returns a controllable result without
    reaching a real Backoffice.
    """
    mock = MagicMock()
    monkeypatch.setattr("client_web.app.client", mock)
    yield mock