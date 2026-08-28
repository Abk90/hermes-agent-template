# Architecture recommandee — Hermes Executive Operating System

Statut : architecture cible apres audit, avec deploiement progressif
Principe : reutiliser Hermes sur Railway et ses primitives natives ; ne pas modifier le core upstream.

## Decision d'architecture

Le systeme doit etre compose de deux Hermes isoles et d'un petit ledger partage :

1. **Hermes Executive** : le service Railway actuel `hermes-agent`, reserve a Ahmed ;
2. **Bureau d'Ahmed** : un service Hermes Railway separe, avec son propre volume et son propre bot Telegram, reserve aux collaborateurs autorises ;
3. **Executive Ledger** : un service prive minimal qui stocke les demandes, liens et evenements d'audit, sans devenir une base metier.

Cette separation est plus forte qu'un simple profil dans le meme conteneur. Un profil Hermes isole config, memoire, skills et sessions, mais ne constitue pas a lui seul une sandbox de filesystem. Le Bot collaborateurs ne doit donc pas cohabiter avec les secrets, la memoire et les connecteurs personnels d'Ahmed.

## Vue cible

```text
Collaborateurs autorises
        |
        v
Telegram : Bureau d'Ahmed
        |
        v
Hermes internal-intake — service Railway isole
  - allowlist stricte
  - aucun terminal/browser general
  - aucun OmniFocus/WhatsApp/Google prive
  - skill internal-request-triage
        |
        v
Executive Ledger — API/MCP prive, append-only
  - request_id / idempotency_key
  - classification et justification
  - source IDs Odoo/Telegram/OmniFocus
  - statut, erreurs, confirmations, timestamps
        |
        +---------------------------+
        |                           |
        v                           v
Odoo MCP read-only           Hermes Executive
source metier                service actuel, Ahmed seul
                                    |
                      +-------------+-------------+
                      |             |             |
                      v             v             v
                Odoo review   OmniFocus relay   Telegram Ahmed
                read-only     Mac, read-only    NOW / FLASH / batches
```

## Responsabilites et sources de verite

| Composant | Responsabilite | N'est pas |
|---|---|---|
| Telegram | Interface humaine, intake, clarification et notification | Une base metier ou un workflow d'approbation officiel |
| Odoo | Transactions, achats, paiements, commandes, validations et documents operationnels | Une liste personnelle de prochaines actions |
| OmniFocus | Actions propres a Ahmed, Waiting, projets personnels/executifs et echeances d'action | Une copie des approbations Odoo |
| Hermes | Comprendre, qualifier, relier, prioriser, proposer, router et resumer | Une nouvelle source de verite metier |
| Executive Ledger | Correlation, idempotence, etats techniques et audit trail | Un CRM, un ERP ou un task manager concurrent |

## Pourquoi deux services Hermes

### Hermes Executive — existant

- Reutilise `@Hermesbelkorabot`.
- Allowlist : Ahmed seulement.
- Conserve le contexte executif, les skills `executive-dispatch`, `odoo-approval-review` et `omnifocus-executive`.
- Peut lire les resumes Odoo, les snapshots OmniFocus et la queue executive.
- Ne recoit aucune ecriture financiere automatique en Phase 1.

### Bureau d'Ahmed — nouveau

- Token Telegram distinct obligatoire.
- Volume, `HERMES_HOME`, memoire, sessions et secrets separes.
- Allowlist de collaborateurs resolus par ID numerique exact.
- Contexte minimal : politiques de triage et procedures internes publiees pour ce Bot.
- Aucun acces a OmniFocus, Google personnel, WhatsApp, terminal general, fichiers d'Ahmed ou memoire executive.
- MCP autorises : ledger et sous-ensemble Odoo read-only necessaire a la verification d'existence/statut.
- Les commandes administration, model, plugins, skills, pause, restart et configuration sont refusees aux utilisateurs ordinaires.

## Extension Hermes choisie par besoin

| Besoin | Primitive native prioritaire | Code custom seulement si necessaire |
|---|---|---|
| Role et contexte | Profil + `SOUL.md` | Non |
| Triage conversationnel | Skill | Moteur de regles deterministe pour controles/gates |
| Odoo | MCP existant filtre en lecture seule | Adaptateur controle uniquement si les requetes metier ne sont pas fiables |
| OmniFocus | MCP local existant | Relais Mac sortant et filtre read-only |
| Schedules | Cron Hermes | Script deterministe pour health/idempotence |
| P0 immediat | Webhook Hermes signe / wake agent | Notification directe de secours seulement si le webhook est insuffisant |
| Audit et mapping | MCP/API prive | Ledger SQLite/PostgreSQL minimal |
| Observabilite | Logs, cron history, CLI | Endpoint `/status` du ledger, sans dashboard lourd |
| Regles de securite | Allowlists, outils/MCP filtres, deny rules | Separer les services et durcir le reseau |

