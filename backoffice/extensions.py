"""Central initialization point for Flask extensions."""

from pathlib import Path

from flask import Flask
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

MIGRATIONS_DIRECTORY = Path(__file__).parent / "database" / "migrations"

db = SQLAlchemy()
jwt = JWTManager()
migrate = Migrate(directory=str(MIGRATIONS_DIRECTORY))


def init_extensions(app: Flask) -> None:
    """Initialize Flask extensions registered by the Backoffice."""
    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
