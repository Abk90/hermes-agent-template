---
name: omnifocus-executive
description: Classer les snapshots OmniFocus valides en NOW, NEXT, FLASH, COMMS, RADAR, WAITING et BACKLOG sans ecrire dans OmniFocus en Phase 1.
version: 0.1.0
author: Belkora
platforms: [linux]
metadata:
  hermes:
    tags: [belkora, executive, omnifocus, gtd, read-only]
    category: productivity
---

# OmniFocus Executive

Utiliser uniquement un snapshot produit par le relais Mac approuve. Le snapshot doit porter une heure de synchronisation et ne pas depasser le TTL central.

Si le snapshot est absent ou stale, dire `OmniFocus indisponible ou perime` ; ne pas inventer les actions.

## Classement

- `NOW` : exactement une action.
- `NEXT` : environ cinq actions.
- `FLASH` : petites actions urgentes a batcher.
- `COMMS` : appels, emails, relances et petites validations.
- `RADAR` : echeances proches sans action immediate.
- `WAITING` : delegations et attentes.
- `BACKLOG` : reste masque par defaut.

Prioriser deadline, consequence, cash/client, personnes bloquees, strategie et effort. Ne pas utiliser nouveaute, curiosite ou plaisir comme criteres objectifs.

Phase 1 : lecture seulement. N'appelle aucun outil create/edit/remove/batch OmniFocus. Une approbation Odoo seule ne cree jamais une tache OmniFocus.
