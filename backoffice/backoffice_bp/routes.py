"""HTML views for the Backoffice web interface."""

from __future__ import annotations

import functools
from typing import Any

import httpx
from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import BadRequest

from backoffice.api_errors import error_response
from backoffice.auth.decorators import current_user, protected_token_required
from backoffice.auth.services import (
    authenticate_user,
    issue_token_pair,
    serialize_user,
)
from backoffice.branches.services import (
    get_accessible_branch,
    list_accessible_branches,
    serialize_branch,
)
from backoffice.config import ACCESS_TOKEN_EXPIRES_IN
from backoffice.database.models import ACCESS_TOKEN_TYPE, ADMIN_ROLE, User
from backoffice.extensions import db
from backoffice.products.services import get_product, list_products
from backoffice.products.schemas import validate_list_query
from backoffice.stocks.services import (
    add_stock,
    authorize_stock_user,
    get_stock,
    list_stocks,
    remove_stock,
    serialize_stock_detail,
    serialize_stock_list,
)
from backoffice.stocks.schemas import (
    validate_external_product_id,
    validate_list_filters as validate_stock_filters,
    validate_movement_payload,
)
from backoffice.users.schemas import (
    validate_create_user,
    validate_list_filters as validate_user_filters,
    validate_password_update,
    validate_update_user,
)
from backoffice.users.services import (
    create_user,
    get_user,
    list_users,
    serialize_user as serialize_user_data,
    soft_delete_user,
    update_password,
    update_user,
)

backoffice_bp = Blueprint("backoffice", __name__, url_prefix="")


# ── Helpers ──────────────────────────────────────────────────────


