# Plan de test et criteres d'acceptation

## Automatises maintenant

La suite couvre : classification P0-P4, clarification d'une urgence vague, routes procedure/delegation/Odoo/OmniFocus, absence de doublon OmniFocus pour une approbation, idempotence, audit append-only, transitions invalides et etat connecteur.

Le bootstrap est teste pour la fusion non destructive, l'idempotence et la preservation des modifications locales. Dans un environnement sans PyYAML, ces tests sont explicitement skips ; l'image Railway installe la dependance.

## Matrice MVP

| # | Scenario | Attendu | Phase 1 |
|---|---|---|---|
| 1 | « reponds vite pour le fournisseur » | questions montant/echeance/consequences/Odoo/recommandation | automatise |
| 2 | danger ou risque irreversible imminent | P0/P1, voie humaine directe | automatise ; notification non active |
| 3 | decision normale | P2 batch, pas d'interruption | automatise |
| 4 | procedure sure connue | route `answer` | automatise |
| 5 | workflow officiel | route Odoo, pas de workflow Telegram | automatise |
| 6 | approbation Odoo sans Telegram | detection | bloque jusqu'au domaine Odoo valide |
| 7 | approbation simple | aucune tache OmniFocus | automatise |
| 8 | appel necessaire avant approbation | route OmniFocus possible | automatise ; ecriture desactivee |
| 9 | « que faire maintenant ? » | fusion de sources fraiches, une action NOW | skill installe ; sources non toutes branchees |
| 10 | collaborateur | aucun contexte prive Ahmed | exige service intake separe |
| 11 | poll repete | aucune demande dupliquee | automatise |
| 12 | action sensible | audit + confirmation | ledger automatise ; ecritures interdites |

## Verification avant et apres Railway

1. tests Python, compilation, `bash -n`, `git diff --check` ;
2. build conteneur si le runtime Docker local est disponible ;
3. deploiement depuis le commit exact ;
4. statut Railway `SUCCESS`, `/health` HTTP 200 ;
5. test MCP live : connexion puis cinq outils exacts ;
6. inventaire des trois skills geres ;
7. Odoo : `ODOO_YOLO=read`, whitelist cinq lectures ;
8. redemarrage controle et second test MCP pour prouver la persistance/idempotence ;
9. aucun cron, bot interne ou ecriture sensible active.

## Pilote observe

Avant Phase 2, constituer un jeu de demandes reelles anonymisees et mesurer faux P0/P1, escalades manquees, questions inutiles, doublons, fraicheur et bruit. Ahmed valide les seuils et routes ; le volume d'automatisation ne constitue pas un critere de succes.
