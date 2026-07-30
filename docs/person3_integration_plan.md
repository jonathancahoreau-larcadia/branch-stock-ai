# Audit et plan d’intégration — Personne 3

Date de l’audit : **2026-07-29**

## Résumé exécutif

L’état observé du dépôt montre des briques métier déjà substantielles, mais
pas encore une plateforme intégrée. Le Backoffice Flask, les deux serveurs MCP
et les couches de classification, d’appel MCP et de génération de l’AI Query
Service sont présents. Les deux interfaces et `docker-compose.yml` sont
partiels : le Backoffice UI ne couvre pas le CRUD administrateur complet, le
Client Web prépare seulement une liste locale, et Compose ne lance que trois
services.

La cible documentaire comporte huit composants logiques et deux flux de bout
en bout. Elle n’est pas déclarée atteinte par ce document. Les preuves restant
à produire comprennent notamment le raccordement HTTP public, le déploiement
des dépendances, les scénarios Docker réels et la démonstration finale.
P3-T02 à P3-T06 répartissent ces écarts sans modifier les contrats publics
validés.

## Méthode et périmètre de l’audit

L’audit est une lecture locale datée des documents, sources, manifestes,
actifs statiques et tests listés dans la section `Sources`. Il compare :

1. l’état observé dans le dépôt au 2026-07-29 ;
2. la cible décrite par les contrats et l’architecture ;
3. les preuves locales déjà disponibles et les preuves restant à produire.

Les statuts ont le sens suivant :

- **implémenté** : responsabilité locale et interface publique présentes dans
  le code, sans conclure que le déploiement intégré est opérationnel ;
- **partiel** : une partie de la responsabilité est présente, mais il manque
  une interface, une configuration ou une preuve d’intégration ;
- **absent** : aucun composant local exécutable correspondant n’a été trouvé.

P3-T01 n’ouvre aucun réseau, ne lance aucun service réel et ne modifie ni
interface, ni production, ni test. Les constats d’exécution cités sont des
preuves locales pytest sans réseau réel. Les chemins Product MCP protégés
restent immuables.

## Inventaire vérifié

### PostgreSQL

- **Fichiers ou répertoires observés :**
  `backoffice/database/models.py`,
  `backoffice/database/migrations/`,
  `backoffice/database/seed.py` et
  `stock_mcp_server/repository.py`.
- **État : partiel.** Schéma, migration, contraintes et initialisation
  applicative sont implémentés, mais aucun service `database` n’est déclaré
  dans le Compose observé.
- **Responsabilité :** conserver utilisateurs, succursales, quantités de
  stock et identifiants JWT révoqués ; ce n’est pas la source des détails
  produit.
- **Source de données :** PostgreSQL est la source de vérité locale pour les
  comptes, rôles, affectations de branche et stocks.
- **Dépendances :** Backoffice Flask en lecture/écriture ; Stock MCP avec un
  compte distinct limité à `SELECT` sur `branches` et `stocks`.
- **Port / route / interface publique :** cible interne PostgreSQL `5432`,
  sans route HTTP publique ; aucune exposition n’est observée dans
  `docker-compose.yml`.
- **Preuve :** les contraintes
  `ck_stocks_quantity_non_negative` et
  `ck_users_branch_assignment` sont présentes dans le modèle et la migration ;
  les requêtes du repository Stock commencent par `SELECT` et sont
  paramétrées.
- **Écart :** P3-T04 doit raccorder le service, son volume, son healthcheck et
  les comptes applicatif/migration/lecture seule ; P3-T05 doit prouver les
  frontières d’accès dans l’environnement intégré.

### External Product API

- **Fichiers ou répertoires observés :**
  `backoffice/products/client.py`,
  `product_mcp_server/product_api.py` et les tests d’adaptateurs ; aucun
  répertoire local `product_api/` n’est présent.
- **État : absent.** Les consommateurs HTTP existent, mais aucun service
  External Product API exécutable ni service Compose `product_api` n’a été
  observé.
- **Responsabilité :** lister les produits et fournir le détail d’un
  identifiant en lecture seule.
- **Source de données :** source officielle unique des informations produit.
- **Dépendances :** consommée par Backoffice Flask et Product MCP ; sa
  disponibilité et son contrat opérationnel sont une dépendance externe.
- **Port / route / interface publique :** cible documentaire interne
  `http://product_api:8080`; le Compose actuel configure seulement un repli
  Backoffice vers `http://host.docker.internal:5001`.
