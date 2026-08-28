# Audit de l'etat actuel — Hermes Executive Operating System

Date de l'audit : 28 aout 2026
Perimetre : projet Railway `hermes-belkora`, service `hermes-agent`, environnement `production`
Mode de l'audit : lecture seule. Aucun message, aucune ecriture Odoo, aucun changement Railway et aucune lecture WhatsApp n'ont ete effectues pendant l'audit.

## Verdict executif

Le socle Railway existant doit etre conserve. Il fournit deja Hermes, Telegram, une persistance durable, les skills, les MCP, les cron jobs, les hooks, le dashboard, l'authentification Codex et des connecteurs utiles.

Il n'est cependant pas encore un Executive Operating System et il ne doit pas etre ouvert aux collaborateurs dans son etat actuel.

Les quatre raisons principales sont :

1. la production n'execute qu'un profil Hermes `default`, puissant et reserve de fait a Ahmed ;
2. aucun Bot `Bureau d'Ahmed`, skill de triage, ledger executif ou cron metier n'est versionne ;
3. l'integration OmniFocus existante est locale au Mac et ne peut pas fonctionner directement dans le conteneur Linux Railway ;
4. la protection Odoo a derive : au 28 aout, le serveur est en `ODOO_YOLO=true` et Hermes expose trois outils d'ecriture Odoo en plus des outils de lecture.

La priorite immediate est donc : remettre Odoo en lecture seule, conserver le bot actuel comme canal executif d'Ahmed, construire le ledger et les skills en mode observation, puis creer le canal collaborateurs dans un service/profil isole avec un token Telegram et une allowlist distincts.

## Etat live verifie

| Element | Etat confirme le 28/08/2026 | Preuve / limite |
|---|---|---|
| Projet Railway | `hermes-belkora` (`9007876b-7f82-4e8d-91ea-4412fbda1e0a`) | CLI Railway avec projet et environnement explicites |
| Service | `hermes-agent` (`0b6e2847-9cdd-4eb2-8ee0-0aa2dba762f6`) | CLI Railway |
| Environnement | `production` (`7511c801-16c0-4460-bb5c-625d64d807e3`) | CLI Railway |
| Deploiement actif | `f234ac74-d6c2-4de9-a3d9-22f1b04dcd0a`, `SUCCESS` | Commit `826b19c67b8666a42104f4a28d5022a262a9dcb9` |
| Source | `Abk90/hermes-agent-template@main` | Railway + depot local propre avant travaux |
| Hermes | `0.20.5`, release `2026.8.19`, config v38 | API native authentifiee |
| Mode gateway | `single` | Un seul profil live : `default` |
| Modele | `openai-codex` / `gpt-5.6-sol` | Etat runtime et logs ; aucun secret affiche |
| Sante publique | HTTP 200, `status=ok`, `gateway=running` | Ne prouve pas les connecteurs metier |
| Telegram | `connected` | Etat runtime ; aucun nouveau message de test envoye pendant l'audit |
| Pause | inactive | Etat wrapper `pause=null` |
| Redemarrages | 0 depuis le boot observe | Etat runtime |
| Volume | `/data`, `READY`, environ 3,6 Go utilises sur 50 Go | API Railway |
| Profil collaborateur | absent | Aucun profil autre que `default` |

## Architecture actuelle

```text
Internet
   |
   v
Railway hermes-agent
   |
   +-- Starlette/Uvicorn : login, setup, health, reverse proxy
   +-- Dashboard Hermes natif sur 127.0.0.1:9119
   +-- Un gateway Hermes supervise : profil default
   +-- Volume /data/.hermes
   |     +-- config.yaml, .env, auth.json
   |     +-- sessions, memories, skills, cron, hooks, pairing
   |     +-- credentials Workspace
   |     +-- etat WhatsApp Pro et personnel
   +-- MCP Google Workspace en lecture seule
   +-- MCP Odoo prive Railway
   +-- deux bridges WhatsApp separes
```

Le conteneur public est protege par un login commun au setup et au dashboard. Le gateway est supervise avec backoff et coupe-circuit. Le dashboard natif ne dispose pas de la meme supervision. Le volume rend la configuration et l'etat persistants entre les redeploiements.

## Capacites Hermes deja disponibles

Les primitives suivantes sont natives et doivent etre reutilisees avant d'ajouter du code :

