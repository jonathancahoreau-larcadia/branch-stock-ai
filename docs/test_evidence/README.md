# Index des preuves de test HBntory

Cet index utilise uniquement des chemins relatifs au dépôt. Il distingue les
tests automatisés sans réseau, les preuves runtime locales, le contrôle manuel
Product MCP et les validations humaines. Une référence n’élève jamais une
preuve antérieure au rang d’observation P3-T06.

## P3-T01 à P3-T05

| Tâche | Type | Preuve |
|---|---|---|
| P3-T01 | validation automatisée de l’audit et des actifs | `person3_handoffs/archive/P3-T01-validated-20260729T162305Z/VALIDATION_REPORT.md` |
| P3-T02 | validation automatisée du Backoffice UI | `person3_handoffs/archive/P3-T02-validated-20260729T204127Z/VALIDATION_REPORT.md` |
| P3-T03 | validation automatisée du Client Web | `person3_handoffs/archive/P3-T03-validated-20260730T094239Z/VALIDATION_REPORT.md` |
| P3-T04 | validation Docker et intégration | `person3_handoffs/archive/P3-T04-validated-20260730T144456Z/VALIDATION_REPORT.md` |
| P3-T05 | automatisation E2E et validation runtime | `person3_handoffs/archive/P3-T05-validated-20260730T161944Z/VALIDATION_REPORT.md` |

La preuve runtime Docker Compose de P3-T05 est le relevé de codes retour
`person3_handoffs/runtime_proofs/P3-T05-runtime-command-results.json`. Elle
porte sur huit commandes locales déjà validées, pas sur pytest P3-T06. Elle
n’est pas rejouée ici et aucun log brut n’est recopié.

## P3-T06

| Catégorie | Preuve | État |
|---|---|---|
| Tests automatisés sans réseau réel, neuf processus pytest | `docs/test_evidence/P3-T06_FINAL_VALIDATION.md` | consigné par SAM, à vérifier indépendamment par Thomas |
| Transcript manuel Product MCP sans réseau réel | `docs/test_evidence/P3-T06_PRODUCT_MCP_MANUAL.md` | quatre scénarios observés et conformes |
| Index des preuves | `docs/test_evidence/README.md` | présent |
| Vérification humaine du README | `person3_handoffs/current/HUMAN_APPROVAL.md` | effectuée et approuvée par le responsable unique |
| Répétition humaine à trois, dix minutes | `person3_handoffs/current/HUMAN_APPROVAL.md` | déclarée non applicable à cette branche |
| Demande de QA manuelle | `person3_handoffs/current/HUMAN_APPROVAL.md` | déclarée non applicable à cette branche |

Les validations humaines ne sont ni automatisées ni déduites du transcript
manuel. La décision humaine en lecture seule
`person3_handoffs/current/HUMAN_APPROVAL.md`, code
`P3-T06_OWNER_FINAL_APPROVAL`, atteste la vérification personnelle du README
par le responsable unique du projet. Elle décide aussi que la répétition
collective de trois responsables, l’attestation collective et la demande de
QA externe ne sont pas applicables à cette branche. Les champs correspondants
de `docs/demo_plan.md` restent donc vides : aucune répétition ou demande QA
non réalisée n’est fabriquée.

## Règles d’expurgation

Les preuves ne conservent que la commande, le code retour et une synthèse
utile. Sont exclus : secrets, mots de passe, hashes, JWT, jetons, en-têtes
sensibles, cookies, URI privées, contenu du fichier d’environnement et lignes
de logs bruts. Les sorties runtime détaillées restent privées.
