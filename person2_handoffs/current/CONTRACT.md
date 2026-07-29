# Contrat P2-T07 — génération fondée sur les données MCP

Statut : **PROPOSÉ — EN ATTENTE DE VALIDATION PAR RÉMI**

## Séquence obligatoire

1. Rémi valide le présent contrat.
2. Thomas crée uniquement `tests/test_ai_generator.py`.
3. Rémi valide les tests.
4. Sam crée uniquement `ai_service/generator.py`.
5. Rémi vérifie la conformité.
6. Thomas exécute et consigne les quatre commandes de preuve finales.

P2-T07 s'arrête à cette génération pure. P2-T08 et les tâches suivantes ne
commencent pas dans ce contrat.

## Objectif et frontière

Ajouter une couche déterministe qui transforme uniquement les données
structurées des outils MCP validés en une réponse métier :

- fondée sur les résultats MCP reçus ;
- traçable grâce à une projection des données MCP exploitées ;
- incapable d'inventer un produit, un détail, une branche, une quantité, une
  disponibilité ou un prix ;
- incapable de recalculer une disponibilité ou un plan de branches.

Cette tâche n'ajoute ni fournisseur IA externe, ni dépendance, ni réseau, ni
route Flask. Elle n'extrait pas d'arguments depuis la question et n'orchestre
aucun appel MCP.

## Chemins figés

Après approbation du contrat et des tests, Sam pourra seulement créer :

- `ai_service/generator.py`

Thomas pourra seulement créer :

- `tests/test_ai_generator.py`

`documentation_paths` est vide. Tous les autres chemins restent inchangés
pendant P2-T07. Cela inclut les huit chemins Product déclarés immuables, les
fichiers Stock validés, `ai_service/__init__.py`,
`ai_service/classifier.py`, `ai_service/mcp_client.py`,
`ai_service/requirements.txt`, leurs tests existants, `docs/`,
`docker-compose.yml`, `client_web/` et `backoffice/`.

## Interface publique

`ai_service.generator` réutilise et réexporte la constante publique déjà
validée de `ai_service.classifier`, puis expose exactement :

```python
SUPPORTED_QUESTION_TYPES: tuple[str, ...] = (
    "product_details",
    "product_availability",
    "branch_inventory",
    "shopping_list",
)

def generate_grounded_response(
    question_type: str,
    mcp_results: dict[str, dict[str, Any]],
) -> dict[str, Any]: ...
```

`question_type` accepte les quatre valeurs de
`SUPPORTED_QUESTION_TYPES` ou `"unsupported"`. Une autre valeur ou une valeur
non chaîne lève `ValueError`. `mcp_results` doit être un dictionnaire, sinon la
fonction lève `ValueError`.

Pour `"unsupported"`, `mcp_results` doit être vide ; sinon la fonction lève
`ValueError`. La réponse est exactement :

```json
{
  "status": "unsupported",
  "answer": "This question is outside the supported inventory scope.",
  "data": {
    "supported_question_types": [
      "product_details",
      "product_availability",
      "branch_inventory",
      "shopping_list"
    ]
  }
}
```

## Résultats MCP autorisés

Chaque famille autorise uniquement les clés suivantes, dans cet ordre :

| Famille | Résultats attendus |
|---|---|
| `product_details` | `get_product_details` |
| `product_availability` | `get_product_details`, `get_stock_for_product` |
| `branch_inventory` | `list_products`, `list_branch_stock` |
| `shopping_list` | `list_products`, `find_branches_for_shopping_list` |

Une clé inattendue ou non chaîne dans `mcp_results` lève `ValueError`. Un
résultat attendu peut être absent : il est alors indisponible.

Chaque valeur fournie doit être une enveloppe MCP. Seul le champ `data` d'une
enveloppe ayant `status == "success"` et respectant intégralement le schéma
ci-dessous est exploitable. Une enveloppe absente, `not_found`, `error`, non
dictionnaire ou mal formée est indisponible ; ni son erreur, ni ses champs
arbitraires ne sont repris dans la réponse.

Une chaîne « non vide » est une instance de `str` dont `strip()` n'est pas
vide. Un « entier » est une instance de `int` qui n'est pas une instance de
`bool`. Si un objet ou un élément d'une liste viole une contrainte, le résultat
complet de cet outil est indisponible.

## Schémas exploitables et projections

Une donnée exploitable est projetée vers les seuls champs énumérés ici. Les
champs supplémentaires de l'enveloppe, de `data` ou des objets imbriqués sont
tolérés en entrée mais toujours supprimés de `tool_results`.

### `get_product_details`

`data` est un dictionnaire avec :

- `external_product_id` : chaîne non vide ;
- `name` : chaîne non vide.

Projection exacte :

```json
{
  "external_product_id": "product-123",
  "name": "Example product"
}
```

### `list_products`

