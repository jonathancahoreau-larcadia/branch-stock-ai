# Interface client web

## Périmètre

Ce document décrit les routes HTTP déjà définies dans les contrats officiels du projet HBntory. Il sert de référence aux interfaces clientes qui doivent communiquer avec l'application sans ajouter de nouvelle règle métier.

La présence d'une route dans ce document signifie uniquement qu'elle est déclarée dans `docs/api_contracts.md`. Ce document ne crée aucune route et ne modifie aucun comportement du backoffice.

## Routes disponibles

| Méthode | Route | Utilisation |
|---|---|---|
| POST | `/api/v1/auth/login` | Envoyer une demande de création ou d'action selon le contrat API existant. |
| POST | `/api/v1/auth/logout` | Envoyer une demande de création ou d'action selon le contrat API existant. |
| POST | `/api/v1/auth/logout/refresh` | Envoyer une demande de création ou d'action selon le contrat API existant. |
| GET | `/api/v1/auth/me` | Consulter une ressource selon le contrat API existant. |
| POST | `/api/v1/auth/refresh` | Envoyer une demande de création ou d'action selon le contrat API existant. |
| GET | `/api/v1/branches` | Consulter une ressource selon le contrat API existant. |
| GET | `/api/v1/branches/{branch_id}` | Consulter une ressource selon le contrat API existant. |
| GET | `/api/v1/products` | Consulter une ressource selon le contrat API existant. |
| GET | `/api/v1/products/{external_product_id}` | Consulter une ressource selon le contrat API existant. |
| GET | `/api/v1/stocks/{external_product_id}` | Consulter une ressource selon le contrat API existant. |
| POST | `/api/v1/stocks/{external_product_id}/add` | Envoyer une demande de création ou d'action selon le contrat API existant. |
| POST | `/api/v1/stocks/{external_product_id}/remove` | Envoyer une demande de création ou d'action selon le contrat API existant. |
| GET | `/api/v1/stocks?available_only=true` | Consulter une ressource selon le contrat API existant. |
| POST | `/api/v1/users` | Envoyer une demande de création ou d'action selon le contrat API existant. |
| GET | `/api/v1/users/{user_id}` | Consulter une ressource selon le contrat API existant. |
| PATCH | `/api/v1/users/{user_id}` | Mettre à jour partiellement une ressource selon le contrat API existant. |
| DELETE | `/api/v1/users/{user_id}` | Demander la suppression prévue par le contrat API existant. |
| PATCH | `/api/v1/users/{user_id}/password` | Mettre à jour partiellement une ressource selon le contrat API existant. |
| GET | `/api/v1/users?status=active&branch_id=2` | Consulter une ressource selon le contrat API existant. |
| GET | `/health` | Consulter une ressource selon le contrat API existant. |

## Règles d'utilisation

- L'interface cliente doit respecter les méthodes HTTP et les chemins déclarés dans les contrats.
- Les formats de requête, les réponses, les droits d'accès et les codes d'erreur restent définis par `docs/api_contracts.md`.
- Une interface ne doit pas supposer qu'une route non présente dans les contrats est disponible.
- Les règles de sécurité et d'autorisation restent appliquées par le backoffice.

## Limites actuelles

- Ce document reflète uniquement l'état décrit par la documentation officielle disponible.
- Il ne constitue pas une preuve qu'une interface graphique complète est déjà implémentée.
- Il ne remplace ni les contrats API détaillés, ni la stratégie de tests, ni les règles de sécurité.
- Toute évolution des contrats devra être reportée dans ce document après validation du projet.

## Sources

- `docs/api_contracts.md`
- `docs/project_context.md`
- `docs/architecture.md`
- `docs/testing_strategy.md`
