# Client Web — Interface publique de questions

## Présentation

Interface web **publique** (sans authentification) permettant aux utilisateurs de poser des questions en langage naturel sur les produits et les stocks.

Les questions sont envoyées à l'**AI Query Service** (`POST /questions`) qui interroge les données du Backoffice et retourne une réponse structurée.

---

## Arborescence

```
client_web/
├── index.html                  # Page principale
│
├── css/
│   ├── reset.css               # Normalisation entre navigateurs
│   ├── variables.css           # Variables CSS (couleurs, espacements)
│   ├── layout.css              # Structure de la page
│   ├── components.css          # Composants réutilisables
│   └── style.css               # Point d'entrée (importe tous les CSS)
│
├── js/
│   ├── config.js               # URL de l'API (AI Query Service)
│   ├── utils.js                # Fonctions utilitaires (escapeHtml, formatDate)
│   ├── api.js                  # Communication avec l'AI Query Service
│   ├── ui.js                   # Gestion de l'affichage (DOM)
│   ├── events.js               # Gestion des événements (submit, input)
│   └── app.js                  # Point d'entrée (initialisation)
│
├── assets/
│   ├── images/
│   │   └── logo.png            # Logo du site (optionnel)
│   └── icons/
│       ├── loading.svg         # Icône de chargement (animée)
│       ├── error.svg           # Icône d'erreur
│       └── success.svg         # Icône de succès
│
└── README.md                   # Ce fichier
```

---

## Fonctionnalités

| Fonctionnalité | Statut |
|---------------|--------|
| ✅ Input texte pour la question | Implémenté |
| ✅ Bouton Envoyer (désactivé si vide) | Implémenté |
| ✅ Compteur de caractères (0/1000) | Implémenté |
| ✅ Envoi par Ctrl+Enter | Implémenté |
| ✅ Indicateur de chargement (spinner) | Implémenté |
| ✅ Affichage de la réponse (colorée selon le statut) | Implémenté |
| ✅ Messages d'erreur clairs (réseau, serveur) | Implémenté |
| ✅ Exemples de questions | Implémenté |
| ✅ Design responsive | Implémenté |
| ✅ Accessibilité (aria-live, labels) | Implémenté |

---

## Exemples de questions

- *Quelle succursale a du stock du produit product-123 ?*
- *Quels produits trouve-t-on à la succursale Toulon ?*
- *Donne-moi les détails du produit product-123.*
- *Si je veux 3 unités de product-123 et 2 de product-456, où dois-je aller ?*

---

## Architecture du code JavaScript

Le code est organisé en modules (IIFE) pour une séparation claire des responsabilités :

| Module | Rôle |
|--------|------|
| `config.js` | Configuration (URL de l'API) |
| `utils.js` | Fonctions utilitaires (escapeHtml, formatDate, translateStatus) |
| `api.js` | Communication HTTP avec l'AI Query Service |
| `ui.js` | Manipulation du DOM (affichage, masquage, mise à jour) |
| `events.js` | Écouteurs d'événements (submit, input, keydown) |
| `app.js` | Initialisation au chargement de la page |

**Flux d'exécution :**

```
1. DOMContentLoaded → app.js
2.   → Ui.init()       (références DOM)
3.   → Ui.updateCharCount() / Ui.updateSubmitButton() (état initial)
4.   → Events.init()   (écouteurs)
5. Utilisateur tape → Events → Ui.updateCharCount() / Ui.updateSubmitButton()
6. Utilisateur envoie → Events.handleSubmit()
7.   → Ui.showLoading()
8.   → Api.sendQuestion(question)
9.   → Ui.hideLoading()
10.  → Ui.displayResponse(data) ou Ui.displayError(message)
```

---

## Formats de réponse supportés

L'interface affiche les réponses de l'AI Query Service avec un code couleur selon le statut :

| Statut | Couleur | Signification |
|--------|---------|---------------|
| `success` | Vert | Réponse complète avec données |
| `partial` | Jaune | Réponse partielle |
| `unavailable` | Bleu | Information non disponible |
| `unsupported` | Rouge | Question hors périmètre |
| Erreur réseau | Rouge | Service inaccessible |

---

## Lancer l'application

```bash
# Il suffit d'ouvrir index.html dans un navigateur
# (pas de serveur nécessaire, c'est du HTML/CSS/JS statique)

open client_web/index.html
```

> **Note :** L'AI Query Service doit être accessible à l'URL configurée dans `js/config.js` (`http://localhost:8000/questions` par défaut).

---

## Personnalisation

- **URL de l'API** : modifier `js/config.js`
- **Couleurs** : modifier `css/variables.css`
- **Exemples de questions** : modifier `index.html`
- **Logo** : placer une image dans `assets/images/logo.png`