- **Preuve :** les deux clients locaux utilisent `PRODUCT_API_BASE_URL` et un
  timeout ; l’inventaire racine et `docker-compose.yml` ne contiennent aucun
  service Product API.
- **Écart :** une image ou une dépendance interpersonnes validée doit être
  fournie avant P3-T04 ; P3-T01 ne simule pas sa présence et P3-T05 devra
  prouver les cas succès, indisponibilité, timeout et réponse invalide.

### Backoffice Flask

- **Fichiers ou répertoires observés :** `backoffice/app.py`, les modules
  `auth/`, `users/`, `branches/`, `products/`, `stocks/`, `database/`,
  `backoffice/tests/`, `Dockerfile` et `backoffice/requirements.txt`.
- **État : implémenté.** La fabrique Flask enregistre les blueprints attendus
  et Compose construit `backoffice-api`; l’intégration complète à PostgreSQL
  et à l’External Product API n’est toutefois pas prouvée par P3-T01.
- **Responsabilité :** authentification JWT, autorisation par rôle et branche,
  CRUD des common users, consultation des branches et produits, transactions
  de stock et erreurs JSON stables.
- **Source de données :** PostgreSQL pour comptes, branches et stocks ;
  External Product API pour les produits.
- **Dépendances :** reçoit REST + JWT Bearer du Backoffice UI ; dépend de
  `DATABASE_URL`, `JWT_SECRET_KEY` et `PRODUCT_API_BASE_URL`.
- **Port / route / interface publique :** port observé `5000`; routes
  `/api/v1/auth/*`, `/api/v1/users*`, `/api/v1/branches*`,
  `/api/v1/products*`, `/api/v1/stocks*` et `GET /health`.
- **Preuve :** `backoffice/app.py` enregistre six blueprints métier et santé ;
  les décorateurs de routes correspondent aux sections 3 à 7 et 12 de
  `docs/api_contracts.md`.
- **Écart :** P3-T04 doit fournir ses dépendances et sa configuration
  complète, puis P3-T05 doit exécuter les scénarios interservices ; aucune
  modification de contrat backend n’est prévue.

### Backoffice UI

- **Fichiers ou répertoires observés :** `backoffice/static/index.html`,
  `backoffice/static/app.js`, `backoffice/static/styles.css`,
  `backoffice/static/nginx.conf` et `backoffice/static/Dockerfile`.
- **État : partiel.** Connexion, refresh, déconnexion, consultation par rôle
  et ajout/retrait de stock sont présents ; le CRUD administrateur complet
  n’a pas d’écrans ou formulaires dédiés.
- **Responsabilité :** interface authentifiée, navigation adaptée au rôle,
  affichage de la branche courante, gestion des common users et opérations de
  stock.
- **Source de données :** exclusivement les réponses REST de Backoffice
  Flask ; aucun accès direct à PostgreSQL ni stockage de détail produit.
- **Dépendances :** Backoffice Flask via le proxy Nginx et JWT Bearer ;
  navigateur pour `sessionStorage`.
- **Port / route / interface publique :** `backoffice-ui` expose le port hôte
  `8080` vers Nginx `80` et proxifie `/api/` vers
  `backoffice-api:5000`.
- **Preuve :** `backoffice/static/app.js` appelle login, refresh, logout,
  ressources et stock ; il emploie `textContent`/`replaceChildren`, jamais
  `innerHTML`.
- **Écart :** P3-T02 doit ajouter création, consultation ciblée, modification,
  changement de mot de passe et suppression logique des common users, avec
  états de chargement, validation et erreurs accessibles.

### Product MCP Server

- **Fichiers ou répertoires observés :** `product_mcp_server/__init__.py`,
  `product_mcp_server/product_api.py`, `product_mcp_server/tools.py`,
  `product_mcp_server/server.py`,
  `product_mcp_server/requirements.txt`, tests unitaires et d’intégration.
- **État : partiel.** L’adaptateur MCP et les deux outils sont implémentés et
  testés localement, mais aucun service Compose ne les lance.
- **Responsabilité :** exposer `list_products` et `get_product_details`,
  normaliser les enveloppes et relayer l’External Product API sans accéder à
  PostgreSQL.
- **Source de données :** External Product API, source officielle produit.
- **Dépendances :** reçoit les appels de l’AI Query Service ; dépend du SDK
  `mcp`, de `httpx` et de `PRODUCT_API_BASE_URL`.
