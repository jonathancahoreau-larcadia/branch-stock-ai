"""Tests for the Backoffice database foundation."""

import pytest

from backoffice import create_app
from backoffice.extensions import db, jwt, migrate

TEST_JWT_SECRET = "test-only-jwt-secret-not-for-production"


def test_database_url_is_read_for_each_application(monkeypatch):
    """Each application reads the current database URL from the environment."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/first_database")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    first_app = create_app()

    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/second_database")
    second_app = create_app()

    assert first_app.config["SQLALCHEMY_DATABASE_URI"] == (
        "postgresql+psycopg://localhost/first_database"
    )
    assert second_app.config["SQLALCHEMY_DATABASE_URI"] == (
        "postgresql+psycopg://localhost/second_database"
    )


def test_only_plain_postgresql_scheme_is_normalized(monkeypatch):
    """URLs already selecting a driver remain unchanged."""
    database_url = "postgresql+psycopg://localhost/hbntory"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    app = create_app()

    assert app.config["SQLALCHEMY_DATABASE_URI"] == database_url


def test_test_config_database_uri_has_priority(monkeypatch):
    """An explicit test URI takes priority over the environment."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/hbntory")
    test_database_uri = "sqlite+pysqlite:///:memory:"

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": test_database_uri,
            "JWT_SECRET_KEY": TEST_JWT_SECRET,
        }
    )

    assert app.config["SQLALCHEMY_DATABASE_URI"] == test_database_uri


def test_database_url_is_required_without_test_override(monkeypatch):
    """Application startup fails clearly when no database URI is available."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        create_app()


def test_jwt_secret_is_required_outside_tests(monkeypatch):
    """Production-like startup never falls back to a signing secret."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/hbntory")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
        create_app()


def test_non_test_config_cannot_inject_jwt_secret(monkeypatch):
    """Only the environment may supply a production signing secret."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
        create_app(
            {
                "SQLALCHEMY_DATABASE_URI": (
                    "sqlite+pysqlite:///:memory:"
                ),
                "JWT_SECRET_KEY": "injected-secret",
            }
        )


def test_database_extensions_are_initialized(app):
    """SQLAlchemy and Flask-Migrate share the configured application."""
    assert app.extensions["sqlalchemy"] is db
    assert app.extensions["flask-jwt-extended"] is jwt
    assert app.extensions["migrate"].db is db
    assert app.extensions["migrate"].migrate is migrate
    assert app.config["JWT_TOKEN_LOCATION"] == ("headers",)
    assert app.config["JWT_HEADER_NAME"] == "Authorization"
    assert app.config["JWT_HEADER_TYPE"] == "Bearer"


def test_database_cli_is_registered(app):
    """Flask-Migrate exposes its database command group."""
    assert "db" in app.cli.commands
