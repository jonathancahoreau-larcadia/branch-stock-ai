# Interface publique Client Web

## Périmètre

Le Client Web HBntory fournit une interface anonyme pour poser une question
indépendante sur les produits et les stocks. Il consomme le contrat public
existant :

```text
POST /questions
Content-Type: application/json

{"question": "<question non vide, 1000 caractères maximum>"}
```

Le chemin est relatif afin que le déploiement puisse placer le Client Web et
l’adaptateur HTTP public derrière la même origine. P3-T03 ne crée ni cet
adaptateur HTTP, ni une route de santé, ni une règle CORS.

## Flux de traitement

Le traitement autorisé est :

```text
Client Web
→ AI Query Service
→ Ollama : intention JSON
→ validation et sélection Python
→ Product MCP ou Stock MCP en lecture seule
→ réponse déterministe fondée sur les MCP
→ Ollama : reformulation contrôlée
→ Client Web
```

Python conserve seul le contrôle du choix et des paramètres des outils MCP.
Ollama ne choisit aucun outil et ne constitue jamais une source de données
métier. Une reformulation qui ajoute, retire ou permute une information
sémantique est ignorée au profit de la réponse déterministe.

En cas d’indisponibilité, de délai dépassé ou d’intention JSON invalide, le
service tente le classificateur déterministe existant. Si les paramètres ne
peuvent pas être extraits sans ambiguïté, il renvoie une erreur contrôlée et
n’appelle aucun MCP.

## Configuration Ollama

La configuration est lue à la construction du service :

| Variable | Utilisation | Valeur locale conseillée |
|---|---|---|
| `OLLAMA_ENABLED` | Active l’intention et la reformulation Ollama | `true` |
| `OLLAMA_BASE_URL` | URL HTTP(S) du runtime Ollama | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | Modèle local obligatoire quand Ollama est activé | `qwen3.5:4b` |
| `OLLAMA_TIMEOUT_SECONDS` | Délai strictement positif | `30` |
| `OLLAMA_KEEP_ALIVE` | Durée de conservation du modèle | `5m` |

Sous WSL, l’URL locale usuelle est
`http://127.0.0.1:11434`. Depuis un conteneur qui joint Ollama sur l’hôte,
utiliser `http://host.docker.internal:11434`.

Le nom du modèle n’est pas fixé dans le code Python. Aucun SDK Ollama n’est
nécessaire : l’adaptateur utilise uniquement la bibliothèque standard.

## Réponses affichées

Pour une réponse HTTP 2xx, l’interface accepte uniquement les quatre statuts
publics `success`, `partial`, `unavailable` et `unsupported`, avec une chaîne
`answer` et un objet `data`. Chaque statut est annoncé textuellement et avec
un style visible distinct.

Pour une erreur HTTP structurée, seul le message sûr est affiché. Une panne
Fetch, un JSON invalide ou une forme de réponse inconnue produit un message
technique stable. Les valeurs reçues sont rendues avec des nœuds texte ; elles
ne sont jamais interprétées comme du HTML.

## Règles d’utilisation et de sécurité

- La requête utilise `credentials: "omit"` et n’envoie aucun en-tête
  d’autorisation.
- Une question vide n’est pas envoyée.
- Une seule requête peut être en cours ; le bouton est désactivé pendant le
  chargement.
- Aucune conversation ni question n’est conservée dans le navigateur.
- Aucun cookie volontaire, jeton ou stockage persistant n’est utilisé.
- Les appels métier passent exclusivement par les clients MCP approuvés en
  lecture seule.
- Le service ne lit pas directement la base de données et ne contacte pas
  directement l’API Produits externe.

## Limites actuelles

- L’adaptateur public `POST /questions` appartient à Personne 2 et doit être
  disponible à la même origine pour un fonctionnement déployé.
- Docker, Compose, proxy et CORS ne sont pas modifiés par P3-T03.
- Les questions non reconnues restent `unsupported`.
- L’interface ne conserve aucun historique entre deux demandes ou
  rechargements.

## Tests sans réseau réel

Les tests automatisés remplacent Ollama et les MCP par des doubles Python.
L’interface est exécutée avec Node.js, un DOM minimal et un faux Fetch. Aucun
test P3-T03 ne joint un serveur, une base, Ollama ou Internet.

## Sources

- `person3_handoffs/current/HUMAN_APPROVAL.md`
- `person3_handoffs/current/CONTRACT.md`
- `docs/api_contracts.md`
- `docs/project_context.md`
- `docs/architecture.md`
- `docs/security_rules.md`
- `docs/testing_strategy.md`
