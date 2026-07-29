# Politique de contexte — Personne 2

Cette politique réduit les relectures et la consommation de contexte sans
sacrifier la conformité documentaire.

## Amorçage unique

Lors de la première session Codex suivant l’installation :

1. Lire une fois les documents Personne 2 existants.
2. Remplir `PROJECT_REFERENCE.md` avec les décisions stables, les interfaces,
   les contraintes et les commandes utiles.
3. Exécuter `python .codex/person2/check_docs.py --write`.
4. Ne commencer P2-T02 qu’après cette synthèse.

## Début de chaque tâche

Lire uniquement :

- `AGENTS.md` chargé automatiquement par Codex ;
- `PROJECT_REFERENCE.md` ;
- `TASK_STATE.md` ;
- le contrat et le handoff de la tâche courante ;
- les fichiers de production et de tests concernés.

Puis lancer :

```bash
python .codex/person2/check_docs.py --check
```

Quand les documents sont inchangés, ne pas les relire intégralement.

## Quand relire une source

Une relecture ciblée est autorisée lorsque :

- l’empreinte du document a changé ;
- le résumé ne contient pas la règle nécessaire ;
- deux sources semblent contradictoires ;
- Rémi doit vérifier une exigence exacte ;
- une erreur de test révèle une hypothèse non documentée.

Commencer par rechercher le titre ou les mots-clés pertinents, puis lire
seulement la section correspondante. La lecture complète reste le dernier
recours.

## Handoffs entre agents

Les agents échangent par fichiers courts plutôt qu’en recopiant les sources :

- `.codex/person2/current/CONTRACT.md`
- `.codex/person2/current/TEST_PLAN.md`
- `.codex/person2/current/IMPLEMENTATION_REPORT.md`
- `.codex/person2/current/VALIDATION_REPORT.md`

Chaque handoff cite les chemins et sections sources utilisés.
