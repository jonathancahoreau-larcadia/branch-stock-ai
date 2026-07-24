# Client Web — Interface utilisateur du Backoffice

## Présentation

`client_web` est une application **Flask** qui sert d'interface graphique au **Backoffice API**.
Elle permet aux utilisateurs de se connecter, consulter et gérer les stocks, et aux administrateurs
de gérer les utilisateurs — le tout via un navigateur web classique.

> **Principe :** client_web est un « frontal » (frontend) qui parle au Backoffice par HTTP.
> Il ne contient **aucune donnée**, **aucune base de données**, **aucune logique métier**.
> Son seul travail est d'afficher des pages HTML et de relayer les actions au Backoffice.

---

## Arborescence

```
client_web/
├── app.py                        # Application Flask (routes, session, décorateurs)
├── config.py                     # Configuration (URL du Backoffice, clés, timeouts)
├── requirements.txt              # Dépendances Python
├── README.md                     # Ce fichier
│
├── services/
│   ├── __init__.py
│   └── backoffice_client.py      # Client HTTP pour l'API Backoffice
│
├── static/
│   ├── favicon.ico               # Icône d'onglet
│   └── style.css                 # Styles de l'interface
│
├── templates/
│   ├── base.html                 # Template parent (navigation, layout)
│   ├── login.html                # Formulaire de connexion
│   ├── dashboard.html            # Tableau de bord utilisateur
│   ├── stock.html                # Consultation et gestion des stocks
│   └── users.html                # Gestion des utilisateurs (admin)
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # Fixtures de test (app, client HTTP, mock)
    └── test_routes.py            # 23 tests fonctionnels
```

---

## Flux des données (schéma textuel)

```
┌──────────────┐      HTTP       ┌────────────────┐      HTTP+JWT     ┌──────────────┐
│  Navigateur  │ ──────────────> │  client_web    │ ───────────────> │  Backoffice  │
│  (HTML/CSS)  │ <────────────── │  (Flask, 8080) │ <─────────────── │  (Flask, 5000)│
└──────────────┘    pages HTML   └────────────────┘    JSON (API)     └──────┬───────┘
                                                                             │
                                                                      ┌──────▼───────┐
                                                                      │  PostgreSQL  │
                                                                      └──────────────┘
```

**Étape par étape (exemple : connexion) :**

1. L'utilisateur remplit le formulaire de login et clique « Se connecter »
2. Le navigateur envoie `POST /login` à client_web (port 8080)
3. `app.py` reçoit la requête, extrait username/password
4. `BackofficeClient.login(username, password)` envoie `POST /api/v1/auth/login` au Backoffice (port 5000)
5. Le Backoffice valide les identifiants, retourne des **JWT** (JSON Web Tokens)
6. client_web stocke les tokens dans la **session Flask** (cookie signé)
7. L'utilisateur est redirigé vers `/dashboard`
8. Pour chaque action suivante (consulter le stock, ajouter un produit…), le token est automatiquement
   extrait de la session et passé dans l'en-tête `Authorization: Bearer <token>` de chaque appel HTTP au Backoffice

---

## Explication détaillée des fichiers

### `config.py` — Configuration centralisée

La classe `Config` rassemble **tous les réglages** de l'application. Les valeurs sont chargées
depuis des **variables d'environnement**, ce qui permet de changer le comportement sans modifier le code.

| Variable d'environnement  | Attribut           | Rôle |
|---------------------------|--------------------|------|
| `CLIENT_WEB_SECRET_KEY`   | `SECRET_KEY`       | Clé pour signer les cookies de session Flask |
| `BACKOFFICE_BASE_URL`     | `BACKOFFICE_BASE_URL` | URL de l'API Backoffice (ex: `http://backoffice:5000/api/v1`) |
| `BACKOFFICE_TIMEOUT`      | `BACKOFFICE_TIMEOUT`  | Timeout max (secondes) pour les appels HTTP au Backoffice |

Les trois attributs `ACCESS_TOKEN_KEY`, `REFRESH_TOKEN_KEY`, `USER_KEY` sont les noms des clés
utilisées dans la session Flask. Ils sont centralisés ici pour éviter les fautes de frappe.

---

### `services/backoffice_client.py` — Client HTTP pour le Backoffice

C'est le **pont** entre l'interface Flask et l'API REST du Backoffice.

#### `BackofficeResponse` (dataclass)

Structure simple qui normalise la réponse de l'API :
- `ok: bool` → l'appel a-t-il réussi ?
- `status_code: int` → code HTTP (200, 401, 503…)
- `data: dict | None` → les données utiles
- `error: dict | None` → les détails d'erreur

#### `BackofficeClient` (classe)