- **Port / route / interface publique :** Streamable HTTP interne
  `http://product_mcp_server:8100/mcp` et `GET /health` sur le port `8100`.
- **Preuve :** `product_mcp_server/server.py` enregistre exactement les deux
  outils et la santé ; les baselines séparées Product MCP sont vertes dans
  l’état d’entrée.
- **Écart :** P3-T04 doit l’empaqueter et le raccorder au réseau interne ;
  P3-T05 doit prouver le flux avec une API Produit contrôlée. Les chemins
  protégés ne sont pas à modifier.

### Stock MCP Server

- **Fichiers ou répertoires observés :** `stock_mcp_server/repository.py`,
  `stock_mcp_server/tools.py`, `stock_mcp_server/server.py`,
  `stock_mcp_server/requirements.txt` et leurs tests.
- **État : partiel.** Les quatre outils et le repository en lecture seule sont
  implémentés, mais le service, son compte PostgreSQL dédié et ses permissions
  ne sont pas intégrés dans Compose.
- **Responsabilité :** fournir les lectures de stock contrôlées et résoudre
  les listes de courses de façon déterministe.
- **Source de données :** tables PostgreSQL `branches` et `stocks` seulement.
- **Dépendances :** reçoit les appels de l’AI Query Service ; dépend du SDK
  `mcp`, de `psycopg` et de `STOCK_MCP_DATABASE_URL`.
- **Port / route / interface publique :** Streamable HTTP interne
  `http://stock_mcp_server:8200/mcp` et `GET /health` sur le port `8200`.
- **Preuve :** `stock_mcp_server/server.py` enregistre les quatre outils ; le
  repository contient uniquement des requêtes `SELECT` paramétrées sur les
  tables autorisées.
- **Écart :** P3-T04 doit définir service, secret de connexion non commité et
  compte read-only ; P3-T05 doit prouver l’interdiction d’écriture et d’accès
  aux données privées. Le désaccord de manifeste décrit plus bas reste un
  risque existant.

### AI Query Service

- **Fichiers ou répertoires observés :** `ai_service/classifier.py`,
  `ai_service/mcp_client.py`, `ai_service/generator.py`,
  `ai_service/__init__.py`, `ai_service/requirements.txt` et
  `tests/test_ai_*.py`.
- **État : partiel.** Classification, client MCP allowlisté et génération
  déterministe fondée sur des résultats structurés existent ; aucun
  adaptateur HTTP Flask n’expose `POST /questions` ou `GET /health`.
- **Responsabilité :** valider et classifier une question indépendante,
  appeler seulement les outils MCP approuvés et produire une réponse fondée
  sur les données.
- **Source de données :** enveloppes Product MCP et Stock MCP uniquement ;
  aucune connexion PostgreSQL directe.
- **Dépendances :** reçoit les requêtes anonymes du Client Web ; dépend des
  URL Product/Stock MCP et du SDK `mcp`.
- **Port / route / interface publique :** cible documentaire port `8000`,
  `POST /questions` public et `GET /health`; aucune route HTTP n’est observée
  dans `ai_service/`.
- **Preuve :** les trois modules et leurs tests unitaires existent ; aucun
  fichier d’application Flask, décorateur `/questions` ou `/health` n’est
  présent.
- **Écart :** l’adaptateur HTTP est une dépendance Personne 2 à obtenir avant
  le raccordement P3-T03/P3-T04 ; P3-T01 ne l’invente pas. P3-T05 devra
  vérifier les statuts métier et les erreurs sans données inventées.

### Client Web

- **Fichiers ou répertoires observés :** `client_web/index.html`,
  `client_web/app.js`, `client_web/styles.css` et
  `client_web/Dockerfile`.
- **État : partiel.** Une liste locale accessible est manipulable, mais
  aucune question libre n’est envoyée et aucun résultat IA n’est affiché.
- **Responsabilité :** accepter anonymement une question, appeler l’AI Query
  Service et afficher chargement, réponse, statuts métier et erreur technique,
  sans historique de conversation.
- **Source de données :** future réponse de `POST /questions`; l’état actuel
  ne reçoit aucune donnée distante.
- **Dépendances :** navigateur et AI Query Service public avec CORS limité à
  l’origine configurée.
- **Port / route / interface publique :** `client-web` expose le port hôte
  `3000` vers Nginx `80`; aucune route API n’est appelée actuellement.
