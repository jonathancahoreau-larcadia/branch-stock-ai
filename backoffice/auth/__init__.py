"""Authentication module."""

from .callbacks import register_jwt_callbacks
from .routes import auth_blueprint

__all__ = ["auth_blueprint", "register_jwt_callbacks"]
