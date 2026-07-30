"""Local contract checks for the Person 3 integration audit and plan.

The P3-T01 deliverable is documentation.  These tests read only that local
document and inspect their own source for forbidden I/O; they do not import an
application service, open a socket, contact an API, or connect to PostgreSQL.
"""

from __future__ import annotations

import ast
import re
import unicodedata
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPOSITORY_ROOT / "docs/person3_integration_plan.md"

REQUIRED_SECTIONS = (
    "Résumé exécutif",
    "Méthode et périmètre de l’audit",
    "Inventaire vérifié",
    "Contrats et flux d’intégration",
    "Écarts, risques et dépendances",
    "Plan d’intégration P3-T02 à P3-T06",
    "Stratégie de preuve",
    "Sources",
)

REQUIRED_COMPONENTS = (
    "PostgreSQL",
    "External Product API",
    "Backoffice Flask",
    "Backoffice UI",
    "Product MCP Server",
    "Stock MCP Server",
    "AI Query Service",
    "Client Web",
)

PROTECTED_PATHS = (
    "product_mcp_server/__init__.py",
    "product_mcp_server/product_api.py",
    "product_mcp_server/tools.py",
    "product_mcp_server/server.py",
    "product_mcp_server/requirements.txt",
    "tests/test_product_mcp_tools.py",
    "tests/test_product_mcp_server.py",
    "integration_tests/test_product_mcp_server.py",
)

PLAN_TASKS = ("P3-T02", "P3-T03", "P3-T04", "P3-T05", "P3-T06")


def _read_plan() -> str:
    assert PLAN_PATH.is_file(), f"Missing integration plan: {PLAN_PATH}"
    plan = PLAN_PATH.read_text(encoding="utf-8")
    assert plan.strip(), "The integration plan must not be empty"
    return plan


def _fold(value: str) -> str:
    """Normalize case and accents for stable checks of French prose."""
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value.casefold())
        if not unicodedata.combining(character)
    )


def _heading(line: str) -> tuple[int, str] | None:
    match = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
    if not match:
        return None
    title = re.sub(r"^\s*\d+[.)]\s*", "", match.group(2))
    return len(match.group(1)), _fold(title.strip())


def _section(plan: str, title: str) -> str:
    """Return one markdown section, accepting optional numeric prefixes."""
    lines = plan.splitlines()
    wanted = _fold(title)
    for index, line in enumerate(lines):
        heading = _heading(line)
        if not heading or heading[1] != wanted:
            continue
        level = heading[0]
        end = len(lines)
        for candidate, following in enumerate(lines[index + 1 :], index + 1):
            next_heading = _heading(following)
            if next_heading and next_heading[0] <= level:
                end = candidate
                break
        return "\n".join(lines[index + 1 : end])
    raise AssertionError(f"Missing markdown section: {title}")


def _entry_blocks(text: str, names: tuple[str, ...]) -> dict[str, str]:
    """Split a section into separately labelled component/task entries.

    A heading, a list item, or a line beginning with the label is accepted;
    the document is not required to use one particular Markdown layout.
    """
    lines = text.splitlines()
    folded_names = {name: _fold(name) for name in names}
    anchors: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        for name, folded_name in folded_names.items():
            folded_line = _fold(line).strip()
            entry_start = re.sub(r"^(?:#+\s+|[-*+]\s+|\d+[.)]\s+)", "", folded_line)
            entry_start = entry_start.lstrip("*`").strip()
            if (
                folded_name in folded_line
                and (
                    _heading(line) is not None
                    or entry_start.startswith(folded_name)
                    or folded_line.startswith(f"| {folded_name} |")
                )
            ):
                anchors.append((index, name))
                break

    missing = [name for name in names if not any(item[1] == name for item in anchors)]
    assert not missing, f"Missing separately anchored entries: {', '.join(missing)}"

    selected = [next(item for item in anchors if item[1] == name) for name in names]
    selected.sort()
    blocks: dict[str, str] = {}
    for position, (start, name) in enumerate(selected):
        end = selected[position + 1][0] if position + 1 < len(selected) else len(lines)
        # Keep the anchor itself: a valid inventory may be a Markdown table
        # whose component row contains every required field.
        blocks[name] = "\n".join(lines[start:end])
    return blocks


