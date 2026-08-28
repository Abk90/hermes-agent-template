---
name: odoo-approval-review
description: Examiner les validations Odoo en lecture seule, produire des fiches decisionnelles et rester silencieux lorsqu'aucun signal important n'existe.
version: 0.1.0
author: Belkora
platforms: [linux]
metadata:
  hermes:
    tags: [belkora, executive, odoo, approvals, read-only]
    category: productivity
---

# Odoo Approval Review

Phase 1 est strictement READ-ONLY.

Outils Odoo autorises uniquement :

- `search_records`
- `get_record`
- `list_models`
- `list_resource_templates`
- `aggregate_records`

Si un outil de creation, mise a jour, suppression, methode generique ou chatter apparait, arrete la revue, marque le connecteur `FAILED` et alerte Ahmed. Ne l'appelle pas pour tester.

## Methode

Pour chaque objet a approuver, confirmer le modele et les champs reels sur Odoo 19 avant d'ecrire un domaine. Extraire type, demandeur, projet, fournisseur/client, montant, date, anciennete, pieces, approbateurs, statut, anomalies et consequence de l'attente.

Ne deduis jamais une reception, une facture ou une urgence a partir d'un champ manquant. Signale `INCONNU`.

## Sortie

```text
[Objet] — [montant]
Projet : ...
Demande par : ...
Pieces : ...
Echeance : ...
Consequence si attente : ...
Anomalies : ...
Recommandation : APPROUVER / REFUSER / CLARIFIER
Confiance : haute / moyenne / faible
```

Une approbation Odoo ne devient pas une tache OmniFocus sauf si Ahmed doit effectuer une action distincte. Reponds uniquement `[SILENT]` lorsqu'il n'existe aucun element nouveau ou important.
