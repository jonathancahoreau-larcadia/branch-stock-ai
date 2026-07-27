#!/usr/bin/env python3
"""Pilote Codex séquentiel pour reprendre P2-T02."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd().resolve()
CURRENT = ROOT / ".codex" / "person2" / "current"
RUN_DIR = ROOT / ".codex" / "person2" / "runs" / (
    "P2-T02-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
)

MANIFEST = ROOT / "product_mcp_server" / "requirements.txt"
MANIFEST_TEXT = "httpx>=0.27,<1.0\nmcp>=1.27,<2\n"

ROLES = {
    "thomas": ("gpt-5.6-luna", ".codex/agents/thomas.toml"),
    "remi": ("gpt-5.6-terra", ".codex/agents/remi.toml"),
    "sam": ("gpt-5.6-sol", ".codex/agents/sam.toml"),
}


class StopPilot(RuntimeError):
    pass


def header(text: str) -> None:
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72, flush=True)


def preflight() -> None:
    required = [
        ROOT / "AGENTS.md",
        ROOT / ".codex/agents/sam.toml",
        ROOT / ".codex/agents/remi.toml",
        ROOT / ".codex/agents/thomas.toml",
        ROOT / ".codex/person2/PROJECT_REFERENCE.md",
        ROOT / ".codex/person2/TASK_STATE.md",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise StopPilot(
            "Lance le pilote depuis la racine branch-stock-ai.\n"
            "Fichiers absents :\n- " + "\n- ".join(missing)
        )

    if subprocess.run(
        ["bash", "-lc", "command -v codex >/dev/null"],
        cwd=ROOT,
        check=False,
    ).returncode != 0:
        raise StopPilot("La commande codex est introuvable.")

    CURRENT.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    if not MANIFEST.exists():
        MANIFEST.write_text(MANIFEST_TEXT, encoding="utf-8")
        print("Créé : product_mcp_server/requirements.txt")
    elif MANIFEST.read_text(encoding="utf-8") != MANIFEST_TEXT:
        raise StopPilot(
            "product_mcp_server/requirements.txt existe mais ne correspond pas "
            "au contenu approuvé. Le pilote ne l'écrase pas."
        )


def run_role(role: str, sandbox: str, log_name: str, mission: str) -> str:
    model, role_file = ROLES[role]
    prompt = f"""
Tu travailles dans le rôle de {role.upper()}.

Lis et respecte :
- {role_file}
- AGENTS.md
- .codex/person2/PROJECT_REFERENCE.md
- .codex/person2/TASK_STATE.md

Règles absolues :
- ne lance aucun sous-agent ;
- aucune installation et aucune nouvelle dépendance ;
- aucun commit et aucun push ;
- aucune commande Git destructive ;
- ne commence pas P2-T03 ;
- ne modifie que les fichiers autorisés dans la mission.

MISSION
{mission.strip()}
""".strip() + "\n"

    command = [
        "codex",
        "-m", model,
        "-c", 'model_reasoning_effort="high"',
        "-c", "agents.enabled=false",
        "-s", sandbox,
        "exec", "--ephemeral", "-",
    ]

    log_path = RUN_DIR / log_name
    header(f"{role.upper()} — {model} — {sandbox}")
    print(f"Journal : {log_path.relative_to(ROOT)}\n")

    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdin is not None
        assert process.stdout is not None

        process.stdin.write(prompt)
        process.stdin.close()

        lines: list[str] = []
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
            lines.append(line)

        code = process.wait()

    output = "".join(lines)
    if code != 0:
        raise StopPilot(
            f"{role.upper()} s'est arrêté avec le code {code}. "
            f"Consulte {log_path.relative_to(ROOT)}"
        )
    if "HUMAN_APPROVAL_REQUIRED:" in output:
        raise StopPilot(
            f"{role.upper()} demande une autorisation humaine. "
            f"Consulte {log_path.relative_to(ROOT)}"
        )
    return output


def require(output: str, marker: str, stage: str) -> None:
    if marker not in output:
        raise StopPilot(f"{stage} n'a pas produit le marqueur : {marker}")


def thomas_tests(round_no: int) -> str:
    feedback = ""
    if (CURRENT / "TEST_REVIEW.md").exists():
        feedback = """
