<!-- BEGIN CODEX PERSONNE 2 MANAGED BLOCK -->
# Personne 2 — règles durables pour Codex

## Point d’entrée documentaire

Avant de lire les documents complets, consulte dans cet ordre :

1. `.codex/person2/PROJECT_REFERENCE.md`
2. `.codex/person2/TASK_STATE.md`
3. `.codex/person2/CONTEXT_POLICY.md`
4. le contrat, les tests ou le rapport de la tâche courante

Ne relis pas tous les documents du projet à chaque étape.

## Politique de lecture

- Au premier démarrage seulement, construis ou actualise
  `.codex/person2/PROJECT_REFERENCE.md` à partir des documents sources.
- En début de tâche, exécute :
  `python .codex/person2/check_docs.py --check`.
- Si les empreintes sont inchangées, utilise la référence persistante et lis
  uniquement les sections sources directement liées à la tâche.
- Relis un document complet seulement si son empreinte a changé, si la
  référence ne permet pas de trancher, ou si Rémi demande une vérification
  précise.
- Ne copie pas les documents entiers dans les prompts des sous-agents.
  Transmets plutôt les chemins, le contrat figé et les extraits nécessaires.
- Après validation d’une tâche, mets à jour `TASK_STATE.md` et les éléments
  concernés de `PROJECT_REFERENCE.md`, puis actualise les empreintes.

## Workflow séquentiel obligatoire

Sam définit le contrat → Rémi valide le contrat → Thomas écrit les tests →
Rémi valide les tests → Sam implémente → Rémi vérifie la conformité →
Thomas exécute les preuves finales.

Un seul agent travaille à la fois sur une tâche donnée.

## Limites

- Aucun commit ni push.
- Aucune installation ou nouvelle dépendance sans accord humain explicite.
- Ne modifie jamais les tests de Thomas pendant l’implémentation.
- Ne déclare jamais une tâche réussie sans commandes réellement exécutées.
<!-- END CODEX PERSONNE 2 MANAGED BLOCK -->
