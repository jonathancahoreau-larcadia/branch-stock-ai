"""Network-free contract checks for the P3-T06 documentation deliverables."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "README.md",
    "docs/test_evidence/README.md",
    "docs/test_evidence/P3-T06_PRODUCT_MCP_MANUAL.md",
    "docs/test_evidence/P3-T06_FINAL_VALIDATION.md",
    "docs/demo_plan.md",
)

REQUIRED_COMMANDS = (
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_person3_documentation.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_person3_end_to_end.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_backoffice_ui.py integration_tests/test_client_web_ui.py integration_tests/test_person3_assets.py integration_tests/test_person3_docker.py integration_tests/test_person3_integration_plan.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider backoffice/tests/test_auth_routes.py backoffice/tests/test_users_routes.py backoffice/tests/test_branches_routes.py backoffice/tests/test_products_routes.py backoffice/tests/test_stocks_routes.py backoffice/tests/test_health.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_ai_classifier.py tests/test_ai_generator.py tests/test_ai_ollama_client.py tests/test_ai_question_service.py tests/test_ai_server.py tests/test_ai_mcp_client.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_product_mcp_tools.py tests/test_product_mcp_server.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_product_mcp_server.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_stock_mcp_repository.py tests/test_stock_mcp_tools.py tests/test_stock_mcp_server.py",
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_stock_mcp_server.py",
)

REQUIRED_SERVICES = (
    "database",
    "external-products-api",
    "backoffice-api",
    "backoffice-ui",
    "product_mcp_server",
    "stock_mcp_server",
    "ai_service",
    "client_web",
)

REQUIRED_ENVIRONMENT_VARIABLES = (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "MIGRATION_DB_USER",
    "MIGRATION_DB_PASSWORD",
    "BACKOFFICE_DB_USER",
    "BACKOFFICE_DB_PASSWORD",
    "STOCK_MCP_DB_USER",
    "STOCK_MCP_DB_PASSWORD",
    "MIGRATION_DATABASE_URL",
    "DATABASE_URL",
    "STOCK_MCP_DATABASE_URL",
    "JWT_SECRET_KEY",
    "ADMIN_INITIAL_PASSWORD",
    "SEED_PRODUCT_ID",
    "BCRYPT_ROUNDS",
    "PRODUCT_API_TIMEOUT",
    "CLIENT_WEB_ORIGIN",
    "BACKOFFICE_UI_PORT",
    "CLIENT_WEB_PORT",
)

REQUIRED_PUBLIC_ENDPOINTS = (
    "http://127.0.0.1:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5000/health",
    "http://127.0.0.1:8100/health",
    "http://127.0.0.1:8200/health",
    "http://127.0.0.1:8000/health",
)

MANUAL_SCENARIOS = {
    "list_products": r"(?im)^#{1,6}\s*(?:scénario\s*)?1\b.*list_products",
    "get_product_details_valid": r"(?im)^#{1,6}\s*(?:scénario\s*)?2\b.*get_product_details.*(?:valide|valid)",
    "invalid_or_unknown": r"(?im)^#{1,6}\s*(?:scénario\s*)?3\b.*(?:invalide|inconnu|invalid|unknown)",
    "unavailable": r"(?im)^#{1,6}\s*(?:scénario\s*)?4\b.*(?:arrêt|inaccessible|unavailable|stopped)",
}

SECRET_PATTERNS = (
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{16,}\b", re.I),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"postgres(?:ql)?://[^\s:@]+:[^\s@]+@", re.I),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)\b(?:set-cookie|cookie|x-api-key|api-key|refresh_token|access_token)\s*[:=]\s*(?!<[^>]+>|\*+|REDACTED|EXAMPLE)[^\s|`]+"),
    re.compile(r"(?i)(?:file://|/run/secrets/|\.env\.runtime\b|runtime\.json\b|docker inspect\s+[^<\s])"),
    re.compile(r"(?i)https?://[^\s|`]*(?:token|secret|password|api[_-]?key|authorization)=[^\s|`]+"),
)

PLACEHOLDER = r"(?:_{3,}|\[\s*(?:à compléter|a completer|à renseigner|a renseigner|tbd|non renseigné|non renseigne)\s*\]|à compléter|a completer|tbd|non renseigné|non renseigne)"


def _read(relative_path: str) -> str:
    path = ROOT / relative_path
    assert path.is_file(), f"missing documentation deliverable: {relative_path}"
    content = path.read_text(encoding="utf-8")
    assert content.strip(), f"empty documentation deliverable: {relative_path}"
    return content


def _fold(value: str) -> str:
    return value.casefold()


def _heading_section(raw: str, heading_pattern: str) -> str:
    match = re.search(heading_pattern, raw)
    assert match, f"missing documentation section matching: {heading_pattern}"
    following = re.search(r"(?m)^#{1,6}\s+", raw[match.end() :])
    return raw[match.start() :] if following is None else raw[match.start() : match.end() + following.start()]


def _has_unfilled_field(raw: str, labels: tuple[str, ...]) -> bool:
    joined = "(?:" + "|".join(re.escape(label) for label in labels) + ")"
    return re.search(rf"(?i){joined}\s*[:|—-]\s*{PLACEHOLDER}", raw) is not None


def test_documentation_contract_test_is_local_and_non_mutating():
    tree = ast.parse((ROOT / "integration_tests/test_person3_documentation.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])

    assert imported.isdisjoint({"aiohttp", "asyncpg", "httpx", "psycopg", "requests", "socket", "subprocess", "urllib"})
    forbidden_calls = {
        "connect", "create_connection", "mkdir", "open", "patch", "rename", "replace",
        "request", "rmdir", "symlink_to", "touch", "unlink", "write_text", "write_bytes",
    }
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls.isdisjoint(forbidden_calls)


def test_all_contractual_documentation_paths_exist_and_have_core_sections():
    contents = {path: _read(path) for path in DOCUMENTS}
    readme = _fold(contents["README.md"])
    for marker in ("prérequis", ".env", "build", "initialiser", "seed", "docker compose", "backoffice", "client web", "health", "pytest", "diagnostic", "reprise", "limites", "sécurité", "sans suppression de volume"):
        assert marker in readme, f"README is missing contract topic: {marker}"

    evidence_index = _fold(contents["docs/test_evidence/README.md"])
    for marker in ("p3-t01", "p3-t02", "p3-t03", "p3-t04", "p3-t05", "p3-t06", "automatis", "runtime", "manuel", "humain"):
        assert marker in evidence_index, f"evidence index is missing: {marker}"

    final_validation = _fold(contents["docs/test_evidence/P3-T06_FINAL_VALIDATION.md"])
    for marker in ("code retour", "utc", "p3-t05", "product_mcp_manual", "scénario", "absent", "expurg"):
        assert marker in final_validation, f"final validation is missing: {marker}"

    demo = _fold(contents["docs/demo_plan.md"])
    for marker in ("10 minutes", "architecture", "authentification", "common user", "admin", "produits", "stocks", "erreurs", "jwt", "bcrypt", "rest", "mcp", "reprise"):
        assert marker in demo, f"demo plan is missing: {marker}"


def test_readme_documents_services_configuration_ports_urls_and_safe_recovery():
    readme = _fold(_read("README.md"))
    for service in REQUIRED_SERVICES:
        assert service.casefold() in readme, f"README omits service: {service}"
    for variable in REQUIRED_ENVIRONMENT_VARIABLES:
        assert re.search(rf"(?i)(?<![a-z0-9_]){re.escape(variable)}(?![a-z0-9_])", readme), f"README omits variable: {variable}"
    for endpoint in REQUIRED_PUBLIC_ENDPOINTS:
        assert endpoint.casefold() in readme, f"README omits endpoint: {endpoint}"
    for marker in ("docker compose config", "docker compose up", "docker compose down", "docker compose ps", "docker compose logs", "health", "seed", "idempot", "diagnostic", "reprise", "sans suppression de volume"):
        assert marker in readme, f"README omits operational topic: {marker}"
    assert "docker compose down -v" not in readme


def test_documentation_uses_relative_paths_and_keeps_all_human_fields_empty():
    index = _read("docs/test_evidence/README.md")
    final_validation = _read("docs/test_evidence/P3-T06_FINAL_VALIDATION.md")
    for raw, name in ((index, "evidence index"), (final_validation, "final validation")):
        assert not re.search(r"(?m)^\s*(?:/|[A-Za-z]:[\\/])", raw), f"{name} contains an absolute evidence path"
        assert not re.search(r"(?i)file://|/tmp/|/var/lib/docker/|/run/secrets/", raw), f"{name} contains a runtime path"
    for relative_path in ("docs/test_evidence/README.md", "docs/test_evidence/P3-T06_PRODUCT_MCP_MANUAL.md", "docs/test_evidence/P3-T06_FINAL_VALIDATION.md", "person3_handoffs/runtime_proofs/P3-T05-runtime-command-results.json"):
        assert relative_path in index or relative_path in final_validation, f"missing relative evidence path: {relative_path}"

    demo = _read("docs/demo_plan.md")
    independent = _heading_section(demo, r"(?im)^#{1,6}\s+.*(?:vérification|verification).*indépendant|^#{1,6}\s+.*setup")
    rehearsal = _heading_section(demo, r"(?im)^#{1,6}\s+.*(?:répétition|repetition)")
    qa = _heading_section(demo, r"(?im)^#{1,6}\s+.*\bqa\b")
    for labels, section_name, section in (
        (("identité", "identite", "membre"), "independent README review", independent),
        (("date UTC", "date"), "independent README review", independent),
        (("environnement", "environment"), "independent README review", independent),
        (("résultat", "resultat", "résultat observé"), "independent README review", independent),
        (("participants", "participant"), "demo rehearsal", rehearsal),
        (("date UTC", "date"), "demo rehearsal", rehearsal),
        (("durée", "duree"), "demo rehearsal", rehearsal),
        (("scénarios", "scenarios"), "demo rehearsal", rehearsal),
        (("incidents", "incident"), "demo rehearsal", rehearsal),
        (("reprise", "recovery"), "demo rehearsal", rehearsal),
        (("demandeur", "équipe demandeuse", "equipe demandeuse"), "QA request", qa),
        (("date UTC", "date"), "QA request", qa),
        (("statut", "status"), "QA request", qa),
    ):
        assert _has_unfilled_field(section, labels), f"{section_name} field is not explicitly empty: {labels[0]}"


def test_product_manual_proof_has_four_observed_expurgated_scenarios():
    raw = _read("docs/test_evidence/P3-T06_PRODUCT_MCP_MANUAL.md")
    transcript = _fold(raw)
    for name, heading in MANUAL_SCENARIOS.items():
        matches = list(re.finditer(heading, raw))
        assert len(matches) == 1, f"manual transcript must have one heading for {name}"
        match = matches[0]
        start = match.start()
        next_heading = re.search(r"(?m)^#{1,6}\s+", raw[match.end() :])
        section = raw[start:] if next_heading is None else raw[start : match.end() + next_heading.start()]
        section = _fold(section)
        assert "commande" in section or "étapes" in section, f"scenario {name} is missing a command or inspector steps"
        for marker in ("observation", "statut", "conclusion"):
            assert marker in section, f"scenario {name} is missing: {marker}"
        if name == "invalid_or_unknown":
            assert "invalid_external_product_id" in section, "scenario 3 must distinguish INVALID_EXTERNAL_PRODUCT_ID locally"
            assert "not_found" in section, "scenario 3 must distinguish not_found locally"
    for marker in ("date utc", "environnement local", "sans réseau", "double", "socket", "expurg", "secret", "jeton", "en-tête", "cookie", "log brut"):
        assert marker in transcript, f"manual transcript is missing: {marker}"


def test_final_validation_records_each_exact_command_with_return_code_and_useful_redacted_output():
    final_validation = _fold(_read("docs/test_evidence/P3-T06_FINAL_VALIDATION.md"))
    assert "processus séparés" in final_validation or "processus distincts" in final_validation
    positions = [final_validation.index(command.casefold()) for command in REQUIRED_COMMANDS]
    assert len(set(positions)) == len(REQUIRED_COMMANDS)
    assert positions == sorted(positions), "required commands must be recorded in contract order"
    for index, command in enumerate(REQUIRED_COMMANDS):
        start = positions[index]
        end = positions[index + 1] if index + 1 < len(positions) else len(final_validation)
        section = final_validation[start:end]
        assert re.search(r"code retour\s*[:|]\s*0|return code\s*[:|]\s*0", section), f"missing return code 0: {command}"
        assert re.search(r"(?:sortie utile|output|résultat|resultat)\s*[:|].{3,}", section), f"missing useful output: {command}"
        assert re.search(r"(?:expurg|sanitis|redact)", section), f"missing redaction marker: {command}"


def test_documentation_contains_no_manifest_secrets_or_raw_runtime_material():
    for path in DOCUMENTS:
        content = _read(path)
        assert not any(pattern.search(content) for pattern in SECRET_PATTERNS), path
        folded = content.casefold()
        assert "authorization: bearer" not in folded
        assert "set-cookie:" not in folded and "cookie:" not in folded
        assert not re.search(r"(?im)^\s*(?:stdout|stderr|raw log|logs bruts?)\s*[:|]", content)
        assert not re.search(r"(?i)(?:/tmp/|/var/lib/docker/|/run/secrets/|\.env\.runtime|runtime\.json)", content)


def test_documented_test_groups_keep_product_and_stock_mcp_processes_separate():
    final_validation = _fold(_read("docs/test_evidence/P3-T06_FINAL_VALIDATION.md"))
    product_position = final_validation.find("integration_tests/test_product_mcp_server.py")
    stock_position = final_validation.find("integration_tests/test_stock_mcp_server.py")
    assert product_position >= 0 and stock_position >= 0
    product_line = next(line for line in final_validation.splitlines() if "integration_tests/test_product_mcp_server.py" in line)
    stock_line = next(line for line in final_validation.splitlines() if "integration_tests/test_stock_mcp_server.py" in line)
    assert "stock_mcp" not in product_line
    assert "product_mcp" not in stock_line