`data` est un dictionnaire avec `products`, une liste éventuellement vide.
Chaque produit est un dictionnaire avec `external_product_id` et `name`,
chaînes non vides. La projection conserve seulement `products` et, dans
chaque produit, seulement ces deux champs.

### `get_stock_for_product`

`data` est un dictionnaire avec :

- `external_product_id` : chaîne non vide ;
- `branches` : liste éventuellement vide.

Chaque branche est un dictionnaire avec :

- `branch_id` : entier strictement positif ;
- `branch_name` : chaîne non vide ;
- `quantity` : entier positif ou nul.

La projection conserve seulement `external_product_id`, `branches` et les
trois champs de chaque branche.

### `list_branch_stock`

`data` est un dictionnaire avec :

- `branch_id` : entier strictement positif ;
- `branch_name` : chaîne non vide ;
- `stocks` : liste éventuellement vide.

Chaque stock est un dictionnaire avec :

- `external_product_id` : chaîne non vide ;
- `quantity` : entier strictement positif.

La projection conserve seulement `branch_id`, `branch_name`, `stocks` et les
deux champs de chaque stock.

### `find_branches_for_shopping_list`

`data` est un dictionnaire avec :

- `complete` : booléen ;
- `strategy` : exactement `"single_branch"`, `"multiple_branches"` ou
  `"unavailable"` ;
- `visits` : liste ;
- `missing_items` : liste.

Chaque élément de `visits` est un dictionnaire avec :

- `branch_id` : entier strictement positif ;
- `branch_name` : chaîne non vide ;
- `items` : liste non vide.

Chaque élément de `items` est un dictionnaire avec :

- `external_product_id` : chaîne non vide ;
- `requested_quantity` : entier strictement positif ;
- `available_quantity` : entier supérieur ou égal à
  `requested_quantity`.

Chaque élément de `missing_items` est un dictionnaire avec :

- `external_product_id` : chaîne non vide ;
- `missing_quantity` : entier strictement positif.

Les contraintes de cohérence sont :

- si `complete` vaut `true`, `strategy` vaut `"single_branch"` ou
  `"multiple_branches"`, `visits` est non vide et `missing_items` est vide ;
- `"single_branch"` impose exactement une visite ;
- `"multiple_branches"` impose au moins deux visites ;
- si `complete` vaut `false`, `strategy` vaut `"unavailable"`, `visits` est
  vide et `missing_items` est non vide.

Tous les champs numériques ci-dessus rejettent explicitement les booléens.
La projection conserve seulement `complete`, `strategy`, `visits`,
`missing_items` et, récursivement, uniquement les champs énumérés pour les
visites, leurs articles et les articles manquants.

## Cohérence Product/Stock

Pour `product_availability`, lorsque les deux résultats sont structurellement
valides, leurs `external_product_id` doivent être strictement égaux.

S'ils diffèrent :

- `get_product_details` reste exploitable et sa projection est conservée ;
- `get_stock_for_product` est déclaré contradictoire, donc indisponible pour
  cette réponse et entièrement exclu de `tool_results` ;
- le statut est `partial` ;
- `answer` vaut exactement la phrase fixe sans fait métier :
  `"Some MCP information is available, but it is insufficient for a complete grounded answer."`

Cette exclusion contextuelle prime sur toute règle générale d'inclusion d'un
résultat structurellement valide.

## Statuts et forme de sortie

Pour une famille supportée :

- `success` : tous les résultats attendus sont exploitables et, pour une liste
  de courses, `complete` vaut `true` ;
- `partial` : au moins un résultat est exploitable mais un résultat attendu
  est absent, indisponible ou contradictoire ; une liste de courses dont les
  deux résultats sont exploitables et dont `complete` vaut `false` est
  également `partial` ;
- `unavailable` : aucun résultat attendu n'est exploitable.

Une liste `branches` vide ou `stocks` vide représente une absence réelle de
stock et reste un `success` lorsque tous les résultats attendus sont
exploitables.

Une réponse `success` ou `partial` contient exactement :

```json
{
  "status": "success-or-partial",
  "answer": "Grounded deterministic text.",
  "data": {
    "question_type": "one-supported-type",
    "tool_results": {
      "tool_name": {}
    }
  }
}
```

`tool_results` contient seulement les projections indépendantes des outils
exploitables, dans l'ordre contractuel. Il ne contient jamais une enveloppe,
une erreur MCP, un champ supplémentaire, une donnée mal formée ou le Stock
contradictoire défini ci-dessus.

Si `partial` résulte d'un outil attendu absent, indisponible ou contradictoire,
`answer` vaut exactement :

```text
Some MCP information is available, but it is insufficient for a complete grounded answer.
```

Cette phrase ne cite aucun fait métier. Le cas distinct où les deux résultats
de `shopping_list` sont exploitables mais où `complete` vaut `false` explique
uniquement `strategy == "unavailable"` et les `missing_items` projetés reçus ;
il ne recalcule aucune quantité.

Une réponse `unavailable` est exactement :

