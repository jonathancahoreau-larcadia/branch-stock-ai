"""Initialize PostgreSQL identities before starting the Backoffice.

Migration uses MIGRATION_DATABASE_URL with the exact command
``python -m flask --app backoffice db upgrade``. Seed uses DATABASE_URL,
ADMIN_INITIAL_PASSWORD, SEED_PRODUCT_ID and BCRYPT_ROUNDS with the exact
command ``python -m flask --app backoffice seed``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import sql


_APPLICATION_ROOT = str(Path(__file__).resolve().parents[1])
if _APPLICATION_ROOT not in sys.path:
    sys.path.insert(0, _APPLICATION_ROOT)

from backoffice.config import validate_runtime_value


ROLE_NAMES = {
    "MIGRATION_DB_USER": "migration_user",
    "BACKOFFICE_DB_USER": "backoffice_app",
    "STOCK_MCP_DB_USER": "stock_reader",
}
REQUIRED_VARIABLES = (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "MIGRATION_DB_USER",
    "MIGRATION_DB_PASSWORD",
    "BACKOFFICE_DB_USER",
    "BACKOFFICE_DB_PASSWORD",
    "STOCK_MCP_DB_USER",
    "STOCK_MCP_DB_PASSWORD",
    "MIGRATION_DATABASE_URL",
    "DATABASE_URL",
    "STOCK_MCP_DATABASE_URL",
    "JWT_SECRET_KEY",
    "ADMIN_INITIAL_PASSWORD",
    "SEED_PRODUCT_ID",
    "BCRYPT_ROUNDS",
    "PRODUCT_API_BASE_URL",
    "PRODUCT_API_TIMEOUT",
)


class BootstrapConfigurationError(RuntimeError):
    """Raised when required runtime configuration is unsafe or incomplete."""


@dataclass(frozen=True)
class Configuration:
    values: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.values[key]


def _required_environment() -> Configuration:
    values: dict[str, str] = {}
    for key in REQUIRED_VARIABLES:
        value = os.environ.get(key)
        if value is None or not value.strip():
            raise BootstrapConfigurationError(
                f"Required runtime variable is missing: {key}"
            )
        values[key] = value

    for key in (
        "JWT_SECRET_KEY",
        "ADMIN_INITIAL_PASSWORD",
        "POSTGRES_PASSWORD",
        "MIGRATION_DB_PASSWORD",
        "BACKOFFICE_DB_PASSWORD",
        "STOCK_MCP_DB_PASSWORD",
        "MIGRATION_DATABASE_URL",
        "DATABASE_URL",
        "STOCK_MCP_DATABASE_URL",
    ):
        try:
            values[key] = validate_runtime_value(key, values[key])
        except RuntimeError as exc:
            raise BootstrapConfigurationError(str(exc)) from None

    for key, expected in ROLE_NAMES.items():
        if values[key] != expected:
            raise BootstrapConfigurationError(
                f"Runtime role name does not match the contract: {key}"
            )

    identities = {
        values["POSTGRES_USER"],
        values["MIGRATION_DB_USER"],
        values["BACKOFFICE_DB_USER"],
        values["STOCK_MCP_DB_USER"],
    }
    if len(identities) != 4:
        raise BootstrapConfigurationError(
            "Bootstrap and application database identities must be distinct."
        )

    _validate_database_url(
        values["MIGRATION_DATABASE_URL"],
        values["MIGRATION_DB_USER"],
        values["MIGRATION_DB_PASSWORD"],
        values["POSTGRES_DB"],
    )
    _validate_database_url(
        values["DATABASE_URL"],
        values["BACKOFFICE_DB_USER"],
        values["BACKOFFICE_DB_PASSWORD"],
        values["POSTGRES_DB"],
    )
    _validate_database_url(
        values["STOCK_MCP_DATABASE_URL"],
        values["STOCK_MCP_DB_USER"],
        values["STOCK_MCP_DB_PASSWORD"],
        values["POSTGRES_DB"],
    )
    return Configuration(values)


def _validate_database_url(
    value: str,
    expected_user: str,
    expected_password: str,
    expected_database: str,
) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise BootstrapConfigurationError(
            "A runtime database URL is invalid."
        ) from exc

    if (
        parsed.scheme not in {"postgresql", "postgresql+psycopg"}
        or parsed.hostname != "database"
        or port != 5432
        or unquote(parsed.username or "") != expected_user
        or unquote(parsed.password or "") != expected_password
        or unquote(parsed.path.lstrip("/")) != expected_database
        or parsed.query
        or parsed.fragment
    ):
        raise BootstrapConfigurationError(
            "A runtime database URL does not match its approved identity."
        )


def _role_statement(
    exists: bool,
    role: str,
    password: str,
) -> sql.Composed:
    statement = (
        "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
        if exists
        else
        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
    )
    return sql.SQL(statement).format(
        sql.Identifier(role),
        sql.Literal(password),
    )


def _align_roles(connection: psycopg.Connection, config: Configuration) -> None:
    with connection.cursor() as cursor:
        for user_key, password_key in (
            ("MIGRATION_DB_USER", "MIGRATION_DB_PASSWORD"),
            ("BACKOFFICE_DB_USER", "BACKOFFICE_DB_PASSWORD"),
            ("STOCK_MCP_DB_USER", "STOCK_MCP_DB_PASSWORD"),
        ):
            role = config[user_key]
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
                (role,),
            )
            exists = cursor.fetchone()[0]
            # Idempotent equivalent of CREATE ROLE IF NOT EXISTS / DO $$.
            cursor.execute(
                _role_statement(exists, role, config[password_key])
            )

            cursor.execute(
                """
                SELECT parent.rolname
                FROM pg_auth_members membership
                JOIN pg_roles parent ON parent.oid = membership.roleid
                JOIN pg_roles member ON member.oid = membership.member
                WHERE member.rolname = %s
                """,
                (role,),
            )
            for (parent_role,) in cursor.fetchall():
                cursor.execute(
                    sql.SQL("REVOKE {} FROM {}").format(
                        sql.Identifier(parent_role),
                        sql.Identifier(role),
                    )
                )


def _prepare_migration_access(
    connection: psycopg.Connection,
    config: Configuration,
) -> None:
    database = sql.Identifier(config["POSTGRES_DB"])
    migration = sql.Identifier(config["MIGRATION_DB_USER"])
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT CONNECT, CREATE ON DATABASE {} TO {}").format(
                database,
                migration,
            )
        )
        cursor.execute(
            sql.SQL(
                "GRANT USAGE, CREATE ON SCHEMA public TO {}"
            ).format(migration)
        )


def _run_migration(config: Configuration) -> None:
    migration_environment = os.environ.copy()
    migration_environment["DATABASE_URL"] = config[
        "MIGRATION_DATABASE_URL"
    ]
    subprocess.run(
        [
            "python",
            "-m",
            "flask",
            "--app",
            "backoffice",
            "db",
            "upgrade",
        ],
        check=True,
        env=migration_environment,
    )


def _apply_runtime_grants(
    connection: psycopg.Connection,
    config: Configuration,
) -> None:
    database = sql.Identifier(config["POSTGRES_DB"])
    migration = sql.Identifier(config["MIGRATION_DB_USER"])
    backoffice = sql.Identifier(config["BACKOFFICE_DB_USER"])
    stock_reader = sql.Identifier(config["STOCK_MCP_DB_USER"])

    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                database,
                backoffice,
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                database,
                backoffice,
            )
        )
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA public FROM {}").format(
                backoffice
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(backoffice)
        )
        cursor.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                "IN SCHEMA public TO {}"
            ).format(backoffice)
        )
        cursor.execute(
            sql.SQL(
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES "
                "IN SCHEMA public TO {}"
            ).format(backoffice)
        )
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
            ).format(migration, backoffice)
        )
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
            ).format(migration, backoffice)
        )

        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                database,
                stock_reader,
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                database,
                stock_reader,
            )
        )
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA public FROM {}").format(
                stock_reader
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(stock_reader)
        )
        cursor.execute(
            sql.SQL(
                "REVOKE ALL PRIVILEGES ON ALL TABLES "
                "IN SCHEMA public FROM {}"
            ).format(stock_reader)
        )
        cursor.execute(
            sql.SQL(
                "REVOKE ALL PRIVILEGES ON ALL SEQUENCES "
                "IN SCHEMA public FROM {}"
            ).format(stock_reader)
        )
        cursor.execute(
            sql.SQL(
                "REVOKE ALL PRIVILEGES ON TABLE "
                "public.users, public.revoked_tokens FROM {}"
            ).format(stock_reader)
        )
        cursor.execute(
            sql.SQL(
                "REVOKE ALL PRIVILEGES ON TABLE "
                "public.branches, public.stocks FROM {}"
            ).format(stock_reader)
        )
        cursor.execute(
            sql.SQL(
                "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
                "ON TABLE public.branches, public.stocks FROM {}"
            ).format(stock_reader)
        )
        cursor.execute(
            sql.SQL(
                "GRANT SELECT ON TABLE public.branches, public.stocks TO {}"
            ).format(stock_reader)
        )
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "REVOKE ALL PRIVILEGES ON TABLES FROM {}"
            ).format(migration, stock_reader)
        )


def _run_seed(config: Configuration) -> None:
    seed_environment = os.environ.copy()
    seed_environment["DATABASE_URL"] = config["DATABASE_URL"]
    seed_environment["ADMIN_INITIAL_PASSWORD"] = config[
        "ADMIN_INITIAL_PASSWORD"
    ]
    seed_environment["SEED_PRODUCT_ID"] = config["SEED_PRODUCT_ID"]
    seed_environment["BCRYPT_ROUNDS"] = config["BCRYPT_ROUNDS"]
    subprocess.run(
        ["python", "-m", "flask", "--app", "backoffice", "seed"],
        check=True,
        env=seed_environment,
    )


def main() -> int:
    try:
        config = _required_environment()
        with psycopg.connect(
            host="database",
            port=5432,
            dbname=config["POSTGRES_DB"],
            user=config["POSTGRES_USER"],
            password=config["POSTGRES_PASSWORD"],
            autocommit=True,
        ) as connection:
            _align_roles(connection, config)
            _prepare_migration_access(connection, config)
            _run_migration(config)
            _apply_runtime_grants(connection, config)
            _run_seed(config)
    except BootstrapConfigurationError as exc:
        print(
            f"Backoffice database initialization failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except (psycopg.Error, subprocess.SubprocessError):
        print("Backoffice database initialization failed.", file=sys.stderr)
        return 1

    print("Backoffice database initialization completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
