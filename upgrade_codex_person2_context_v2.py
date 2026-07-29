#!/usr/bin/env python3
"""Optimise le contexte documentaire des agents Codex Personne 2."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

MANAGED_FILES = json.loads('{".codex/person2/CONTEXT_POLICY.md": "# Politique de contexte — Personne 2\\n\\nCette politique réduit les relectures et la consommation de contexte sans\\nsacrifier la conformité documentaire.\\n\\n## Amorçage unique\\n\\nLors de la première session Codex suivant l’installation :\\n\\n1. Lire une fois les documents Personne 2 existants.\\n2. Remplir `PROJECT_REFERENCE.md` avec les décisions stables, les interfaces,\\n   les contraintes et les commandes utiles.\\n3. Exécuter `python .codex/person2/check_docs.py --write`.\\n4. Ne commencer P2-T02 qu’après cette synthèse.\\n\\n## Début de chaque tâche\\n\\nLire uniquement :\\n\\n- `AGENTS.md` chargé automatiquement par Codex ;\\n- `PROJECT_REFERENCE.md` ;\\n- `TASK_STATE.md` ;\\n- le contrat et le handoff de la tâche courante ;\\n- les fichiers de production et de tests concernés.\\n\\nPuis lancer :\\n\\n```bash\\npython .codex/person2/check_docs.py --check\\n```\\n\\nQuand les documents sont inchangés, ne pas les relire intégralement.\\n\\n## Quand relire une source\\n\\nUne relecture ciblée est autorisée lorsque :\\n\\n- l’empreinte du document a changé ;\\n- le résumé ne contient pas la règle nécessaire ;\\n- deux sources semblent contradictoires ;\\n- Rémi doit vérifier une exigence exacte ;\\n- une erreur de test révèle une hypothèse non documentée.\\n\\nCommencer par rechercher le titre ou les mots-clés pertinents, puis lire\\nseulement la section correspondante. La lecture complète reste le dernier\\nrecours.\\n\\n## Handoffs entre agents\\n\\nLes agents échangent par fichiers courts plutôt qu’en recopiant les sources :\\n\\n- `.codex/person2/current/CONTRACT.md`\\n- `.codex/person2/current/TEST_PLAN.md`\\n- `.codex/person2/current/IMPLEMENTATION_REPORT.md`\\n- `.codex/person2/current/VALIDATION_REPORT.md`\\n\\nChaque handoff cite les chemins et sections sources utilisés.\\n", ".codex/person2/PROJECT_REFERENCE.md": "# Référence persistante — Personne 2\\n\\n> Cette synthèse est un index de travail. Les documents du dépôt restent les\\n> sources de vérité. Mettre à jour seulement les sections touchées lorsqu’une\\n> source change.\\n\\n## Documents sources\\n\\n| Document | Usage principal |\\n|---|---|\\n| `docs/project_context.md` | périmètre métier et règles Stock |\\n| `docs/architecture.md` | responsabilités et échanges entre services |\\n| `docs/api_contracts.md` | routes, entrées, sorties et erreurs |\\n| `docs/security_rules.md` | authentification, autorisations et secrets |\\n| `docs/testing_strategy.md` | niveaux et commandes de test |\\n| `docs/compliance_matrix.md` | correspondance exigences/preuves |\\n| `docs/database_schema.md` | tables et contraintes de données |\\n| `docs/presentation_plan.md` | présentation, non prioritaire pour le code |\\n\\n## Périmètre stable de Personne 2\\n\\n### Product MCP\\n\\nExpose exactement :\\n\\n- `list_products`\\n- `get_product_details`\\n\\nIl consulte l’API Produits externe. Il ne lit pas PostgreSQL.\\n\\n### Stock MCP\\n\\nExpose exactement :\\n\\n- `list_branch_stock`\\n- `get_stock_for_product`\\n- `find_branches_with_stock`\\n- `find_branches_for_shopping_list`\\n\\nIl utilise uniquement des requêtes `SELECT` paramétrées et ne consulte jamais\\nles utilisateurs, mots de passe, jetons ou tables privées.\\n\\n### AI Query Service\\n\\n- Classifie les questions.\\n- Appelle uniquement les outils MCP approuvés.\\n- Fonde ses réponses sur les données structurées reçues.\\n- N’invente aucun produit, branche, stock ou prix.\\n- N’accède pas directement à PostgreSQL.\\n\\n### API et Client Web publics\\n\\n- `POST /questions` est public.\\n- Aucune conversation n’est persistée.\\n- Le Client Web envoie des questions indépendantes.\\n- Aucun historique dans `localStorage` ou `sessionStorage`.\\n- Pas de `innerHTML` pour afficher les données reçues.\\n\\n## Dépendances et architecture\\n\\n- SDK MCP : paquet `mcp` avec la borne approuvée, pas un paquet `fastmcp`\\n  inventé séparément.\\n- La couche protocole `server.py` enregistre les outils.\\n- La logique métier reste dans `tools.py`.\\n- Les appels HTTP Produits restent dans `product_api.py`.\\n- Les tests d’une couche ne doivent pas imposer une bibliothèque interne à une\\n  autre couche.\\n\\n## Workflow et validation\\n\\nPour chaque tâche :\\n\\n1. contrat figé ;\\n2. tests écrits et approuvés avant le code ;\\n3. implémentation minimale ;\\n4. tests ciblés ;\\n5. conformité documentaire ;\\n6. validation finale avec sorties de commandes.\\n\\n## Points à compléter pendant l’amorçage\\n\\n- Commandes exactes par tâche :\\n- Variables d’environnement Personne 2 :\\n- Ports et services Docker :\\n- Formats de réponse et erreurs :\\n- Sections documentaires précises par tâche :\\n", ".codex/person2/TASK_STATE.md": "# État des tâches — Personne 2\\n\\nDernière mise à jour initiale : 2026-07-27.\\n\\n| Tâche | État | Preuve / prochaine action |\\n|---|---|---|\\n| P2-T01 | VALIDÉE | `tests/test_product_mcp_tools.py` : 10 tests réussis |\\n| P2-T02 | À REPRENDRE | serveur protocolaire Product MCP |\\n| P2-T03 | À FAIRE | requêtes Stock MCP en lecture seule |\\n| P2-T04 | À FAIRE | disponibilité et liste de courses |\\n| P2-T05 | À FAIRE | serveur Stock MCP et sécurité |\\n| P2-T06 | À FAIRE | classification et client MCP |\\n| P2-T07 | À FAIRE | génération fondée sur les données MCP |\\n| P2-T08 | À FAIRE | route publique `POST /questions` |\\n| P2-T09 | À FAIRE | Client Web public |\\n| P2-T10 | À FAIRE | services Docker Personne 2 |\\n| P2-T11 | À FAIRE | proxy et tests de bout en bout |\\n| P2-T12 | À FAIRE | documentation et preuves finales |\\n\\nAprès chaque validation de Thomas :\\n\\n1. passer la tâche à `VALIDÉE` ;\\n2. enregistrer les commandes et résultats essentiels ;\\n3. indiquer la prochaine tâche ;\\n4. mettre à jour uniquement la partie concernée de `PROJECT_REFERENCE.md`.\\n", ".codex/person2/current/README.md": "# Handoff de la tâche courante\\n\\nCes fichiers sont temporaires et doivent rester courts :\\n\\n- `CONTRACT.md` : contrat approuvé par Rémi ;\\n- `TEST_PLAN.md` : tests approuvés par Rémi ;\\n- `IMPLEMENTATION_REPORT.md` : fichiers modifiés et commandes de Sam ;\\n- `VALIDATION_REPORT.md` : preuves et décision de Thomas.\\n\\nNe recopier aucun document source complet dans ce dossier.\\n", ".codex/person2/LAUNCH_PROMPT.md": "# Prompt optimisé de lancement — Personne 2\\n\\n```text\\nRéalise les tâches restantes de Personne 2 avec les agents personnalisés sam,\\nremi et thomas, strictement de manière séquentielle.\\n\\nAvant toute chose :\\n1. lis AGENTS.md ;\\n2. lis .codex/person2/CONTEXT_POLICY.md ;\\n3. vérifie .codex/person2/PROJECT_REFERENCE.md et TASK_STATE.md ;\\n4. exécute python .codex/person2/check_docs.py --check.\\n\\nSi aucune empreinte documentaire n’existe encore, effectue une seule lecture\\ninitiale des documents Personne 2, complète PROJECT_REFERENCE.md, puis exécute\\npython .codex/person2/check_docs.py --write.\\n\\nSi les documents sont inchangés, ne les relis pas intégralement. Pour chaque\\ntâche, lis seulement la référence persistante, l’état, les handoffs et les\\nsections ou fichiers directement concernés.\\n\\nOrdre obligatoire :\\nSam propose le contrat -> Rémi valide le contrat -> Thomas écrit les tests ->\\nRémi valide les tests -> Sam implémente -> Rémi vérifie la conformité ->\\nThomas exécute la validation finale.\\n\\nNe lance jamais plusieurs de ces agents en parallèle sur la même tâche.\\nNe passe pas à la tâche suivante avant VALIDÉ de Thomas.\\nP2-T01 est déjà validée ; commence à P2-T02.\\n\\nAucun commit, aucun push et aucune installation de dépendance sans mon accord.\\n```\\n", ".codex/person2/check_docs.py": "#!/usr/bin/env python3\\n\\"\\"\\"Vérifie si les documents de référence Personne 2 ont changé.\\"\\"\\"\\n\\nfrom __future__ import annotations\\n\\nimport argparse\\nimport hashlib\\nimport json\\nfrom pathlib import Path\\n\\nROOT = Path(__file__).resolve().parents[2]\\nSTATE = ROOT / \\".codex/person2/DOC_HASHES.json\\"\\nDOCUMENTS = [\\n    \\"docs/project_context.md\\",\\n    \\"docs/architecture.md\\",\\n    \\"docs/api_contracts.md\\",\\n    \\"docs/security_rules.md\\",\\n    \\"docs/testing_strategy.md\\",\\n    \\"docs/compliance_matrix.md\\",\\n    \\"docs/database_schema.md\\",\\n    \\"docs/presentation_plan.md\\",\\n]\\n\\n\\ndef digest(path: Path) -> str:\\n    return hashlib.sha256(path.read_bytes()).hexdigest()\\n\\n\\ndef current_hashes() -> dict[str, str | None]:\\n    return {\\n        relative: (\\n            digest(ROOT / relative)\\n            if (ROOT / relative).is_file()\\n            else None\\n        )\\n        for relative in DOCUMENTS\\n    }\\n\\n\\ndef main() -> int:\\n    parser = argparse.ArgumentParser()\\n    parser.add_argument(\\"--write\\", action=\\"store_true\\")\\n    parser.add_argument(\\"--check\\", action=\\"store_true\\")\\n    args = parser.parse_args()\\n\\n    current = current_hashes()\\n\\n    if args.write:\\n        STATE.parent.mkdir(parents=True, exist_ok=True)\\n        STATE.write_text(\\n            json.dumps(current, indent=2) + \\"\\\\n\\",\\n            encoding=\\"utf-8\\",\\n        )\\n        print(f\\"Empreintes enregistrées : {STATE}\\")\\n        return 0\\n\\n    if not STATE.is_file():\\n        print(\\"NO_BASELINE: lance --write après la synthèse initiale.\\")\\n        return 3\\n\\n    baseline = json.loads(STATE.read_text(encoding=\\"utf-8\\"))\\n    changed = []\\n\\n    for relative in DOCUMENTS:\\n        old = baseline.get(relative)\\n        new = current.get(relative)\\n        status = \\"UNCHANGED\\" if old == new else \\"CHANGED\\"\\n        print(f\\"{status:9} {relative}\\")\\n        if old != new:\\n            changed.append(relative)\\n\\n    if changed:\\n        print(\\"Relire uniquement les documents CHANGED et mettre à jour la référence.\\")\\n        return 2\\n\\n    print(\\"Tous les documents sont inchangés : aucune relecture complète requise.\\")\\n    return 0\\n\\n\\nif __name__ == \\"__main__\\":\\n    raise SystemExit(main())\\n", ".codex/agents/sam.toml": "name = \\"sam\\"\\ndescription = \\"Architecte-développeur de Personne 2. Il définit un contrat exact puis implémente après validation.\\"\\n\\nmodel = \\"gpt-5.6-sol\\"\\nmodel_reasoning_effort = \\"high\\"\\nmodel_verbosity = \\"medium\\"\\nsandbox_mode = \\"workspace-write\\"\\n\\ndeveloper_instructions = \\"\\"\\"\\nTu es Sam, architecte-développeur de Personne 2.\\n\\nCONTEXTE\\nCommence par lire AGENTS.md, .codex/person2/PROJECT_REFERENCE.md,\\n.codex/person2/TASK_STATE.md et les handoffs courants. Ne relis jamais tous les\\ndocuments par défaut. Exécute check_docs.py --check ; si les empreintes sont\\ninchangées, lis seulement les sections sources indispensables à la tâche.\\n\\nTRAVAIL\\n1. Propose une petite séquence et un contrat exact.\\n2. Enregistre le contrat dans .codex/person2/current/CONTRACT.md.\\n3. Attends APPROUVÉ de Rémi.\\n4. Attends les tests de Thomas approuvés par Rémi.\\n5. Implémente un seul fichier ou une unité cohérente à la fois.\\n6. Exécute les tests ciblés après chaque modification.\\n7. Écris IMPLEMENTATION_REPORT.md avec fichiers, commandes et résultats.\\n\\nRÈGLES\\nRespecte strictement les symboles figés. Ne modifie jamais les tests. En cas\\nd’échec, corrige le plus petit nombre de fichiers de production. Réutilise les\\ncouches existantes. N’ajoute aucune dépendance sans accord humain. Utilise le\\npaquet mcp approuvé, jamais un paquet fastmcp séparé. Aucun secret, commit ou\\npush. Ne prétends jamais qu’un test a réussi sans l’avoir exécuté.\\n\\"\\"\\"\\n", ".codex/agents/remi.toml": "name = \\"remi\\"\\ndescription = \\"Réviseur read-only de Personne 2. Il valide les contrats, les tests, l’architecture et la conformité.\\"\\n\\nmodel = \\"gpt-5.6-terra\\"\\nmodel_reasoning_effort = \\"high\\"\\nmodel_verbosity = \\"medium\\"\\nsandbox_mode = \\"read-only\\"\\n\\ndeveloper_instructions = \\"\\"\\"\\nTu es Rémi, réviseur de Personne 2. Tu ne modifies aucun fichier.\\n\\nCONTEXTE\\nLis AGENTS.md, PROJECT_REFERENCE.md, TASK_STATE.md et le handoff à examiner.\\nNe relis une source complète que si son empreinte a changé, si la référence est\\ninsuffisante ou si une vérification exacte l’exige. Cherche d’abord la section\\npertinente.\\n\\nREVUE DU CONTRAT\\nVérifie périmètre, fichiers, symboles, signatures, erreurs, dépendances,\\nvariables d’environnement, architecture et critères de réussite. Réponds\\nAPPROUVÉ ou REFUSÉ avec des corrections précises.\\n\\nREVUE DES TESTS\\nVérifie que les tests couvrent le contrat public sans imposer un détail interne\\narbitraire, une bibliothèque non approuvée ou un appel réseau réel. Les tests\\ndoivent respecter la séparation server -> tools -> client/repository.\\n\\nREVUE FINALE\\nCompare l’implémentation au contrat, aux règles de sécurité et aux sections\\nsources citées. Une ambiguïté importante, une dépendance surprise ou une preuve\\nmanquante impose REFUSÉ. Aucun commit ni push.\\n\\"\\"\\"\\n", ".codex/agents/thomas.toml": "name = \\"thomas\\"\\ndescription = \\"Responsable des tests contractuels et des preuves finales de Personne 2.\\"\\n\\nmodel = \\"gpt-5.6-luna\\"\\nmodel_reasoning_effort = \\"high\\"\\nmodel_verbosity = \\"medium\\"\\nsandbox_mode = \\"workspace-write\\"\\n\\ndeveloper_instructions = \\"\\"\\"\\nTu es Thomas, responsable des tests de Personne 2.\\n\\nCONTEXTE\\nLis AGENTS.md, PROJECT_REFERENCE.md, le contrat approuvé et les fichiers ciblés.\\nNe relis pas tous les documents. Consulte uniquement testing_strategy.md et les\\nsections métier nécessaires lorsque le contrat ne suffit pas.\\n\\nAVANT LE CODE\\nÉcris uniquement les tests prévus dans TEST_PLAN.md. Vérifie les interfaces\\npubliques et comportements approuvés, pas un détail interne. Aucun réseau réel.\\nN’impose jamais requests, httpx ou une autre bibliothèque dans une couche qui\\nne doit pas la posséder. Utilise des tests pytest synchrones et asyncio.run pour\\nle code async sauf dépendance explicitement approuvée. Soumets les tests à Rémi.\\n\\nAPRÈS LE CODE\\nExécute les commandes approuvées. Enregistre commande, code retour et sortie\\nutile dans VALIDATION_REPORT.md. Réponds VALIDÉ uniquement si toutes les preuves\\nobligatoires existent et réussissent. Sinon indique la commande exacte, l’erreur\\ndéterminante et le fichier ou symbole probable. Ne corrige jamais le code de\\nproduction. Aucun commit, push ou ajout de dépendance.\\n\\"\\"\\"\\n"}')
MANAGED_BLOCK = '<!-- BEGIN CODEX PERSONNE 2 MANAGED BLOCK -->\n# Personne 2 — règles durables pour Codex\n\n## Point d’entrée documentaire\n\nAvant de lire les documents complets, consulte dans cet ordre :\n\n1. `.codex/person2/PROJECT_REFERENCE.md`\n2. `.codex/person2/TASK_STATE.md`\n3. `.codex/person2/CONTEXT_POLICY.md`\n4. le contrat, les tests ou le rapport de la tâche courante\n\nNe relis pas tous les documents du projet à chaque étape.\n\n## Politique de lecture\n\n- Au premier démarrage seulement, construis ou actualise\n  `.codex/person2/PROJECT_REFERENCE.md` à partir des documents sources.\n- En début de tâche, exécute :\n  `python .codex/person2/check_docs.py --check`.\n- Si les empreintes sont inchangées, utilise la référence persistante et lis\n  uniquement les sections sources directement liées à la tâche.\n- Relis un document complet seulement si son empreinte a changé, si la\n  référence ne permet pas de trancher, ou si Rémi demande une vérification\n  précise.\n- Ne copie pas les documents entiers dans les prompts des sous-agents.\n  Transmets plutôt les chemins, le contrat figé et les extraits nécessaires.\n- Après validation d’une tâche, mets à jour `TASK_STATE.md` et les éléments\n  concernés de `PROJECT_REFERENCE.md`, puis actualise les empreintes.\n\n## Workflow séquentiel obligatoire\n\nSam définit le contrat → Rémi valide le contrat → Thomas écrit les tests →\nRémi valide les tests → Sam implémente → Rémi vérifie la conformité →\nThomas exécute les preuves finales.\n\nUn seul agent travaille à la fois sur une tâche donnée.\n\n## Limites\n\n- Aucun commit ni push.\n- Aucune installation ou nouvelle dépendance sans accord humain explicite.\n- Ne modifie jamais les tests de Thomas pendant l’implémentation.\n- Ne déclare jamais une tâche réussie sans commandes réellement exécutées.\n<!-- END CODEX PERSONNE 2 MANAGED BLOCK -->\n'
BEGIN = "<!-- BEGIN CODEX PERSONNE 2 MANAGED BLOCK -->"
END = "<!-- END CODEX PERSONNE 2 MANAGED BLOCK -->"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        os.chmod(path, 0o644)
    finally:
        temp.unlink(missing_ok=True)


def update_agents_md(existing: str) -> str:
    if BEGIN in existing and END in existing:
        start = existing.index(BEGIN)
        finish = existing.index(END) + len(END)
        prefix = existing[:start].rstrip()
        suffix = existing[finish:].lstrip()
        parts = [part for part in (prefix, MANAGED_BLOCK.rstrip(), suffix) if part]
        return "\n\n".join(parts) + "\n"

    prefix = existing.rstrip()
    if prefix:
        return prefix + "\n\n" + MANAGED_BLOCK.rstrip() + "\n"
    return MANAGED_BLOCK.rstrip() + "\n"


def main() -> None:
    root = Path.cwd().resolve()
    if not (root / "backoffice").is_dir():
        raise RuntimeError(
            "Lance ce script depuis la racine de branch-stock-ai."
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = root / ".codex/backups" / f"{timestamp}-context-v2"
    backup_root.mkdir(parents=True, exist_ok=False)

    targets = ["AGENTS.md", *MANAGED_FILES.keys()]
    for relative in targets:
        target = root / relative
        if target.exists():
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)

    agents_path = root / "AGENTS.md"
    existing_agents = (
        agents_path.read_text(encoding="utf-8")
        if agents_path.is_file()
        else ""
    )
    atomic_write(agents_path, update_agents_md(existing_agents))

    for relative, content in MANAGED_FILES.items():
        atomic_write(root / relative, content)

    for relative in (
        ".codex/agents/sam.toml",
        ".codex/agents/remi.toml",
        ".codex/agents/thomas.toml",
    ):
        with (root / relative).open("rb") as handle:
            tomllib.load(handle)

    print("Optimisation documentaire Codex Personne 2 installée.")
    print(f"Sauvegarde : {backup_root}")
    print("AGENTS.md : règles chargées automatiquement.")
    print("PROJECT_REFERENCE.md : référence persistante.")
    print("TASK_STATE.md : progression persistante.")
    print("check_docs.py : détection des documents modifiés.")
    print("Aucun agent n'a été lancé.")
    print("Aucun fichier applicatif, commit ou push n'a été effectué.")
    print()
    print("Au premier lancement, utilise le prompt :")
    print(".codex/person2/LAUNCH_PROMPT.md")


if __name__ == "__main__":
    main()
