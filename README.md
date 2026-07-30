# HBntory

HBntory est une plateforme pédagogique locale de gestion de stock. Le
Backoffice authentifié gère les utilisateurs et les quantités d’une
succursale ; le Client Web public répond à des questions indépendantes à
partir des catalogues Produit et Stock exposés en lecture seule par MCP.

## Prérequis

- Docker Engine avec le plugin Docker Compose ;
- les images de base accessibles lors d’un premier build, ou les images
  HBntory déjà construites pour un lancement hors réseau ;
- Python 3, `pytest` et les dépendances déjà déclarées pour les tests ;
- Node.js 18 pour les seuls tests d’interface existants ;
- assez de mémoire et de ports libres pour les huit services ;
- un fichier d’environnement externe au dépôt, privé et non versionné.

Le lancement standard n’exige pas Ollama : l’AI Query Service utilise alors
son classificateur et son générateur déterministes. L’activation optionnelle
d’Ollama exige un runtime local configuré séparément ; aucun neuvième service
Ollama n’est déclaré dans le Compose actuel.

## Préparer le fichier `.env` externe

Ne placez aucune valeur réelle dans Git. Copiez le gabarit vers un chemin
extérieur au dépôt, limitez ses permissions, puis éditez uniquement cette
copie :

```bash
cp .env.example ../hbntory-runtime.env
chmod 600 ../hbntory-runtime.env
HBN_RUNTIME_ENV_FILE=../hbntory-runtime.env
export HBN_RUNTIME_ENV_FILE
```

Les valeurs ci-dessous sont des exemples manifestement factices. Les trois
URL de base de données doivent être complétées dans le fichier privé avec le
schéma PostgreSQL approprié, l’hôte interne `database`, le port `5432`, le
nom `POSTGRES_DB`, et l’identité dédiée correspondante. N’affichez jamais ce
fichier dans un rapport ou un terminal partagé.

Le bootstrap et l’API refusent au démarrage les valeurs vides ou manifestement
factices (`replace-with-…`, `replace_me`, `<…>` et `${…}`) pour les secrets,
les quatre mots de passe PostgreSQL et les trois URL PostgreSQL. Le message
d’erreur nomme uniquement la variable concernée, jamais sa valeur.

| Variable | Exemple factice / règle |
|---|---|
| `POSTGRES_DB` | `hbntory_example` |
| `POSTGRES_USER` | `bootstrap_example` |
| `POSTGRES_PASSWORD` | `<secret-bootstrap-factice>` |
| `MIGRATION_DB_USER` | `migration_user` (nom imposé) |
| `MIGRATION_DB_PASSWORD` | `<secret-migration-factice>` |
| `BACKOFFICE_DB_USER` | `backoffice_app` (nom imposé) |
| `BACKOFFICE_DB_PASSWORD` | `<secret-backoffice-factice>` |
| `STOCK_MCP_DB_USER` | `stock_reader` (nom imposé) |
| `STOCK_MCP_DB_PASSWORD` | `<secret-lecture-factice>` |
| `MIGRATION_DATABASE_URL` | `<url-postgresql-migration-factice>` |
| `DATABASE_URL` | `<url-postgresql-backoffice-factice>` |
| `STOCK_MCP_DATABASE_URL` | `<url-postgresql-stock-factice>` |
| `JWT_SECRET_KEY` | `<cle-jwt-longue-et-factice>` |
| `ADMIN_INITIAL_PASSWORD` | `<mot-de-passe-admin-factice>` |
| `APP_ENV` | `development` pour un environnement local explicite |
| `LARGE_SEED_USER_PASSWORD` | `<mot-de-passe-utilisateur-demo-factice>` |
| `SEED_PRODUCT_ID` | `HB-MON-2102` |
| `BCRYPT_ROUNDS` | `12` |
| `PRODUCT_API_TIMEOUT` | `5` |
| `CLIENT_WEB_ORIGIN` | `http://127.0.0.1:3000` |
| `BACKOFFICE_UI_PORT` | `8080` |
| `CLIENT_WEB_PORT` | `3000` |

