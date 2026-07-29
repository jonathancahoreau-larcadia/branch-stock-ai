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
from backoffice.database.models import Stock as StockModel
from backoffice.stocks import repositories as stock_repositories
from backoffice.stocks.schemas import (
    validate_external_product_id,
    validate_list_filters as validate_stock_filters,
    validate_movement_payload,
)
from backoffice.stocks.services import (
    add_stock as stock_service_add,
    authorize_stock_user,
    get_stock as stock_service_get,
    list_stocks as stock_service_list,
    remove_stock as stock_service_remove,
    serialize_stock_detail,
    serialize_stock_list,
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


# ── Catalogue produits local (fallback quand l'API externe est indisponible) ──

_PRODUCT_CATALOG: list[dict[str, Any]] = [
    {
        "external_product_id": "HB-MON-2102",
        "name": "Écran 24 pouces",
        "description": "Écran Full HD 24 pouces avec dalle IPS, idéal pour le travail bureautique.",
        "category": "Périphériques",
        "brand": "TechView",
        "supplier": {"id": "SUP-001", "name": "Fournitures Pro", "country": "France", "lead_time_days": 5, "reliability_score": 0.92},
        "unit_price": 249.99,
        "currency": "EUR",
        "discontinued": False,
        "weight_kg": 3.5,
        "tags": ("écran", "full-hd", "ips", "bureautique"),
        "updated_at": "2026-06-15T10:30:00Z",
    },
    {
        "external_product_id": "HB-KEY-1103",
        "name": "Clavier mécanique",
        "description": "Clavier mécanique rétroéclairé avec switches Cherry MX Blue.",
        "category": "Périphériques",
        "brand": "KeyMaster",
        "supplier": {"id": "SUP-002", "name": "Tech Import", "country": "Allemagne", "lead_time_days": 3, "reliability_score": 0.88},
        "unit_price": 89.99,
        "currency": "EUR",
        "discontinued": False,
        "weight_kg": 1.2,
        "tags": ("clavier", "mécanique", "cherry-mx", "rétroéclairé"),
        "updated_at": "2026-07-01T14:00:00Z",
    },
    {
        "external_product_id": "HB-CAM-3301",
        "name": "Caméra de surveillance",
        "description": "Caméra IP extérieure 4MP avec vision nocturne et détection de mouvement.",
        "category": "Sécurité",
        "brand": "SafeGuard",
        "supplier": {"id": "SUP-003", "name": "Sécurité Plus", "country": "France", "lead_time_days": 7, "reliability_score": 0.95},
        "unit_price": 159.50,
        "currency": "EUR",
        "discontinued": False,
        "weight_kg": 0.8,
        "tags": ("caméra", "surveillance", "ip", "nocturne"),
        "updated_at": "2026-05-20T08:15:00Z",
    },
    {
        "external_product_id": "HB-PRI-4402",
        "name": "Imprimante laser",
        "description": "Imprimante laser monochrome A4, 30 pages/minute, recto-verso automatique.",
        "category": "Périphériques",
        "brand": "PrintEco",
        "supplier": {"id": "SUP-001", "name": "Fournitures Pro", "country": "France", "lead_time_days": 4, "reliability_score": 0.90},
        "unit_price": 329.00,
        "currency": "EUR",
        "discontinued": False,
        "weight_kg": 8.2,
        "tags": ("imprimante", "laser", "a4", "recto-verso"),
        "updated_at": "2026-06-28T16:45:00Z",
    },
    {
        "external_product_id": "HB-SPK-5501",
        "name": "Enceinte Bluetooth",
        "description": "Enceinte Bluetooth portable 20W, étanche IPX7, autonomie 12h.",
        "category": "Audio",
        "brand": "SoundWave",
        "supplier": {"id": "SUP-002", "name": "Tech Import", "country": "Allemagne", "lead_time_days": 2, "reliability_score": 0.85},
        "unit_price": 59.99,
        "currency": "EUR",
        "discontinued": True,
        "weight_kg": 0.5,
        "tags": ("enceinte", "bluetooth", "portable", "étanche"),
        "updated_at": "2026-04-10T11:30:00Z",
    },
]


def _get_local_product(sku: str) -> dict[str, Any] | None:
    """Find a product by SKU in the local catalog."""
    for p in _PRODUCT_CATALOG:
        if p["external_product_id"] == sku:
            return dict(p)  # copy
    return None


def _search_local_products(
    q: str = "",
    category: str = "",
    include_discontinued: bool = False,
    sort: str = "",
) -> list[dict[str, Any]]:
    """Filter and sort the local product catalog."""
    results = list(_PRODUCT_CATALOG)

    # Filtre discontinué
    if not include_discontinued:
        results = [p for p in results if not p["discontinued"]]

    # Filtre catégorie
    if category:
        cat_lower = category.strip().lower()
        results = [
            p
            for p in results
            if cat_lower in p["category"].lower()
        ]

    # Recherche texte
    if q:
        q_lower = q.strip().lower()
        results = [
            p for p in results
            if q_lower in p["name"].lower()
            or q_lower in p["external_product_id"].lower()
            or q_lower in p["brand"].lower()
            or q_lower in p["category"].lower()
        ]

    # Tri
    if sort == "name":
        results.sort(key=lambda p: p["name"].lower())
    elif sort == "-name":
        results.sort(key=lambda p: p["name"].lower(), reverse=True)
    elif sort == "sku":
        results.sort(key=lambda p: p["external_product_id"])
    elif sort == "-sku":
        results.sort(key=lambda p: p["external_product_id"], reverse=True)
    elif sort == "unit_price":
        results.sort(key=lambda p: p["unit_price"])
    elif sort == "-unit_price":
        results.sort(key=lambda p: p["unit_price"], reverse=True)
    elif sort == "updated_at":
        results.sort(key=lambda p: p["updated_at"])
    elif sort == "-updated_at":
        results.sort(key=lambda p: p["updated_at"], reverse=True)

    return results


# ── Products ─────────────────────────────────────────────────────


@backoffice_bp.route("/products")
@login_required
def products_list():
    """Render the product catalog with local data."""
    raw_args = request.args.to_dict(flat=False)

    # Extraire les filtres
    q = (raw_args.get("q", [""])[0])
    category = (raw_args.get("category", [""])[0])
    include_discontinued = raw_args.get("include_discontinued", [""])[0] == "true"
    sort = (raw_args.get("sort", [""])[0])

    # Essayer l'API externe d'abord
    token = session.get("access_token", "")
    api_data = _api_get(
        f"/api/v1/products?{_build_query({'include_discontinued': 'true' if include_discontinued else 'false', 'limit': '100', 'offset': '0'})}",
        token,
    )
    if api_data and isinstance(api_data, list):
        products = api_data
    else:
        # Fallback local
        products = _search_local_products(
            q=q,
            category=category,
            include_discontinued=include_discontinued,
            sort=sort,
        )

    limit = 20
    offset = 0
    try:
        limit = min(int(raw_args.get("limit", ["20"])[0]), 100)
        offset = int(raw_args.get("offset", ["0"])[0])
    except (TypeError, ValueError):
        pass

    total = len(products)
    page_products = products[offset:offset + limit]

    pagination = {
        "limit": limit,
        "offset": offset,
        "total": total,
        "page": (offset // limit) + 1 if limit else 1,
        "pages": max(1, (total + limit - 1) // limit) if limit else 1,
        "query_params": lambda p: {
            k: v[0] if isinstance(v, list) and len(v) == 1 else v
            for k, v in {**raw_args, "offset": [(p - 1) * limit], "limit": [limit]}.items()
        },
    }

    filters = {
        "q": q,
        "category": category,
        "include_discontinued": "true" if include_discontinued else "",
        "sort": sort,
    }

    return render_template(
        "products.html",
        products=page_products,
        filters=filters,
        pagination=pagination,
    )


@backoffice_bp.route("/products/<path:external_product_id>")
@login_required
def products_detail(external_product_id: str):
    """Render the product detail page."""
    # Essayer l'API externe d'abord
    token = session.get("access_token", "")
    data = _api_get(f"/api/v1/products/{external_product_id}", token)
    product = data if isinstance(data, dict) else None

    # Fallback local
    if product is None:
        product = _get_local_product(external_product_id)

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


# ── Noms de produits locaux (fallback quand l'API externe est indisponible) ──

_PRODUCT_NAMES: dict[str, str] = {
    "HB-MON-2102": "Écran 24 pouces",
    "HB-KEY-1103": "Clavier mécanique",
    "HB-CAM-3301": "Caméra de surveillance",
    "HB-PRI-4402": "Imprimante laser",
    "HB-SPK-5501": "Enceinte Bluetooth",
}


def _get_product_name(external_product_id: str) -> str:
    """Récupère le nom d'un produit (API externe d'abord, fallback local)."""
    # Fallback local
    if external_product_id in _PRODUCT_NAMES:
        return _PRODUCT_NAMES[external_product_id]
    # Essayer l'API externe
    try:
        product = get_product(external_product_id)
        return product.get("name", external_product_id)
    except Exception:
        return external_product_id


# ── Stocks ───────────────────────────────────────────────────────


def _get_user_branch(user_session: dict[str, Any]) -> tuple[Any, int | None]:
    """Return the branch id for a common user."""
    role = user_session.get("role", "")
    if role == ADMIN_ROLE:
        return None, None
    return None, user_session.get("branch", {}).get("id")


def _search_stocks_by_name(branch_id: int, search_term: str) -> list[str]:
    """Search stock products by name (local names + API)."""
    search_lower = search_term.strip().lower()
    results = []

    # 1. Chercher par correspondance directe d'ID
    stock_rows = stock_repositories.list_stocks(branch_id, available_only=False)
    for s in stock_rows:
        if search_lower in s.external_product_id.lower():
            results.append(s.external_product_id)

    # 2. Chercher par nom local
    for sku, name in _PRODUCT_NAMES.items():
        if search_lower in name.lower() and sku not in results:
            # Vérifier que ce SKU existe dans les stocks de cette branche
            for s in stock_rows:
                if s.external_product_id == sku:
                    results.append(sku)
                    break

    # 3. Chercher par nom via l'API produits externe
    try:
        from backoffice.products.schemas import validate_list_query
        query = validate_list_query({"q": [search_term]})
        page = list_products(query)
        for prod in page.data:
            sku = prod.get("external_product_id")
            if sku and sku not in results:
                results.append(sku)
    except Exception:
        pass  # API non disponible

    return results


@backoffice_bp.route("/stocks")
@login_required
def stocks_list():
    """Render the stock management page with direct DB access."""
    user_session = session.get("user", {})

    # Vérifier que l'utilisateur est un common_user avec une branche
    branch_id = user_session.get("branch", {}).get("id")
    role = user_session.get("role", "")
    if role != "common_user" or branch_id is None:
        flash("Seuls les utilisateurs de succursale peuvent gérer les stocks.", "error")
        return redirect(url_for("backoffice.index"))

    raw_args = request.args.to_dict(flat=False)
    try:
        filters = validate_stock_filters(raw_args)
    except Exception:
        filters = validate_stock_filters({})

    available_only = filters.available_only
    search_query = request.args.get("search", "").strip()

    # Récupérer la succursale
    from backoffice.branches import repositories as branch_repositories
    branch = branch_repositories.get_branch(branch_id)
    branch_data = {"id": branch.id, "name": branch.name} if branch else None

    # Si recherche par nom, trouver les SKU correspondants
    search_skus = None
    if search_query:
        search_skus = _search_stocks_by_name(branch_id, search_query)

    # Charger les stocks
    all_stocks = stock_repositories.list_stocks(branch_id, available_only=False)

    items = []
    for stock in all_stocks:
        # Appliquer le filtre available_only
        if available_only and stock.quantity <= 0:
            continue
        # Appliquer la recherche
        if search_skus is not None and stock.external_product_id not in search_skus:
            continue

        product_name = _get_product_name(stock.external_product_id)
        items.append({
            "external_product_id": stock.external_product_id,
            "quantity": stock.quantity,
            "product": {"name": product_name},
        })

    return render_template(
        "stocks.html",
        stocks=items,
        branch=branch_data,
        filters={"available_only": available_only},
        search_query=search_query,
    )


@backoffice_bp.route("/stocks/add", methods=["POST"])
@login_required
def stocks_add():
    """Add stock via direct DB access."""
    user_session = session.get("user", {})
    branch_id = user_session.get("branch", {}).get("id")
    role = user_session.get("role", "")
    if role != "common_user" or branch_id is None:
        flash("Action non autorisée.", "error")
        return redirect(url_for("backoffice.index"))

    external_product_id = request.form.get("external_product_id", "").strip()
    quantity = request.form.get("quantity", "1")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        flash("Quantité invalide.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    if not external_product_id:
        flash("ID produit requis.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    if quantity <= 0:
        flash("La quantité doit être positive.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    try:
        # Valider l'ID produit (format)
        validate_external_product_id(external_product_id)
    except Exception as exc:
        flash(f"ID produit invalide.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    try:
        stock = stock_repositories.add_stock(branch_id, external_product_id, quantity)
        db.session.commit()
        flash("Stock ajouté avec succès.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erreur lors de l'ajout: {exc}", "error")

    return redirect(url_for("backoffice.stocks_list"))


@backoffice_bp.route("/stocks/remove", methods=["POST"])
@login_required
def stocks_remove():
    """Remove stock via direct DB access."""
    user_session = session.get("user", {})
    branch_id = user_session.get("branch", {}).get("id")
    role = user_session.get("role", "")
    if role != "common_user" or branch_id is None:
        flash("Action non autorisée.", "error")
        return redirect(url_for("backoffice.index"))

    external_product_id = request.form.get("external_product_id", "").strip()
    quantity = request.form.get("quantity", "1")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        flash("Quantité invalide.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    if not external_product_id:
        flash("ID produit requis.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    if quantity <= 0:
        flash("La quantité doit être positive.", "error")
        return redirect(url_for("backoffice.stocks_list"))

    try:
        stock = stock_repositories.get_stock(branch_id, external_product_id, for_update=True)
        if stock is None:
            db.session.rollback()
            flash("Stock introuvable pour ce produit.", "error")
            return redirect(url_for("backoffice.stocks_list"))

        if stock.quantity < quantity:
            db.session.rollback()
            flash(f"Stock insuffisant. Disponible: {stock.quantity}, demandé: {quantity}.", "error")
            return redirect(url_for("backoffice.stocks_list"))

        stock.quantity -= quantity
        db.session.commit()
        flash("Stock retiré avec succès.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erreur lors du retrait: {exc}", "error")

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