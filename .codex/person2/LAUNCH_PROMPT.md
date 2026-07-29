# Prompt optimisé de lancement — Personne 2

```text
Réalise les tâches restantes de Personne 2 avec les agents personnalisés sam,
remi et thomas, strictement de manière séquentielle.

Avant toute chose :
1. lis AGENTS.md ;
2. lis .codex/person2/CONTEXT_POLICY.md ;
3. vérifie .codex/person2/PROJECT_REFERENCE.md et TASK_STATE.md ;
4. exécute python .codex/person2/check_docs.py --check.

Si aucune empreinte documentaire n’existe encore, effectue une seule lecture
initiale des documents Personne 2, complète PROJECT_REFERENCE.md, puis exécute
python .codex/person2/check_docs.py --write.

Si les documents sont inchangés, ne les relis pas intégralement. Pour chaque
tâche, lis seulement la référence persistante, l’état, les handoffs et les
sections ou fichiers directement concernés.

Ordre obligatoire :
Sam propose le contrat -> Rémi valide le contrat -> Thomas écrit les tests ->
Rémi valide les tests -> Sam implémente -> Rémi vérifie la conformité ->
Thomas exécute la validation finale.

Ne lance jamais plusieurs de ces agents en parallèle sur la même tâche.
Ne passe pas à la tâche suivante avant VALIDÉ de Thomas.
P2-T01 est déjà validée ; commence à P2-T02.

Aucun commit, aucun push et aucune installation de dépendance sans mon accord.
```
