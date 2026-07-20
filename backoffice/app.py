"""Flask application factory for the Backoffice service."""

from flask import Flask

from .auth import auth_blueprint
from .branches import branches_blueprint
from .config import Config
from .extensions import init_extensions
from .health import health_blueprint
from .products import products_blueprint
from .stocks import stocks_blueprint
from .users import users_blueprint


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure a Backoffice Flask application."""
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)

    if test_config is not None:
        app.config.from_mapping(test_config)

    init_extensions(app)

    app.register_blueprint(health_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(users_blueprint)
    app.register_blueprint(branches_blueprint)
    app.register_blueprint(stocks_blueprint)
    app.register_blueprint(products_blueprint)

    return app
