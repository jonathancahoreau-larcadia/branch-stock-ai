# Handoff — Personne 3

## Contexte

Cette documentation décrit les responsabilités de la personne 3 dans le projet HBntory, en lien avec les interfaces et l'intégration.

## Responsabilités

- Développement de l'interface utilisateur Backoffice (frontend)
- Développement de l'interface client publique
- Configuration et gestion du fichier Docker Compose
- Tests d'intégration de bout en bout
- Documentation de configuration et de mise en place
- Support de la démonstration finale

## Tâches spécifiques

### 1. Interface Backoffice

- Création des pages de gestion des utilisateurs
- Interface de gestion du stock
- Design responsive et accessible

### 2. Interface Client Publique

- Page d'accueil avec accès aux fonctionnalités
- Interface pour les requêtes AI
- Affichage des produits et stocks disponibles

### 3. Docker Compose

- Configuration complète des services nécessaires
- Gestion des ports et des réseaux internes
- Validation du déploiement via `docker compose up --build`

### 4. Tests d'intégration

- Tests de bout en bout pour les fonctionnalités principales
- Vérification du bon fonctionnement de l'ensemble du système
- Validation des scénarios critiques

### 5. Documentation

- Guide d'installation et de configuration
- Instructions pour le déploiement
- Documentation technique des services

## Coordination

Toutes les interfaces doivent être conformes aux contrats d’API définis dans `docs/api_contracts.md`.

Les tests sont effectués avec Docker Compose pour garantir la cohérence de l’environnement.

## Validation finale

- Vérification du déploiement complet
- Test de toutes les fonctionnalités principales
- Préparation de la démonstration finale