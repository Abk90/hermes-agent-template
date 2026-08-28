# Operations — Hermes Executive OS

## Composants Phase 1

- code immuable : `/app/executive-os` ;
- config centrale : `/app/executive-os/config/executive-os.toml` ;
- ledger persistant : `/data/.hermes/executive-os/ledger.sqlite3` ;
- skills geres : `/data/.hermes/skills/{executive-dispatch,odoo-approval-review,omnifocus-executive}` ;
- MCP local : `executive_os`, cinq outils whitelistes ;
- flag de deploiement : `EXECUTIVE_OS_ENABLED=true`.

Le bootstrap s'execute avant le gateway. Il sauvegarde une fois `config.yaml`, deep-merge le serveur MCP et preserve les skills modifiees localement. Une entree MCP existante non geree ou modifiee fait echouer le demarrage plutot que d'etre ecrasee. Un self-test bloquant connecte ensuite un client MCP 2, decouvre les cinq outils et appelle `connector_status` ; le gateway ne demarre pas si ce test echoue.

## Controle quotidien

1. `/health` confirme seulement wrapper/gateway ; ce n'est pas une preuve metier.
2. Verifier le dernier deploiement Railway et l'absence de restart loop.
3. Dans Hermes, tester la connexion MCP `executive_os` et relire ses cinq outils.
4. Relire le filtre Odoo et la variable `ODOO_YOLO=read`.
5. `connector_status` doit indiquer explicitement `OK`, `STALE`, `FAILED` ou `RETRYING` une fois les probes actives.
6. Examiner la queue P0/P1 et les erreurs ; ne pas confondre absence de signal et connecteur non teste.

## Commandes locales

```bash
PYTHONPATH=executive-os/src python3 -m unittest discover -s executive-os/tests -v
PYTHONPATH=executive-os/src python3 -m executive_os triage --payload request.json --idempotency-key source:id --actor test
PYTHONPATH=executive-os/src python3 -m executive_os queue
```

## Backup et reprise

Le volume Railway contient la config, les sessions et le ledger. Utiliser le backup/restore Hermes et un snapshot Railway avant toute migration majeure. SQLite est en WAL ; sauvegarder ensemble la base et ses fichiers WAL/SHM ou utiliser l'API de backup SQLite. Ne jamais restaurer par ecrasement pendant que le processus ecrit.

Apres restart, une meme cle d'idempotence retourne la demande existante. Une action distante reste `PENDING` jusqu'a relecture. Odoo/OmniFocus indisponible produit `FAILED` ou `RETRYING`, jamais `DONE`.

## Rollback

1. Mettre `EXECUTIVE_OS_ENABLED=false` sur le service Hermes et redeployer.
2. Le ledger et les skills restent sur le volume pour audit ; aucune suppression automatique.
3. Si necessaire, restaurer manuellement `config.yaml.pre-executive-os.bak` apres inspection et arret du service.
4. Ne pas remettre Odoo en ecriture : son mode `read` est une correction de securite independante.

## Incidents

- P0 humain : utiliser la voie humaine directe ; le systeme n'est jamais l'unique canal.
- MCP Executive OS absent : desactiver le feature flag ou corriger le bootstrap avant de relancer.
- Odoo expose un outil d'ecriture : stopper les revues, remettre les deux barrieres read-only et relire.
- Ledger corrompu : isoler une copie, restaurer le dernier backup coherent, conserver les traces.
- Secret expose : rotation, invalidation des sessions, purge controlee et verification de la nouvelle authentification.
