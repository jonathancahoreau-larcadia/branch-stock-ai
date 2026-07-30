"""Configuration defaults and environment loading for the Backoffice."""

import os
from datetime import timedelta

ACCESS_TOKEN_EXPIRES_IN = 1800
REFRESH_TOKEN_EXPIRES_IN = 604800


def validate_runtime_value(name: str, value: object) -> str:
    """Return a non-placeholder runtime value without exposing it on error."""
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{name} must be set to a real runtime value.")
    normalized = value.strip()
    folded = normalized.casefold()
    placeholder_markers = (
        "replace-with-",
        "replace_with_",
        "replace-me",
        "replace_me",
    )
    if (
        any(marker in folded for marker in placeholder_markers)
        or (normalized.startswith("<") and normalized.endswith(">"))
        or (normalized.startswith("${") and normalized.endswith("}"))
    ):
        raise RuntimeError(
            f"{name} must not use a documented placeholder value."
        )
    return normalized


def get_database_url() -> str | None:
    """Read and normalize the database URL from the environment."""
    database_url = os.getenv("DATABASE_URL")

    if database_url is not None and database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    return database_url


def get_jwt_secret() -> str | None:
    """Read the JWT signing secret without providing an unsafe default."""
    return os.getenv("JWT_SECRET_KEY")


class Config:
    """Base application configuration."""

    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=ACCESS_TOKEN_EXPIRES_IN
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=REFRESH_TOKEN_EXPIRES_IN
    )
    JWT_TOKEN_LOCATION = ("headers",)
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    PRODUCT_API_BASE_URL = os.getenv(
        "PRODUCT_API_BASE_URL",
        "http://localhost:5001",
    )
    PRODUCT_API_TIMEOUT = os.getenv("PRODUCT_API_TIMEOUT", "5")
    APP_ENV = os.getenv("APP_ENV")
    ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD")
    LARGE_SEED_USER_PASSWORD = os.getenv("LARGE_SEED_USER_PASSWORD")
    SEED_PRODUCT_ID = os.getenv("SEED_PRODUCT_ID", "HB-MON-2102")
    BCRYPT_ROUNDS = os.getenv("BCRYPT_ROUNDS", "12")