## Executive Ledger

### Schema minimal

`requests`

- `request_id` stable ;
- `idempotency_key` unique ;
- `source` et `source_message_id` ;
- `requester_id` exact ;
- sujet, projet/client, type ;
- decision attendue ;
- deadline et consequence de l'attente ;
- montant, personnes bloquees, reversibilite ;
- solution et recommandation du demandeur ;
- priorite P0-P4, confiance et justification ;
- route, statut et horodatages.

`links`

- `request_id` ;
- systeme cible ;
- type et ID cible ;
- URL ou reference non secrete.

`events`

- sequence append-only ;
- timestamp ;
- acteur ;
- action ;
- ancien/nouvel etat ;
- justification ;
- resultat ou erreur ;
- confirmation Ahmed eventuelle.

`connector_state`

- connecteur ;
- derniere tentative ;
- derniere reussite ;
- curseur/fraicheur ;
- etat `OK`, `STALE`, `FAILED`, `RETRYING` ;
- erreur sanitisee.

### Invariants

- une `idempotency_key` ne cree jamais deux demandes ;
- une transition d'etat invalide est refusee ;
- aucun evenement d'audit n'est supprime par l'application ;
- les IDs metier restent des references vers Odoo/OmniFocus, pas des copies silencieuses ;
- toute action distante est `PENDING` jusqu'a la relecture du systeme cible ;
- un timeout ou une erreur n'est jamais transforme en `DONE`.

## Triage et routes

### Qualification obligatoire

Avant escalade, le Bot cherche au minimum :

- demandeur et sujet ;
- projet/client ;
- decision attendue ;
- vraie echeance ;
- consequence dans deux heures et demain ;
- personnes bloquees ;
- montant ;
- reversibilite ;
- solution et recommandation du collaborateur ;
- existence du workflow Odoo quand applicable.

### Route

```text
Demande recue
  |
  +-- danger / crise irreversible imminente --> P0 + voie humaine directe
  |
  +-- consequence importante aujourd'hui ----> P1 / FLASH
  |
  +-- procedure ou responsable connu --------> reponse / delegation
  |
  +-- workflow officiel ---------------------> Odoo, pas de doublon Telegram
  |
  +-- Ahmed doit faire une action ------------> OmniFocus, apres gate
  |
  +-- Ahmed doit decider ---------------------> Executive Queue
  |
  +-- information / idee ---------------------> P3/P4, sans interruption
```

La priorite est expliquee et stockee. « Urgent » seul ne suffit jamais. Le demandeur peut toujours recevoir l'instruction d'utiliser la voie humaine directe pour un danger reel.

## Odoo Approval Monitor

### Phase 1

- `ODOO_YOLO=read` ;
- seuls les outils de lecture sont exposes ;
- cron configurable, suggestion initiale toutes les quinze minutes aux heures de travail ;
- `[SILENT]` si aucun changement important ;
- idempotency key derivee du modele, record ID, etat et version/date ;
- aucune approbation ni chatter automatique ;
- chaque item produit une fiche decisionnelle, pas une nouvelle tache OmniFocus.

### Gate OmniFocus

Une approbation Odoo ne cree une action OmniFocus que si Ahmed doit effectivement agir hors Odoo : appeler, obtenir une piece, clarifier ou negocier.

### Phase ulterieure

Une ecriture Odoo ne pourra etre activee que par outil/metier explicitement autorise, apres :

1. proposition normalisee ;
2. confirmation Ahmed liee au `request_id` ;
3. idempotency key ;
4. ecriture sous identite tracee ;
5. relecture du record ;
6. evenement d'audit `DONE` ou `FAILED`.

## OmniFocus Executive Manager

### Transport recommande

Le Mac initie la connexion vers Railway. Railway ne recoit aucun acces general entrant au Mac.

```text
LaunchAgent Mac
  -> client MCP local `omnifocus-mcp`
  -> requetes de lecture autorisees
  -> snapshot minimal signe
  -> Executive Ledger prive
```

Le snapshot contient les IDs, titres, projets, tags, statut, echeances, defer dates, estimation et fraicheur necessaires au triage. Il exclut les donnees non requises et n'est jamais visible par `internal-intake`.

### Vues produites

