# Bureau Ahmed — architecture d'accueil interne

## Ce que reçoit un collaborateur

Chaque collaborateur dispose de trois éléments distincts :

1. le skill portable `bureau-ahmed-request` dans Claude Code ou Kimi Code ;
2. un credential API propre à sa personne et à son appareil ;
3. son compte Telegram personnel, pré-enregistré par son ID numérique exact.

Le modèle aide à rechercher, comparer et structurer. Le serveur reste l'autorité : il injecte l'identité, limite les sociétés Odoo, vérifie les références et refuse les écritures.

## Parcours normal

1. Le collaborateur décrit le problème à Claude Code ou Kimi Code.
2. Le skill exige la recherche, les sources, les options, la recommandation et le travail déjà réalisé.
3. Pour Odoo, le client appelle l'API Bureau Ahmed :
   - recherche par nom uniquement sur `project.project` ou `project.task` ;
   - vérification par ID exact sur projet, tâche, document ou approbation ;
   - filtrage par société autorisée et champs non sensibles ;
   - retour d'un reçu signé, lié à la personne et à la cible.
4. Le client soumet un request pack v1 avec une clé d'idempotence.
5. Bureau Ahmed crée un `request_id`, indexe les liens et les opérations au statut `PROPOSED`, puis exécute zéro écriture métier.
6. L'API retourne un lien privé `t.me/<bot>?start=<jeton-unique>`.
7. Le collaborateur ouvre ce lien avec son compte Telegram pré-vérifié. Le bot rattache le chat privé au même `request_id` ; les précisions suivantes complètent le dossier existant.

Une demande issue de Telegram n'est acceptée qu'après appairage. Un collaborateur deja pre-verifie peut aussi envoyer `/start` sans jeton : le serveur ne l'accepte que depuis son propre chat prive, jamais depuis le groupe Gotion. Telegram est la conversation ; Odoo demeure la source métier.

## Séparation Railway

Le service actuel d'Ahmed reste inchangé. Le pilote interne utilise un second service Railway construit depuis la même image, avec :

- la commande de démarrage `/app/start-internal-intake.sh` ;
- un volume `/data` distinct ;
- un nouveau bot Telegram et un token distincts ;
- des credentials modèle distincts ;
- un accès privé au lecteur Odoo MCP ;
- seulement le toolset `mcp-internal-intake` ; terminal et navigateur désactivés.

Variables requises sur ce second service :

- `TELEGRAM_BOT_TOKEN` ;
- `TELEGRAM_ALLOWED_USERS` avec les IDs numériques exacts des pilotes ;
- `INTERNAL_INTAKE_TELEGRAM_BOT_USERNAME` ;
- `INTERNAL_INTAKE_DEVICE_CREDENTIALS_JSON` ;
- `INTERNAL_INTAKE_CONTEXT_SIGNING_KEY` d'au moins 32 caractères ;
- `ODOO_MCP_URL` vers une adresse privée, par exemple `*.railway.internal` ;
- les credentials du fournisseur de modèle choisis pour ce service.

Format du registre d'identité :

```json
{
  "credentials": [
    {
      "credential_id": "cred-employe-appareil",
      "requester_id": "collaborateur-exact",
      "display_name": "Nom vérifié",
      "device_id": "poste-exact",
      "token_sha256": "SHA256_DU_TOKEN_REMIS_HORS_BANDE",
      "telegram_user_id": "ID_NUMERIQUE_EXACT",
      "odoo_company_ids": [1],
      "active": true
    }
  ]
}
```

Le token brut n'entre jamais dans Railway sous ce registre : seul son hash y est stocké. Le token brut est remis individuellement à l'employé et placé uniquement dans `BUREAU_AHMED_DEVICE_TOKEN` sur son appareil.

## Limite du pilote

Le pilote sait qualifier, rechercher un contexte restreint, relier, converser et proposer. Il ne sait pas créer une activité Odoo, publier une note, modifier une tâche, lier un document, approuver, payer, acheter ou envoyer un engagement externe. Une future phase writer devra avoir une approbation explicite, une identité de service séparée et une relecture Odoo après chaque écriture.