- **Preuve :** `client_web/app.js` ne contient aucun `fetch` et le bouton
  produit uniquement un résumé local ; les sorties utilisent `textContent`.
- **Écart :** P3-T03 doit implémenter le formulaire `POST /questions`, les
  états `success`, `partial`, `unavailable`, `unsupported`, les erreurs
  techniques, le chargement et l’absence de persistance.

L’architecture décrit donc **huit composants logiques**, mais sa section 17
nomme **sept services Compose** :
`database`, `product_api`, `backoffice`, `product_mcp_server`,
`stock_mcp_server`, `ai_service`, `client_web`. Le dépôt observé sépare déjà
`backoffice-api` et `backoffice-ui`. La correspondance entre ces vues, les
noms finaux et le choix d’un ou deux conteneurs Backoffice sont un contrat
partagé à faire valider en P3-T04 ; P3-T01 ne tranche pas cette différence.

## Contrats et flux d’intégration

### Flux Backoffice figé

```text
Backoffice UI
  -> REST
  -> JWT Bearer
  -> Backoffice Flask
  -> PostgreSQL
  -> External Product API
```

Le dernier embranchement représente deux dépendances distinctes du
Backoffice : PostgreSQL pour les comptes, branches et stocks, et External
Product API pour les produits. Les contrôles d’autorisation restent côté
backend.

### Flux public IA figé

```text
Client Web anonyme
  -> POST /questions
  -> AI Query Service
  -> Product MCP
  -> External Product API
  -> Stock MCP
  -> PostgreSQL
```

Product MCP ne consulte jamais PostgreSQL. Stock MCP consulte PostgreSQL en
lecture seule. L’ordre textuel ci-dessus rend les deux branches de
dépendances visibles ; l’AI Query Service orchestre Product MCP et Stock MCP,
sans transformer la chaîne en accès Product API vers Stock MCP.

### Matrice de compatibilité des contrats publics

La matrice de compatibilité référence les sections 3 à 12 de
`docs/api_contracts.md` sans redéfinir leurs payloads, codes d’erreur,
autorisations ou outils.

| Section | Domaine et consommateurs | Compatibilité observée | Manque vers la cible | Tâche propriétaire |
|---:|---|---|---|---|
| Section 3 | Authentification — Backoffice UI vers Backoffice Flask | Login, refresh, logout et `/auth/me` avec JWT Bearer sont appelés. | Preuves E2E de cycle complet et états UI d’erreur. | P3-T02, puis P3-T05 |
| Section 4 | Utilisateurs — Backoffice UI admin | Le backend expose liste, création, détail, patch, mot de passe et suppression logique ; l’UI liste seulement. | CRUD administrateur complet et validation accessible. | P3-T02 |
| Section 5 | Succursales — Backoffice UI | Liste et détail existent côté backend ; l’UI liste les ressources autorisées. | Preuve des restrictions admin/common user dans le navigateur intégré. | P3-T02, puis P3-T05 |
| Section 6 | Produits — Backoffice UI et Backoffice Flask | Routes proxy et vue de liste présentes. | External Product API déployée et cas d’erreur intégrés. | P3-T04, puis P3-T05 |
| Section 7 | Stocks — Backoffice UI common user | Liste, ajout et retrait sont câblés sans `branch_id` client. | Preuves de branche serveur, concurrence, stock insuffisant et quantité non négative. | P3-T02, puis P3-T05 |
| Section 8 | `POST /questions` et statuts métier — Client Web anonyme | Classifier et générateur existent, mais aucun endpoint ni appel client. | Adaptateur HTTP Personne 2, UI publique, absence d’historique et gestion de `success`/`partial`/`unavailable`/`unsupported`. | P3-T03, dépendance interpersonnes, puis P3-T04 |
| Section 9 | Enveloppes MCP — AI Query Service | Le client valide les enveloppes MCP `success`, `not_found` et `error`. | Preuve interservices des erreurs, timeouts et réponses invalides. | P3-T05 |
| Section 10 | Product MCP — AI Query Service | `list_products` et `get_product_details` sont implémentés dans les chemins protégés. | Service Compose et External Product API contrôlée. | P3-T04, puis P3-T05 |
| Section 11 | Stock MCP — AI Query Service | `list_branch_stock`, `get_stock_for_product`, `find_branches_with_stock` et `find_branches_for_shopping_list` sont implémentés en lecture seule. | Service Compose, compte PostgreSQL restreint et preuves de permissions. | P3-T04, puis P3-T05 |
| Section 12 | `GET /health` — orchestration | Backoffice Flask, Product MCP et Stock MCP exposent la route. | Santé AI absente, dépendances non composées et agrégation/dégradation non prouvées. | P3-T04 |