- profils Hermes, chacun avec config, memoire, skills, secrets, sessions et gateway distincts ;
- Bots, qui sont une vue UI des profils et non une nouvelle base de donnees ;
- skills charges a la demande ;
- MCP avec filtrage explicite par outil ;
- plugins et hooks ;
- cron jobs avec skills, historique et suppression de livraison par `[SILENT]` ;
- webhooks ;
- allowlists, pairing et controles de commandes Telegram ;
- dashboard, logs, analytics, Kanban et backup/restore ;
- ESTOP/pause, a restreindre au proprietaire avant tout usage collectif.

Sources amont consultees :

- https://hermes-agent.nousresearch.com/docs/llms.txt
- https://hermes-agent.nousresearch.com/docs/user-guide/profiles
- https://hermes-agent.nousresearch.com/docs/user-guide/security
- https://hermes-agent.nousresearch.com/docs/user-guide/features/cron
- https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram

## Profils, Bots, skills, plugins et cron actuels

### Confirme live

- Un seul profil live existe : `default`.
- Le gateway fonctionne en mode `single`.
- Le bot documente est `@Hermesbelkorabot`, actuellement utilise par Ahmed.
- Telegram est connecte, avec une identite approuvee et aucune demande de pairing en attente.
- Les API Hermes recensent 102 skills globaux actives : 77 bundled, 23 agent et 2 hub. Le profil en annonce 108 ; l'ecart doit etre explique avant migration.
- Cinquante-cinq plugins bundled sont recenses, aucun plugin utilisateur/custom n'est actif et `plugins.enabled=[]`. Deux extensions de dashboard orphelines, Achievements et Kanban, restent visibles.
- Huit cron jobs existent : quatre actifs, trois termines et un pause. Deux jobs actifs sont en `blocked_config`, avec dix et quatre echecs consecutifs ; deux autres ont un dernier resultat `ok`.
- `cron.allow_agent_scheduling=false` et `approvals.cron_mode=deny`. Les jobs deja enregistres continuent neanmoins d'etre planifies.
- Le fuseau Hermes est vide : les horaires ressortent en UTC, a corriger avant les batchs Casablanca.
- Le depot ne versionne aucun profil ou Bot metier, aucun prompt `Bureau d'Ahmed`, aucun skill executif ni hook metier.
- Hermes conserve ces composants sur le volume ; le depot ignore volontairement l'etat runtime des skills.
- Quatre MCP sont actives : Google Workspace read-only, Odoo prive, WhatsApp Pro et WhatsApp personnel. Chaque bridge WhatsApp expose huit outils de lecture.
- Aucun MCP, skill, plugin, toolset ou cron OmniFocus n'est deploye.

### Non prouve pendant cet audit

- Le contenu exact de chaque skill et cron runtime n'a pas ete exporte depuis le volume : aucune cle Railway SSH locale n'est enregistree.
- La sante loopback actuelle `authenticated/connected` des deux bridges WhatsApp n'a pas pu etre relue sans SSH.
- Les API permettent l'inventaire, mais une absence dans Git ne suffit pas a garantir la reproductibilite. Toute migration doit produire un export Hermes avant activation.

## Telegram et Messaging Gateway

Le gateway Telegram est connecte. Le wrapper expose un seul token et une allowlist utilisateurs. Le modele de securite Hermes permet le deny-by-default, les allowlists, le pairing et des commandes differentes pour admins et utilisateurs ordinaires.

Ce socle est insuffisant pour les collaborateurs parce que le profil `default` partage son contexte, ses skills et ses MCP puissants. Un profil Hermes isole separe l'etat, mais la documentation precise qu'un profil n'est pas a lui seul une sandbox de filesystem. Le bot collaborateurs ne doit donc pas partager le meme environnement puissant que le bot executif.

Un second profil Telegram exige son propre token ; le meme token ne peut pas etre poll par deux profils simultanement.

## Integration OmniFocus existante

L'« API OmniFocus » actuelle n'est pas une API cloud. Elle fonctionne ainsi :

```text
Client MCP local
  -> npx -y omnifocus-mcp 1.15.0 (stdio)
  -> daemon local via socket Unix
  -> osascript / JXA / Omni Automation
  -> OmniFocus 4.8.12 sur le Mac d'Ahmed
```

Elle expose douze outils couvrant la lecture, la creation, la modification, la suppression et les operations par lot. Aucun filtre de permissions n'est applique par le serveur lui-meme.

Consequences :

- elle est utile et ne doit pas etre reecrite ;
- elle ne peut pas tourner nativement dans Railway/Linux, car elle depend d'OmniFocus.app et de `osascript` ;
- elle ne doit jamais etre exposee au Bot collaborateurs ;
- la Phase 1 doit la reutiliser derriere un adaptateur Mac sortant, initialement en lecture seule ;
- toute future ecriture doit etre confirmee, idempotente et relue dans OmniFocus.

