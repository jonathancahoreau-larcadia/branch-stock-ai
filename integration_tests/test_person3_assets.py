"""Contrôles d'intégration réels des actifs de Personne 3."""

from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).parent.parent

EXPECTED_FILES = (
    "backoffice/static/index.html",
    "backoffice/static/styles.css",
    "backoffice/static/app.js",
    "backoffice/static/nginx.conf",
    "backoffice/static/Dockerfile",
    "client_web/index.html",
    "client_web/styles.css",
    "client_web/app.js",
    "client_web/Dockerfile",
    "Dockerfile",
    "docker-compose.yml",
)


def read_asset(relative_path: str) -> str:
    return (
        REPOSITORY_ROOT
        / relative_path
    ).read_text(encoding="utf-8")


def test_person3_assets_exist_and_are_non_empty():
    invalid_assets = []

    for relative_path in EXPECTED_FILES:
        asset_path = REPOSITORY_ROOT / relative_path

        if (
            not asset_path.is_file()
            or not asset_path.read_text(encoding="utf-8").strip()
        ):
            invalid_assets.append(relative_path)

    assert not invalid_assets, (
        "Missing or empty Personne 3 assets: "
        + ", ".join(invalid_assets)
    )


def test_backoffice_loads_real_static_assets():
    html = read_asset("backoffice/static/index.html")

    assert re.search(
        r'<link[^>]+href=["\'](?:\./)?styles\.css["\']',
        html,
        re.IGNORECASE,
    )
    assert re.search(
        r'<script[^>]+src=["\'](?:\./)?app\.js["\']',
        html,
        re.IGNORECASE,
    )


def test_backoffice_javascript_calls_real_auth_api():
    javascript = read_asset("backoffice/static/app.js")

    assert "addEventListener" in javascript
    assert "fetch(" in javascript
    assert "/api/v1/auth/login" in javascript
    assert "/api/v1/auth/me" in javascript

    forbidden = (
        "firebase/app",
        "firebase/auth",
        "from 'vue'",
        'from "vue"',
        "App.vue",
        "from './router'",
        'from "./router"',
    )

    assert not any(marker in javascript for marker in forbidden)


def test_backoffice_nginx_proxies_api_to_flask():
    nginx = read_asset("backoffice/static/nginx.conf")

    assert "location /api/" in nginx
    assert "proxy_pass http://backoffice-api:5000" in nginx

    dockerfile = read_asset("backoffice/static/Dockerfile")

    assert "nginx.conf" in dockerfile
    assert "/etc/nginx/conf.d/default.conf" in dockerfile


def test_client_web_uses_executable_native_javascript():
    javascript = read_asset("client_web/app.js")

    assert "addEventListener" in javascript
    assert "createElement" in javascript
    assert "from 'vue'" not in javascript
    assert 'from "vue"' not in javascript
    assert "App.vue" not in javascript
    assert "from './router'" not in javascript


def test_no_embedded_jwt_or_firebase_key():
    patterns = (
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\b"
        ),
        re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    )

    for relative_path in (
        "backoffice/static/index.html",
        "backoffice/static/app.js",
        "client_web/index.html",
        "client_web/app.js",
        "docker-compose.yml",
    ):
        content = read_asset(relative_path)

        assert not any(
            pattern.search(content)
            for pattern in patterns
        ), relative_path


def test_docker_assets_have_minimum_structure():
    for relative_path in (
        "backoffice/static/Dockerfile",
        "client_web/Dockerfile",
        "Dockerfile",
    ):
        assert "from " in read_asset(relative_path).casefold()

    compose = read_asset("docker-compose.yml")

    for service in (
        "backoffice-api:",
        "backoffice-ui:",
        "client-web:",
    ):
        assert service in compose

def test_backoffice_role_navigation_contract():
    javascript = read_asset("backoffice/static/app.js")
    normalized = re.sub(r"\s+", " ", javascript)

    assert (
        'admin: new Set(["dashboard", "branches", "products", "users"])'
        in normalized
    )
    assert (
        'common_user: new Set(["dashboard", "branches", "products", "stocks"])'
        in normalized
    )

    assert "function canAccessResource(resource)" in javascript
    assert "function applyRoleNavigation(role)" in javascript
    assert "button.hidden" in javascript
    assert "if (!canAccessResource(resource))" in javascript
    assert 'if (!canAccessResource("stocks"))' in javascript
    assert "currentRole = user?.role ?? null;" in javascript
    assert "innerHTML" not in javascript

