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
    PRODUCT_API_BASE_URL = os.getenv(
        "PRODUCT_API_BASE_URL",
        "http://localhost:5001",
    )
    PRODUCT_API_TIMEOUT = os.getenv("PRODUCT_API_TIMEOUT", "5")
    ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD")
    SEED_PRODUCT_ID = os.getenv("SEED_PRODUCT_ID", "HB-MON-2102")
    BCRYPT_ROUNDS = os.getenv("BCRYPT_ROUNDS", "12")