## Écarts, risques et dépendances

### G1 — Compose incomplet

- **Constat observé :** `docker-compose.yml` contient exactement
  `backoffice-api`, `backoffice-ui` et `client-web`.
- **Cible :** intégrer les services documentés et résoudre explicitement le
  décompte huit composants logiques / sept services Compose.
- **Propriétaire :** P3-T04, avec validation partagée des noms et de la
  topologie.

### G2 — Client public non raccordé

- **Constat observé :** `client_web/app.js` gère une liste locale et n’appelle pas `POST /questions`.
- **Cible :** question anonyme indépendante, chargement, statuts métier,
  réponse et erreur technique, sans historique.
- **Propriétaire :** P3-T03 ; l’endpoint AI est une dépendance Personne 2.

### G3 — Adaptateur HTTP AI absent

- **Constat observé :** `ai_service/` contient classification, client MCP et génération, mais aucun adaptateur HTTP exposant `POST /questions` ou `/health`.
- **Cible :** contrat de la section 8 et santé de la section 12, sans accès
  direct à PostgreSQL.
- **Propriétaire :** dépendance Personne 2 à obtenir ; raccordement P3-T03 et
  déploiement P3-T04. Une dépendance non disponible n’est pas reclassée en
  défaut Personne 3.

### G4 — Backoffice UI incomplet

- **Constat observé :** l’interface sait s’authentifier, consulter branches,
  produits, stocks et utilisateurs, et modifier le stock ; elle ne fournit
  pas le CRUD administrateur complet.
- **Cible :** écrans de création, détail, modification, changement de mot de
  passe et suppression logique des common users.
- **Propriétaire :** P3-T02.

### G5 — Documentation de lancement et initialisation

- **Constat observé :** `README.md`, `.env.example` et le répertoire `seed/`
  attendus par la documentation sont absents. Une commande de seed existe
  toutefois dans `backoffice/database/seed.py`.
- **Cible :** configuration sans secret, lancement reproductible,
  initialisation et limites connues.
- **Propriétaire :** P3-T04 pour la configuration et l’initialisation
  conteneurisées ; P3-T06 pour le guide final.

### G6 — Couverture d’intégration Personne 3 limitée

- **Constat observé :**
  `integration_tests/test_person3_assets.py` vérifie des actifs statiques, le
  proxy, l’absence de secrets évidents et une structure minimale ; il ne
  couvre pas encore les scénarios bout en bout.
- **Cible :** scénarios critiques Backoffice, AI/MCP, Client Web, santé et
  redémarrage Compose.
- **Propriétaire :** P3-T05.

### R1 — Risque existant de collecte pytest, hors correction P3-T01

- **Constat du 2026-07-29 :** un conflit de collecte existant apparaît quand
  `tests/` et `integration_tests/` chargent ensemble les modules homonymes
  `test_product_mcp_server.py` et `test_stock_mcp_server.py`.
- **Classement :** risque déjà présent, hors correction P3-T01 ; P3-T01 ne le
  corrige pas et ne modifie aucun test.
- **Mesure :** processus pytest séparés immédiatement ; P3-T05 décidera d’une
  convention durable sans réécrire les baselines validées.

### R2 — Risque existant de manifeste Stock, hors correction P3-T01

- **Constat du 2026-07-29 :**
  `tests/test_stock_mcp_repository.py` exige que
  `stock_mcp_server/requirements.txt` ne contienne que `psycopg[binary]`,
  alors que ce manifeste contient aussi le SDK MCP nécessaire au serveur.
- **Classement :** désaccord existant et risque déjà présent, hors correction
  P3-T01 ; P3-T01 ne le corrige pas et n’ajoute aucune dépendance.
- **Mesure :** conserver le test concerné hors des commandes normatives
  P3-T01 ; résolution interpersonnes préalable au build P3-T04.

### Dépendances bloquantes à distinguer

- L’External Product API exécutable et son mode de fourniture ne sont pas
  disponibles dans le dépôt : décision/entrée interpersonnes pour P3-T04.