Chaque **méthode publique** correspond à une route de l'API Backoffice.
Le token JWT est passé en paramètre pour que le client reste **stateless** (pas d'état interne).

**Méthodes privées (infrastructure) :**

| Méthode | Rôle |
|---------|------|
| `_headers(token)` | Construit les en-têtes HTTP (Content-Type, Authorization) |
| `_parse(resp)` | Convertit une réponse `requests` en `BackofficeResponse` |
| `_get(path, token, params)` | Envoie une requête HTTP GET |
| `_post(path, token, json_body)` | Envoie une requête HTTP POST avec un corps JSON |
| `_patch(path, token, json_body)` | Envoie une requête HTTP PATCH |
| `_delete(path, token)` | Envoie une requête HTTP DELETE |

Toutes les méthodes privées gèrent les exceptions `ConnectionError` et `Timeout`
et retournent une `BackofficeResponse` avec un `ok=False` en cas d'échec réseau.

**Méthodes publiques (domaines métier) :**

| Domaine | Méthodes | Routes API correspondantes |
|---------|----------|---------------------------|
| **Auth** | `login`, `refresh_token`, `get_me`, `logout_access`, `logout_refresh` | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`, `POST /auth/logout` |
| **Users** | `list_users`, `get_user`, `create_user`, `update_user`, `change_user_password`, `delete_user` | `GET/POST/PATCH/DELETE /users` |
| **Branches** | `list_branches`, `get_branch` | `GET /branches` |
| **Products** | `list_products`, `get_product` | `GET /products` |
| **Stocks** | `list_stocks`, `get_stock`, `add_stock`, `remove_stock` | `GET /stocks`, `POST /stocks/…/add`, `POST /stocks/…/remove` |

---

### `app.py` — L'application Flask (le cœur)

C'est le fichier principal. Il contient :

#### `create_app(test_config)` — La *factory*

Fonction qui **crée et configure** l'instance Flask. C'est le point d'entrée :
```python
app = create_app()      # Production
app = create_app({…})   # Tests (configuration surchargée)
```

#### Helpers (fonctions internes)

| Fonction | Rôle |
|----------|------|
| `_get_session_user()` | Récupère l'utilisateur stocké en session |
| `_get_access_token()` | Récupère le JWT d'accès |
| `_get_refresh_token()` | Récupère le JWT de rafraîchissement |
| `_clear_session()` | Vide la session (déconnexion) |

#### Décorateurs

Ce sont des « filtres » qui s'appliquent avant l'exécution d'une route :

```python
@login_required
def dashboard(): …
```

| Décorateur | Effet |
|------------|-------|
| `@login_required` | Redirige vers `/login` si l'utilisateur n'est pas connecté |
| `@admin_required` | Redirige vers `/dashboard` si l'utilisateur n'est pas admin |

**Ordre d'application :** les décorateurs s'appliquent de bas en haut :
```python
@app.route("/users")
@login_required       # 2e : vérifie la connexion
@admin_required       # 1er : vérifie le rôle admin
def users(): …
```

#### Routes

| Route | Méthode | Accès | Description |
|-------|---------|-------|-------------|
| `/` | GET | Public | Redirige vers `/dashboard` ou `/login` |
| `/login` | GET, POST | Public | Formulaire de connexion + traitement |
| `/logout` | GET | Connecté | Révoque les tokens + vide la session |
| `/dashboard` | GET | Connecté | Affiche les infos de l'utilisateur |
| `/stock` | GET | Connecté | Liste le stock de la branche |
| `/stock/add` | POST | Connecté | Ajoute du stock |
| `/stock/remove` | POST | Connecté | Retire du stock |
| `/users` | GET | Admin | Liste les utilisateurs |
| `/users/create` | POST | Admin | Crée un utilisateur |
| `/users/<id>/delete` | POST | Admin | Supprime un utilisateur |
| `/users/<id>/password` | POST | Admin | Change le mot de passe |

#### Contexte processor

```python
@app.context_processor
def inject_globals():
    return {"current_user": _get_session_user()}
```

Cette fonction rend la variable `current_user` disponible dans **tous les templates**
sans avoir à la passer manuellement à chaque `render_template()`.

---

### Templates Jinja2

Les templates utilisent le système d'**héritage** de Jinja2 :
- `base.html` définit la structure commune (HTML, CSS, navigation)
- Les autres templates « étendent » base.html et ne définissent que le contenu spécifique

#### `base.html` — Structure commune

- Balise `<link>` pour le favicon et le CSS
- Menu de navigation qui s'affiche **uniquement si `current_user` existe**
- Liens conditionnels : « Utilisateurs » visible **seulement pour les admins**
- Blocs `{% block title %}` et `{% block content %}` que les enfants remplissent

#### `login.html` — Page de connexion

- Formulaire POST vers `/login`
- Affiche un message d'erreur si `error` est passé au template
- Design centré, largeur max 400px

#### `dashboard.html` — Tableau de bord

- Tableau des informations utilisateur (ID, username, rôle, branche)
- Badge coloré selon le rôle (admin / common user)
- Boutons d'actions rapides : « Voir le stock », « Gérer les utilisateurs » (admin)

#### `stock.html` — Gestion des stocks

- Filtres : « Disponible seulement » / « Tout »
- Tableau avec colonnes : Produit, Quantité, Actions
- Chaque ligne a deux formulaires inline :
  - Un pour ajouter du stock (bouton `+`)
  - Un pour retirer du stock (bouton `−`)
- Les formulaires envoient en POST vers `/stock/add` ou `/stock/remove`

#### `users.html` — Gestion des utilisateurs (admin)

- Filtres : Actifs / Supprimés / Tous
- Tableau complet avec ID, username, rôle, succursale, statut
- Actions par utilisateur :
  - **Supprimer** avec confirmation JavaScript (`confirm()`)
  - **Changer le mot de passe** (formulaire masqué, s'affiche au clic)
- Formulaire de **création d'utilisateur** en bas : username + password + sélection de succursale

---

### `static/style.css` — Styles

Utilise les **variables CSS** pour la cohérence des couleurs :
```css
:root {
  --accent: #0f3460;     /* Bleu principal */
  --error: #8a1c1c;      /* Rouge pour erreurs */
  --success: #1b7a3d;    /* Vert pour succès */
}
```

Convention de nommage **BEM** (Block Element Modifier) :
- `.nav` → bloc
- `.nav__link` → élément
- `.nav__link--logout` → élément modifié

---

### Tests

#### `conftest.py` — Fixtures

| Fixture | Rôle |
|---------|------|
| `app` | Crée l'application Flask avec une config de test |
| `client` | Crée un client HTTP de test (sans serveur) |
| `mock_backoffice` | Remplace le vrai BackofficeClient par un mock (MagicMock) |

#### `test_routes.py` — 23 tests fonctionnels

Tous les tests utilisent le **mock** pour simuler le Backoffice sans avoir besoin d'un vrai serveur.

| Classe de test | Nombre de tests | Scénarios couverts |
|---------------|:---------------:|--------------------|
| `TestLogin` | 5 | Affichage formulaire, login réussi, mauvais mot de passe, champs vides, déjà connecté |
| `TestLogout` | 2 | Déconnexion avec révocation, accès sans auth |
| `TestIndex` | 2 | Redirection selon état de connexion |
| `TestDashboard` | 2 | Affichage infos, accès sans auth |
| `TestStock` | 5 | Affichage, liste vide, erreur backoffice, ajout, retrait |
| `TestUsersAdmin` | 5 | Blocage common user, liste admin, création, suppression, changement MDP |

---

## Dépendances

```
Flask>=3.0,<4.0     # Framework web (routes, sessions, templates)
requests>=2.31,<3.0 # Appels HTTP vers le Backoffice
pytest>=8.0,<9.0    # Tests unitaires et fonctionnels
```

---

## Lancer l'application

```bash
# 1. Démarrer le Backoffice (dans un terminal)
cd backoffice
FLASK_APP=app.py FLASK_DEBUG=1 python -m flask run --port=5000

# 2. Démarrer le client web (dans un autre terminal)
cd client_web
FLASK_APP=app.py FLASK_DEBUG=1 \
  CLIENT_WEB_SECRET_KEY=ma-cle-secrete \
  BACKOFFICE_BASE_URL=http://localhost:5000/api/v1 \
  python -m flask run --port=8080
```

Puis ouvrir **http://localhost:8080** dans le navigateur.

---

## Lancer les tests

```bash
cd client_web
python -m pytest tests/ -v
```

---

## Points clés à retenir

| Concept | Explication |
|---------|-------------|
| **client_web est un frontal** | Il ne fait qu'afficher des pages et relayer les actions au Backoffice |
| **Pas de base de données** | Toutes les données sont stockées dans le Backoffice et sa base PostgreSQL |
| **Authentification par JWT** | Les tokens sont stockés dans la session Flask, pas dans une base |
| **Séparation des rôles** | Les admins ont accès à la gestion des utilisateurs, les common users uniquement aux stocks |
| **Tests sans dépendance** | Le mock BackofficeClient permet de tester toutes les routes sans Backoffice réel |
| **Configuration par variables d'environnement** | Permet de changer l'URL du Backoffice ou la clé secrète sans modifier le code |