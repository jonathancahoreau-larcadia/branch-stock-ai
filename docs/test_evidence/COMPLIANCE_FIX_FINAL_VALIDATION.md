# Validation finale de conformité — correction historique

Date UTC de collecte : `2026-07-30`

Toutes les commandes ci-dessous ont été exécutées localement sans réseau réel,
sans daemon Docker, sans pull d’image, sans volume et sans secret recopié.

## Preuves de tests

| Groupe | Commande | Code retour | Sortie utile |
|---:|---|---:|---|
| 1 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider integration_tests/test_person3_documentation.py` | 0 | `8 passed` |
| 2 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider integration_tests/test_person3_end_to_end.py` | 0 | `15 passed` |
| 3 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider integration_tests/test_backoffice_ui.py integration_tests/test_client_web_ui.py integration_tests/test_person3_assets.py integration_tests/test_person3_docker.py integration_tests/test_person3_integration_plan.py` | 0 | `67 passed` |
| 4 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider backoffice/tests/test_auth_routes.py backoffice/tests/test_users_routes.py backoffice/tests/test_branches_routes.py backoffice/tests/test_products_routes.py backoffice/tests/test_stocks_routes.py backoffice/tests/test_health.py` | 0 | `87 passed` |
| 5 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ai_classifier.py tests/test_ai_generator.py tests/test_ai_ollama_client.py tests/test_ai_question_service.py tests/test_ai_server.py tests/test_ai_mcp_client.py` | 0 | `486 passed` |
| 6 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_product_mcp_tools.py tests/test_product_mcp_server.py` | 0 | `65 passed` |
| 7 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider integration_tests/test_product_mcp_server.py` | 0 | `14 passed` |
| 8 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_stock_mcp_repository.py tests/test_stock_mcp_tools.py tests/test_stock_mcp_server.py` | 0 | `129 passed, 1 warning` |
| 9 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider integration_tests/test_stock_mcp_server.py` | 0 | `26 passed` |

Suite complète :

```text
.venv/bin/python -m pytest -q --import-mode=importlib --tb=no
code retour 0 — 1119 passed, 42 skipped, 1 warning
```

Contrôles statiques :

```text
.venv/bin/python -m py_compile [tests ciblés]
code retour 0

git diff --check
code retour 0
```

## Compose et limites

```text
docker compose config --quiet
code retour 1 — variables runtime obligatoires absentes (POSTGRES_DB)

docker compose --env-file .env.example config --quiet
code retour 0
```

La seconde commande valide uniquement la configuration statique avec les
valeurs d’exemple. Aucun `docker compose up`, build, pull, daemon, volume ou
service réseau n’a été lancé.

Les tests JavaScript du groupe 3 utilisent Node et des doubles DOM/fetch
locaux ; aucun navigateur réel n’a été démarré. La preuve runtime HTTP Docker
et la démonstration navigateur restent des vérifications manuelles distinctes
et ne sont pas revendiquées par ce rapport.
