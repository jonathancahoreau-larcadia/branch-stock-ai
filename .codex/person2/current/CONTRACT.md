# Contrat P2-T02 — serveur protocolaire Product MCP

Statut : **PROPOSÉ — BLOQUÉ PAR DÉPENDANCE — EN ATTENTE DE REVUE DE RÉMI**

## Sources et constat

Sources de vérité : `docs/project_context.md` §§10–11 et 18,
`docs/architecture.md` §§4.5 et 15–18, `docs/api_contracts.md` §§9–10,
12–13, `docs/security_rules.md` §§10–12 et
`docs/testing_strategy.md` §8. Les empreintes documentaires sont inchangées.

P2-T01 est validée et reste hors modification. `product_mcp_server/server.py`
est absent. Aucun manifeste de dépendances propre à Product MCP n'existe et
aucun manifeste du dépôt ne déclare `mcp`. Le Python système ne trouve pas le
paquet ; le `.venv` local contient actuellement `mcp==1.28.1`, mais cette
installation non déclarée n'est ni une autorisation ni une preuve de
reproductibilité.

## Périmètre exact

Après les validations séquentielles requises, P2-T02 pourra créer :

- `product_mcp_server/server.py` : serveur et adaptateur protocolaire ;
- `product_mcp_server/requirements.txt` : manifeste du service, uniquement
  après accord humain explicite sur la dépendance.

Thomas créera séparément `tests/test_product_mcp_server.py`.

Sont exclus : toute modification de `product_mcp_server/tools.py`,
`product_mcp_server/product_api.py`, `product_mcp_server/__init__.py`,
`tests/test_product_mcp_tools.py`, des services Docker, de l'AI Query Service
ou de PostgreSQL. Aucun nouvel outil, ressource, prompt, appel HTTP métier,
retry, cache, persistance, authentification ou CORS n'est ajouté.

## Symboles figés dans `server.py`

- `mcp: FastMCP`, construit avec :
  - nom `Product MCP Server` ;
  - `host="0.0.0.0"` et `port=8100` ;
  - `streamable_http_path="/mcp"` ;
  - `stateless_http=True` ;
  - `json_response=True`.
- `async def list_products() -> dict[str, Any]`.
- `async def get_product_details(external_product_id: str) -> dict[str, Any]`.
- `async def health(request: Request) -> JSONResponse`.
- `def main() -> None`, qui appelle exclusivement
  `mcp.run(transport="streamable-http")`.
- Le garde d'exécution `if __name__ == "__main__": main()`.

Le SDK est importé avec `from mcp.server.fastmcp import FastMCP`. Le paquet
séparé `fastmcp` est interdit.

Les deux wrappers sont enregistrés explicitement avec le décorateur public
`@mcp.tool()` : c'est ce qui les rend découvrables comme outils MCP. La route
de santé ne reçoit jamais ce décorateur.

La route de santé est enregistrée explicitement avec le décorateur public du
SDK : `@mcp.custom_route("/health", methods=["GET"])`. Les seuls imports
hors SDK admis dans `server.py` sont les types ASGI nécessaires à cette route
(`Request` et `JSONResponse`), `Any` pour les annotations et le module local
`product_mcp_server.tools`; aucun client HTTP ou module d'accès aux données
n'est importé par cette couche protocolaire.

## API publique et transport

Le serveur expose exactement deux **outils MCP** :

1. `list_products`, sans argument ;
2. `get_product_details`, avec l'unique argument requis
   `external_product_id` de type chaîne.

Il n'expose aucun autre outil, aucune ressource et aucun prompt. Les fonctions
portent des annotations afin que le SDK publie les schémas d'entrée et une
sortie structurée. L'URL MCP interne cible est
`http://product_mcp_server:8100/mcp`, soit le `/mcp` ajouté à la base
`PRODUCT_MCP_URL=http://product_mcp_server:8100`.

Le transport est exclusivement **MCP Streamable HTTP**, stateless, avec
réponses JSON. `stdio` et le transport SSE historique ne font pas partie de
P2-T02.

La seule route HTTP non-MCP est `GET /health`. Elle retourne HTTP 200 et
exactement `{"status": "ok"}` ; elle atteste que le processus répond et
n'effectue pas d'appel à Product API. Elle n'est pas enregistrée comme outil.

## Délégation et erreurs

Les wrappers importent le module `product_mcp_server.tools` et délèguent
exactement une fois :

- `list_products()` vers `await tools.list_products()`, sans argument ;
- `get_product_details(external_product_id)` vers
  `await tools.get_product_details(external_product_id)`, sans normalisation
  préalable.

