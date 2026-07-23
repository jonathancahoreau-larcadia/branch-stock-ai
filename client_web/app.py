"""Flask application for the Client Web.

Provides a Jinja2-based UI that consumes the Backoffice REST API
via ``BackofficeClient``.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .config import Config
from .services.backoffice_client import BackofficeClient, BackofficeResponse

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Client Web Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config is not None:
        app.config.from_mapping(test_config)

    app.secret_key = app.config["SECRET_KEY"]

    _register_routes(app)
    _register_context_processors(app)

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

client = BackofficeClient()


def _get_session_user() -> dict[str, Any] | None:
    """Return the user dict stored in the session, or ``None``."""
    return session.get(Config.USER_KEY)


def _get_access_token() -> str | None:
    return session.get(Config.ACCESS_TOKEN_KEY)


def _get_refresh_token() -> str | None:
    return session.get(Config.REFRESH_TOKEN_KEY)


def _clear_session() -> None:
    session.pop(Config.ACCESS_TOKEN_KEY, None)
    session.pop(Config.REFRESH_TOKEN_KEY, None)
    session.pop(Config.USER_KEY, None)


def login_required(fn: Callable) -> Callable:
    """Decorator — redirect to login when no access token is present."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _get_access_token() is None:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn: Callable) -> Callable:
    """Decorator — redirect to dashboard when the user is not admin."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        user = _get_session_user()
        if user is None or user.get("role") != "admin":
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def _register_routes(app: Flask) -> None:
    """Attach all route functions to the Flask app."""

    @app.route("/")
    def index() -> Any:
        """Landing page — redirect to dashboard if logged in, else login."""
        if _get_access_token():
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    # ── Authentication ─────────────────────────────────────────

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        """Handle login form and POST to Backoffice /auth/login."""
        if _get_access_token():
            return redirect(url_for("dashboard"))

        error: str | None = None

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                error = "Veuillez saisir un nom d'utilisateur et un mot de passe."
            else:
                resp = client.login(username, password)
                if resp.ok and resp.data:
                    session[Config.ACCESS_TOKEN_KEY] = resp.data["access_token"]
                    session[Config.REFRESH_TOKEN_KEY] = resp.data["refresh_token"]
                    session[Config.USER_KEY] = resp.data["user"]
                    return redirect(url_for("dashboard"))
                error = "Identifiants invalides."

        return render_template("login.html", error=error)

    @app.route("/logout")
    @login_required
    def logout() -> Any:
        """Revoke tokens on Backoffice and clear session."""
        access_token = _get_access_token()
        refresh_token = _get_refresh_token()
        if access_token:
            client.logout_access(access_token)
        if refresh_token:
            client.logout_refresh(refresh_token)
        _clear_session()
        return redirect(url_for("login"))

    # ── Dashboard ──────────────────────────────────────────────

    @app.route("/dashboard")
    @login_required
    def dashboard() -> Any:
        """Main dashboard — shows current user info."""
        user = _get_session_user()
        return render_template("dashboard.html", user=user)

    # ── Stock ──────────────────────────────────────────────────

    @app.route("/stock")
    @login_required
    def stock() -> Any:
        """View stock for the current user's branch."""
        access_token = _get_access_token()
        user = _get_session_user()
        assert access_token is not None
        assert user is not None

        available_only = request.args.get("available_only", "true").lower() == "true"
        resp = client.list_stocks(access_token, available_only=available_only)

        error: str | None = None
        stocks: list[dict[str, Any]] = []
        branch: dict[str, Any] | None = None

        if resp.ok and resp.data:
            branch = resp.data.get("branch")
            stocks = resp.data.get("items", [])
        else:
            error = "Impossible de charger les stocks."

        return render_template(
            "stock.html",
            user=user,
            stocks=stocks,
            branch=branch,
            available_only=available_only,
            error=error,
        )

    @app.route("/stock/add", methods=["POST"])
    @login_required
    def stock_add() -> Any:
        """Add stock for a product."""
        access_token = _get_access_token()
        assert access_token is not None

        product_id = request.form.get("product_id", "").strip()
        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            quantity = 0

        if product_id and quantity > 0:
            client.add_stock(access_token, product_id, quantity)

        return redirect(url_for("stock"))

    @app.route("/stock/remove", methods=["POST"])
    @login_required
    def stock_remove() -> Any:
        """Remove stock for a product."""
        access_token = _get_access_token()
        assert access_token is not None

        product_id = request.form.get("product_id", "").strip()
        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            quantity = 0

        if product_id and quantity > 0:
            client.remove_stock(access_token, product_id, quantity)

        return redirect(url_for("stock"))

    # ── Users (admin only) ─────────────────────────────────────

    @app.route("/users")
    @login_required
    @admin_required
    def users() -> Any:
        """List users (admin)."""
        access_token = _get_access_token()
        user = _get_session_user()
        assert access_token is not None
        assert user is not None

        status = request.args.get("status", "active")
        resp = client.list_users(access_token, status=status)
        branches_resp = client.list_branches(access_token)

        error: str | None = None
        users_list: list[dict[str, Any]] = []
        branches_list: list[dict[str, Any]] = []

        if resp.ok and resp.data:
            users_list = resp.data if isinstance(resp.data, list) else []
        else:
            error = "Impossible de charger les utilisateurs."

        if branches_resp.ok and branches_resp.data:
            branches_list = branches_resp.data if isinstance(branches_resp.data, list) else []

        return render_template(
            "users.html",
            user=user,
            users=users_list,
            branches=branches_list,
            current_status=status,
            error=error,
        )

    @app.route("/users/create", methods=["POST"])
    @login_required
    @admin_required
    def users_create() -> Any:
        """Create a new common user."""
        access_token = _get_access_token()
        assert access_token is not None

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            branch_id = int(request.form.get("branch_id", "0"))
        except ValueError:
            branch_id = 0

        if username and password and branch_id > 0:
            client.create_user(access_token, username, password, branch_id)

        return redirect(url_for("users"))

    @app.route("/users/<int:user_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def users_delete(user_id: int) -> Any:
        """Soft-delete a user."""
        access_token = _get_access_token()
        assert access_token is not None

        client.delete_user(access_token, user_id)
        return redirect(url_for("users"))

    @app.route("/users/<int:user_id>/password", methods=["POST"])
    @login_required
    @admin_required
    def users_change_password(user_id: int) -> Any:
        """Change a user's password."""
        access_token = _get_access_token()
        assert access_token is not None

        new_password = request.form.get("new_password", "")
        if new_password:
            client.change_user_password(access_token, user_id, new_password)

        return redirect(url_for("users"))


# ---------------------------------------------------------------------------
# Context processors
# ---------------------------------------------------------------------------


def _register_context_processors(app: Flask) -> None:
    """Make common variables available in all templates."""

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {
            "current_user": _get_session_user(),
        }