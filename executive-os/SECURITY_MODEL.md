# Modele de securite — Hermes Executive OS

Statut : Phase 1 `OBSERVE`, deny-by-default, 28 aout 2026.

## Frontieres de confiance

```text
Ahmed -> Bot executive -> Hermes Executive -> ledger prive
                                  |-> Odoo lecture seule
                                  |-> futur snapshot OmniFocus lecture seule

Collaborateur non fiable -> futur Bot Bureau d'Ahmed -> service/volume separes
                                                   |-> ledger minimal
                                                   |-> Odoo lecture filtree
                                                   X-> contexte Ahmed, shell, WhatsApp,
                                                       Google prive, OmniFocus, secrets
```

Le profil `default` live reste reserve a Ahmed. Le Bot collaborateurs n'est pas active dans le service actuel : un token Telegram distinct, les identites exactes et un second service/volume Railway sont des prerequis.

## Barrieres actives en Phase 1

- Odoo : `ODOO_YOLO=read` sur le serveur prive et whitelist Hermes limitee aux cinq outils de lecture.
- Executive OS : cinq outils locaux seulement ; aucune action Odoo, OmniFocus, financiere ou de communication externe.
- Ledger : fichier SQLite prive sous `/data/.hermes/executive-os`, mode `0600`, repertoire `0700`, evenements append-only.
- Telegram executive : allowlist, pas de `allow_all`, identite Ahmed uniquement.
- Secrets : variables Railway ou fichiers Hermes proteges ; aucun token dans Git, le ledger ou les prompts.
- Persistance : config Hermes sauvegardee avant la premiere fusion ; bootstrap idempotent qui preserve toute modification locale non reconnue.
- Ecritures sensibles : flags centraux a `false`, confirmation Ahmed et relecture du systeme cible obligatoires dans toute phase ulterieure.

## Menaces et controles

| Menace | Controle | Preuve attendue |
|---|---|---|
| Prompt injection collaborateur | service intake minimal, aucun outil general, schemas stricts | inventaire des outils du profil |
| Homonyme ou mauvais utilisateur | ID Telegram numerique exact, resolution du collaborateur avant allowlist | identite et canal verifies |
| Ecriture Odoo accidentelle | mode serveur `read` + `tools.include` Hermes | variables et inventaire relus |
| Doublon apres retry | `idempotency_key` unique + ID stable | test automatise et trace unique |
| Faux succes connecteur | etats `PENDING/RETRYING/FAILED/DONE`, relecture obligatoire | evenement d'audit |
| Fuite OmniFocus | relais Mac sortant, snapshot minimal, jamais expose a intake | scope et fraicheur du snapshot |
| Modification d'une skill par redeploiement | marqueur de contenu, preservation si divergence | resultat du bootstrap |
| Vol de token ou secret historique | rotation puis purge controlee | nouvelle authentification verifiee |

## Actions interdites en Phase 1

- paiement, approbation, creation ou modification Odoo ;
- creation, modification ou suppression OmniFocus ;
- envoi email, Telegram sortant automatise, WhatsApp ou partage Drive ;
- commande serveur declenchee par un collaborateur ;
- ouverture publique d'un bot, d'un MCP ou du ledger ;
- activation des nouveaux cron jobs avant tests de qualite et de bruit.

## Gates pour changer de phase

Une capacite d'ecriture exige : outil exact, identite exacte, autorisation explicite, proposition liee a un `request_id`, cle d'idempotence, prelecture, execution, relecture, resultat audite et rollback documente. Les seuils de delegation financiers restent a definir et ne valent jamais autorisation implicite.