- L’adaptateur HTTP de l’AI Query Service n’est pas disponible : livrable
  Personne 2 requis avant le raccordement complet.
- Les URL, secrets factices, comptes PostgreSQL et origines CORS doivent être
  configurés en P3-T04 ; aucune valeur réelle ne doit entrer dans Git.
- Ces absences ne prouvent pas un défaut des couches Product MCP, Stock MCP ou
  AI déjà validées et ne justifient aucune modification de leurs contrats.

### Invariants de sécurité et de données

- External Product API demeure la **source officielle** des produits ;
  aucun détail produit ni aucune donnée produit n’est persisté dans
  PostgreSQL.
- Le stock ne devient jamais négatif.
- Pour un **common user**, la branche provient du backend/serveur ; un
  `branch_id` envoyé par le client ne décide jamais du stock visé.
- Product MCP ne dispose d’aucun accès PostgreSQL.
- Les MCP restent en lecture seule pour l’IA : aucun outil d’écriture ou SQL
  arbitraire n’est exposé.
- L’IA reste sans écriture de stock et ses réponses fondées sur les données
  structurées reçues ; elle n’invente ni produit, ni branche, ni quantité.
- Le Client Web reste anonyme, sans authentification et sans historique de
  conversation dans `localStorage` ou `sessionStorage`.
- Le CORS public restrictif autorise uniquement l’origine configurée du
  Client Web, la méthode nécessaire et `Content-Type`.
- Les valeurs affichées provenant des services utilisent `textContent` ou un
  mécanisme équivalent sûr, jamais `innerHTML`.
- Aucun secret, mot de passe, hash, JWT, clé, header d’autorisation ou URI de
  connexion n’est exposé dans les sources, réponses, logs ou preuves.
- Tous les tests automatisés planifiés sont sans réseau réel ; les services
  Docker réels font l’objet de preuves distinctes et contrôlées.

### Chemins Product MCP protégés

Les huit chemins validés suivants restent inchangés pendant P3-T01 :

- `product_mcp_server/__init__.py`
- `product_mcp_server/product_api.py`
- `product_mcp_server/tools.py`
- `product_mcp_server/server.py`
- `product_mcp_server/requirements.txt`
- `tests/test_product_mcp_tools.py`
- `tests/test_product_mcp_server.py`
- `integration_tests/test_product_mcp_server.py`

## Plan d’intégration P3-T02 à P3-T06

### P3-T02 — Compléter l’interface Backoffice

- **Écarts :** G4 et compléments UI des sections 3 à 7.
- **Prérequis :** contrats Backoffice validés inchangés ; routes backend
  disponibles ; actifs et navigation par rôle actuels verts.
- **Dépendances interpersonnes :** réponses et autorisations de Personne 1 ;
  aucune extension de route sans validation partagée.
- **Chemins pressentis :** `backoffice/static/index.html`,
  `backoffice/static/app.js`, `backoffice/static/styles.css` et tests
  d’intégration Personne 3 dédiés.
- **Livrables :** formulaires admin complets, confirmations, validation,
  chargement et erreurs accessibles ; maintien des opérations common user.
- **Critères d'entrée :** contrat UI figé et tests approuvés avant code.
- **Critères de sortie :** chaque action des sections 3 à 7 est utilisable par
  le rôle autorisé, les données reçues sont rendues sûrement et les tests
  locaux passent sans réseau réel.
- **Tests automatisés :** DOM/fetch simulés, rôles admin/common user, erreurs
  401/403/validation, CRUD utilisateur et stock, sans service réel.
- **Preuves :** sorties pytest ciblées et captures locales sans jeton ni
  donnée sensible.
- **Repli non destructif :** conserver la navigation et les vues de
  consultation actuelles, isoler toute nouvelle action incomplète sans
  suppression ni restauration destructive.

### P3-T03 — Compléter le Client Web public

- **Écarts :** G2 et consommation de la section 8.
- **Prérequis :** contrat `POST /questions` stable et décision sur l’URL
  publique ; adaptateur HTTP AI fourni par Personne 2 ou mock contractuel
  approuvé pour les tests locaux.
- **Dépendances interpersonnes :** Personne 2 possède l’endpoint, les statuts
  métier et leur payload ; P3-T03 ne les redéfinit pas.
- **Chemins pressentis :** `client_web/index.html`, `client_web/app.js`,
  `client_web/styles.css` et tests UI dédiés.
