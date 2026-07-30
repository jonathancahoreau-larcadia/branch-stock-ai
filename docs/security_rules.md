# Règles de sécurité — HBntory

## 1. Principes

- moindre privilège ;
- validation côté serveur ;
- aucun secret dans Git ;
- aucun mot de passe en clair ;
- aucune confiance dans les champs d’autorisation envoyés par le navigateur ;
- aucun accès SQL libre pour l’agent ;
- aucune donnée produit interdite dans PostgreSQL.

---

## 2. Mots de passe

Mécanisme :

```text
bcrypt
```

Règles :

- hachage avant insertion ;
- vérification par la fonction bcrypt dédiée ;
- coût configurable ;
- aucun log du mot de passe ou du hash ;
- mot de passe initial admin fourni par variable d’environnement.
- valeurs vides et placeholders manifestes (`replace-with-…`, `replace_me`,
  `<…>`, `${…}`) refusés au runtime sans recopier leur contenu dans l’erreur ;
- la commande `flask --app backoffice admin-password` re-hache la valeur
  runtime, incrémente `token_version` et applique mise à jour ou rollback en
  une transaction.

Pourquoi pas SHA-256 seul :

- trop rapide ;
- pas conçu pour ralentir le brute force ;
- aucun coût adaptatif ;
- gestion du sel non intégrée comme bcrypt.

---

## 3. JWT

### Durées

```text
Access: 30 minutes
Refresh: 7 jours
```

### Transport

```http
Authorization: Bearer <token>
```

Aucun token d’authentification dans un cookie.

### Claims vérifiés

```text
signature
sub
jti
type
iat
exp
token_version
```

### Source de vérité

À chaque requête protégée, le backend recharge :

```text
is_active
deleted_at
role
branch_id
token_version
```

Les autorisations ne reposent jamais uniquement sur un ancien token.

---

## 4. Stockage frontend

MVP :

```text
sessionStorage
```

Règles :

- effacer access et refresh tokens après déconnexion ;
- considérer la révocation distante comme confirmée uniquement si chaque
  requête de révocation aboutit avec un statut HTTP réussi ;
- en cas d’échec réseau ou HTTP, effacer tout de même les jetons locaux et
  signaler que la révocation serveur n’a pas pu être confirmée ;
- ne jamais utiliser `localStorage`;
- ne jamais placer un token dans une URL ;
- ne jamais afficher un token dans la console ;
- ne pas inclure de scripts tiers non nécessaires.

Limitation :

- une faille XSS peut lire `sessionStorage`.

Mesures :

- échapper les données affichées ;
- utiliser `textContent` plutôt que `innerHTML` pour les réponses ;
- politique CSP ;
- aucun JavaScript inline lorsque possible ;
- dépendances frontend minimales ;
- validation des entrées ;
- CORS restrictif.

Les deux interfaces Nginx ajoutent systématiquement, y compris aux réponses
d’erreur, une CSP same-origin sans `unsafe-inline`, `X-Content-Type-Options:
nosniff`, `Referrer-Policy: no-referrer` et `X-Frame-Options: DENY`. La CSP
inclut aussi `frame-ancestors 'none'`.

---

## 5. Blocklist

La table `revoked_tokens` stocke :

```text
jti
user_id
token_type
expires_at
revoked_at
reason
```

Elle ne stocke jamais :

```text
JWT complet
Authorization header
signature secrète
refresh token complet
```

Chaque route protégée vérifie le `jti`.

Les lignes expirées peuvent être nettoyées.

---

## 6. Révocation globale

`users.token_version` est inclus dans chaque token.

Un changement de mot de passe incrémente la version.

Conséquence :

- les anciens access tokens sont refusés ;
- les anciens refresh tokens sont refusés.

La suppression logique ou désactivation est également vérifiée à chaque requête.

---

## 7. Autorisation

### Common user

La branche utilisée pour le stock provient de :

```text
current_user.branch_id
```

Tout `branch_id` envoyé dans une opération de stock est rejeté.

### Admin

Les routes de stock refusent explicitement le rôle admin.

### Frontend

Masquer un bouton améliore l’expérience mais ne remplace jamais le contrôle backend.

---

## 8. CORS

Backoffice :

- interface et API servies idéalement depuis la même origine ;
- aucune origine générique `*` avec les routes internes.

Client public :

- l’AI Query Service autorise uniquement l’origine configurée du `client_web`;
- méthodes limitées à celles nécessaires ;
- headers limités à `Content-Type`.

---

## 9. CSRF

Les JWT sont transmis dans l’en-tête `Authorization` et ne sont pas ajoutés automatiquement par le navigateur.

Le risque CSRF classique lié à un cookie d’authentification est fortement réduit.

Cela ne protège pas contre :

- XSS ;
- token volé ;
- CORS incorrect ;
- ingénierie sociale.

---

## 10. Product API et MCP

- timeouts obligatoires ;
- reprises limitées aux lectures idempotentes ;
- aucune donnée inventée ;
- aucune clé API dans les logs ;
- Product MCP sans accès PostgreSQL ;
- Stock MCP avec compte SELECT uniquement ;
- aucun outil `execute_sql`.
- `list_products` parcourt toutes les pages avec `limit=100`, vérifie
  `count`, `limit`, `offset`, la longueur de page et les doublons avant de
  rendre une projection complète ;
- `get_product_details` ne projette que les champs publics validés du contrat
  Produit et ne les persiste jamais dans PostgreSQL.

---

## 11. Journalisation

Autorisé :

- request ID ;
- route ;
- code HTTP ;
- durée ;
- user ID interne si nécessaire ;
- nom de l’outil MCP ;
- code d’erreur.

Interdit :

- mot de passe ;
- hash ;
- JWT ;
- refresh token ;
- header `Authorization` ;
- clé API ;
- chaîne de connexion ;
- données privées inutiles.

---

## 12. Erreurs

Les réponses ne révèlent pas :

- traceback ;
- SQL ;
- détail de configuration ;
- existence d’un nom d’utilisateur pendant le login ;
- secret interne.

Les erreurs sont stables et documentées dans `api_contracts.md`.

---

## 13. TLS

SSL/TLS n’est pas requis par l’exercice.

Limitation documentée :

- un Bearer token doit normalement être protégé par HTTPS hors environnement pédagogique local.

Toute utilisation réelle ou publique devra activer HTTPS.

---

## 14. Tests de sécurité minimums

- login invalide ;
- utilisateur supprimé ;
- route sans token ;
- access expiré ;
- refresh expiré ;
- token révoqué ;
- mauvais type de token ;
- ancien `token_version`;
- common user sur route admin ;
- admin sur route stock ;
- common user avec `branch_id` étranger ;
- quantité inattendue ;
- injection de champs supplémentaires ;
- Stock MCP incapable d’écrire ;
- aucun secret dans les logs.