## Integration Odoo existante

### Architecture

- Service Railway prive `odoo-mcp`.
- Image `ghcr.io/ivnvxd/mcp-server-odoo:0.7.1`.
- Transport Streamable HTTP sur le reseau prive Railway.
- `call_model_method` desactive.
- Une ancienne note du 25 aout indiquait `ODOO_YOLO=read` et cinq outils de lecture exposes.

### Derive live du 28 aout

La configuration actuelle n'est plus celle du 25 aout :

- `ODOO_YOLO=true` ; dans le contrat du serveur 0.7.1, `true` signifie acces lecture/ecriture via XML-RPC, sous les ACL et record rules du compte Odoo ;
- le serveur annonce neuf outils ;
- Hermes en expose huit : cinq lectures plus `create_record`, `update_record` et `post_message` ;
- seul `delete_record` est filtre ;
- aucune ecriture n'a ete effectuee pendant l'audit.

Cette derive contredit directement la Phase 1 demandee. Elle doit etre corrigee avant tout cron Odoo ou ouverture du systeme aux collaborateurs.

Autre contradiction a conserver : la mission parle d'Odoo 18, alors que l'instance publique verifiee aujourd'hui repond comme Odoo 19.0+e et le depot Assistant designe Odoo 19 comme source courante. Aucun developpement ne doit etre fige sur un schema Odoo 18 sans arbitrage.

## Google Workspace et WhatsApp

- Google Workspace MCP 1.24.1 est installe dans un environnement separe et documente en lecture seule.
- Deux bridges WhatsApp persistent separement : Pro sur 8180, personnel sur 8181.
- La barriere binaire rejette l'envoi lorsque `WHATSAPP_READ_ONLY=true`.
- Le wrapper MCP vendored contient neanmoins des outils d'envoi : la selection live des outils et le refus HTTP doivent etre re-testes apres chaque changement.
- Les bridges ecoutent actuellement toutes les interfaces du conteneur (`:8180` et `:8181`), pas uniquement loopback. Plusieurs endpoints sans authentification existent. Le reseau prive Railway reduit l'exposition publique, mais le bind doit etre durci.

## Configuration, secrets et persistance

| Donnee | Emplacement actuel | Observation |
|---|---|---|
| Config Hermes | `/data/.hermes/config.yaml` | Source comportementale autoritative |
| Secrets Hermes | `/data/.hermes/.env` et `auth.json` | Ne jamais versionner |
| Skills | `/data/.hermes/skills/` | Persistants mais pas versionnes dans ce fork |
| Cron | `/data/.hermes/cron/` | Bases et sorties persistantes |
| Sessions/memoire | `/data/.hermes/` | Contexte prive du profil default |
| Google OAuth | sous `/data/.hermes/workspace-mcp/` | Permissions durcies documentees |
| WhatsApp | `/data/.hermes/whatsapp/{pro,personnel}` | Etats isoles |

`auth.json` et les credentials Workspace sont explicitement durcis en `0600`, mais `.env`, `config.yaml`, certaines bases WhatsApp et certains medias ne le sont pas tous explicitement.

Une ancienne valeur sensible est egalement encore presente en clair dans `SESSION_STATE.md` local. Elle n'est pas reproduite ici. Sa rotation et sa purge doivent faire l'objet d'une operation controlee separee.

## Problemes et risques classes

### Critiques — avant tout pilote collaborateur

1. Odoo est en mode full YOLO et trois outils d'ecriture sont visibles par Hermes.
2. Un seul profil puissant contient le contexte prive d'Ahmed.
3. Aucun ledger idempotent n'empeche les doublons apres retry ou redemarrage.
4. Le connecteur OmniFocus existant inclut des ecritures et n'est pas filtrable nativement.
5. Aucun token ni allowlist exacts du futur Bot collaborateurs ne sont encore fournis.
6. Tous les skills sont actives, y compris des capacites sans rapport avec le perimetre et un skill nomme `godmode`; la surface doit etre reduite avant le pilote.

### Eleves

1. `/health` renvoie HTTP 200 meme si le gateway est en erreur et ne teste ni Telegram, ni Odoo, ni OmniFocus, ni WhatsApp.
2. Les bridges WhatsApp ne bindent pas uniquement loopback.
3. `/pause` peut etre utilise par un utilisateur paire et persiste tout en laissant la sante verte.
4. Skills, profils, MCP et cron runtime peuvent deriver de Git.
5. Les credentials Odoo historiques existent encore dans le service `hermes-agent` malgre le service MCP prive ; leur utilite doit etre prouvee avant suppression.
6. Deux cron jobs actifs sont en `blocked_config` et echouent de facon repetee.