- **Livrables :** question libre, soumission anonyme, indicateur de
  chargement, réponses `success`/`partial`/`unavailable`/`unsupported`,
  erreurs techniques et exemples réalistes.
- **Critères d'entrée :** adaptateur ou double local contractuel disponible,
  stratégie CORS décidée, tests approuvés avant code.
- **Critères de sortie :** aucun historique persistant, bouton désactivé
  quand nécessaire, rendu via `textContent`, tous les statuts et erreurs
  couverts sans réseau réel.
- **Tests automatisés :** `fetch` simulé, validation vide/longueur,
  concurrence de soumission, erreurs HTTP/JSON et absence de stockage.
- **Preuves :** pytest UI, revue accessibilité et démonstration locale sur
  serveur simulé.
- **Repli non destructif :** garder le client statique disponible avec un
  message d’indisponibilité explicite si l’AI HTTP manque, sans suppression
  des actifs ni restauration destructive.

### P3-T04 — Intégrer les services et la configuration Docker

- **Écarts :** G1, G3, G5, services et dépendances absents des inventaires.
- **Prérequis :** images/commandes de lancement Product API, Product MCP,
  Stock MCP et AI validées ; adaptateur HTTP AI disponible ; résolution du
  risque R2 ; noms des sept services et découpage Backoffice approuvés.
- **Dépendances interpersonnes :** Personne 1 fournit migrations/seed et
  paramètres DB ; Personne 2 fournit commandes MCP/AI ; équipe fournit
  l’External Product API.
- **Chemins pressentis :** `docker-compose.yml`, Dockerfiles/manifestes
  nécessaires, `.env.example` sans secret et scripts d’initialisation
  approuvés.
- **Livrables :** réseau interne, volumes, healthchecks, ordre de démarrage,
  ports documentés, comptes DB séparés, URL internes, CORS restrictif et
  initialisation idempotente.
- **Critères d'entrée :** toutes les dépendances exécutables sont disponibles
  et leurs baselines sont vertes séparément.
- **Critères de sortie :** `docker compose config` valide ; tous les services
  convenus deviennent sains ; les deux flux atteignent leurs dépendances sans
  exposer de secret.
- **Tests automatisés :** validation Compose et configuration avec valeurs
  factices, healthchecks contrôlés, permissions DB et démarrage sur données de
  test.
- **Preuves :** sorties `docker compose config`, build, santé et logs
  expurgés ; les scénarios Docker réels commencent ici.
- **Repli non destructif :** intégrer un service à la fois et conserver le
  Compose minimal vérifié comme variante documentée, sans suppression de
  volumes ni restauration destructive.

### P3-T05 — Automatiser l’intégration et le bout en bout

- **Écarts :** G6, preuves interservices de G1 à G5 et risques R1/R2 après
  décision de leurs propriétaires.
- **Prérequis :** Compose P3-T04 sain, données de test reproductibles, contrats
  figés et suites unitaires vertes.
- **Dépendances interpersonnes :** scénarios métier Personne 1, doubles et
  comportements d’erreur Personne 2, environnement intégré Personne 3.
- **Chemins pressentis :** `integration_tests/`, fixtures locales,
  `docs/test_evidence/` et commandes de test documentées.
- **Livrables :** scénarios Backoffice complets, Product API/MCP, Stock MCP,
  AI, Client Web, santé et redémarrage ; convention évitant les collisions de
  modules pytest.
- **Critères d'entrée :** environnement reproductible sans secret et
  responsabilités des échecs connues.
- **Critères de sortie :** scénarios critiques automatisés réussis, échecs
  négatifs prouvés, aucune écriture MCP/IA et aucun réseau externe non
  contrôlé.
- **Tests automatisés :** processus pytest séparés ou packages sans collision,
  services locaux conteneurisés, doubles de l’External Product API et absence
  de réseau Internet réel.
- **Preuves :** rapports pytest, santé Compose, permissions read-only,
  captures Client Web et logs expurgés.
- **Repli non destructif :** conserver les groupes de tests isolés et les
  preuves partielles identifiées si un service est indisponible, sans
  suppression de données ni restauration destructive.

### P3-T06 — Finaliser lancement, preuves et démonstration

- **Écarts :** G5, preuves finales, guide d’installation et préparation de la
  démonstration.
- **Prérequis :** P3-T02 à P3-T05 validées, limites résiduelles connues,
  commandes reproductibles et preuves centralisées.