def _assert_any_marker(text: str, markers: tuple[str, ...], context: str) -> None:
    folded = _fold(text)
    assert any(_fold(marker) in folded for marker in markers), (
        f"{context} is missing one of: {', '.join(markers)}"
    )


def _contains_in_order(text: str, markers: tuple[str, ...]) -> bool:
    folded = _fold(text)
    cursor = 0
    for marker in markers:
        position = folded.find(_fold(marker), cursor)
        if position < 0:
            return False
        cursor = position + len(_fold(marker))
    return True


def test_contract_test_uses_local_reads_without_network_or_writes():
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".", 1)[0])

    forbidden_modules = {
        "aiohttp",
        "asyncpg",
        "ftplib",
        "httpx",
        "psycopg",
        "requests",
        "socket",
        "subprocess",
        "telnetlib",
        "urllib",
    }
    assert imported_modules.isdisjoint(forbidden_modules)

    forbidden_calls = {
        "connect",
        "create_connection",
        "chmod",
        "hardlink_to",
        "mkdir",
        "open",
        "patch",
        "rename",
        "replace",
        "request",
        "rmdir",
        "symlink_to",
        "touch",
        "urlopen",
        "unlink",
        "write_text",
        "write_bytes",
    }
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls.isdisjoint(forbidden_calls)


def test_integration_plan_has_the_eight_contractual_sections_and_date():
    plan = _read_plan()
    for section_title in REQUIRED_SECTIONS:
        _section(plan, section_title)

    folded = _fold(plan)
    for marker in ("2026-07-29", "etat observe", "cible", "preuves restant"):
        assert marker in folded, f"The dated audit is missing: {marker}"


def test_each_logical_component_has_all_inventory_fields_in_its_own_entry():
    inventory = _section(_read_plan(), "Inventaire vérifié")
    blocks = _entry_blocks(inventory, REQUIRED_COMPONENTS)

    field_markers = (
        ("fichiers ou répertoires", "fichiers", "répertoires", "chemins observés"),
        ("état", "status"),
        ("responsabilité",),
        ("source de données", "sources de données", "source officielle"),
        ("dépendances",),
        ("port / route / interface", "port", "route", "interface publique"),
        ("preuve",),
        ("écart",),
    )
    for component, block in blocks.items():
        for markers in field_markers:
            _assert_any_marker(block, markers, f"{component} inventory field")
        assert re.search(r"\b(implemente|partiel|absent)\b", _fold(block)), (
            f"{component} is missing an explicit implementation status"
        )


def test_integration_plan_describes_both_fixed_flows_and_public_contracts():
    contracts = _section(_read_plan(), "Contrats et flux d’intégration")
    assert _contains_in_order(
        contracts,
        (
            "Backoffice UI",
            "REST",
            "JWT Bearer",
            "Backoffice Flask",
            "PostgreSQL",
            "External Product API",
        ),
    ), "The Backoffice UI flow is not described in its contractual order"
    assert _contains_in_order(
        contracts,
        (
            "Client Web anonyme",
            "POST /questions",
            "AI Query Service",
            "Product MCP",
            "External Product API",
            "Stock MCP",
            "PostgreSQL",
        ),
    ), "The public AI flow is not described in its contractual order"

    for marker in (
        "lecture seule",
        "GET /health",
        "matrice de compatibilité",
        "authentification",
        "utilisateurs",
        "succursales",
        "produits",
        "stocks",
        "statuts métier",
        "enveloppes MCP",
        "list_products",
        "get_product_details",
        "list_branch_stock",
        "get_stock_for_product",
        "find_branches_with_stock",
        "find_branches_for_shopping_list",
    ):
        assert _fold(marker) in _fold(contracts), f"Missing public contract marker: {marker}"


