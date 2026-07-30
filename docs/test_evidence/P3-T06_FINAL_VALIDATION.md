# Validation finale automatisée — P3-T06

- Date UTC de collecte : `2026-07-30T17:13:42Z`
- Mode : neuf processus séparés, sans réseau réel.
- Expurgation : seules les synthèses pytest utiles sont conservées ; aucun
  secret, URI sensible, contenu de fichier runtime ou log brut n’est reproduit.

## Groupe 1 — documentation P3-T06

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_person3_documentation.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `8 passed`.

## Groupe 2 — flux intégrés en mémoire

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_person3_end_to_end.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `15 passed in 1.93s`.

## Groupe 3 — interfaces, actifs, Docker statique et plan

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_backoffice_ui.py integration_tests/test_client_web_ui.py integration_tests/test_person3_assets.py integration_tests/test_person3_docker.py integration_tests/test_person3_integration_plan.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `61 passed in 6.39s`.

## Groupe 4 — routes Backoffice

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider backoffice/tests/test_auth_routes.py backoffice/tests/test_users_routes.py backoffice/tests/test_branches_routes.py backoffice/tests/test_products_routes.py backoffice/tests/test_stocks_routes.py backoffice/tests/test_health.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `87 passed in 1.42s`.

## Groupe 5 — AI Query Service

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_ai_classifier.py tests/test_ai_generator.py tests/test_ai_ollama_client.py tests/test_ai_question_service.py tests/test_ai_server.py tests/test_ai_mcp_client.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `476 passed in 0.99s`.

## Groupe 6 — Product MCP unitaire

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_product_mcp_tools.py tests/test_product_mcp_server.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `52 passed in 0.64s`.

## Groupe 7 — Product MCP intégration

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_product_mcp_server.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `14 passed in 0.56s`.

## Groupe 8 — Stock MCP unitaire

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_stock_mcp_repository.py tests/test_stock_mcp_tools.py tests/test_stock_mcp_server.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `129 passed, 1 warning in 0.80s`.
- Avertissement expurgé : `RuntimeWarning` connu du garde d’exécution directe ;
  aucun réseau n’a été démarré.

## Groupe 9 — Stock MCP intégration

Commande :
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_stock_mcp_server.py`

- Code retour : 0.
- Sortie utile : synthèse expurgée, `26 passed in 0.71s`.

## Preuves distinctes et état des scénarios

La preuve runtime Docker Compose P3-T05 déjà validée reste référencée par
`person3_handoffs/runtime_proofs/P3-T05-runtime-command-results.json`. Elle
n’a pas été rejouée et n’est pas présentée comme un test pytest P3-T06.

Le transcript manuel est
`docs/test_evidence/P3-T06_PRODUCT_MCP_MANUAL.md`. Ses quatre scénarios sont
présents et conformes ; aucun scénario Product MCP absent ou non conforme n’a
été identifié.

La décision humaine en lecture seule
`person3_handoffs/current/HUMAN_APPROVAL.md`, code
`P3-T06_OWNER_FINAL_APPROVAL`, confirme la vérification personnelle du README
par le responsable unique et approuve la clôture de P3-T06. Elle déclare non
applicables à cette branche la répétition collective de trois responsables,
l’attestation collective et la demande de QA externe. Les champs historiques
de `docs/demo_plan.md` restent non renseignés afin de ne pas fabriquer une
répétition ou une demande qui n’a pas eu lieu.