### Moyens

1. Le dashboard natif n'a pas le meme superviseur que le gateway.
2. L'image installe Chromium alors qu'une valeur de config desactive le backend navigateur par defaut.
3. Plusieurs dependances Python ne sont pas epinglees exactement.
4. La couverture de tests du wrapper est limitee aux cinq cas Go de pairing WhatsApp et au self-test SQLite/FTS5 du build.

## Composants reutilisables

- service Railway, fork controle, image immuable et volume persistant ;
- profil `default` comme futur `Hermes Executive` reserve a Ahmed ;
- Telegram gateway, allowlists et pairing ;
- Odoo MCP prive apres retour en lecture seule ;
- Google Workspace MCP lecture seule ;
- skills, cron, hooks, webhooks et MCP natifs Hermes ;
- `[SILENT]` pour les polls sans signal ;
- backup/restore Hermes ;
- ponts WhatsApp separes, hors perimetre MVP tant que leur reseau n'est pas durci ;
- `omnifocus-mcp` local, reutilise derriere un adaptateur plutot que remplace.

## Fichiers a creer ou modifier pour le MVP

Le MVP doit rester hors du core upstream Hermes.

```text
executive-os/
  AUDIT_CURRENT_STATE.md
  ARCHITECTURE.md
  SECURITY_MODEL.md
  TRIAGE_RULES.md
  ODOO_INTEGRATION.md
  OMNIFOCUS_INTEGRATION.md
  TELEGRAM_GATEKEEPER.md
  OPERATIONS.md
  TEST_PLAN.md
  HOW_AHMED_USES_IT.md
  HOW_EMPLOYEES_USE_IT.md
  config/executive-os.toml
  src/executive_os/
  skills/
  profiles/
  tests/
```

Fichiers existants susceptibles d'etre modifies :

- `Dockerfile` uniquement pour embarquer le composant versionne et ses dependances ;
- `start.sh` uniquement pour un bootstrap idempotent, jamais pour ecraser un volume ;
- `requirements.txt` avec versions controlees ;
- `server.py` uniquement si une route de sante fonctionnelle etroite ne peut pas etre obtenue nativement ;
- configuration Railway du service Odoo pour remettre `ODOO_YOLO=read` ;
- `config.yaml` persistant via les commandes/API Hermes prises en charge, avec relecture apres ecriture.

## Plan de migration

### Etape 0 — securiser et figer

- sauvegarder/exporter le profil Hermes courant ;
- remettre Odoo en `read` et verifier que create/update/post/unlink sont absents ou refuses ;
- verifier les outils WhatsApp exposes et les refus d'envoi ;
- ne pas ouvrir le bot actuel aux collaborateurs.

### Etape 1 — observer

- ajouter un ledger d'evenements avec IDs stables ;
- installer les skills de triage, revue Odoo et dispatch executif ;
- utiliser le bot actuel uniquement pour Ahmed ;
- garder Odoo et OmniFocus en lecture seule ;
- laisser tous les cron jobs nouveaux desactives jusqu'aux tests manuels.

### Etape 2 — connecter OmniFocus sans le remplacer

- installer sur le Mac un adaptateur qui appelle `omnifocus-mcp` local ;
- pousser des snapshots signes vers Railway ou utiliser un tunnel prive authentifie ;
- refuser toute ecriture en Phase 1 ;
- mesurer et afficher la fraicheur de la derniere synchro.

### Etape 3 — pilote collaborateurs

- creer un BotFather token distinct `Bureau d'Ahmed` ;
- resoudre les identites Telegram exactes des collaborateurs pilotes ;
- deployer le profil/service intake avec volume et contexte minimaux ;
- activer uniquement le ledger et la lecture Odoo necessaire ;
- tester les douze criteres d'acceptation avec donnees synthetiques.

### Etape 4 — assistance controlee

- activer creation OmniFocus uniquement apres confirmation Ahmed, idempotency key et relecture ;
- batcher les decisions ;
- conserver toutes les ecritures Odoo desactivees jusqu'a un GO distinct par type d'objet et action.

## Gates avant go-live

- Odoo prouve read-only par test negatif d'ecriture.
- Bot collaborateurs separe avec token et allowlist exacts.
- Aucun acces au contexte, a OmniFocus, aux WhatsApp ou aux credentials d'Ahmed.
- Tests de doublon, retry, panne et reprise conformes.
- P0 conserve une voie humaine directe.
- Les douze tests MVP sont traces avec preuves.
- Ahmed valide le contenu du Bot, les utilisateurs pilotes et les horaires avant activation.
