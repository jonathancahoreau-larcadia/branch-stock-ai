# Workflow Codex — Personne 2

## Ordre obligatoire

1. **Sam** lit les documents et propose un contrat technique précis.
2. **Rémi** approuve ou refuse le contrat.
3. **Thomas** écrit les tests contractuels avant le code.
4. **Rémi** approuve ou refuse les tests.
5. **Sam** implémente une petite unité à la fois.
6. **Rémi** vérifie la conformité finale.
7. **Thomas** exécute les tests et valide les preuves réelles.

Les agents ne travaillent pas en parallèle sur une même tâche.

## Prompt de lancement à donner au parent Codex

```text
Réalise le travail de Personne 2 du projet en utilisant uniquement les agents
personnalisés sam, remi et thomas.

Respecte strictement cet ordre pour chaque petite tâche :
Sam propose le contrat -> Rémi valide le contrat -> Thomas écrit les tests ->
Rémi valide les tests -> Sam implémente -> Rémi vérifie la conformité ->
Thomas exécute la validation finale.

Ne lance jamais Sam, Rémi et Thomas en parallèle sur la même tâche.
Ne commence pas la tâche suivante avant la décision VALIDÉ de Thomas.
Aucun commit, aucun push et aucune installation de dépendance sans mon accord.
Commence par lire les documents du projet et présente la première séquence,
sans modifier le code avant les validations prévues.
```

## Répartition des modèles

- Sam : `gpt-5.6-sol`, effort `high`
- Rémi : `gpt-5.6-terra`, effort `high`
- Thomas : `gpt-5.6-luna`, effort `high`
- Parent Codex : `gpt-5.6-terra`, effort `high`