Les quatre identités PostgreSQL sont distinctes. Le bootstrap crée ou aligne
les rôles ; `migration_user` applique les migrations, `backoffice_app` sert
l’API métier et `stock_reader` ne lit que les branches et stocks nécessaires.
Les produits restent dans l’External Product API et ne sont jamais dupliqués
dans PostgreSQL.

Validez la syntaxe sans révéler les valeurs :

```bash
test -n "${HBN_RUNTIME_ENV_FILE:-}" && test -r "$HBN_RUNTIME_ENV_FILE"
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" config --quiet
```

Cette étape correspond au contrôle `docker compose config`.

## Les huit services

| Service Compose | Responsabilité | Port |
|---|---|---:|
| `database` | PostgreSQL : utilisateurs, succursales, stocks et révocations | `5432` interne |
| `external-products-api` | source officielle du catalogue produit | `5000` interne |
| `backoffice-api` | API Flask, JWT, utilisateurs et mouvements de stock | `5000` interne |
| `backoffice-ui` | interface Nginx du Backoffice | `8080` public par défaut |
| `product_mcp_server` | outils produit MCP en lecture seule | `8100` interne |
| `stock_mcp_server` | outils stock MCP avec compte SQL en lecture seule | `8200` interne |
| `ai_service` | route publique de questions et orchestration MCP | `8000` interne |
| `client_web` | interface publique Nginx et proxy vers l’IA | `3000` public par défaut |

Les huit services partagent `branch-stock-internal`, réseau déclaré
`internal: true`. Seuls `backoffice-ui` et `client_web` rejoignent en plus le
réseau non interne `branch-stock-public` et publient respectivement
`127.0.0.1:${BACKOFFICE_UI_PORT:-8080}:80` et
`127.0.0.1:${CLIENT_WEB_PORT:-3000}:80`. Aucun service métier ni PostgreSQL
n’est publié sur l’hôte.

## Build, initialisation et lancement

Pour initialiser l’environnement, le lancement attend les dépendances puis
exécute automatiquement la migration et le seed idempotent.

Pour un premier lancement autorisé à construire les images :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" build
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" up --detach --wait
```

Il s’agit du flux `docker compose up` avec construction préalable.

Pour réutiliser strictement les images locales déjà validées, sans build ni
téléchargement :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" up --detach --wait --no-build --pull never
```

L’entrée du `backoffice-api` attend PostgreSQL et l’API Produits, aligne les
rôles, exécute la migration puis le seed avant Gunicorn. La migration et le
seed sont idempotents : les relancer avec la même configuration conserve les
données compatibles. Le seed crée le compte unique `admin`, les succursales
Toulon et Marseille, puis le stock d’exemple de `SEED_PRODUCT_ID`. Son mot de
passe est exclusivement la valeur privée de `ADMIN_INITIAL_PASSWORD`, hachée
avec bcrypt ; aucun compte common user n’est précréé.

Le seed refuse un produit absent, arrêté ou incohérent et annule sa
transaction au lieu de laisser un état partiel. Un conflit avec des données
initiales déjà modifiées doit être diagnostiqué, pas contourné par une
réinitialisation.

Pour remplacer ensuite le mot de passe du compte admin unique par la valeur
privée courante de `ADMIN_INITIAL_PASSWORD`, utilisez :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" exec backoffice-api \
  flask --app backoffice admin-password
```

La commande refuse les placeholders, réutilise bcrypt, incrémente
`token_version` pour invalider les anciens JWT et effectue un rollback si le
compte admin est absent ou incohérent. Elle n’affiche ni mot de passe ni hash.

## Grand jeu de démonstration local

Le petit seed exécuté au démarrage reste inchangé : il crée l’admin, Toulon,
Marseille et le stock minimal obligatoire. La commande indépendante
`seed-large` complète ce socle avec un volume destiné aux démonstrations.
Elle n’est jamais exécutée automatiquement.

La commande est autorisée seulement si `APP_ENV` vaut explicitement
`development`, `local`, `demo` ou `test`. Elle refuse toute valeur absente,
inconnue, `prod` ou `production`. Définissez dans le fichier runtime privé :

```env
APP_ENV=development
LARGE_SEED_USER_PASSWORD=<valeur-réelle-privée>
```

Le mot de passe est obligatoire uniquement pour `seed-large`. Il est refusé
s’il est vide, factice ou supérieur à 72 octets UTF-8, puis haché avec
bcrypt. Il n’est jamais affiché.

Vérifiez d’abord le plan sans écrire dans PostgreSQL :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" exec backoffice-api \
  flask --app backoffice seed-large --dry-run
```

