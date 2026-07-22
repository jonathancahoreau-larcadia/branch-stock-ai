"""Shared fixtures for Backoffice tests."""

import pytest

from backoffice import create_app


@pytest.fixture()
def app():
    """Create a Backoffice application configured for tests."""
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        }
    )


@pytest.fixture()
def client(app):
    """Create an HTTP client for the test application."""
    return app.test_client()