Lis aussi .codex/person2/current/TEST_REVIEW.md et corrige uniquement
les points refusés par Rémi.
"""
    return run_role(
        "thomas",
        "workspace-write",
        f"01-thomas-tests-{round_no}.log",
        f"""
P2-T01 est déjà validée avec 10 tests réussis.
Le contrat P2-T02 a déjà été approuvé par Rémi.

Contrat :
- product_mcp_server/server.py expose un serveur MCP ;
- exactement list_products et get_product_details sont enregistrés ;
- les appels HTTP restent dans product_api.py ;
- la logique métier reste dans tools.py ;
- server.py ne dépend directement ni de requests ni de httpx ;
- aucun réseau réel dans les tests.

Tu peux uniquement créer ou modifier :
- .codex/person2/current/TEST_PLAN.md
- integration_tests/test_product_mcp_server.py

Ne modifie aucun fichier d'implémentation.
{feedback}

Termine exactement par :
RESULT: THOMAS_TESTS_READY
""",
    )


def remi_tests(round_no: int) -> str:
    return run_role(
        "remi",
        "workspace-write",
        f"02-remi-tests-{round_no}.log",
        """
Examine :
- .codex/person2/current/TEST_PLAN.md
- integration_tests/test_product_mcp_server.py
- les fichiers P2-T02 existants dans product_mcp_server/

Ne modifie ni les tests ni le code.
Écris uniquement .codex/person2/current/TEST_REVIEW.md.

Approuve seulement si les tests vérifient le contrat public sans imposer
requests, httpx, une architecture interne arbitraire ou un réseau réel.

Termine exactement par l'une de ces lignes :
DECISION_TESTS: APPROUVE
DECISION_TESTS: REFUSE
""",
    )


def sam_code(round_no: int, after_validation: bool = False) -> str:
    extra = ""
    if after_validation:
        extra = """
Lis aussi .codex/person2/current/VALIDATION_REPORT.md et corrige uniquement
la cause démontrée par Thomas.
"""
    elif (CURRENT / "COMPLIANCE_REVIEW.md").exists():
        extra = """
Lis aussi .codex/person2/current/COMPLIANCE_REVIEW.md et corrige uniquement
les non-conformités signalées par Rémi.
"""
    return run_role(
        "sam",
        "workspace-write",
        f"03-sam-code-{round_no}.log",
        f"""
Implémente uniquement P2-T02 à partir des tests approuvés.

Lis :
- .codex/person2/current/TEST_PLAN.md
- .codex/person2/current/TEST_REVIEW.md
- integration_tests/test_product_mcp_server.py

Contraintes :
- server.py expose le serveur MCP ;
- exactement list_products et get_product_details sont enregistrés ;
- server.py délègue à tools.py ;
- les appels HTTP restent dans product_api.py ;
- aucune dépendance directe à requests ou httpx dans server.py ;
- ne modifie jamais les tests.

Tu peux uniquement modifier :
- product_mcp_server/server.py
- product_mcp_server/__init__.py si strictement nécessaire
- .codex/person2/current/IMPLEMENTATION_REPORT.md

{extra}

Termine exactement par :
RESULT: SAM_IMPLEMENTATION_DONE
""",
    )


def remi_code(round_no: int) -> str:
    return run_role(
        "remi",
        "workspace-write",
        f"04-remi-code-{round_no}.log",
        """
Examine l'implémentation P2-T02, les tests approuvés et :
- .codex/person2/current/IMPLEMENTATION_REPORT.md
- product_mcp_server/server.py
- product_mcp_server/__init__.py s'il existe
- product_mcp_server/tools.py
- product_mcp_server/product_api.py
- integration_tests/test_product_mcp_server.py

Ne modifie ni le code ni les tests.
Écris uniquement .codex/person2/current/COMPLIANCE_REVIEW.md.