Créez ensuite le jeu par défaut :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" exec backoffice-api \
  flask --app backoffice seed-large
```

Options disponibles :

```text
--branches INTEGER          15 par défaut, de 1 à 15
--users-per-branch INTEGER  3 par défaut, strictement positif
--seed INTEGER              42 par défaut
--dry-run                   validation sans écriture
```

Avec le catalogue de démonstration de 40 produits, les valeurs par défaut
produisent 15 succursales réservées, 45 common users et 600 lignes de stock.
Les succursales commencent par `Démo Large —` et les identifiants utilisateurs
par `demo-`, par exemple `demo-marseille-01`. Le mot de passe reste uniquement
dans le fichier runtime privé.

Toute la pagination de l’External Product API est validée avant la transaction.
PostgreSQL reçoit seulement les SKU externes et les quantités ; aucun nom,
prix, fournisseur ou autre détail Produit n’est copié. Environ 20 % des
lignes restent à zéro, 20 % contiennent 1 à 5 unités et les autres 6 à 200,
selon la graine déterministe.

Une nouvelle exécution identique complète uniquement les lignes manquantes
sûres et ne crée aucun doublon. Une donnée réservée incompatible provoque un
rollback sans écrasement. Il n’existe volontairement ni option de reset ni
historique de mouvements : le schéma officiel reste inchangé et les données
manuelles ne sont jamais supprimées.

Même si la commande est additive, effectuez une sauvegarde PostgreSQL avant
de préparer une démonstration importante, selon la procédure validée de votre
environnement. Gardez le dump et le fichier runtime hors du dépôt et ne
recopiez aucune URL privée dans une preuve.

## Accès et contrôles de santé

- Backoffice : `http://127.0.0.1:8080`
- Client Web : `http://127.0.0.1:3000`

Les adresses suivantes sont les sondes locales des conteneurs. Elles
documentent les endpoints, mais ne sont pas publiées directement sur l’hôte
par le Compose :

- Backoffice API : `http://127.0.0.1:5000/health`
- Product MCP : `http://127.0.0.1:8100/health`
- Stock MCP : `http://127.0.0.1:8200/health`
- AI Query Service : `http://127.0.0.1:8000/health`

Le Backoffice publie aussi sa santé via
`http://127.0.0.1:8080/health`. Contrôlez d’abord les états Compose :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" ps --all
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" exec backoffice-api python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:5000/health")))'
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" exec product_mcp_server python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8100/health")))'
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" exec stock_mcp_server python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8200/health")))'
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" exec ai_service python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8000/health")))'
```

Le diagnostic commence donc par `docker compose ps`.

Connectez-vous au Backoffice avec l’identité `admin` et le mot de passe
conservé dans le fichier privé. L’admin gère les common users mais ne modifie
pas les stocks. Chaque common user est assigné à une seule succursale et le
backend dérive cette succursale du compte authentifié. Le Client Web est
anonyme et chaque question est indépendante.

## Tests sans réseau réel

Exécutez les neuf groupes dans neuf processus séparés, dans cet ordre. Cette
séparation évite les collisions entre modules Product MCP et Stock MCP
homonymes. Les tests remplacent les transports externes par des doubles et ne
lancent ni Docker ni réseau réel.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_person3_documentation.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_person3_end_to_end.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_backoffice_ui.py integration_tests/test_client_web_ui.py integration_tests/test_person3_assets.py integration_tests/test_person3_docker.py integration_tests/test_person3_integration_plan.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider backoffice/tests/test_auth_routes.py backoffice/tests/test_users_routes.py backoffice/tests/test_branches_routes.py backoffice/tests/test_products_routes.py backoffice/tests/test_stocks_routes.py backoffice/tests/test_health.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_ai_classifier.py tests/test_ai_generator.py tests/test_ai_ollama_client.py tests/test_ai_question_service.py tests/test_ai_server.py tests/test_ai_mcp_client.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_product_mcp_tools.py tests/test_product_mcp_server.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_product_mcp_server.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_stock_mcp_repository.py tests/test_stock_mcp_tools.py tests/test_stock_mcp_server.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider integration_tests/test_stock_mcp_server.py
```

