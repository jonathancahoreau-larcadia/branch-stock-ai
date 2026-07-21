"""Tests for the Backoffice database foundation."""

import pytest

from backoffice import create_app
from backoffice.extensions import db, migrate


def test_database_url_is_read_for_each_application(monkeypatch):
    """Each application reads the current database URL from the environment."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/first_database")
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
        }
    )

    assert app.config["SQLALCHEMY_DATABASE_URI"] == test_database_uri


def test_database_url_is_required_without_test_override(monkeypatch):
    """Application startup fails clearly when no database URI is available."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        create_app()


def test_database_extensions_are_initialized(app):
    """SQLAlchemy and Flask-Migrate share the configured application."""
    assert app.extensions["sqlalchemy"] is db
    assert app.extensions["migrate"].db is db
    assert app.extensions["migrate"].migrate is migrate


def test_database_cli_is_registered(app):
    """Flask-Migrate exposes its database command group."""
    assert "db" in app.cli.commands
