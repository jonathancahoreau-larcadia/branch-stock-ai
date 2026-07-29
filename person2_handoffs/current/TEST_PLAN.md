# P2-T07 — plan de tests Thomas

## Périmètre

Tester uniquement l’interface publique de `ai_service.generator` avec des
enveloppes MCP locales. Aucun appel réseau, MCP, HTTP, PostgreSQL ou
fournisseur IA n’est utilisé. La production et les tests existants restent
inchangés.

## Matrice contractuelle

- Surface publique : réexport exact de `SUPPORTED_QUESTION_TYPES`, signature
  de `generate_grounded_response`, validation des types et des clés d’outils.
- Familles : `product_details`, `product_availability`, `branch_inventory` et
  `shopping_list`, plus la réponse exacte `unsupported`.
- Enveloppes : succès exploitable, absence, `not_found`, `error`, enveloppe ou
  donnée mal formée ; statuts `success`, `partial` et `unavailable`.
- `product_details` ne possède qu’un résultat attendu : un résultat valide est
  donc `success`, tandis que les cas `partial` avec un outil compagnon sont
  vérifiés pour les trois familles à deux outils, dans les deux sens : premier
  outil seul exploitable et second outil seul exploitable, avec projection
  exclusive et phrase partielle fixe.
- Schémas : projection récursive des champs publics, champs supplémentaires
  supprimés, chaînes non vides et types non-chaîne, entiers stricts (booléens
  exclus), contraintes des branches, stocks, visites, articles et articles
  manquants.
- Métier : absence réelle de stock, produit inconnu, combinaison Product/Stock,
  contradiction d’identifiants avec exclusion du Stock, liste de courses
  complète et indisponible sans recalcul.
- Sûreté : aucune invention dans les réponses, aucune fuite d’erreur ou de
  champ arbitraire, jeux de données alternatifs aux valeurs disjointes pour
  vérifier l’absence de noms, identifiants, branches et quantités hors
  projection, absence de fuite du prix numérique `999`, entrées inchangées et
  copies de sortie indépendantes.
- Révision demandée par Rémi : l’invariant isolé
  `available_quantity >= requested_quantity`, la suppression des champs
  supplémentaires des branches de `get_stock_for_product` et des articles de
  `list_branch_stock`, ainsi que le signalement explicite d’une liste `branches`
  ou `stocks` vide sont couverts par des assertions dédiées.

## Preuves

Après création de `ai_service/generator.py` par Sam et validation de Rémi :

```bash
python3 -m pytest tests/test_ai_generator.py -q
python3 -m pytest tests/test_ai_classifier.py tests/test_ai_mcp_client.py tests/test_ai_generator.py -q
python3 -m pytest --import-mode=importlib tests/test_product_mcp_tools.py tests/test_product_mcp_server.py integration_tests/test_product_mcp_server.py -q
python3 -m pytest --import-mode=importlib tests/test_stock_mcp_repository.py tests/test_stock_mcp_tools.py tests/test_stock_mcp_server.py integration_tests/test_stock_mcp_server.py -q --deselect tests/test_stock_mcp_repository.py::test_runtime_manifest_contains_only_the_approved_dependency
```

Avant l’implémentation, la preuve locale disponible est la compilation
syntaxique du fichier de tests ; l’import de la nouvelle production est
volontairement laissé à la phase suivante.
