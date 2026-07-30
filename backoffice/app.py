"""Flask application factory for the Backoffice service."""

from flask import Flask

from .api_errors import register_api_error_handlers
from .auth import auth_blueprint, register_jwt_callbacks
from .branches import branches_blueprint
from .config import (
    Config,
    get_database_url,
    get_jwt_secret,
    validate_runtime_value,
)
from .database import load_models
from .extensions import init_extensions, jwt
from .health import health_blueprint
from .products import products_blueprint
from .stocks import stocks_blueprint
from .users import users_blueprint


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure a Backoffice Flask application."""
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url()
    environment_jwt_secret = get_jwt_secret()
    app.config["JWT_SECRET_KEY"] = environment_jwt_secret

    if test_config is not None:
        app.config.from_mapping(test_config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "DATABASE_URL must be set when no test database URI is provided."
        )

    if (
        not app.testing
        and (
            not isinstance(environment_jwt_secret, str)
            or not environment_jwt_secret.strip()
        )
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY must be set outside the test environment."
        )
    if not app.testing:
        validate_runtime_value("DATABASE_URL", get_database_url())
        app.config["JWT_SECRET_KEY"] = validate_runtime_value(
            "JWT_SECRET_KEY", environment_jwt_secret
        )

    init_extensions(app)
    load_models()
    register_jwt_callbacks(jwt)
    register_api_error_handlers(app)

    from .database.admin_password import admin_password_command
    from .database.large_seed import seed_large_command
    from .database.seed import seed_command

    app.cli.add_command(seed_command)
    app.cli.add_command(seed_large_command)
    app.cli.add_command(admin_password_command)

    app.register_blueprint(health_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(users_blueprint)
    app.register_blueprint(branches_blueprint)
    app.register_blueprint(stocks_blueprint)
    app.register_blueprint(products_blueprint)

    return app
