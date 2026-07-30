"""HTML views for the Backoffice web interface — page rendering only.

Each route simply renders a template.  Data is fetched client-side
via the REST API (JWT in sessionStorage, Authorization: Bearer).
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, session, url_for

backoffice_bp = Blueprint("backoffice", __name__, url_prefix="")


@backoffice_bp.get("/login")
def login_page():
    """Display the login form."""
    return render_template("login.html")


@backoffice_bp.get("/logout")
def logout_page():
    """Clear the Flask session and redirect to login."""
    session.clear()
    return redirect(url_for("backoffice.login_page"))


@backoffice_bp.get("/")
def index():
    """Render the dashboard."""
    return render_template("index.html")


@backoffice_bp.get("/products")
def products_page():
    """Render the product catalogue page."""
    return render_template("products.html")


@backoffice_bp.get("/products/<path:external_product_id>")
def product_detail_page(external_product_id: str):
    """Render the product detail page."""
    return render_template("product_detail.html")


@backoffice_bp.get("/stocks")
def stocks_page():
    """Render the stock management page."""
    return render_template("stocks.html")


@backoffice_bp.get("/branches")
def branches_page():
    """Render the branches list page."""
    return render_template("branches.html")


@backoffice_bp.get("/users")
def users_page():
    """Render the user management page (admin only — enforced client-side)."""
    return render_template("users.html")