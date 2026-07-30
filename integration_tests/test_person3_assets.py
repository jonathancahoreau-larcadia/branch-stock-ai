"""Network-free contract tests for P3-T04 deployment assets."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

DEPLOYMENT_FILES = (
    "Dockerfile",
    "product_mcp_server/Dockerfile",
    "stock_mcp_server/Dockerfile",
    "ai_service/Dockerfile",
    "client_web/Dockerfile",
    "client_web/nginx.conf",
    "docker/backoffice-entrypoint.sh",
    "docker/database-bootstrap.py",
    "docker-compose.yml",
)
STATIC_FILES = (
    "backoffice/static/index.html",
    "backoffice/static/styles.css",
    "backoffice/static/app.js",
    "backoffice/static/nginx.conf",
    "backoffice/static/Dockerfile",
    "client_web/index.html",
    "client_web/styles.css",
    "client_web/app.js",
)
RUNTIME_KEYS = {
    "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
    "MIGRATION_DB_USER", "MIGRATION_DB_PASSWORD",
    "BACKOFFICE_DB_USER", "BACKOFFICE_DB_PASSWORD",
    "STOCK_MCP_DB_USER", "STOCK_MCP_DB_PASSWORD",
    "MIGRATION_DATABASE_URL", "DATABASE_URL", "STOCK_MCP_DATABASE_URL",
    "JWT_SECRET_KEY", "ADMIN_INITIAL_PASSWORD", "APP_ENV",
    "LARGE_SEED_USER_PASSWORD", "SEED_PRODUCT_ID",
    "BCRYPT_ROUNDS", "PRODUCT_API_TIMEOUT", "CLIENT_WEB_ORIGIN",
    "BACKOFFICE_UI_PORT", "CLIENT_WEB_PORT",
}


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def read_if_present(relative_path: str) -> str:
    path = ROOT / relative_path
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def test_deployment_and_existing_static_assets_are_non_empty():
    missing = [
        path for path in DEPLOYMENT_FILES + STATIC_FILES
        if not (ROOT / path).is_file() or not read(path).strip()
    ]
    assert not missing, f"missing or empty assets: {', '.join(missing)}"


def test_env_example_contains_only_fake_complete_runtime_configuration():
    path = ROOT / ".env.example"
    assert path.is_file(), ".env.example is required"
    assignments = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator and re.fullmatch(r"[A-Z][A-Z0-9_]+", key), line
        assignments[key] = value
    assert set(assignments) == RUNTIME_KEYS
    assert assignments["MIGRATION_DB_USER"] == "migration_user"
    assert assignments["BACKOFFICE_DB_USER"] == "backoffice_app"
    assert assignments["STOCK_MCP_DB_USER"] == "stock_reader"
    assert len({assignments["POSTGRES_USER"], assignments["MIGRATION_DB_USER"],
                 assignments["BACKOFFICE_DB_USER"], assignments["STOCK_MCP_DB_USER"]}) == 4
    assert assignments["CLIENT_WEB_ORIGIN"].startswith(("http://", "https://"))
    assert "*" not in assignments["CLIENT_WEB_ORIGIN"]
    for key, value in assignments.items():
        assert value, key
        assert not re.search(r"postgres(?:ql)?://[^\s:@]+:[^\s@]+@", value, re.I), key
        assert not re.fullmatch(r"[0-9a-f]{32,}", value, re.I), key
        assert not re.fullmatch(r"eyJ[^.]+\.[^.]+\.[^.]+", value), key
    forbidden_env_files = sorted(
        str(path.relative_to(ROOT))
        for path in ROOT.rglob(".env*")
        if path.is_file() and path.name != ".env.example"
        and ".git" not in path.parts
    )
    assert not forbidden_env_files, forbidden_env_files


def test_existing_web_assets_keep_public_local_references():
    html = read("backoffice/static/index.html")
    assert re.search(r'<link[^>]+href=["\'](?:\./)?styles\.css', html, re.I)
    assert re.search(r'<script[^>]+src=["\'](?:\./)?app\.js', html, re.I)
    assert "location /api/" in read("backoffice/static/nginx.conf")
    assert "proxy_pass http://backoffice-api:5000" in read("backoffice/static/nginx.conf")
    proxy = read("client_web/nginx.conf")
    assert re.search(r"location\s*=\s*/questions\s*\{|location\s+/questions\s*\{", proxy)
    assert re.findall(r"(?m)^\s*proxy_pass\s+([^;]+);", proxy) == [
        "http://ai_service:8000/questions"
    ]


def test_both_nginx_interfaces_publish_the_approved_security_headers():
    expected_csp = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    for path in ("backoffice/static/nginx.conf", "client_web/nginx.conf"):
        source = read(path)
        csp = re.search(
            r"add_header\s+Content-Security-Policy\s+\"(?P<value>[^\"]+)\"\s+always\s*;",
            source,
            re.S,
        )
        assert csp, f"CSP must be one complete add_header ... always directive in {path}"
        assert re.sub(r"\s+", " ", csp.group("value")).strip() == expected_csp
        assert re.search(r"add_header\s+X-Content-Type-Options\s+nosniff\s+always", source)
        assert re.search(r"add_header\s+Referrer-Policy\s+no-referrer\s+always", source)
        assert re.search(r"add_header\s+X-Frame-Options\s+DENY\s+always", source)
        assert "unsafe-inline" not in source
        assert "unsafe-eval" not in source
        assert not re.search(r"(?:https?:)?//|\*", csp.group("value"))


def test_backoffice_global_hidden_rule_overrides_layout_display_rules():
    css = read("backoffice/static/styles.css")
    hidden = re.search(r"(?s)\[hidden\]\s*\{(?P<body>[^}]*)\}", css)
    assert hidden, "all hidden sections need a global CSS safety rule"
    assert re.search(r"display\s*:\s*none\s*!important", hidden.group("body"))


def test_dockerfiles_use_declared_manifests_without_forbidden_installations():
    for path in DEPLOYMENT_FILES:
        content = read_if_present(path).casefold()
        assert "curl" not in content, path
        if path != "docker-compose.yml":
            assert "wget" not in content, path
        assert "fastmcp" not in content, path
        assert "host.docker.internal" not in content, path
        assert "latest" not in content, path
    dockerfiles = ("Dockerfile", "product_mcp_server/Dockerfile",
                   "stock_mcp_server/Dockerfile", "ai_service/Dockerfile",
                   "client_web/Dockerfile")
    for path in dockerfiles:
        content = read(path).casefold()
        assert not re.search(r"\b(?:apt(?:-get)?|apk)\s+(?:-\S+\s+)*install\b", content), path
        for command in re.findall(r"\bpip(?:3)?\s+install\b([^\n]*)", content):
            assert "-r" in command, f"{path} installs a dependency outside a declared manifest"
    for path in ("Dockerfile", "product_mcp_server/Dockerfile", "stock_mcp_server/Dockerfile",
                 "ai_service/Dockerfile", "client_web/Dockerfile"):
        assert "from " in read(path).casefold(), path


def test_deployment_descriptors_contain_no_embedded_secrets():
    secret_patterns = (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
        re.compile(r"postgres(?:ql)?://[^\s:@]+:[^\s@]+@"),
    )
    for path in DEPLOYMENT_FILES:
        assert not any(pattern.search(read_if_present(path)) for pattern in secret_patterns), path
        folded = read_if_present(path).casefold()
        assert "ollama" not in folded and "download" not in folded, path


def test_runtime_secrets_and_database_identities_are_not_hard_coded():
    compose = read("docker-compose.yml")
    for key in (
        "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
        "MIGRATION_DB_USER", "MIGRATION_DB_PASSWORD",
        "BACKOFFICE_DB_USER", "BACKOFFICE_DB_PASSWORD",
        "STOCK_MCP_DB_USER", "STOCK_MCP_DB_PASSWORD",
        "MIGRATION_DATABASE_URL", "DATABASE_URL", "STOCK_MCP_DATABASE_URL",
        "JWT_SECRET_KEY", "ADMIN_INITIAL_PASSWORD",
    ):
        assert re.search(rf"\$\{{{key}(?::[-?][^}}]*)?\}}", compose), key

    bootstrap = read("docker/database-bootstrap.py")
    entrypoint = read("docker/backoffice-entrypoint.sh")
    for key in ("POSTGRES_USER", "MIGRATION_DATABASE_URL", "DATABASE_URL",
                "MIGRATION_DB_USER", "BACKOFFICE_DB_USER", "STOCK_MCP_DB_USER"):
        assert key in bootstrap or key in entrypoint, key
    assert not re.search(r"(?i)(?:print|logger?\.(?:info|debug|warning|error))\s*\([^\n]*(?:PASSWORD|SECRET|DATABASE_URL)", bootstrap)
    assert not re.search(r"(?i)(?:echo|printf)\s+[^\n]*(?:PASSWORD|SECRET|DATABASE_URL)", entrypoint)


def test_runtime_configuration_rejects_all_documented_placeholder_forms_without_leaking_values(monkeypatch):
    import importlib.util
    import sys

    bootstrap_path = ROOT / "docker" / "database-bootstrap.py"
    spec = importlib.util.spec_from_file_location("person3_database_bootstrap", bootstrap_path)
    assert spec and spec.loader
    database_bootstrap = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = database_bootstrap
    spec.loader.exec_module(database_bootstrap)

    values = {
        "POSTGRES_DB": "hbntory",
        "POSTGRES_USER": "postgres_owner",
        "POSTGRES_PASSWORD": "postgres-real",
        "MIGRATION_DB_USER": "migration_user",
        "MIGRATION_DB_PASSWORD": "migration-real",
        "BACKOFFICE_DB_USER": "backoffice_app",
        "BACKOFFICE_DB_PASSWORD": "backoffice-real",
        "STOCK_MCP_DB_USER": "stock_reader",
        "STOCK_MCP_DB_PASSWORD": "stock-real",
        "MIGRATION_DATABASE_URL": "postgresql://migration_user:migration-real@database:5432/hbntory",
        "DATABASE_URL": "postgresql://backoffice_app:backoffice-real@database:5432/hbntory",
        "STOCK_MCP_DATABASE_URL": "postgresql://stock_reader:stock-real@database:5432/hbntory",
        "JWT_SECRET_KEY": "jwt-real-value",
        "ADMIN_INITIAL_PASSWORD": "admin-real-value",
        "SEED_PRODUCT_ID": "HB-MON-2102",
        "BCRYPT_ROUNDS": "12",
        "PRODUCT_API_BASE_URL": "http://external-products-api:5000",
        "PRODUCT_API_TIMEOUT": "5",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    assert database_bootstrap._required_environment().values["JWT_SECRET_KEY"] == "jwt-real-value"

    placeholders = ("", "replace-with-secret", "replace_with_secret", "replace-me", "replace_me", "<fake-value>")
    protected = (
        "JWT_SECRET_KEY", "ADMIN_INITIAL_PASSWORD",
        "POSTGRES_PASSWORD", "MIGRATION_DB_PASSWORD",
        "BACKOFFICE_DB_PASSWORD", "STOCK_MCP_DB_PASSWORD",
        "MIGRATION_DATABASE_URL", "DATABASE_URL", "STOCK_MCP_DATABASE_URL",
    )
    for key in protected:
        original = values[key]
        for placeholder in placeholders:
            monkeypatch.setenv(key, placeholder)
            with pytest.raises(database_bootstrap.BootstrapConfigurationError) as error:
                database_bootstrap._required_environment()
            if placeholder:
                assert placeholder not in str(error.value)
        monkeypatch.setenv(key, original)


def test_bootstrap_enforces_effective_role_boundaries_and_idempotence():
    bootstrap = read("docker/database-bootstrap.py")
    entrypoint = read("docker/backoffice-entrypoint.sh")
    folded = re.sub(r"\s+", " ", bootstrap.casefold())
    for marker in ("POSTGRES_USER", "MIGRATION_DB_USER", "BACKOFFICE_DB_USER",
                   "STOCK_MCP_DB_USER", "migration_user", "backoffice_app", "stock_reader",
                   "CREATE ROLE", "CONNECT", "USAGE", "SELECT",
                   "branches", "stocks", "users", "revoked_tokens", "db upgrade", "seed"):
        assert marker.casefold() in bootstrap.casefold(), marker
    assert re.search(r"revoke\s+all\s+privileges\s+on\s+table\s+[^;]*(users|revoked_tokens)", folded)
    assert re.search(r"grant\s+select\s+on\s+table\s+[^;]*(branches|stocks)[^;]*stock_reader", folded)
    for table in ("users", "revoked_tokens"):
        assert re.search(rf"revoke\s+[^;]+\s+on\s+table\s+[^;]*{table}[^;]*stock_reader", folded)
    assert re.search(r"create\s+role\s+if\s+not\s+exists|do\s+\$\$", folded)
    assert "alter role" in folded
    assert "on conflict" in folded or "if not exists" in folded
    assert "grant" in folded and "revoke" in folded
    assert re.search(r"db upgrade", folded) and re.search(r"seed", folded)
    assert "python -m flask --app backoffice db upgrade" in folded
    assert "python -m flask --app backoffice seed" in folded
    migration_pos = folded.find("db upgrade")
    seed_pos = folded.find("seed")
    assert migration_pos >= 0 and "migration_database_url" in folded[max(0, migration_pos - 500):migration_pos + 500]
    assert seed_pos >= 0 and all(marker in folded[max(0, seed_pos - 900):seed_pos + 900]
                                  for marker in ("database_url", "admin_initial_password",
                                                 "seed_product_id", "bcrypt_rounds"))
    assert "set -e" in entrypoint or "set -Eeuo pipefail" in entrypoint
    assert entrypoint.find("database-bootstrap.py") >= 0
    assert entrypoint.find("database-bootstrap.py") < entrypoint.find("gunicorn")
    for privilege in ("insert", "update", "delete", "truncate", "create"):
        assert privilege in folded
    assert "gunicorn" in entrypoint and "exec" in entrypoint


def test_client_assets_remain_native_and_do_not_render_received_html():
    javascript = read("client_web/app.js")
    assert "addEventListener" in javascript
    assert "createElement" in javascript
    assert "innerHTML" not in javascript
    assert "from 'vue'" not in javascript and 'from "vue"' not in javascript


def test_asset_test_module_itself_performs_no_external_io():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint({"requests", "httpx", "socket", "subprocess", "psycopg"})