def _api_get(path: str, token: str) -> dict[str, Any] | None:
    """Call an internal API endpoint with a Bearer token."""
    base = request.host_url.rstrip("/")
    try:
        resp = httpx.get(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if resp.is_success:
            return resp.json().get("data")
    except httpx.RequestError:
        pass
    return None


def login_required(view):
    """Require a valid session with an access token."""

    @functools.wraps(view)
    def wrapped(**kwargs):
        if "access_token" not in session or "user" not in session:
            return redirect(url_for("backoffice.login"))
        return view(**kwargs)

    return wrapped


def admin_required(view):
    """Require the session user to be an admin."""

    @functools.wraps(view)
    @login_required
    def wrapped(**kwargs):
        if session.get("user", {}).get("role") != ADMIN_ROLE:
            flash("Accès réservé aux administrateurs.", "error")
            return redirect(url_for("backoffice.index"))
        return view(**kwargs)

    return wrapped


def _get_branches_for_user() -> list[dict[str, Any]]:
    """Fetch branches using the session token."""
    token = session.get("access_token", "")
    data = _api_get("/api/v1/branches", token)
    return data if isinstance(data, list) else []


# ── Auth routes ──────────────────────────────────────────────────


@backoffice_bp.route("/login", methods=["GET", "POST"])
def login():
    """Display the login form or process credentials."""
    if request.method == "GET":
        if "access_token" in session:
            return redirect(url_for("backoffice.index"))
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Nom d'utilisateur et mot de passe requis.", "error")
        return render_template("login.html"), 401

    try:
        user = authenticate_user(username, password)
    except Exception:
        flash("Identifiants invalides.", "error")
        return render_template("login.html"), 401

    tokens = issue_token_pair(user)
    session["access_token"] = tokens["access_token"]
    session["refresh_token"] = tokens["refresh_token"]
    session["user"] = serialize_user(user)

    return redirect(url_for("backoffice.index"))


@backoffice_bp.route("/logout")
def logout():
    """Clear the session and redirect to login."""
    session.clear()
    return redirect(url_for("backoffice.login"))


# ── Dashboard ────────────────────────────────────────────────────


@backoffice_bp.route("/")
@login_required
def index():
    """Render the dashboard."""
    return render_template("index.html")


# ── Products ─────────────────────────────────────────────────────


@backoffice_bp.route("/products")
@login_required
def products_list():
    """Render the product catalog with filters and pagination."""
    token = session.get("access_token", "")
    raw_args = request.args.to_dict(flat=False)

    try:
        query = validate_list_query(raw_args)
    except Exception:
        query = validate_list_query({})

    data = _api_get(
        f"/api/v1/products?{_build_query(query.params)}",
        token,
    )
    products = data if isinstance(data, list) else []

    limit = query.limit
    offset = query.offset
    total = len(products)  # fallback; real total comes from API meta

    pagination = {
        "limit": limit,
        "offset": offset,
        "total": total,
        "page": (offset // limit) + 1 if limit else 1,
        "pages": max(1, (total + limit - 1) // limit) if limit else 1,
        "query_params": lambda page: {
            **{k: v[0] if isinstance(v, list) and len(v) == 1 else v
               for k, v in raw_args.items() if k != "offset"},
            "offset": (page - 1) * limit,
            "limit": limit,
        },
    }

    filters = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v)
               for k, v in raw_args.items()}

    return render_template(
        "products.html",
        products=products,
        filters=filters,
        pagination=pagination,
    )


@backoffice_bp.route("/products/<path:external_product_id>")
@login_required
def products_detail(external_product_id: str):
    """Render the product detail page."""
    token = session.get("access_token", "")
    data = _api_get(f"/api/v1/products/{external_product_id}", token)
    product = data if isinstance(data, dict) else None

    if product is None:
        flash("Produit introuvable.", "error")
        return redirect(url_for("backoffice.products_list"))

    return render_template("product_detail.html", product=product)


# ── Branches ─────────────────────────────────────────────────────


@backoffice_bp.route("/branches")
@login_required
def branches_list():
    """Render the branches list."""
    branches = _get_branches_for_user()
    return render_template("branches.html", branches=branches)


# ── Stocks ───────────────────────────────────────────────────────


@backoffice_bp.route("/stocks")
@login_required
def stocks_list():
    """Render the stock management page."""
    token = session.get("access_token", "")
    user = session.get("user", {})

    raw_args = request.args.to_dict(flat=False)
    try:
        filters = validate_stock_filters(raw_args)
    except Exception:
        filters = validate_stock_filters({})

    data = _api_get(
        f"/api/v1/stocks?available_only={'true' if filters.available_only else 'false'}",
        token,
    )
    stocks_data = data if isinstance(data, dict) else {}
    stocks = stocks_data.get("items", [])
    branch = stocks_data.get("branch")

    return render_template(
        "stocks.html",
        stocks=stocks,
        branch=branch,
        filters={"available_only": filters.available_only},
    )


@backoffice_bp.route("/stocks/add", methods=["POST"])
@login_required
def stocks_add():
    """Add stock via the API."""
    token = session.get("access_token", "")
    external_product_id = request.form.get("external_product_id", "").strip()
    quantity = request.form.get("quantity", "1")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        flash("Quantité invalide.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    data = _api_post(
        f"/api/v1/stocks/{external_product_id}/add",
        token,
        json={"quantity": quantity},
    )
    if data is None:
        flash("Erreur lors de l'ajout de stock.", "error")
    else:
        flash("Stock ajouté avec succès.", "success")

    return redirect(url_for("backoffice.stocks_list"))


@backoffice_bp.route("/stocks/remove", methods=["POST"])
@login_required
def stocks_remove():
    """Remove stock via the API."""
    token = session.get("access_token", "")
    external_product_id = request.form.get("external_product_id", "").strip()
    quantity = request.form.get("quantity", "1")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        flash("Quantité invalide.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    data = _api_post(
        f"/api/v1/stocks/{external_product_id}/remove",
        token,
        json={"quantity": quantity},
    )
    if data is None:
        flash("Erreur lors du retrait de stock.", "error")
    else:
        flash("Stock retiré avec succès.", "success")

    return redirect(url_for("backoffice.stocks_list"))


# ── Users (admin only) ───────────────────────────────────────────


@backoffice_bp.route("/users")
@admin_required
def users_list():
    """Render the user management page."""
    token = session.get("access_token", "")
    raw_args = request.args.to_dict(flat=False)

    try:
        filters = validate_user_filters(raw_args)
    except Exception:
        filters = validate_user_filters({})

    query_params = {}
    if filters.status != "active":
        query_params["status"] = filters.status
    if filters.branch_id is not None:
        query_params["branch_id"] = str(filters.branch_id)

    path = "/api/v1/users"
    if query_params:
        path += "?" + _build_query(query_params)

    data = _api_get(path, token)
    users = data if isinstance(data, list) else []
    branches = _get_branches_for_user()

    return render_template(
        "users.html",
        users=users,
        branches=branches,
        filters={
            "status": filters.status,
            "branch_id": filters.branch_id,
        },
    )


@backoffice_bp.route("/users/create", methods=["POST"])
@admin_required
def users_create():
    """Create a user via the API."""
    token = session.get("access_token", "")
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    branch_id = request.form.get("branch_id", "")

    try:
        branch_id = int(branch_id)
    except (TypeError, ValueError):
        flash("ID de succursale invalide.", "error")
        return redirect(url_for("backoffice.users_list"))

    data = _api_post(
        "/api/v1/users",
        token,
        json={
            "username": username,
            "password": password,
            "branch_id": branch_id,
        },
    )
    if data is None:
        flash("Erreur lors de la création de l'utilisateur.", "error")
    else:
        flash("Utilisateur créé avec succès.", "success")

    return redirect(url_for("backoffice.users_list"))


@backoffice_bp.route("/users/<int:user_id>/edit", methods=["POST"])
@admin_required
def users_edit(user_id: int):
    """Update a user via the API."""
    token = session.get("access_token", "")
    payload = {}
    username = request.form.get("username", "").strip()
    branch_id = request.form.get("branch_id", "")

    if username:
        payload["username"] = username
    if branch_id:
        try:
            payload["branch_id"] = int(branch_id)
        except (TypeError, ValueError):
            flash("ID de succursale invalide.", "error")
            return redirect(url_for("backoffice.users_list"))

    data = _api_post(f"/api/v1/users/{user_id}", token, json=payload, method="PATCH")
    if data is None:
        flash("Erreur lors de la modification.", "error")
    else:
        flash("Utilisateur modifié avec succès.", "success")

    return redirect(url_for("backoffice.users_list"))


@backoffice_bp.route("/users/<int:user_id>/password", methods=["POST"])
@admin_required
def users_password(user_id: int):
    """Change a user's password via the API."""
    token = session.get("access_token", "")
    new_password = request.form.get("new_password", "")

    if not new_password:
        flash("Mot de passe requis.", "error")
        return redirect(url_for("backoffice.users_list"))

    success = _api_post(
        f"/api/v1/users/{user_id}/password",
        token,
        json={"new_password": new_password},
        method="PATCH",
    )
    if success is None:
        flash("Erreur lors du changement de mot de passe.", "error")
    else:
        flash("Mot de passe changé avec succès.", "success")

    return redirect(url_for("backoffice.users_list"))


@backoffice_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def users_delete(user_id: int):
    """Soft-delete a user via the API."""
    token = session.get("access_token", "")
    success = _api_post(f"/api/v1/users/{user_id}", token, method="DELETE")
    if success is None:
        flash("Erreur lors de la suppression.", "error")
    else:
        flash("Utilisateur supprimé avec succès.", "success")

    return redirect(url_for("backoffice.users_list"))


# ── Internal helpers ─────────────────────────────────────────────


def _build_query(params: dict[str, str]) -> str:
    """Build a query string from a dict."""
    return "&".join(f"{k}={v}" for k, v in params.items() if v is not None)


def _api_post(
    path: str,
    token: str,
    json: dict[str, Any] | None = None,
    method: str = "POST",
) -> dict[str, Any] | None:
    """Call an internal API endpoint with a Bearer token (POST/PATCH/DELETE)."""
    base = request.host_url.rstrip("/")
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.request(
                method,
                f"{base}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=json,
            )
            if resp.is_success:
                return resp.json().get("data") if resp.content else {}
            flash(f"Erreur API: {resp.status_code}", "error")
    except httpx.RequestError as e:
        flash(f"Erreur de connexion: {e}", "error")
    return None