# Preuve manuelle Product MCP — P3-T06

- Date UTC : `2026-07-30T16:49:01Z`
- Environnement local : Python du dépôt, vrais
  `product_mcp_server.tools`, adaptateur HTTP remplacé en mémoire par un double
  déterministe.
- Réseau : sans réseau réel ; le garde est installé après création de la
  boucle asynchrone et bloque toute nouvelle socket ou connexion.
- Exécution : une invocation manuelle Python distincte de pytest, code retour
  observé `0`.

## Méthode et expurgation

Depuis la racine du dépôt, l’inspecteur a lancé
`PYTHONDONTWRITEBYTECODE=1 python3 -` avec un script local éphémère. Le script
a importé les vrais outils, remplacé uniquement
`product_api.httpx.AsyncClient` par un double local, puis invoqué les
coroutines indiquées ci-dessous. Le double comptait ses appels et renvoyait
des réponses HTTP déterministes ; le cas indisponible levait une erreur de
connexion locale contrôlée, immédiatement convertie par le vrai adaptateur.

La sortie a été expurgée avant transcription. Aucun secret, mot de passe,
hash, JWT, jeton, en-tête, cookie, URI sensible, contenu de fichier runtime ou
log brut n’a été conservé. Seuls l’enveloppe MCP publique, le scénario et le
nombre d’appels du double sont reproduits.

## Scénario 1 — `list_products`

- Commande / étapes : état du double `list`, puis
  `await tools.list_products()`.
- Observation :
  `{"result":{"data":{"products":[{"external_product_id":"HB-MON-2102","name":"24 inch Compact Monitor"}]},"status":"success"},"scenario":"list_products","transport_calls":1}`
- Statut observé : `success`.
- Conclusion : conforme ; la projection publique contient uniquement
  l’identifiant externe et le nom.

## Scénario 2 — `get_product_details` avec identifiant valide

- Commande / étapes : état du double `valid`, puis
  `await tools.get_product_details("HB-MON-2102")`.
- Observation :
  `{"result":{"data":{"external_product_id":"HB-MON-2102","name":"24 inch Compact Monitor"},"status":"success"},"scenario":"details_valid","transport_calls":1}`
- Statut observé : `success`.
- Conclusion : conforme ; le détail correspond à l’identifiant demandé.

## Scénario 3 — identifiant invalide ou inconnu

- Commande / étapes, entrée invalide :
  `await tools.get_product_details("   ")`.
- Observation invalide :
  `{"result":{"error":{"code":"INVALID_EXTERNAL_PRODUCT_ID","message":"Product identifier is invalid."},"status":"error"},"scenario":"details_invalid","transport_calls":0}`
- Statut observé pour l’entrée invalide : `error` avec
  `INVALID_EXTERNAL_PRODUCT_ID`; aucun appel au double.
- Commande / étapes, entrée inconnue : état du double `unknown`, puis
  `await tools.get_product_details("HB-UNKNOWN-0000")`.
- Observation inconnue :
  `{"result":{"data":null,"status":"not_found"},"scenario":"details_unknown","transport_calls":1}`
- Statut observé pour l’entrée bien formée mais inconnue : `not_found`.
- Conclusion : conforme ; `INVALID_EXTERNAL_PRODUCT_ID` est distingué de
  `not_found` selon la validité de l’entrée.

## Scénario 4 — API Produits arrêtée ou inaccessible

- Commande / étapes : état du double `unavailable`, levée déterministe d’une
  erreur de connexion, puis
  `await tools.get_product_details("HB-MON-2102")`.
- Observation :
  `{"result":{"error":{"code":"PRODUCT_API_UNAVAILABLE","message":"Product API is unavailable."},"status":"error"},"scenario":"api_unavailable","transport_calls":1}`
- Statut observé : `error` avec `PRODUCT_API_UNAVAILABLE`.
- Conclusion : conforme ; l’indisponibilité produit une erreur claire,
  structurée et sans échec silencieux.

## Résultat manuel

Les quatre scénarios requis ont une observation réelle dans l’environnement
local contrôlé. Le processus a terminé avec le code retour `0`. Cette preuve
manuelle n’est ni un test pytest, ni une preuve Docker P3-T05, ni une
validation humaine du README ou de la démonstration.
