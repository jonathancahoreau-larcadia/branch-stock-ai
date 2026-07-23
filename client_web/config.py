"""Configuration for the Client Web Flask application."""

import os


class Config:
    """Configuration defaults loaded from environment variables."""

    SECRET_KEY: str = os.getenv("CLIENT_WEB_SECRET_KEY", "change-me-in-production")
    BACKOFFICE_BASE_URL: str = os.getenv(
        "BACKOFFICE_BASE_URL", "http://localhost:5000/api/v1"
    )
    BACKOFFICE_TIMEOUT: int = int(os.getenv("BACKOFFICE_TIMEOUT", "10"))

    # Session key names
    ACCESS_TOKEN_KEY: str = "access_token"
    REFRESH_TOKEN_KEY: str = "refresh_token"
    USER_KEY: str = "current_user"