"""Tests for Backoffice application creation."""

from flask import Flask

import pytest

from backoffice import create_app


def test_application_starts(app):
    """The application factory returns a configured Flask application."""
    assert isinstance(app, Flask)
    assert app.testing is True
    assert app.config["JWT_SECRET_KEY"] == (
        "test-only-jwt-secret-not-for-production"
    )


def test_application_registers_expected_route_groups(app):
    """The application factory registers every expected API route group."""
    registered_routes = {
        rule.rule
        for rule in app.url_map.iter_rules()
    }

    expected_route_prefixes = {
        "/health",
        "/api/v1/auth",
        "/api/v1/users",
        "/api/v1/branches",
        "/api/v1/stocks",
        "/api/v1/products",
    }

    missing_prefixes = {
        prefix
        for prefix in expected_route_prefixes
        if not any(
            route == prefix
            or route.startswith(f"{prefix}/")
            for route in registered_routes
        )
    }

    assert not missing_prefixes, (
        "Missing expected route groups: "
        + ", ".join(sorted(missing_prefixes))
    )


def test_application_registers_large_seed_command(app):
    """The independent large seed is available without replacing seed."""
    commands = app.cli.list_commands(app.test_cli_runner())

    assert "seed" in commands
    assert "seed-large" in commands
    assert "admin-password" in commands


@pytest.mark.parametrize("key", ["JWT_SECRET_KEY", "DATABASE_URL"])
def test_create_app_rejects_runtime_placeholder_before_database_use(monkeypatch, key):
    monkeypatch.setenv("JWT_SECRET_KEY", "real-jwt-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv(key, "replace-with-secret")

    with pytest.raises((RuntimeError, ValueError)) as error:
        create_app({"TESTING": False, "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:"})

    assert "replace-with-secret" not in str(error.value)