Termine exactement par l'une de ces lignes :
DECISION_CODE: APPROUVE
DECISION_CODE: REFUSE
""",
    )


def thomas_final(round_no: int) -> str:
    return run_role(
        "thomas",
        "workspace-write",
        f"05-thomas-final-{round_no}.log",
        """
Effectue la validation finale réelle de P2-T02.

Lis les plans, avis, rapports et fichiers concernés.
Exécute les commandes de test approuvées sans installer de dépendance.
N'utilise aucun réseau réel.
Ne corrige jamais le code ni les tests.

Écris uniquement .codex/person2/current/VALIDATION_REPORT.md avec :
- commandes ;
- codes retour ;
- sorties utiles ;
- décision motivée.

Termine exactement par l'une de ces lignes :
FINAL_DECISION: VALIDE
FINAL_DECISION: REFUSE
FINAL_DECISION: BLOQUE_DEPENDANCES
""",
    )


def summary(status: str, detail: str) -> None:
    (RUN_DIR / "PILOT_SUMMARY.txt").write_text(
        f"STATUS: {status}\nTASK: P2-T02\nDETAIL: {detail}\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        header("PILOTE AUTOMATIQUE CODEX — P2-T02")
        preflight()

        tests_ok = False
        for round_no in range(1, 4):
            out = thomas_tests(round_no)
            require(out, "RESULT: THOMAS_TESTS_READY", "Thomas/tests")

            out = remi_tests(round_no)
            if "DECISION_TESTS: APPROUVE" in out:
                tests_ok = True
                break
            if "DECISION_TESTS: REFUSE" not in out:
                raise StopPilot("Décision de Rémi sur les tests introuvable.")

        if not tests_ok:
            raise StopPilot("Tests refusés après 3 tours.")

        code_ok = False
        last_code_round = 0
        for round_no in range(1, 4):
            last_code_round = round_no
            out = sam_code(round_no)
            require(out, "RESULT: SAM_IMPLEMENTATION_DONE", "Sam/code")

            out = remi_code(round_no)
            if "DECISION_CODE: APPROUVE" in out:
                code_ok = True
                break
            if "DECISION_CODE: REFUSE" not in out:
                raise StopPilot("Décision de Rémi sur le code introuvable.")

        if not code_ok:
            raise StopPilot("Code refusé après 3 tours.")

        for final_round in range(1, 4):
            out = thomas_final(final_round)

            if "FINAL_DECISION: VALIDE" in out:
                summary("VALIDE", "P2-T02 validée par Thomas.")
                header("P2-T02 VALIDÉE")
                print(f"Rapports : {RUN_DIR.relative_to(ROOT)}")
                return 0

            if "FINAL_DECISION: BLOQUE_DEPENDANCES" in out:
                summary("BLOQUE_DEPENDANCES", "Installation requise.")
                raise StopPilot(
                    "Thomas a identifié un blocage de dépendances. "
                    "Aucune installation n'a été lancée. Consulte "
                    ".codex/person2/current/VALIDATION_REPORT.md"
                )

            if "FINAL_DECISION: REFUSE" not in out:
                raise StopPilot("Décision finale de Thomas introuvable.")

            if final_round == 3:
                break

            out = sam_code(last_code_round + final_round, after_validation=True)
            require(out, "RESULT: SAM_IMPLEMENTATION_DONE", "Sam/correction")

            out = remi_code(last_code_round + final_round)
            if "DECISION_CODE: APPROUVE" not in out:
                raise StopPilot("Rémi refuse la correction après validation.")

        raise StopPilot("P2-T02 reste non validée après 3 validations finales.")

    except KeyboardInterrupt:
        summary("INTERROMPU", "Arrêt au clavier.")
        print("\nPilote interrompu. Aucun retour arrière automatique.")
        return 130
    except StopPilot as exc:
        summary("ARRETE", str(exc).replace("\n", " | "))
        header("PILOTE ARRÊTÉ DE MANIÈRE CONTRÔLÉE")
        print(exc)
        print(f"\nJournaux : {RUN_DIR.relative_to(ROOT)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
