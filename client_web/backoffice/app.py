import os
import secrets
from contextlib import contextmanager
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, 
    url_for, session, flash, abort
)
from dotenv import load_dotenv

# Import de la BDD et des services
from db.database import Session, _engine
from backoffice.auth.service import authenticate_user, create_user, get_all_users, update_user_role
from backoffice.stock.service import add_stock, remove_stock, get_stock_by_branch
from backoffice.api_client.service import get_products_sync, get_product_details_sync

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

# -----------------------------------------------------------------------------
# Gestionnaire de session BDD
# -----------------------------------------------------------------------------
@contextmanager
def db_session():
    """Fournit un contexte transactionnel sécurisé autour d'une série d'opérations."""
    db = Session(_engine)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Protection CSRF légère & Injection Globale
# -----------------------------------------------------------------------------
@app.before_request
def csrf_protect():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
        
    if request.method == "POST":
        token = session.get("csrf_token")
        form_token = request.form.get("csrf_token")
        if not token or token != form_token:
            abort(403, description="Jeton CSRF invalide ou manquant.")

@app.context_processor
def inject_globals():
    return {"csrf_token": session.get("csrf_token", "")}

# -----------------------------------------------------------------------------
# Décorateurs d'authentification
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Veuillez vous connecter pour accéder à cette page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Veuillez vous connecter pour accéder à cette page.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Accès réservé aux administrateurs.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

# -----------------------------------------------------------------------------
# Routes : Authentification
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with db_session() as db:
            user = authenticate_user(db, username, password)
            if user:
                session["user_id"] = user.id
                session["username"] = user.username
                session["role"] = user.role
                session["branch_id"] = user.branch_id
                flash(f"Bienvenue, {user.username} !", "success")
                return redirect(url_for("dashboard"))
            
        flash("Identifiants invalides.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("login"))

# -----------------------------------------------------------------------------
# Routes : Backoffice General
# -----------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/stock", methods=["GET"])
@login_required
def stock_page():
    branch_id = session.get("branch_id")
    
    with db_session() as db:
        stock_items = get_stock_by_branch(db, branch_id)
        
    # Optimisation N+1: Récupération de tous les produits en un seul appel
    all_products = get_products_sync()
    products_map = {p["id"]: p for p in all_products} if isinstance(all_products, list) else {}

    enriched_stock = []
    for item in stock_items:
        prod_info = products_map.get(item.product_id)
        enriched_stock.append({
            "product_id": item.product_id,
            "quantity": item.quantity,
            "title": prod_info.get("title", f"Produit #{item.product_id}") if prod_info else f"Produit #{item.product_id}",
            "price": prod_info.get("price") if prod_info else None
        })

    return render_template("stock.html", stock=enriched_stock, products=all_products)

@app.route("/stock/add", methods=["POST"])
@login_required
def stock_add():
    product_id = request.form.get("product_id", type=int)
    quantity = request.form.get("quantity", type=int)
    branch_id = session.get("branch_id")

    if not product_id or not quantity or quantity <= 0:
        flash("Saisie invalide pour l'ajout de stock.", "warning")
        return redirect(url_for("stock_page"))

    with db_session() as db:
        add_stock(db, branch_id, product_id, quantity)
    
    flash("Stock ajouté avec succès.", "success")
    return redirect(url_for("stock_page"))

@app.route("/stock/remove", methods=["POST"])
@login_required
def stock_remove():
    product_id = request.form.get("product_id", type=int)
    quantity = request.form.get("quantity", type=int)
    branch_id = session.get("branch_id")

    if not product_id or not quantity or quantity <= 0:
        flash("Saisie invalide pour le retrait de stock.", "warning")
        return redirect(url_for("stock_page"))

    with db_session() as db:
        success = remove_stock(db, branch_id, product_id, quantity)
        if success:
            flash("Stock retiré avec succès.", "success")
        else:
            flash("Quantité insuffisante ou produit non trouvé.", "danger")

    return redirect(url_for("stock_page"))

# -----------------------------------------------------------------------------
# Routes : Administration des Utilisateurs
# -----------------------------------------------------------------------------
@app.route("/users")
@admin_required
def users_list():
    with db_session() as db:
        users = get_all_users(db)
        # On extrait les données nécessaires pour éviter les problèmes de detached instance Jinja
        users_data = [{
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "branch_id": u.branch_id
        } for u in users]
        
    return render_template("users.html", users=users_data)

@app.route("/users/create", methods=["POST"])
@admin_required
def users_create():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "employee")
    branch_id = request.form.get("branch_id", type=int)

    if not username or not password or not branch_id:
        flash("Tous les champs sont requis.", "warning")
        return redirect(url_for("users_list"))

    with db_session() as db:
        try:
            create_user(db, username, password, role, branch_id)
            flash(f"Utilisateur {username} créé avec succès.", "success")
        except Exception as e:
            flash("Erreur lors de la création de l'utilisateur (nom déjà pris ?).", "danger")

    return redirect(url_for("users_list"))

@app.route("/users/role", methods=["POST"])
@admin_required
def users_update_role():
    user_id = request.form.get("user_id", type=int)
    new_role = request.form.get("role")

    if not user_id or new_role not in ["admin", "employee"]:
        flash("Modification de rôle invalide.", "warning")
        return redirect(url_for("users_list"))

    with db_session() as db:
        update_user_role(db, user_id, new_role)
        flash("Rôle mis à jour avec succès.", "success")

    return redirect(url_for("users_list"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
