"""Shared fixtures for Backoffice tests."""

import os
import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from backoffice import create_app
from backoffice.extensions import db


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


@pytest.fixture(scope="session")
def postgres_app():
    """Create a schema only in an explicitly dedicated PostgreSQL database."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL tests.")

    parsed_url = make_url(database_url)
    if not parsed_url.drivername.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL.")
    test_schema = os.getenv("TEST_DATABASE_SCHEMA")
    dedicated_database = bool(
        parsed_url.database and parsed_url.database.endswith("_test")
    )
    dedicated_schema = bool(
        test_schema and re.fullmatch(r"[a-z][a-z0-9_]*_test", test_schema)
    )
    if not dedicated_database and not dedicated_schema:
        pytest.fail(
            "PostgreSQL test database or schema name must end with '_test'."
        )

    bootstrap_engine = None
    if test_schema:
        if not dedicated_schema:
            pytest.fail("TEST_DATABASE_SCHEMA is not a safe test schema name.")
        bootstrap_url = parsed_url.set(query={})
        bootstrap_engine = create_engine(bootstrap_url)
        with bootstrap_engine.begin() as connection:
            connection.execute(CreateSchema(test_schema, if_not_exists=True))
        parsed_url = parsed_url.update_query_dict(
            {"options": f"-csearch_path={test_schema}"}
        )
        database_url = parsed_url.render_as_string(hide_password=False)

    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": database_url,
            "PRODUCT_API_BASE_URL": "http://product-api.test",
            "PRODUCT_API_TIMEOUT": "1",
            "ADMIN_INITIAL_PASSWORD": "integration-admin-password",
            "SEED_PRODUCT_ID": "HB-MON-2102",
            "BCRYPT_ROUNDS": "4",
        }
    )

    with application.app_context():
        db.drop_all()
        db.create_all()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()
    if test_schema and bootstrap_engine is not None:
        with bootstrap_engine.begin() as connection:
            connection.execute(
                DropSchema(test_schema, cascade=True, if_exists=True)
            )
        bootstrap_engine.dispose()


@pytest.fixture()
def clean_postgres_app(postgres_app):
    """Reset only the dedicated PostgreSQL seed-test tables."""
    with postgres_app.app_context():
        db.session.execute(
            text(
                "TRUNCATE TABLE revoked_tokens, stocks, users, branches "
                "RESTART IDENTITY CASCADE"
            )
        )
        db.session.commit()
        yield postgres_app
        db.session.rollback()
        db.session.remove()