Ils retournent directement, sans mutation, copie, cache ni nouvelle enveloppe,
le dictionnaire produit par P2-T01. Les résultats publics restent donc :

```python
{"status": "success", "data": ...}
{"status": "not_found", "data": None}
{"status": "error", "error": {"code": str, "message": str}}
```

Les erreurs métier et d'amont déjà normalisées par P2-T01, notamment
`INVALID_EXTERNAL_PRODUCT_ID`, `PRODUCT_API_UNAVAILABLE`,
`PRODUCT_API_TIMEOUT` et `PRODUCT_API_INVALID_RESPONSE`, traversent la couche
protocolaire à l'identique. Un argument MCP absent ou de mauvais type est
refusé par la validation de schéma du SDK avant délégation. P2-T02 n'ajoute
aucun `try/except` métier et ne transforme pas une exception Python
inattendue : le SDK la traite comme une erreur protocolaire. Le code du serveur
ne renvoie ni traceback, secret, configuration, SQL, jeton ni chaîne de
connexion.

## Dépendance, prérequis et blocage

Proposition minimale à soumettre à accord humain dans
`product_mcp_server/requirements.txt` :

```text
httpx>=0.27,<1.0
mcp>=1.27,<2
```

`mcp>=1.27,<2` cible la branche v1 stable et l'API `FastMCP` vérifiée pour ce
contrat ; l'extra `[cli]` n'est pas requis. `httpx` est déjà utilisé par
P2-T01, mais doit être déclaré dans le manifeste autonome du service.

**Décision de blocage :** aucune création de manifeste, installation,
écriture de tests dépendant du SDK ou implémentation de `server.py` ne doit
commencer avant accord humain explicite sur cette borne et ce manifeste. La
présence accidentelle de `mcp` dans `.venv` ne lève pas ce blocage. Si une
autre version majeure ou un autre emplacement de manifeste est choisi, Rémi
doit faire réviser le présent contrat avant Thomas.

## Tests que Thomas devra écrire

Sans toucher aux tests de P2-T01, `tests/test_product_mcp_server.py` devra :

1. utiliser le client/session en mémoire public du paquet `mcp`, pas les
   attributs privés de `FastMCP` ;
2. vérifier par `list_tools` que les noms sont exactement
   `list_products` et `get_product_details`, que le premier n'a aucun argument
   et que le second requiert une chaîne `external_product_id` ;
3. vérifier qu'aucune ressource et aucun prompt ne sont publiés ;
4. monkeypatcher les deux fonctions de `product_mcp_server.tools`, appeler
   chaque outil via une session MCP, puis prouver une délégation unique avec
   les arguments exacts et un `structuredContent` égal à l'enveloppe retournée
   par le mock ;
5. couvrir au minimum une enveloppe `success`, une `not_found` et une `error`
   et prouver leur transmission sans mutation ;
6. vérifier qu'un argument manquant ou non-chaîne est rejeté sans appeler
   `tools.get_product_details` ;
7. vérifier la configuration publique : nom, hôte, port, chemin `/mcp`, mode
   stateless et réponse JSON ;
8. remplacer `mcp.run`, appeler `main()` et vérifier l'appel unique avec
   `transport="streamable-http"` sans démarrer de serveur réel ;
9. interroger l'application ASGI en mémoire et vérifier que `GET /health`
   retourne HTTP 200 avec exactement `{"status": "ok"}` sans appeler un outil ;
10. inclure un contrôle source/import interdisant `fastmcp`, tout accès
    PostgreSQL et toute méthode Product API dans `server.py`.

Les tests ne doivent ni ouvrir un port, ni joindre Product API, ni dépendre de
Docker ou du réseau.

## Critères d'acceptation

P2-T02 est acceptable lorsque :

- l'accord humain sur les dépendances est consigné ;
- Rémi a approuvé ce contrat puis les tests de Thomas ;
- seuls `server.py` et le manifeste approuvé sont implémentés par Sam ;
- les deux outils sont découvrables et appelables sur MCP Streamable HTTP à
  `/mcp`, avec leurs signatures exactes ;
- la délégation et les enveloppes P2-T01 sont inchangées ;
- `/health` répond conformément au contrat ;
- aucun outil ou accès supplémentaire n'est exposé ;
- les tests ciblés de Thomas et les tests P2-T01 existants réussissent dans un
  environnement reconstruit depuis le manifeste, avec commandes et sorties
  consignées.

Ce contrat attend explicitement la revue de Rémi.
