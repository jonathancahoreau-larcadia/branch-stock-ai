#!/usr/bin/env python3
"""Vérifie si les documents de référence Personne 2 ont changé."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".codex/person2/DOC_HASHES.json"
DOCUMENTS = [
    "docs/project_context.md",
    "docs/architecture.md",
    "docs/api_contracts.md",
    "docs/security_rules.md",
    "docs/testing_strategy.md",
    "docs/compliance_matrix.md",
    "docs/database_schema.md",
    "docs/presentation_plan.md",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_hashes() -> dict[str, str | None]:
    return {
        relative: (
            digest(ROOT / relative)
            if (ROOT / relative).is_file()
            else None
        )
        for relative in DOCUMENTS
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    current = current_hashes()

    if args.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(
            json.dumps(current, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Empreintes enregistrées : {STATE}")
        return 0

    if not STATE.is_file():
        print("NO_BASELINE: lance --write après la synthèse initiale.")
        return 3

    baseline = json.loads(STATE.read_text(encoding="utf-8"))
    changed = []

    for relative in DOCUMENTS:
        old = baseline.get(relative)
        new = current.get(relative)
        status = "UNCHANGED" if old == new else "CHANGED"
        print(f"{status:9} {relative}")
        if old != new:
            changed.append(relative)

    if changed:
        print("Relire uniquement les documents CHANGED et mettre à jour la référence.")
        return 2

    print("Tous les documents sont inchangés : aucune relecture complète requise.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