- `NOW` : exactement une action recommandee ;
- `NEXT` : environ cinq actions ;
- `FLASH` : petites urgences batchables ;
- `COMMS` : appels, emails, relances et petites validations ;
- `RADAR` : echeances et risques a surveiller ;
- `WAITING` : delegations et attentes ;
- `BACKLOG` : reste non affiche par defaut.

### Ecritures

Desactivees en Phase 1. En Phase 2, le Mac pollera une queue de commandes confirmees et appliquera chaque commande avec prelecture, idempotency key et relecture. Le serveur MCP existant est reutilise ; il n'est pas remplace.

## Cron et evenements

Tous les nouveaux jobs sont initialement installes desactives.

| Job | Frequence de depart | Profil | Livraison |
|---|---|---|---|
| Odoo approval scan | toutes les 15 min, heures de travail | executive | `[SILENT]` si rien |
| Executive digest matin | milieu de matinee | executive | Ahmed |
| Executive digest apres-midi | debut et fin d'apres-midi | executive | Ahmed |
| Connector health | toutes les 15 min | script deterministe | seulement erreur/stale |
| Weekly Review prep | hebdomadaire | executive | decisions seulement |

P0 doit etre evenementiel via webhook signe lorsque possible. Le polling n'est qu'un filet de securite.

## Securite

### Barriere de confiance

```text
Collaborateur non fiable
  -> Telegram allowlist
  -> profil/service intake minimal
  -> validation de schema
  -> ledger append-only
  -> lecture Odoo filtree
  -X-> secrets / shell / OmniFocus / WhatsApp / memoire Ahmed
```

### Regles obligatoires

- `GATEWAY_ALLOW_ALL_USERS=false` ;
- pairing collaborateurs desactive ou approuve manuellement par Ahmed ;
- tokens Telegram distincts ;
- aucune commande d'administration pour les collaborateurs ;
- aucun secret dans config versionnee, prompts, logs ou ledger ;
- MCP allowlist par nom exact d'outil ;
- terminal et browser absents du profil intake ;
- Odoo read-only prouve au serveur et au client ;
- donnees financieres et RH minimales ;
- prompt utilisateur traite comme contenu non fiable ;
- rate limiting et taille maximale des demandes ;
- voie humaine directe P0 ;
- backups chiffres ou stockes dans un emplacement controle ;
- rotation du secret local historique avant le pilote.

## Observabilite

Le MVP utilise une CLI et des rapports, pas un dashboard lourd.

Commandes cibles :

```text
executive-os status
executive-os queue --priority P0,P1
executive-os connectors
executive-os why <request_id>
executive-os audit <request_id>
```

La sante distingue :

- deploiement Railway ;
- processus Hermes ;
- gateway Telegram ;
- connexion MCP ;
- derniere lecture Odoo ;
- fraicheur OmniFocus ;
- erreurs/retries ;
- taille des queues P0/P1.

Un HTTP 200 Railway ne suffit jamais a conclure que le systeme metier fonctionne.

## Strategie de deploiement

### Phase 1A — correction et dry run

- corriger Odoo vers `read` ;
- ajouter ledger, config centrale, skills et tests au fork ;
- deployer sans cron actif ;
- tester via le profil executif actuel, Ahmed uniquement ;
- ne rien ecrire dans Odoo ou OmniFocus.

### Phase 1B — observation

- activer scans Odoo en lecture seule ;
- activer le snapshot OmniFocus Mac ;
- comparer les classifications Hermes aux decisions Ahmed ;
- conserver les notifications P2-P4 silencieuses/batchees.

### Phase 1C — intake pilote

- nouveau token Telegram ;
- service/volume intake distinct ;
- deux ou trois collaborateurs exacts maximum ;
- donnees synthetiques puis demandes reelles non financieres ;
- revue quotidienne des faux positifs/negatifs.

### Phase 2 — assist

- ecritures OmniFocus confirmees ;
- batching et Weekly Review ;
- toujours aucune ecriture Odoo sensible.

### Phase 3 et 4

- canal interne recommande ;
- automatisations simples uniquement apres historique, seuils et GO distincts.

## Criteres de passage

Le MVP ne passe en pilote collaborateurs que si :

- les douze tests d'acceptation sont automatises ou traces ;
- le test negatif Odoo prouve le refus des ecritures ;
- les retries ne dupliquent aucune demande ;
- `why <id>` reconstruit la justification ;
- un connecteur indisponible reste `FAILED/PENDING`, jamais `DONE` ;
- aucun test ne revele le contexte prive d'Ahmed ;
- Ahmed valide le bot, les utilisateurs, les horaires, les seuils et le texte d'urgence.
