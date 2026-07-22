"""Flask application factory for the Backoffice service."""

from flask import Flask

from .auth import auth_blueprint
from .branches import branches_blueprint
from .config import Config, get_database_url
from .extensions import init_extensions
from .health import health_blueprint
from .products import products_blueprint
from .stocks import stocks_blueprint
from .users import users_blueprint


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure a Backoffice Flask application."""
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url()

    if test_config is not None:
        app.config.from_mapping(test_config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "DATABASE_URL must be set when no test database URI is provided."
        )

    init_extensions(app)

    app.register_blueprint(health_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(users_blueprint)
    app.register_blueprint(branches_blueprint)
    app.register_blueprint(stocks_blueprint)
    app.register_blueprint(products_blueprint)

    return app