def test_compatibility_matrix_covers_sections_three_to_twelve_and_ownership():
    contracts = _section(_read_plan(), "Contrats et flux d’intégration")
    matrix_lines = contracts.splitlines()
    matrix_start = next(
        index
        for index, line in enumerate(matrix_lines)
        if "matrice de compatibilite" in _fold(line)
    )
    matrix = "\n".join(matrix_lines[matrix_start:])
    for section_number in range(3, 13):
        row_exists = any(
            re.search(
                rf"(?:^|\|)\s*(?:section\s*)?(?:§\s*)?{section_number}(?:\s*\||\s*[-—:.])",
                line,
                flags=re.IGNORECASE,
            )
            for line in matrix.splitlines()
        )
        assert row_exists, f"Compatibility matrix lacks contract section {section_number}"

    for marker in ("compatibilité", "manque", "tâche propriétaire"):
        assert _fold(marker) in _fold(matrix), f"Matrix lacks column/field: {marker}"


def test_integration_plan_registers_mandatory_gaps_and_existing_proof_risks():
    gaps = _section(_read_plan(), "Écarts, risques et dépendances")
    folded = _fold(gaps)
    required_markers = (
        "docker-compose.yml",
        "backoffice-api",
        "backoffice-ui",
        "client-web",
        "client_web/app.js",
        "ai_service/",
        "post /questions",
        "/health",
        "crud administrateur",
        "readme.md",
        ".env.example",
        "seed/",
        "integration_tests/test_person3_assets.py",
        "conflit de collecte",
        "test_product_mcp_server.py",
        "test_stock_mcp_repository.py",
        "stock_mcp_server/requirements.txt",
        "sdk mcp",
        "risque",
    )
    missing = [marker for marker in required_markers if _fold(marker) not in folded]
    assert not missing, f"Missing audit gap or risk: {', '.join(missing)}"

    assert re.search(r"backoffice-api.{0,100}backoffice-ui.{0,100}client-web", folded)
    assert re.search(r"client_web/app\.js.{0,180}post /questions", folded)
    assert re.search(r"ai_service/.{0,220}(?:post /questions|/health)", folded)

    risk_lines = gaps.splitlines()
    for risk_markers, label in (
        (("conflit de collecte", "test_product_mcp_server.py"), "pytest collection conflict"),
        (("test_stock_mcp_repository.py", "stock_mcp_server/requirements.txt"), "Stock manifest mismatch"),
    ):
        matching_contexts = []
        for index, line in enumerate(risk_lines):
            folded_line = _fold(line)
            if _fold(risk_markers[0]) in folded_line:
                context_start = max(0, index - 3)
                context_end = min(len(risk_lines), index + 4)
                context = _fold("\n".join(risk_lines[context_start:context_end]))
                if all(_fold(marker) in context for marker in risk_markers):
                    matching_contexts.append(context)
        assert matching_contexts, f"{label} must have a dedicated gap/risk entry"
        assert any(
            re.search(r"existant|existante|deja present|deja presentes", context)
            and re.search(
                r"hors (?:la )?correction|hors perimetre|ne les? corrige|p3-t01 ne",
                context,
            )
            for context in matching_contexts
        ), f"{label} must be classified as existing and outside P3-T01 correction"