Les tests propres au grand seed s’exécutent séparément :

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  backoffice/tests/test_large_seed.py \
  backoffice/tests/test_large_seed_postgresql.py
```

Le second fichier utilise la fixture PostgreSQL protégée et est ignoré si
`TEST_DATABASE_URL` ne désigne pas une base ou un schéma de test explicite.

Les résultats datés et expurgés de P3-T06 sont indexés dans
`docs/test_evidence/README.md`. Le transcript manuel Product MCP reste une
preuve distincte des groupes pytest.

## Diagnostic

1. Exécutez `docker compose --env-file "$HBN_RUNTIME_ENV_FILE" config --quiet`.
   Une erreur à ce stade indique une variable absente ou une URL privée mal
   structurée.
2. Exécutez `docker compose --env-file "$HBN_RUNTIME_ENV_FILE" ps --all` et
   identifiez le premier service non sain dans l’ordre
   `database`, `external-products-api`, `backoffice-api`, MCP, IA, interfaces.
3. Consultez une fenêtre courte et ciblée :
   `docker compose --env-file "$HBN_RUNTIME_ENV_FILE" logs --tail=100 <service>`.
   Gardez les logs bruts privés ; ne copiez dans une preuve qu’un résumé
   expurgé sans valeur d’environnement, jeton, en-tête ou chaîne de connexion.
4. Si le seed échoue, vérifiez la disponibilité de `SEED_PRODUCT_ID` dans
   l’API Produits et la cohérence des données existantes. Ne supprimez pas la
   base.
5. Si le Client Web répond mais l’IA est indisponible, vérifiez successivement
   `ai_service`, `product_mcp_server`, `stock_mcp_server`, puis leurs
   dépendances officielles.

La troisième étape est le contrôle ciblé `docker compose logs`.

## Reprise non destructive et arrêt

Conservez le fichier d’environnement privé, le volume PostgreSQL et le dernier
jeu de démonstration validé. Pour reprendre un service défaillant :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" restart <service>
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" up --detach --wait --no-build --pull never
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" ps --all
```

Pour arrêter l’environnement sans suppression de volume :

```bash
docker compose --env-file "$HBN_RUNTIME_ENV_FILE" down
```

Cette commande applique `docker compose down` sans suppression de volume.

N’utilisez pas d’option de retrait de volume, de restauration ou de
réinitialisation comme procédure de dépannage. En démonstration, si un état
muté ne correspond plus au seed idempotent, conservez-le et basculez vers les
données préparées déjà vérifiées.

## Limites connues

- aucune création, modification ou suppression de succursale ;
- aucun historique de conversation et aucune persistance des questions ;
- aucun WebSocket ni streaming ;
- aucune rotation automatique des refresh tokens ;
- les jetons du Backoffice utilisent `sessionStorage` ;
- TLS n’est pas imposé par l’exercice ; hors usage pédagogique local, HTTPS
  est obligatoire pour protéger l’authentification ;
- l’affichage produit, le seed et Product MCP dépendent de l’External Product
  API ;
- les questions IA sont limitées aux détails produit, disponibilités,
  inventaires de succursale et listes d’achats documentés ;
- Ollama est optionnel et absent du Compose ; lorsqu’il est activé, il peut
  proposer l’intention structurée, mais la réponse publique française ou
  anglaise reste toujours générée localement et de manière déterministe ;
- l’interface est volontairement simple et le projet n’est pas une
  configuration de production publique.

## Frontières de sécurité

L’External Product API est l’unique source produit. Product MCP ne lit pas
PostgreSQL ; Stock MCP n’écrit jamais et ne peut lire ni utilisateurs ni
révocations. L’AI Query Service sélectionne seulement les outils approuvés et
ne modifie aucun stock. Les quantités ne deviennent jamais négatives, un
common user reste limité à sa succursale et les autorisations sont imposées
par le backend. Aucun secret, mot de passe, hash, JWT, jeton complet, en-tête
sensible, URI privée ou contenu du fichier d’environnement ne doit être
consigné.