- **Dépendances interpersonnes :** revue croisée du README, disponibilité des
  trois responsables et validation manuelle finale.
- **Chemins pressentis :** `README.md`, documentation de configuration,
  `docs/test_evidence/`, checklist et support de démonstration.
- **Livrables :** guide configuration/build/seed/lancement/tests, limites,
  plan de démonstration de dix minutes et procédure de reprise.
- **Critères d'entrée :** toutes les commandes finales connues, aucun secret
  dans les exemples et environnement de démonstration préparé.
- **Critères de sortie :** un tiers suit le README avec succès, les preuves
  sont datées, la répétition de démonstration couvre les scénarios obligatoires
  et la revue QA manuelle est demandée.
- **Tests automatisés :** vérification des chemins/commandes documentés,
  smoke tests finaux et nouvelle exécution des suites isolées.
- **Preuves :** transcript de lancement, rapports, captures expurgées,
  checklist signée et journal de répétition.
- **Repli non destructif :** conserver le dernier environnement et jeu de
  preuves vérifiés, documenter toute limite résiduelle et basculer vers des
  données de démonstration préparées sans suppression ni restauration
  destructive.

## Stratégie de preuve

P3-T01 utilise les commandes locales normatives ci-dessous, toutes sans réseau
réel. Cette stratégie est donc **sans réseau réel**. Les suites qui possèdent
des modules homonymes restent dans des
**processus pytest séparés** :

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_person3_integration_plan.py integration_tests/test_person3_assets.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_product_mcp_tools.py tests/test_product_mcp_server.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_product_mcp_server.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_ai_classifier.py tests/test_ai_generator.py tests/test_ai_mcp_client.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_stock_mcp_server.py
```

Le premier groupe contrôle le présent plan et les actifs Personne 3. Les
quatre suivants protègent les baselines Product MCP unitaires, Product MCP
d’intégration, AI et Stock MCP d’intégration. Aucun groupe ne lance de socket,
de base distante ou d’API réelle.

Les scénarios **Docker** avec services réels sont expressément réservés à
P3-T04 et P3-T05. Ils devront utiliser des dépendances locales contrôlées,
publier des sorties de santé et conserver des logs expurgés. Une simple
présence de fichiers ou un test mocké ne sera pas présenté comme preuve qu’un
flux réel fonctionne.

## Sources

### Références documentaires

- `.codex/person3/PROJECT_REFERENCE.md` — mission, services attendus,
  démonstration et invariants.
- `.codex/person3/TASK_STATE.md` — ordre et état de P3-T01 à P3-T06.
- `.codex/person2/PROJECT_REFERENCE.md` — périmètres Product/Stock/AI,
  dépendances et frontières.
- `.codex/person2/TASK_STATE.md` — état des tâches Personne 2.
- `docs/person3_handoff.md` — responsabilités interfaces, Compose, E2E et
  documentation.
- `docs/project_context.md` — composants, flux, Product/Stock/AI, interface
  publique, organisation et définition de fini.
- `docs/architecture.md` — responsabilités, flux, accès DB, configuration,
  sept services Compose et rôles d’équipe.
- `docs/api_contracts.md` — sections 3 à 12.
- `docs/security_rules.md` — JWT, autorisations, CORS, MCP, logs et erreurs.
- `docs/testing_strategy.md` — niveaux, scénarios critiques et preuves.
- `docs/interface_client_web.md` — routes existantes et limites de l’interface.

### Code et preuves locales audités

- `docker-compose.yml` et `Dockerfile`.
- `backoffice/static/` et les routes/modules `backoffice/`.
- `client_web/`.
- `ai_service/`.
- `product_mcp_server/`.
- `stock_mcp_server/`.
- `integration_tests/test_person3_assets.py`.
- `integration_tests/test_person3_integration_plan.py`.
- `tests/test_stock_mcp_repository.py`.
- Les huit chemins Product MCP protégés listés dans le registre.

Les résultats préparatoires du contrat au 2026-07-29 sont conservés comme
état d’entrée, pas comme validation finale : actifs Personne 3 `8 passed`,
Product MCP unitaire `52 passed`, Product MCP intégration `14 passed`, Stock
MCP intégration `26 passed`, et groupe Stock unitaire + AI `399 passed,
1 failed` sur le désaccord de manifeste. Les codes retour réellement obtenus
après création du présent livrable sont consignés dans
`person3_handoffs/current/IMPLEMENTATION_REPORT.md`.
