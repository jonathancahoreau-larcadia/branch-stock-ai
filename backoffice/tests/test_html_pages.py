"""Tests for Backoffice HTML page routes and static files."""

import re


class TestHtmlPages:
    """Every HTML page route returns 200 and renders a template."""

    def test_login_page(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Connexion" in response.data

    def test_login_page_always_shows_form(self, client):
        """The login page always shows the form (auth is client-side)."""
        response = client.get("/login")
        assert response.status_code == 200
        assert b"login-form" in response.data or b"Se connecter" in response.data

    def test_index_page(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"Dashboard" in response.data

    def test_products_page(self, client):
        response = client.get("/products")
        assert response.status_code == 200
        assert b"Produits" in response.data

    def test_product_detail_page(self, client):
        response = client.get("/products/HB-MON-2102")
        assert response.status_code == 200
        assert b"Produit" in response.data

    def test_stocks_page(self, client):
        response = client.get("/stocks")
        assert response.status_code == 200
        assert b"Stocks" in response.data

    def test_branches_page(self, client):
        response = client.get("/branches")
        assert response.status_code == 200
        assert b"Succursales" in response.data

    def test_users_page(self, client):
        response = client.get("/users")
        assert response.status_code == 200
        assert b"Utilisateurs" in response.data

    def test_logout_page(self, client):
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.location


class TestStaticFiles:
    """CSS and JavaScript files are accessible."""

    def test_css_accessible(self, client):
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert b"text/css" in response.data or "css" in response.content_type

    def test_js_config_accessible(self, client):
        response = client.get("/static/js/config.js")
        assert response.status_code == 200
        assert b"CONFIG" in response.data

    def test_js_api_accessible(self, client):
        response = client.get("/static/js/api.js")
        assert response.status_code == 200
        assert b"apiFetch" in response.data

    def test_js_auth_accessible(self, client):
        response = client.get("/static/js/auth.js")
        assert response.status_code == 200
        assert b"login" in response.data

    def test_js_app_accessible(self, client):
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        assert b"initNavigation" in response.data

    def test_js_products_accessible(self, client):
        response = client.get("/static/js/products.js")
        assert response.status_code == 200
        assert b"initProductsPage" in response.data

    def test_js_stocks_accessible(self, client):
        response = client.get("/static/js/stocks.js")
        assert response.status_code == 200
        assert b"initStocksPage" in response.data

    def test_js_branches_accessible(self, client):
        response = client.get("/static/js/branches.js")
        assert response.status_code == 200
        assert b"initBranchesPage" in response.data

    def test_js_users_accessible(self, client):
        response = client.get("/static/js/users.js")
        assert response.status_code == 200
        assert b"initUsersPage" in response.data

    def test_js_navigation_accessible(self, client):
        response = client.get("/static/js/navigation.js")
        assert response.status_code == 200
        assert b"initNavigation" in response.data

    def test_js_modals_accessible(self, client):
        response = client.get("/static/js/modals.js")
        assert response.status_code == 200
        assert b"openModal" in response.data

    def test_js_utils_accessible(self, client):
        response = client.get("/static/js/utils.js")
        assert response.status_code == 200
        assert b"escapeHtml" in response.data

    def test_js_dashboard_accessible(self, client):
        response = client.get("/static/js/dashboard.js")
        assert response.status_code == 200
        assert b"initDashboard" in response.data


class TestApiRoutesStillWork:
    """Existing API routes remain functional."""

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_login_api_rejects_missing_json(self, client):
        response = client.post("/api/v1/auth/login")
        assert response.status_code == 400

    def test_login_api_rejects_invalid_credentials(self, client, sqlite_database_app):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "wrong"},
        )
        assert response.status_code == 401

    def test_products_api_requires_auth(self, client):
        response = client.get("/api/v1/products")
        assert response.status_code == 401

    def test_stocks_api_requires_auth(self, client):
        response = client.get("/api/v1/stocks")
        assert response.status_code == 401

    def test_branches_api_requires_auth(self, client):
        response = client.get("/api/v1/branches")
        assert response.status_code == 401

    def test_users_api_requires_auth(self, client):
        response = client.get("/api/v1/users")
        assert response.status_code == 401
