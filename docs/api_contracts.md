# Contrats d’API — HBntory

## 1. Conventions générales

### Base URL du Backoffice

```text
/api/v1
```

### Format

```http
Content-Type: application/json
```

Champs en `snake_case`, texte UTF-8, dates ISO 8601 UTC.

### Réponse de succès

```json
{
  "data": {}
}
```

Pour une liste :

```json
{
  "data": [],
  "meta": {
    "count": 0
  }
}
```

### Réponse d’erreur

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message.",
    "details": {}
  }
}
```

Aucune réponse ne contient :

- mot de passe ;
- hash ;
- JWT complet ;
- clé API ;
- SQL ;
- traceback ;
- chaîne de connexion.

---

## 2. Authentification JWT

### En-tête

```http
Authorization: Bearer <token>
```

### Durées

```text
Access token: 1800 secondes
Refresh token: 604800 secondes
```

### Claims minimums

```text
sub
jti
type
iat
exp
token_version
```

Le backend recharge toujours l’utilisateur actuel et vérifie :

- compte actif ;
- absence de suppression logique ;
- rôle actuel ;
- branche actuelle ;
- `token_version` actuel ;
- blocklist.

---

## 3. Authentification

### 3.1 Connexion

```http
POST /api/v1/auth/login
```

Corps :

```json
{
  "username": "alice",
  "password": "secret-password"
}
```

Succès `200` :

```json
{
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "Bearer",
    "access_token_expires_in": 1800,
    "refresh_token_expires_in": 604800,
    "user": {
      "id": 12,
      "username": "alice",
      "role": "common_user",
      "branch": {
        "id": 2,
        "name": "Toulon"
      }
    }
  }
}
```

Erreurs :

| HTTP | Code |
|---:|---|
| `400` | `VALIDATION_ERROR` |
| `401` | `INVALID_CREDENTIALS` |
| `403` | `ACCOUNT_INACTIVE` |

Le message de connexion ne révèle pas si le nom d’utilisateur existe.

### 3.2 Rafraîchir l’access token

```http
POST /api/v1/auth/refresh
Authorization: Bearer <refresh_token>
```

Succès `200` :

```json
{
  "data": {
    "access_token": "new-access-token",
    "token_type": "Bearer",
    "access_token_expires_in": 1800
  }
}
```

Erreurs :

```text
AUTHENTICATION_REQUIRED
TOKEN_INVALID
TOKEN_EXPIRED
TOKEN_REVOKED
WRONG_TOKEN_TYPE
ACCOUNT_INACTIVE
TOKEN_VERSION_INVALID
```

### 3.3 Révoquer l’access token

```http
POST /api/v1/auth/logout
Authorization: Bearer <access_token>
```

Succès :

```text
204 No Content
```

Le `jti` est ajouté à la blocklist.

### 3.4 Révoquer le refresh token

```http
POST /api/v1/auth/logout/refresh
Authorization: Bearer <refresh_token>
```

Succès :

```text
204 No Content
```

Lors d’une déconnexion normale, le frontend appelle les deux routes puis efface `sessionStorage`.

### 3.5 Utilisateur courant

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

Succès `200` :

```json
{
  "data": {
    "id": 12,
    "username": "alice",
    "role": "common_user",
    "branch": {
      "id": 2,
      "name": "Toulon"
    }
  }
}
```

---

## 4. Utilisateurs — Admin uniquement

Toutes les routes utilisent un access token de rôle `admin`.

### 4.1 Lister

```http
GET /api/v1/users?status=active&branch_id=2
```

`status` :

```text
active
deleted
all
```

Succès :

```json
{
  "data": [
    {
      "id": 12,
      "username": "alice",
      "role": "common_user",
      "branch": {
        "id": 2,
        "name": "Toulon"
      },
      "is_active": true,
      "deleted_at": null
    }
  ],
  "meta": {
    "count": 1
  }
}
```

### 4.2 Créer un common user

```http
POST /api/v1/users
```

Corps :

```json
{
  "username": "alice",
  "password": "secret-password",
  "branch_id": 2
}
```

Le client ne fournit pas `role`.

Le serveur impose :

```text
role = common_user
```

Succès `201`.

Erreurs principales :

```text
BRANCH_NOT_FOUND
USERNAME_ALREADY_EXISTS
RESERVED_USERNAME
VALIDATION_ERROR
```

### 4.3 Consulter

```http
GET /api/v1/users/{user_id}
```

Succès `200`, erreur `USER_NOT_FOUND`.

### 4.4 Modifier

```http
PATCH /api/v1/users/{user_id}
```

Champs autorisés :

```json
{
  "username": "alice.dupont",
  "branch_id": 3
}
```

Champs interdits :

```text
role
password
password_hash
is_active
deleted_at
token_version
```

L’administrateur lui-même n’est pas modifiable par cette route.

### 4.5 Changer le mot de passe

```http
PATCH /api/v1/users/{user_id}/password
```

Corps :

```json
{
  "new_password": "new-secret-password"
}
```

Effets :

- nouveau hash bcrypt ;
- incrément de `token_version`;
- anciens access et refresh tokens invalides.

Succès :

```text
204 No Content
```

### 4.6 Suppression logique

```http
DELETE /api/v1/users/{user_id}
```

Effets :

```text
is_active = false
deleted_at = now
```

Aucun stock n’est supprimé.

Succès :

```text
204 No Content
```

---

## 5. Succursales

Aucune route de création, modification ou suppression n’appartient au MVP.

### 5.1 Lister

```http
GET /api/v1/branches
Authorization: Bearer <access_token>
```

- admin : toutes les succursales ;
- common user : sa succursale uniquement.

### 5.2 Consulter

```http
GET /api/v1/branches/{branch_id}
```

Un common user ne peut consulter que sa succursale.

---

## 6. Produits dans le Backoffice

Ces routes proxifient l’API Produit sans persistance locale.

### 6.1 Lister les produits

```http
GET /api/v1/products
```

Succès :

```json
{
  "data": [
    {
      "external_product_id": "product-123",
      "name": "Example product"
    }
  ],
  "meta": {
    "count": 1
  }
}
```

Les champs dépendent du contrat réel de l’API Produit.

### 6.2 Détail d’un produit

```http
GET /api/v1/products/{external_product_id}
```

Erreurs :

```text
PRODUCT_NOT_FOUND
PRODUCT_API_UNAVAILABLE
PRODUCT_API_TIMEOUT
PRODUCT_API_INVALID_RESPONSE
```

---

## 7. Stock — Common user uniquement

Toutes les routes utilisent la branche actuelle du compte authentifié.

Un `branch_id` fourni par le client est rejeté comme champ inattendu.

### 7.1 Lister les produits actuellement en stock

```http
GET /api/v1/stocks?available_only=true
```

Valeur par défaut :

```text
available_only = true
```

Succès :

```json
{
  "data": {
    "branch": {
      "id": 2,
      "name": "Toulon"
    },
    "items": [
      {
        "external_product_id": "product-123",
        "quantity": 8,
        "product": {
          "name": "Example product"
        }
      }
    ]
  },
  "meta": {
    "count": 1
  }
}
```

Avec `available_only=false`, les lignes à zéro peuvent être incluses.

Les détails `product` viennent de l’API externe et ne sont pas stockés.

### 7.2 Consulter une quantité

```http
GET /api/v1/stocks/{external_product_id}
```

Une quantité de zéro est une réponse valide.

Succès :

```json
{
  "data": {
    "branch": {
      "id": 2,
      "name": "Toulon"
    },
    "external_product_id": "product-123",
    "quantity": 0,
    "product": {
      "name": "Example product"
    }
  }
}
```

### 7.3 Ajouter

```http
POST /api/v1/stocks/{external_product_id}/add
```

Corps :

```json
{
  "quantity": 3
}
```

Règles :

- entier strictement positif ;
- produit existant ;
- branche issue de l’utilisateur ;
- transaction ;
- création ou augmentation atomique.

Succès `200` avec la quantité finale.

### 7.4 Retirer

```http
POST /api/v1/stocks/{external_product_id}/remove
```

Corps :

```json
{
  "quantity": 3
}
```

Règles :

- entier strictement positif ;
- ligne verrouillée ;
- stock suffisant ;
- ligne conservée à zéro.

Erreurs :

```text
STOCK_NOT_FOUND
INVALID_QUANTITY
INSUFFICIENT_STOCK
STOCK_CONFLICT
```

L’administrateur reçoit `ADMIN_STOCK_FORBIDDEN`.

---

## 8. AI Query Service

### 8.1 Endpoint public

```http
POST /questions
Content-Type: application/json
```

Aucune authentification.

Corps :

```json
{
  "question": "Which branch has three units of product X?"
}
```

Validation :

- objet JSON ;
- `question` obligatoire ;
- chaîne non vide ;
- taille maximale recommandée : 1000 caractères ;
- aucune mémoire conversationnelle.

### 8.2 Statuts métier

```text
success
partial
unavailable
unsupported
```

#### Success

```json
{
  "status": "success",
  "answer": "The product is available in Toulon with 8 units.",
  "data": {
    "products": [
      {
        "external_product_id": "product-123",
        "name": "Example product"
      }
    ],
    "branches": [
      {
        "branch_id": 2,
        "branch_name": "Toulon",
        "available_quantity": 8
      }
    ]
  }
}
```

#### Partial

Certaines données sont disponibles, mais pas toutes.

#### Unavailable

```json
{
  "status": "unavailable",
  "answer": "I do not have enough information to answer this question.",
  "data": {}
}
```

#### Unsupported

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

Une absence réelle de stock ou une question hors périmètre retourne `200`, car il s’agit d’un résultat métier, pas d’une panne HTTP.

---

## 9. Contrats MCP

### 9.1 Format de succès

```json
{
  "status": "success",
  "data": {}
}
```

### 9.2 Format not found

```json
{
  "status": "not_found",
  "data": null
}
```

### 9.3 Format d’erreur

```json
{
  "status": "error",
  "error": {
    "code": "MCP_ERROR_CODE",
    "message": "Human-readable message."
  }
}
```

---

## 10. Product MCP

### 10.1 `list_products`

```python
list_products() -> dict
```

Succès :

```json
{
  "status": "success",
  "data": {
    "products": [
      {
        "external_product_id": "product-123",
        "name": "Example product"
      }
    ]
  }
}
```

### 10.2 `get_product_details`

```python
get_product_details(external_product_id: str) -> dict
```

Erreurs :

```text
INVALID_EXTERNAL_PRODUCT_ID
PRODUCT_API_UNAVAILABLE
PRODUCT_API_TIMEOUT
PRODUCT_API_INVALID_RESPONSE
```

Un produit inconnu retourne `status: "not_found"`.

---

## 11. Stock MCP

Le Stock MCP est strictement en lecture seule.

### 11.1 `list_branch_stock`

```python
list_branch_stock(branch_id: int) -> dict
```

Retourne uniquement les produits avec quantité positive par défaut.

### 11.2 `get_stock_for_product`

```python
get_stock_for_product(external_product_id: str) -> dict
```

Retourne toutes les succursales et quantités connues.

Une liste vide n’est pas une erreur.

### 11.3 `find_branches_with_stock`

```python
find_branches_with_stock(
    external_product_id: str,
    quantity: int
) -> dict
```

Retourne les succursales avec :

```text
available_quantity >= requested_quantity
```

### 11.4 `find_branches_for_shopping_list`

```python
find_branches_for_shopping_list(items: list[dict]) -> dict
```

Entrée :

```json
{
  "items": [
    {
      "external_product_id": "product-123",
      "quantity": 3
    },
    {
      "external_product_id": "product-456",
      "quantity": 2
    }
  ]
}
```

Succès complet :

```json
{
  "status": "success",
  "data": {
    "complete": true,
    "strategy": "single_branch",
    "visits": [
      {
        "branch_id": 2,
        "branch_name": "Toulon",
        "items": [
          {
            "external_product_id": "product-123",
            "requested_quantity": 3,
            "available_quantity": 8
          }
        ]
      }
    ],
    "missing_items": []
  }
}
```

Succès incomplet :

```json
{
  "status": "success",
  "data": {
    "complete": false,
    "strategy": "unavailable",
    "visits": [],
    "missing_items": [
      {
        "external_product_id": "product-456",
        "missing_quantity": 2
      }
    ]
  }
}
```

---

## 12. Health Checks

Services HTTP :

```http
GET /health
```

Succès :

```json
{
  "status": "ok"
}
```

État dégradé possible :

```json
{
  "status": "degraded",
  "dependencies": {
    "database": "ok",
    "product_api": "unavailable"
  }
}
```

Aucun secret n’est exposé.

---

## 13. Catalogue des erreurs

| Code | HTTP | Signification |
|---|---:|---|
| `INVALID_JSON` | `400` | JSON invalide |
| `VALIDATION_ERROR` | `400` | Données invalides |
| `AUTHENTICATION_REQUIRED` | `401` | Bearer absent |
| `INVALID_CREDENTIALS` | `401` | Connexion refusée |
| `TOKEN_INVALID` | `401` | JWT invalide |
| `TOKEN_EXPIRED` | `401` | JWT expiré |
| `TOKEN_REVOKED` | `401` | `jti` révoqué |
| `WRONG_TOKEN_TYPE` | `401` | Mauvais type |
| `TOKEN_VERSION_INVALID` | `401` | Ancienne version |
| `ACCOUNT_INACTIVE` | `403` | Compte désactivé |
| `FORBIDDEN` | `403` | Rôle insuffisant |
| `ADMIN_STOCK_FORBIDDEN` | `403` | Admin sur stock |
| `BRANCH_ACCESS_FORBIDDEN` | `403` | Mauvaise branche |
| `USER_NOT_FOUND` | `404` | Utilisateur inconnu |
| `BRANCH_NOT_FOUND` | `404` | Succursale inconnue |
| `PRODUCT_NOT_FOUND` | `404` | Produit inconnu |
| `STOCK_NOT_FOUND` | `404` | Stock inconnu |
| `USERNAME_ALREADY_EXISTS` | `409` | Nom déjà utilisé |
| `STOCK_CONFLICT` | `409` | Concurrence |
| `RESERVED_USERNAME` | `422` | `admin` réservé |
| `INVALID_QUANTITY` | `422` | Quantité incorrecte |
| `INSUFFICIENT_STOCK` | `422` | Stock insuffisant |
| `PRODUCT_API_ERROR` | `502` | Réponse externe incorrecte |
| `MCP_ERROR` | `502` | Erreur MCP |
| `PRODUCT_API_UNAVAILABLE` | `503` | API indisponible |
| `MCP_UNAVAILABLE` | `503` | MCP indisponible |
| `AI_PROVIDER_UNAVAILABLE` | `503` | Modèle indisponible |
| `UPSTREAM_TIMEOUT` | `504` | Timeout |
| `INTERNAL_ERROR` | `500` | Erreur inattendue |

---

## 14. Tableau des routes

| Méthode | Route | Autorisation |
|---|---|---|
| `POST` | `/api/v1/auth/login` | Publique |
| `POST` | `/api/v1/auth/refresh` | Refresh JWT |
| `POST` | `/api/v1/auth/logout` | Access JWT |
| `POST` | `/api/v1/auth/logout/refresh` | Refresh JWT |
| `GET` | `/api/v1/auth/me` | Access JWT |
| `GET` | `/api/v1/users` | Admin |
| `POST` | `/api/v1/users` | Admin |
| `GET` | `/api/v1/users/{id}` | Admin |
| `PATCH` | `/api/v1/users/{id}` | Admin |
| `PATCH` | `/api/v1/users/{id}/password` | Admin |
| `DELETE` | `/api/v1/users/{id}` | Admin |
| `GET` | `/api/v1/branches` | Access JWT |
| `GET` | `/api/v1/branches/{id}` | Access JWT |
| `GET` | `/api/v1/products` | Access JWT |
| `GET` | `/api/v1/products/{external_product_id}` | Access JWT |
| `GET` | `/api/v1/stocks` | Common user |
| `GET` | `/api/v1/stocks/{external_product_id}` | Common user |
| `POST` | `/api/v1/stocks/{external_product_id}/add` | Common user |
| `POST` | `/api/v1/stocks/{external_product_id}/remove` | Common user |
| `POST` | `/questions` | Publique |
| `GET` | `/health` | Publique |
