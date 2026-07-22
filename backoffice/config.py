"""Configuration defaults and environment loading for the Backoffice."""

import os


def get_database_url() -> str | None:
    """Read and normalize the database URL from the environment."""
    database_url = os.getenv("DATABASE_URL")

    if database_url is not None and database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    return database_url


class Config:
    """Base application configuration."""

    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
