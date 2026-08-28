# Integration OmniFocus — reutiliser, ne pas reecrire

## Existant confirme

L'integration actuelle est locale au Mac : `omnifocus-mcp` 1.15.0 communique par socket Unix avec un daemon qui utilise `osascript`, JXA/Omni Automation et OmniFocus.app 4.8.12. Elle expose des lectures et des ecritures, sans filtre de permissions natif.

Elle ne peut pas etre executee dans Railway/Linux et ne doit jamais etre exposee au Bot collaborateurs.

## Architecture Phase 1

```text
OmniFocus.app <- omnifocus-mcp <- relais Mac sortant
                                    |
                                    v
                      snapshot minimal et horodate
                                    |
                                    v
                         Hermes Executive Railway
```

Le Mac initie le flux ; aucun acces general entrant vers le Mac. Le snapshot autorise seulement IDs, titres, projets, tags, statut, echeances, defer dates et estimations necessaires. TTL initial : 30 minutes. Au-dela, Hermes dit `OmniFocus indisponible ou perime`.

## Vues

- `NOW` : exactement une action recommandee ;
- `NEXT` : environ cinq actions ;
- `FLASH` : petites urgences batchees ;
- `COMMS` : appels, emails, relances et petites validations ;
- `RADAR` : echeances et risques ;
- `WAITING` : delegations/attentes ;
- `BACKLOG` : masque par defaut.

La priorite compare deadline, consequence, cash/client, personnes bloquees, strategie et effort. Nouveaute, curiosite et plaisir ne sont pas des criteres objectifs.

## Gates

Phase 1 n'active ni relais ni ecriture : le code et le skill savent signaler une source absente/stale. En Phase 2, une commande de creation devra etre confirmee, stable, appliquee une seule fois sur le Mac et relue dans OmniFocus. Une approbation Odoo ne devient une tache que si Ahmed doit accomplir une action distincte.
