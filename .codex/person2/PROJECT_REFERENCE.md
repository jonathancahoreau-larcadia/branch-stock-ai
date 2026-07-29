# Référence persistante — Personne 2

> Cette synthèse est un index de travail. Les documents du dépôt restent les
> sources de vérité. Mettre à jour seulement les sections touchées lorsqu’une
> source change.

## Documents sources

| Document | Usage principal |
|---|---|
| `docs/project_context.md` | périmètre métier et règles Stock |
| `docs/architecture.md` | responsabilités et échanges entre services |
| `docs/api_contracts.md` | routes, entrées, sorties et erreurs |
| `docs/security_rules.md` | authentification, autorisations et secrets |
| `docs/testing_strategy.md` | niveaux et commandes de test |
| `docs/database_schema.md` | tables et contraintes de données |

`docs/compliance_matrix.md` et `docs/presentation_plan.md`, listés par le
script d'empreintes, sont absents du dépôt au 2026-07-27. Leur empreinte doit
donc rester `null` jusqu'à leur éventuelle création ; ils ne sont pas une
source disponible à relire.

## Périmètre stable de Personne 2

### Product MCP

Expose exactement :

- `list_products`
- `get_product_details`

Il consulte l’API Produits externe. Il ne lit pas PostgreSQL. Le contrat MCP
commun est toujours l'une des trois enveloppes :

```python
{"status": "success", "data": ...}
{"status": "not_found", "data": None}
{"status": "error", "error": {"code": str, "message": str}}
```

Les erreurs documentées pour les détails produit sont
`INVALID_EXTERNAL_PRODUCT_ID`, `PRODUCT_API_UNAVAILABLE`,
`PRODUCT_API_TIMEOUT` et `PRODUCT_API_INVALID_RESPONSE`.

### Stock MCP

Expose exactement :

- `list_branch_stock`
- `get_stock_for_product`
- `find_branches_with_stock`
- `find_branches_for_shopping_list`

Il utilise uniquement des requêtes `SELECT` paramétrées et ne consulte jamais
les utilisateurs, mots de passe, jetons ou tables privées.

### AI Query Service

- Classifie les questions.
- Appelle uniquement les outils MCP approuvés.
- Fonde ses réponses sur les données structurées reçues.
- N’invente aucun produit, branche, stock ou prix.
- N’accède pas directement à PostgreSQL.

### API et Client Web publics

- `POST /questions` est public.
- Aucune conversation n’est persistée.
- Le Client Web envoie des questions indépendantes.
- Aucun historique dans `localStorage` ou `sessionStorage`.
- Pas de `innerHTML` pour afficher les données reçues.

## Dépendances et architecture

- SDK MCP : paquet `mcp` avec la borne approuvée, pas un paquet `fastmcp`
  inventé séparément.
- La couche protocole `server.py` enregistre les outils.
- La logique métier reste dans `tools.py`.
- Les appels HTTP Produits restent dans `product_api.py`.
- Les tests d’une couche ne doivent pas imposer une bibliothèque interne à une
  autre couche.
- Le serveur protocolaire Product MCP est attendu dans
  `product_mcp_server/server.py`, mais ce fichier est absent à l'amorçage de
  P2-T02.
- Le SDK approuvé est le paquet `mcp` ; ni ce paquet ni `fastmcp` ne sont
  actuellement disponibles dans l'environnement, et aucun fichier de
  dépendances Personne 2 ne le déclare. L'ajout ou l'installation du SDK exige
  l'accord humain préalable.

## Configuration et frontières utiles

- `PRODUCT_API_BASE_URL` est obligatoire pour joindre l'API produit et doit
  être une URL HTTP(S) ; `PRODUCT_API_TIMEOUT` vaut 5 secondes par défaut.
- La cible d'architecture est `PRODUCT_MCP_URL=http://product_mcp_server:8100`.
- Les services obligatoires à terme sont `database`, `product_api`,
  `backoffice`, `product_mcp_server`, `stock_mcp_server`, `ai_service` et
  `client_web`. Le Compose actuel ne déclare pas encore les services Personne
  2 : ce point relève des tâches Docker ultérieures.
- Aucune donnée produit ne doit être persistée dans PostgreSQL. Les timeouts
  sont obligatoires, les réponses et logs ne doivent révéler aucun secret, et
  aucune donnée ne peut être inventée.

## Workflow et validation

Pour chaque tâche :

1. contrat figé ;
2. tests écrits et approuvés avant le code ;
3. implémentation minimale ;
4. tests ciblés ;
5. conformité documentaire ;
6. validation finale avec sorties de commandes.

Commande Python disponible dans cet environnement : `python3` (la commande
`python` est absente). Les tests existants utilisent `pytest` et
`asyncio.run`; une validation ciblée utilisera donc `python3 -m pytest ...`.

## État initial P2-T02

- P2-T01 reste validée et ses tests ne sont pas à refaire ni à modifier.
- P2-T02 est à reprendre : l'adaptateur et les deux outils existent dans le
  répertoire non suivi `product_mcp_server/`, mais aucun serveur MCP
  protocolaire n'est présent et aucun handoff n'a encore été créé.
- Les changements Git préexistants hors P2 (notamment `.gitignore` et
  `backoffice/tests/test_app.py`) sont à préserver.

## Sources P2-T02 directement concernées

- `docs/project_context.md`, sections 10–11 et 18 ;
- `docs/architecture.md`, sections 4.5, 15–18 et 21 ;
- `docs/api_contracts.md`, sections 9–10 et 12 ;
- `docs/security_rules.md`, sections 10–12 ;
- `docs/testing_strategy.md`, section 8.