```json
{
  "status": "unavailable",
  "answer": "I do not have enough information to answer this question.",
  "data": {}
}
```

## Règles de génération

Pour `success`, le texte est déterministe et adapté à la famille :

- `product_details` cite uniquement le nom et l'identifiant projetés ;
- `product_availability` cite uniquement le produit, les branches et les
  quantités projetés, ou indique que la liste projetée de branches est vide ;
- `branch_inventory` cite uniquement la branche, les identifiants, les noms
  corrélés par identifiant et les quantités projetés, ou indique que la liste
  projetée de stocks est vide ;
- `shopping_list` explique uniquement `complete`, `strategy`, `visits` et
  `missing_items` projetés.

La ponctuation, les mots de liaison et les libellés fixes ne constituent pas
des faits métier. Aucun nom, identifiant, détail, branche, nombre, prix ou état
de disponibilité absent des projections exploitables ne peut apparaître.

La fonction ne modifie jamais l'entrée, retourne des copies indépendantes et
ne conserve aucun état entre deux appels.

## Dépendances, sécurité et hors périmètre

`ai_service/generator.py` utilise uniquement la bibliothèque standard Python
et `ai_service.classifier.SUPPORTED_QUESTION_TYPES`. Il n'importe pas le SDK
MCP et n'effectue aucun appel réseau, HTTP, MCP, PostgreSQL ou fournisseur IA.
Il ne lit aucune variable d'environnement et n'écrit aucun log ou état
persistant.

`ai_service/requirements.txt` reste inchangé. Aucun paquet de fournisseur IA,
Flask, client HTTP ou `fastmcp` séparé n'est ajouté ou installé.

Restent hors périmètre :

- Flask, `POST /questions`, validation JSON et CORS ;
- extraction des identifiants, quantités ou branches depuis une question ;
- orchestration du classifieur et du client MCP ;
- fournisseur IA externe, `AI_MODEL` et `AI_PROVIDER_UNAVAILABLE` ;
- logs de tool calls ;
- Client Web, Docker, proxy et tests de bout en bout.

## Tests et preuves

`tests/test_ai_generator.py` teste uniquement l'interface publique avec des
données locales. Toute connexion socket réelle est bloquée. La couverture
contractuelle comprend :

- les quatre familles et `unsupported` ;
- les réponses Product, Stock et combinées ;
- un produit inconnu ;
- les statuts `success`, `partial` et `unavailable` ;
- les enveloppes absentes, d'erreur et mal formées ;
- tous les types et contraintes des visites, articles et articles manquants,
  dont le rejet des booléens pour chaque entier ;
- une incohérence d'identifiant entre Product et Stock, avec exclusion du
  Stock, statut `partial` et phrase fixe ;
- la suppression récursive des champs supplémentaires dans chaque projection ;
- l'absence réelle de stock ;
- une liste de courses complète et incomplète ;
- l'absence de nom, branche ou quantité inventés ;
- l'absence de recalcul du plan Stock ;
- l'immuabilité des entrées et l'indépendance des appels.

Commandes finales obligatoires :

```bash
python3 -m pytest tests/test_ai_generator.py -q
python3 -m pytest tests/test_ai_classifier.py tests/test_ai_mcp_client.py tests/test_ai_generator.py -q
python3 -m pytest --import-mode=importlib tests/test_product_mcp_tools.py tests/test_product_mcp_server.py integration_tests/test_product_mcp_server.py -q
python3 -m pytest --import-mode=importlib tests/test_stock_mcp_repository.py tests/test_stock_mcp_tools.py tests/test_stock_mcp_server.py integration_tests/test_stock_mcp_server.py -q --deselect tests/test_stock_mcp_repository.py::test_runtime_manifest_contains_only_the_approved_dependency
```

Chaque commande doit terminer avec le code retour `0`. Aucun succès n'est
présumé avant son exécution après l'implémentation.

## Sections documentaires réellement utilisées

- `docs/project_context.md` §13 : quatre familles, `unsupported` et
  interdiction d'inventer ;
- `docs/architecture.md` §4.7 : combinaison structurée et réponse fondée ;
- `docs/architecture.md` §§10–12 : flux, association familles-outils et
  explication du plan sans recalcul ;
- `docs/architecture.md` §15 : erreurs stables sans secret ;
- `docs/api_contracts.md` §8.2 : statuts et réponses publiques de référence ;
- `docs/api_contracts.md` §§9–11, spécialement §11.4 : enveloppes MCP et
  schémas publics des résultats Product, Stock et liste de courses ;
- `docs/security_rules.md` §§10–12 : absence d'invention, secrets et erreurs ;
- `docs/testing_strategy.md` §§2 et 10 : doubles locaux et scénarios de
  génération fondée.

Interfaces validées consultées, sans modification :
`ai_service/classifier.py`, `ai_service/mcp_client.py`,
`product_mcp_server/tools.py` et `stock_mcp_server/tools.py`.