def test_each_future_task_has_its_own_ordered_plan_and_non_destructive_fallback():
    plan_section = _section(_read_plan(), "Plan d’intégration P3-T02 à P3-T06")
    lines = plan_section.splitlines()
    task_anchors: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        folded_line = _fold(line).strip()
        entry_start = re.sub(r"^(?:#+\s+|[-*+]\s+|\d+[.)]\s+)", "", folded_line)
        entry_start = entry_start.lstrip("*`").strip()
        match = re.match(r"(P3-T0[2-6])(?:\b|\s)", entry_start.upper())
        if match:
            task_anchors.append((index, match.group(1)))

    assert [task for _, task in task_anchors] == list(PLAN_TASKS)

    for position, (start, task) in enumerate(task_anchors):
        end = task_anchors[position + 1][0] if position + 1 < len(task_anchors) else len(lines)
        task_plan = _fold("\n".join(lines[start + 1 : end]))
        for field in (
            "ecarts",
            "prerequis",
            "livrables",
            "criteres d'entree",
            "criteres de sortie",
            "preuves",
            "repli",
        ):
            assert field in task_plan, f"{task} lacks planning field: {field}"
        assert (
            "non destructif" in task_plan
            or "sans restauration destructive" in task_plan
            or "sans suppression" in task_plan
        ), f"{task} lacks a non-destructive fallback"


def test_integration_plan_preserves_negative_security_data_and_testing_invariants():
    plan = _fold(_read_plan())
    positive_markers = (
        "source officielle",
        "stock ne devient jamais negatif",
        "branche",
        "common user",
        "lecture seule",
        "reponses fondees sur les donnees",
        "cors public restrictif",
        "textcontent",
        "aucun secret",
        "sans reseau reel",
    )
    missing = [marker for marker in positive_markers if marker not in plan]
    assert not missing, f"Missing invariant or protection: {', '.join(missing)}"

    assert re.search(r"aucun.{0,100}(?:detail|donnee).{0,100}persist", plan)
    assert re.search(r"mcp.{0,180}(?:lecture seule|sans ecriture|aucune ecriture)", plan)
    assert re.search(r"ia.{0,180}(?:lecture seule|sans ecriture|aucune ecriture)", plan)
    assert re.search(r"common user.{0,180}(?:branche|backend|serveur)", plan)

    missing_paths = [path for path in PROTECTED_PATHS if path not in plan]
    assert not missing_paths, (
        "The plan must preserve every protected Product MCP path: "
        + ", ".join(missing_paths)
    )


def test_integration_plan_cites_audited_sources_and_local_proofs():
    sources = _section(_read_plan(), "Sources")
    required_sources = (
        ".codex/person3/PROJECT_REFERENCE.md",
        ".codex/person3/TASK_STATE.md",
        ".codex/person2/PROJECT_REFERENCE.md",
        ".codex/person2/TASK_STATE.md",
        "docs/person3_handoff.md",
        "docs/project_context.md",
        "docs/architecture.md",
        "docs/api_contracts.md",
        "docs/security_rules.md",
        "docs/testing_strategy.md",
        "docs/interface_client_web.md",
        "docker-compose.yml",
        "backoffice/static/",
        "client_web/",
        "ai_service/",
        "product_mcp_server/",
        "stock_mcp_server/",
        "integration_tests/test_person3_assets.py",
    )
    missing = [source for source in required_sources if _fold(source) not in _fold(sources)]
    assert not missing, f"Missing documentary citation: {', '.join(missing)}"


def test_proof_strategy_separates_duplicate_pytest_modules_and_defers_docker():
    strategy = _fold(_section(_read_plan(), "Stratégie de preuve"))
    for marker in (
        "integration_tests/test_person3_integration_plan.py",
        "integration_tests/test_person3_assets.py",
        "tests/test_product_mcp_tools.py",
        "tests/test_product_mcp_server.py",
        "integration_tests/test_product_mcp_server.py",
        "tests/test_ai_classifier.py",
        "tests/test_ai_generator.py",
        "tests/test_ai_mcp_client.py",
        "integration_tests/test_stock_mcp_server.py",
        "processus pytest séparés",
        "p3-t04",
        "p3-t05",
        "docker",
        "sans réseau réel",
    ):
        assert _fold(marker) in strategy, f"Missing proof-strategy marker: {marker}"
