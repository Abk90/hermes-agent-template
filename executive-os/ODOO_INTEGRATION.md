# Integration Odoo — Phase 1

## Etat reel et contradiction de version

Le service prive Railway `odoo-mcp` utilise `ghcr.io/ivnvxd/mcp-server-odoo:0.7.1`. La mission mentionne Odoo 18, mais l'instance observee repond comme Odoo Enterprise 19.0. Toute requete doit donc verifier les modeles et champs reels avant de figer un domaine.

Le 28 aout, l'audit a detecte une derive dangereuse : `ODOO_YOLO=true` et trois outils d'ecriture visibles dans Hermes. La correction Phase 1 impose deux barrieres independantes :

1. serveur MCP : `ODOO_YOLO=read` ;
2. Hermes : `tools.include` limite a `search_records`, `get_record`, `list_models`, `list_resource_templates`, `aggregate_records`.

Ne jamais appeler un outil d'ecriture pour « tester » la protection. Verifier la variable, la decouverte du serveur et la whitelist Hermes.

## Approval Monitor

Le moniteur est specifie mais reste desactive tant que les modeles d'approbation exacts, les domaines et les champs obligatoires n'ont pas ete valides sur Odoo 19.

Pour chaque objet, produire : type, demandeur, projet, fournisseur/client, montant, date, anciennete, pieces, approbateurs, statut, anomalies, consequence de l'attente, recommandation et confiance. Une donnee absente reste `INCONNU`.

Configuration initiale : poll toutes les 15 minutes pendant les heures de travail, `[SILENT]` sans signal, puis batches a 10:30, 14:30 et 17:00. Ces horaires ne sont pas actives dans le cron live.

## Idempotence

La cle proposee est derivee de :

```text
odoo:<database>:<model>:<record_id>:<state>:<write_date>
```

Un poll identique reutilise la meme demande. Un changement Odoo cree une nouvelle version logique, reliee au meme objet. Le ledger stocke les references, jamais une copie concurrente du workflow.

## Ecriture future

Une approbation future exige une confirmation Ahmed non ambigue, liee au `request_id`, puis prelecture, appel exact, relecture du record et audit. Un resultat technique ne prouve ni paiement, ni livraison, ni reception, ni resultat metier.
