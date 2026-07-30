# Plan de démonstration HBntory — 10 minutes

## Objectif et responsabilités

La démonstration montre le flux intégré sans exposer de secret et sans
modifier les contrats validés.

- Responsable 1 — Backoffice et base : authentification, admin, common user,
  contraintes de stock et frontières PostgreSQL.
- Responsable 2 — IA et MCP : Product MCP, Stock MCP, sélection d’outils en
  lecture seule et réponses fondées sur les données.
- Responsable 3 — interfaces et intégration : architecture, Client Web,
  Docker Compose, erreurs, preuves et reprise.

Les noms humains et l’attribution finale des prises de parole restent à
renseigner pendant la répétition.

## Déroulé chronométré

| Temps | Responsable | Démonstration |
|---|---|---|
| 0:00–1:00 | Responsable 3 | Présenter l’architecture : huit services, REST entre interfaces et API, MCP entre IA et outils, PostgreSQL limité aux données locales. |
| 1:00–2:00 | Responsable 1 | Ouvrir le Backoffice, montrer l’authentification et rappeler les durées, rôles et contrôles JWT. |
| 2:00–3:30 | Responsable 1 | Avec un common user préparé, consulter sa succursale, ajouter puis retirer une unité de stock ; montrer le refus d’un retrait insuffisant ou d’une autre branche. |
| 3:30–4:45 | Responsable 1 | Avec l’admin, créer ou consulter un common user, changer sa branche ou son mot de passe, puis rappeler que l’admin ne gère pas les stocks. |
| 4:45–5:45 | Responsable 3 | Ouvrir le Client Web public, rechercher les détails d’un produit et montrer qu’aucune authentification ni historique n’est requis. |
| 5:45–7:30 | Responsable 2 | Poser une question de disponibilité puis une liste d’achats ; relier la réponse aux données de Product MCP et Stock MCP en lecture seule. |
| 7:30–8:30 | Responsable 2 | Montrer une question non prise en charge, un produit inconnu ou une dépendance indisponible ; commenter les statuts et erreurs sûres. |
| 8:30–9:20 | Responsable 3 | Expliquer les limites : API Produits officielle, questions IA bornées, absence de streaming, d’historique et de TLS imposé dans l’exercice. |
| 9:20–10:00 | Responsable 3 | Présenter les preuves, la santé Compose et la procédure de reprise non destructive avec les données préparées. |

## Checklist de préparation

- [ ] Fichier d’environnement externe lisible, non affiché et non versionné.
- [ ] Huit services sains dans `docker compose ps`.
- [ ] Backoffice lisible sur le vidéoprojecteur.
- [ ] Client Web lisible et exemples de questions copiés hors écran partagé.
- [ ] Diagramme d’architecture lisible avec responsabilités et sens des flux.
- [ ] Données de démonstration vérifiées : admin, common user, Toulon,
  Marseille et produit `HB-MON-2102`.
- [ ] Quantités de départ et opérations de stock choisies pour éviter un état
  négatif.
- [ ] Scénarios critiques testés : login, stock common user, refus admin,
  gestion utilisateur, produit, disponibilité, inventaire, liste d’achats,
  inconnu et indisponible.
- [ ] Aucune valeur sensible, console détaillée ou ligne de log brute visible.
- [ ] Dernier environnement sain et jeu de données préparé conservés pour la
  reprise.

## Sujets techniques à expliquer

- JWT : access et refresh, révocation par identifiant, version du compte,
  contrôles backend et absence de rotation automatique du refresh token.
- bcrypt : fonction dédiée au stockage des mots de passe, coût configurable,
  absence de mot de passe en clair.
- REST : Backoffice UI vers API Flask et Client Web vers `POST /questions`.
- MCP : deux outils Produit et quatre outils Stock approuvés, tous en lecture
  seule pour l’IA.
- Frontières de base de données : migration privilégiée, Backoffice métier,
  Stock MCP en `SELECT`; Product MCP et AI sans accès PostgreSQL direct.
- Propriété des données : produits dans l’External Product API, stock et
  comptes dans PostgreSQL.
- Compromis d’architecture : interfaces simples, réseau Docker interne,
  classificateur déterministe par défaut, Ollama optionnel, pas de streaming
  ni d’historique.
- Sécurité : autorisation par rôle et branche, quantités non négatives,
  erreurs stables, expurgation et HTTPS requis hors contexte pédagogique.

## Erreurs et procédure de reprise

Si une étape échoue, annoncer la limite sans improviser de donnée :

1. conserver l’environnement, le volume et les preuves existants ;
2. vérifier l’état du service concerné et sa dépendance immédiate ;
3. redémarrer seulement ce service, puis attendre les healthchecks ;
4. si l’état métier a changé, utiliser le common user et les quantités de
   secours préparés plutôt qu’une restauration ou une réinitialisation ;
5. basculer vers les sorties expurgées déjà validées si le service ne revient
   pas dans le temps de la démonstration.

La reprise ne supprime aucun volume, ne relance aucun build et ne contacte pas
Internet.

## Vérification indépendante du setup README

À renseigner uniquement par un membre qui n’a pas écrit la section setup :

- Identité : [à compléter]
- Date UTC : [à compléter]
- Environnement : [à compléter]
- Résultat : [à compléter]
- Limites observées : [à compléter]

## Répétition chronométrée à trois

À renseigner uniquement après une répétition réelle :

- Participants : [à compléter]
- Date UTC : [à compléter]
- Durée : [à compléter]
- Scénarios : [à compléter]
- Incidents : [à compléter]
- Reprise : [à compléter]
- Attribution finale des prises de parole : [à compléter]

## Demande QA manuelle

À renseigner uniquement lorsqu’une demande réelle a été transmise :

- Demandeur : [à compléter]
- Date UTC : [à compléter]
- Statut : [à compléter]
- Référence de la demande : [à compléter]

## Décision du responsable unique

La décision humaine en lecture seule
`person3_handoffs/current/HUMAN_APPROVAL.md`, code
`P3-T06_OWNER_FINAL_APPROVAL`, confirme que le responsable unique a
personnellement vérifié le README et approuve la clôture de P3-T06.

Pour cette branche, cette même décision déclare non applicables la répétition
collective de trois responsables, l’attestation collective et la demande de
QA externe. Les champs ci-dessus restent donc volontairement vides : ils ne
constituent ni une répétition, ni une demande QA, ni une attestation fabriquée.
