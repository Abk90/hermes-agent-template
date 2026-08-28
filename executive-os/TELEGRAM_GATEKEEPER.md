# Telegram Gatekeeper — Bureau d'Ahmed

## Decision de securite

Le Bot collaborateurs ne partage pas le service `hermes-agent`, son volume, sa memoire ou ses connecteurs. Il exige un second service Railway, un second volume, un token BotFather distinct et une allowlist d'IDs Telegram resolus exactement.

Il n'est pas active en Phase 1 faute de ces identites et du token distinct. Le bot executive existant reste reserve a Ahmed.

## Conversation attendue

Le collaborateur peut ecrire naturellement. Le Bot extrait le demandeur, le sujet, le projet/client, la decision attendue, l'echeance, les consequences, les personnes bloquees, le montant, la reversibilite, la reference Odoo et sa recommandation. Il ne pose que les questions manquantes.

Exemple :

```text
Collaborateur : Ahmed repond-moi vite pour le fournisseur.
Bot : Quel montant ? Avant quelle heure ? Que se passe-t-il dans deux heures,
      puis demain ? Quelle reference Odoo ? Quelle solution recommandes-tu ?
```

Une urgence humaine reelle conserve une voie directe. Le Bot ne promet jamais qu'Ahmed a lu ou accepte une demande.

## Permissions du futur service

- allowlist numerique, `allow_all=false`, pairing manuel ;
- aucune commande model/plugin/skill/config/pause/restart pour collaborateurs ;
- aucun shell, navigateur general, fichiers prives, WhatsApp, Google prive ou OmniFocus ;
- ledger minimal et sous-ensemble Odoo lecture seule seulement ;
- texte utilisateur traite comme non fiable ;
- reponses limitees aux procedures publiees et faits accessibles ;
- aucune donnee RH, finance confidentielle ou memoire executive revelee.

## Activation

Avant le pilote : creer le bot distinct, verifier chaque identite sans homonyme, construire le service/volume separes, inspecter ses outils, tester les douze scenarios d'acceptation, puis obtenir le GO d'Ahmed. Une paire Telegram ou un message livre n'est pas une preuve de lecture ou de decision.
