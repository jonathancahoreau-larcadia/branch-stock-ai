"""Static, network-free tests for the P3-T04 Docker Compose contract."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
SERVICES = {"database", "external-products-api", "backoffice-api", "backoffice-ui",
            "product_mcp_server", "stock_mcp_server", "ai_service", "client_web"}
EXTERNAL_IMAGE = "hbntory-products-api-external-products-api@sha256:bc3d2e796577ec36b3ab272def86f6b5831a70510432c0946a62a2b5f6fed00c"
POSTGRES_IMAGE = "postgres@sha256:33f923b05f64ca54ac4401c01126a6b92afe839a0aa0a52bc5aeb5cc958e5f20"


def compose_text() -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    assert text.strip()
    return text


def service_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line == f"  {name}:"), None)
    assert start is not None, f"missing service {name}"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.fullmatch(r"  [A-Za-z0-9_-]+:", lines[i]):
            end = i
            break
    return "\n".join(lines[start:end]) + "\n"


def section_body(block: str, key: str) -> str:
    """Return a YAML section without requiring a particular child indent."""
    lines = block.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if re.fullmatch(rf"(\s*){re.escape(key)}:\s*", line)), None)
    if start is None:
        return ""
    parent_indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        indent = len(lines[i]) - len(lines[i].lstrip())
        if stripped and indent <= parent_indent:
            end = i
            break
    return "\n".join(lines[start + 1:end])


def environment_block(service: str, text: str | None = None) -> str:
    return section_body(service_block(compose_text() if text is None else text, service), "environment")


def ports_block(service: str, text: str) -> str:
    return section_body(service_block(text, service), "ports")


def dependency_names(service: str, text: str) -> set[str]:
    body = section_body(service_block(text, service), "depends_on")
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return set()
    child_indent = min(len(line) - len(line.lstrip()) for line in lines)
    return {match.group(1) for line in lines
            if len(line) - len(line.lstrip()) == child_indent
            for match in [re.match(r"\s*(?:-\s*)?([A-Za-z0-9_-]+):", line)]
            if match}


def top_level_service_names(text: str) -> set[str]:
    match = re.search(r"(?ms)^services:\s*\n(?P<body>.*?)(?=^[^ \n].*:|\Z)", text)
    assert match
    return set(re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", match.group("body"), re.M))


def top_level_network_block(text: str) -> str:
    match = re.search(r"(?ms)^networks:\s*\n(?P<body>.*?)(?=^[^ \n].*:|\Z)", text)
    assert match, "a top-level networks declaration is required"
    return match.group("body")


def top_level_network_names(text: str) -> set[str]:
    return set(re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", top_level_network_block(text), re.M))


def top_level_volume_block(text: str) -> str:
    match = re.search(r"(?ms)^volumes:\s*\n(?P<body>.*?)(?=^[^ \n].*:|\Z)", text)
    assert match, "a top-level volumes declaration is required"
    return match.group("body")


def top_level_volume_names(text: str) -> set[str]:
    return set(re.findall(r"^  ([A-Za-z0-9_.-]+):\s*$", top_level_volume_block(text), re.M))


def service_network_names(service: str, text: str) -> set[str]:
    block = service_block(text, service)
    match = re.search(r"(?ms)^    networks:\s*\n(?P<body>.*?)(?=^    [A-Za-z_][A-Za-z0-9_-]*:|\Z)", block)
    assert match, f"{service} must join the internal network"
    body = match.group("body")
    return set(re.findall(r"^      (?:-\s+)?([A-Za-z0-9_-]+)(?::\s*)?$", body, re.M))


def interpolation_default(value: str, variable: str) -> str:
    match = re.search(rf"\$\{{{re.escape(variable)}:-([^}}]+)\}}", value)
    assert match, f"{variable} must have a runtime/default value"
    return match.group(1).strip('"\' ')


def environment_value(service: str, variable: str, text: str) -> str:
    body = environment_block(service, text)
    match = re.search(rf"^\s*(?:{re.escape(variable)}:\s*(?P<mapping>.+)|-\s*{re.escape(variable)}=(?P<list>.*))$", body, re.M)
    assert match, f"{service} must define {variable}"
    return (match.group("mapping") or match.group("list")).strip()


def has_environment_key(service: str, variable: str, text: str) -> bool:
    try:
        environment_value(service, variable, text)
    except AssertionError:
        return False
    return True


def test_compose_declares_exactly_the_eight_contractual_services():
    assert top_level_service_names(compose_text()) == SERVICES


def test_compose_uses_approved_images_persistent_database_and_read_only_catalogue():
    text = compose_text()
    products = service_block(text, "external-products-api")
    database = service_block(text, "database")
    assert f"image: {EXTERNAL_IMAGE}" in products and "build:" not in products
    assert environment_value("external-products-api", "HBN_PRODUCTS_PORT", text) == "5000"
    assert environment_value("external-products-api", "HBN_PRODUCTS_LATENCY_MS", text) == "0"
    assert not has_environment_key("external-products-api", "HBN_PRODUCTS_HOST", text)
    assert not has_environment_key("external-products-api", "HBN_PRODUCTS_DATA_FILE", text)
    assert f"image: {POSTGRES_IMAGE}" in database and "build:" not in database
    assert re.search(r"(?m)^\s+- [A-Za-z0-9_.-]+:/var/lib/postgresql/data\s*$", database)
    assert all(has_environment_key("database", key, text)
               for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"))
    assert all(has_environment_key("database", key, text)
               for key in ("MIGRATION_DB_USER", "BACKOFFICE_DB_USER", "STOCK_MCP_DB_USER"))
    assert "pg_isready" in database
    assert not re.search(r"(?ms)^\s+ports:\s*\n(?:\s+-[^\n]*\n)+", database)


def test_postgres_data_mount_uses_a_declared_top_level_named_volume():
    text = compose_text()
    assert "postgres-data" in top_level_volume_names(text)
    database = service_block(text, "database")
    assert re.search(
        r"(?m)^\s+-\s+postgres-data:/var/lib/postgresql/data\s*$",
        database,
    )


def test_compose_uses_only_internal_urls_and_the_two_public_ports():
    text = compose_text()
    assert "localhost" not in text and "host.docker.internal" not in text and "5001" not in text
    assert "ports:" not in service_block(text, "external-products-api")
    assert re.search(r"^\s*-\s*", ports_block("backoffice-ui", text), re.M)
    assert re.search(r"^\s*-\s*", ports_block("client_web", text), re.M)
    assert len(re.findall(r"^\s*-\s*", ports_block("backoffice-ui", text), re.M)) == 1
    assert len(re.findall(r"^\s*-\s*", ports_block("client_web", text), re.M)) == 1
    assert environment_value("backoffice-api", "PRODUCT_API_BASE_URL", text) == "http://external-products-api:5000"
    assert environment_value("product_mcp_server", "PRODUCT_API_BASE_URL", text) == "http://external-products-api:5000"
    assert environment_value("ai_service", "PRODUCT_MCP_URL", text) == "http://product_mcp_server:8100/mcp"
    assert environment_value("ai_service", "STOCK_MCP_URL", text) == "http://stock_mcp_server:8200/mcp"
    assert has_environment_key("ai_service", "CLIENT_WEB_ORIGIN", text)
    assert environment_value("ai_service", "AI_SERVICE_PORT", text) == "8000"
    for service in SERVICES - {"backoffice-ui", "client_web"}:
        assert "ports:" not in service_block(text, service)
    assert re.search(r"BACKOFFICE_UI_PORT:-8080", text)
    assert re.search(r"CLIENT_WEB_PORT:-3000", text)


def test_every_service_has_an_exact_contractual_healthcheck():
    text = compose_text()
    assert "curl" not in text and "wget" not in text
    for service in SERVICES:
        assert "healthcheck:" in service_block(text, service), service
    assert re.search(r"pg_isready[^\n]*(?:POSTGRES_USER|--username)", service_block(text, "database"))
    external = service_block(text, "external-products-api")
    external_health = re.search(r"(?ms)^    healthcheck:\s*\n(?P<body>.*?)(?=^    [A-Za-z_][A-Za-z0-9_-]*:|\Z)", external)
    assert external_health
    external_body = external_health.group("body")
    assert "127.0.0.1:5000/health" in external_body
    assert all(marker in external_body for marker in ('"status"', '"products"', '"suppliers"'))
    assert "200" in external_body and "python" in external_body.casefold()
    assert any(marker in external_body for marker in ("urllib.request", "http.client"))
    for service in ("backoffice-api", "product_mcp_server", "stock_mcp_server", "ai_service"):
        block = service_block(text, service)
        health = re.search(r"(?ms)^    healthcheck:\s*\n(?P<body>.*?)(?=^    [A-Za-z_][A-Za-z0-9_-]*:|\Z)", block)
        assert health
        health_body = health.group("body")
        assert "127.0.0.1" in health_body and "/health" in health_body and "200" in health_body
        assert '"status"' in health_body and '"ok"' in health_body
        assert "python" in health_body.casefold()
        assert any(marker in health_body for marker in ("urllib.request", "http.client"))
    assert "nginx -t" in service_block(text, "backoffice-ui")
    assert "nginx -t" in service_block(text, "client_web")


def test_dependencies_are_exactly_conditioned_on_healthy_services():
    text = compose_text()
    expected = {"backoffice-api": {"database", "external-products-api"},
                "backoffice-ui": {"backoffice-api"},
                "product_mcp_server": {"external-products-api"},
                "stock_mcp_server": {"database"},
                "ai_service": {"product_mcp_server", "stock_mcp_server"},
                "client_web": {"ai_service"}}
    assert {service for service in SERVICES if dependency_names(service, text)} == set(expected)
    for service, dependencies in expected.items():
        block = service_block(text, service)
        assert dependency_names(service, text) == dependencies
        for dependency in dependencies:
            dependency_block = re.search(
                rf"(?ms)^      {re.escape(dependency)}:\s*\n(?P<body>.*?)(?=^      [A-Za-z0-9_-]+:|\Z)",
                block,
            )
            assert dependency_block and "condition: service_healthy" in dependency_block.group("body")


def test_network_commands_and_public_proxy_are_wired():
    text = compose_text()
    assert re.search(r"(?m)^networks:\s*$", text)
    assert re.search(r"(?m)^\s{2}[A-Za-z0-9_-]+:\s*\n\s{4}driver:\s*bridge", text)
    for service in SERVICES:
        assert "networks:" in service_block(text, service)
    for module, service in (("product_mcp_server", "product_mcp_server"),
                            ("stock_mcp_server", "stock_mcp_server"),
                            ("ai_service", "ai_service")):
        assert f"python -m {module}.server" in service_block(text, service)
    assert "docker/backoffice-entrypoint.sh" in service_block(text, "backoffice-api")
    assert "proxy_pass http://ai_service:8000/questions" in (ROOT / "client_web/nginx.conf").read_text()


def test_all_services_share_one_named_bridge_network():
    text = compose_text()
    networks = top_level_network_names(text)
    assert len(networks) == 1
    network = next(iter(networks))
    network_block = top_level_network_block(text)
    declared = re.search(rf"(?ms)^  {re.escape(network)}:\s*\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", text)
    assert declared and re.search(r"^    driver:\s*bridge\s*$", declared.group("body"), re.M)
    assert re.search(r"^    name:\s*[A-Za-z0-9_.-]+\s*$", declared.group("body"), re.M)
    assert "internal: true" in declared.group("body").casefold()
    for service in SERVICES:
        assert service_network_names(service, text) == {network}, service


def test_compose_passes_the_public_client_origin_to_ai_service():
    text = compose_text()
    ai = service_block(text, "ai_service")
    assert has_environment_key("ai_service", "CLIENT_WEB_ORIGIN", text)


def test_client_origin_is_http_origin_matching_the_published_client_port():
    text = compose_text()
    client = service_block(text, "client_web")
    port_match = re.search(r"^\s*-\s*[\"']?\$\{CLIENT_WEB_PORT:-([0-9]+)\}:80[\"']?\s*$", ports_block("client_web", text), re.M)
    assert port_match, "client_web must publish the configured client port"
    public_port = int(port_match.group(1))
    raw_origin = environment_value("ai_service", "CLIENT_WEB_ORIGIN", text)
    origin = interpolation_default(raw_origin, "CLIENT_WEB_ORIGIN")
    parsed = urlsplit(origin)
    assert parsed.scheme in {"http", "https"}
    assert parsed.hostname and parsed.username is None and parsed.password is None
    assert parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
    assert parsed.port == public_port
    assert "*" not in origin


def test_database_healthcheck_uses_its_database_name_and_runtime_identities_are_scoped():
    text = compose_text()
    database = service_block(text, "database")
    healthcheck = re.search(r"(?ms)^    healthcheck:\s*\n(?P<body>.*?)(?=^    [A-Za-z_][A-Za-z0-9_-]*:|\Z)", database)
    assert healthcheck
    assert "pg_isready" in healthcheck.group("body")
    assert "POSTGRES_USER" in healthcheck.group("body")
    assert "POSTGRES_DB" in healthcheck.group("body")
    assert "MIGRATION_DB_PASSWORD" not in environment_block("database", text)
    assert "BACKOFFICE_DB_PASSWORD" not in environment_block("database", text)
    assert "STOCK_MCP_DB_PASSWORD" not in environment_block("database", text)
    backoffice = environment_block("backoffice-api", text)
    stock = environment_block("stock_mcp_server", text)
    assert "BACKOFFICE_DB_USER" in environment_value("backoffice-api", "DATABASE_URL", text)
    assert "STOCK_MCP_DB_USER" in environment_value("stock_mcp_server", "STOCK_MCP_DATABASE_URL", text)


def test_compose_interpolates_all_runtime_identity_urls_and_secrets():
    text = compose_text()
    expected = {
        "database": ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
                     "MIGRATION_DB_USER", "BACKOFFICE_DB_USER", "STOCK_MCP_DB_USER"),
        "backoffice-api": ("DATABASE_URL", "JWT_SECRET_KEY"),
        "stock_mcp_server": ("STOCK_MCP_DATABASE_URL",),
        "ai_service": ("CLIENT_WEB_ORIGIN",),
    }
    for service, keys in expected.items():
        for key in keys:
            value = environment_value(service, key, text)
            assert re.search(r"\$\{" + re.escape(key) + r"(?:[:-])", value), (service, key, value)
    for key in ("MIGRATION_DB_PASSWORD", "BACKOFFICE_DB_PASSWORD", "STOCK_MCP_DB_PASSWORD"):
        assert key not in environment_block("database", text)


def test_application_passwords_and_migration_url_are_bootstrap_only():
    text = compose_text()
    bootstrap_service = "backoffice-api"
    bootstrap_environment = environment_block(bootstrap_service, text)
    bootstrap_only = (
        "MIGRATION_DB_PASSWORD",
        "BACKOFFICE_DB_PASSWORD",
        "STOCK_MCP_DB_PASSWORD",
        "MIGRATION_DATABASE_URL",
    )
    for key in bootstrap_only:
        value = environment_value(bootstrap_service, key, text)
        assert re.search(r"\$\{" + re.escape(key) + r"(?:[:-])", value), (key, value)
        assert re.search(
            rf"^\s*(?:{re.escape(key)}\s*:|-\s*{re.escape(key)}\s*=)",
            bootstrap_environment,
            re.M,
        )

    for service in SERVICES - {bootstrap_service}:
        environment = environment_block(service, text)
        for key in bootstrap_only:
            assert not re.search(
                rf"^\s*(?:{re.escape(key)}\s*:|-\s*{re.escape(key)}\s*=)",
                environment,
                re.M,
            ), (
                service,
                key,
            )


def test_only_contractual_base_images_and_no_model_runtime_are_declared():
    text = compose_text().casefold()
    assert "ollama" not in text and "pull" not in text
    allowed = {
        "python:3.11-slim", "nginx:1.27-alpine",
        EXTERNAL_IMAGE.casefold(), POSTGRES_IMAGE.casefold(),
    }
    for path in ("Dockerfile", "product_mcp_server/Dockerfile", "stock_mcp_server/Dockerfile",
                 "ai_service/Dockerfile", "client_web/Dockerfile"):
        content = (ROOT / path).read_text(encoding="utf-8").casefold()
        bases = re.findall(r"(?m)^\s*from\s+([^\s]+)", content)
        assert bases and set(bases) <= allowed, (path, bases)


def test_deployment_test_module_performs_no_network_or_process_io():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint({"requests", "httpx", "socket", "subprocess", "psycopg", "yaml"})
