---
name: executive-dispatch
description: Repondre a now, retriage, flash, comms, waiting et why en fusionnant prudemment la queue executive et les sources disponibles.
version: 0.1.0
author: Belkora
platforms: [linux]
metadata:
  hermes:
    tags: [belkora, executive, dispatch, now]
    category: productivity
---

# Executive Dispatch

Ce skill est reserve au profil executif d'Ahmed.

## Commandes naturelles

Reconnais notamment `now`, `retriage`, `flash`, `comms`, `waiting`, `approvals` et `why <id>` ainsi que leurs formulations naturelles en francais.

## Sources

1. Lis la queue via `mcp_executive_os_list_executive_queue`.
2. Utilise uniquement les connecteurs dont la fraicheur est `OK`.
3. Si Odoo ou OmniFocus est absent/stale, dis-le et ne presente pas l'arbitrage comme exhaustif.
4. Pour `why`, appelle `mcp_executive_os_why_request` et restitue la classification, les faits et l'audit.

## Arbitrage

Compare : deadline, consequence de l'inaction, impact cash/client, personnes bloquees, irreversibilite, importance strategique et effort.

Ne favorise jamais une action parce qu'elle est nouvelle, curieuse ou plaisante.

## Format principal

```text
MAINTENANT
[une action]
Pourquoi : ...
Duree estimee : ...
Debloque/protege : ...

ENSUITE
[jusqu'a cinq actions]

COMMS
[nombre + duree totale]
```

Propose un choix ; Ahmed conserve la decision finale. Une nouvelle demande ne remplace `MAINTENANT` que si attendre le prochain triage a une consequence superieure et prouvee.

Phase 1 : aucune ecriture Odoo ou OmniFocus.
