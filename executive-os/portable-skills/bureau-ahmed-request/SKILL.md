---
name: bureau-ahmed-request
description: Préparer et soumettre à Bureau d'Ahmed une demande interne prête à décider, après recherche, résolution du contexte exact et proposition d'opérations ciblées. Utiliser avant toute escalade, approbation ou décision demandée à Ahmed.
---

# Bureau Ahmed Request

Transforme un problème interne en dossier prêt à décider. Ne transmets pas un problème brut à Ahmed.

## Barrières

- Ne révèle ni secret, token, mot de passe, clé API ou credential dans le dossier.
- Ne sélectionne jamais un homonyme. Résous l'identité, la société et l'objet métier exacts ; sinon marque le contexte `unresolved`.
- Travaille en lecture seule pour retrouver le contexte. N'effectue que les actions réversibles déjà autorisées à la personne.
- Arrête-toi avant une dépense, une approbation, un engagement client/fournisseur, une action irréversible, une modification sensible ou toute action hors mandat.
- Les opérations Odoo restent des propositions. Ce skill ne les exécute pas.
- Pour un danger humain ou une urgence réelle, utilise aussi la voie humaine directe sans attendre la fin du dossier.

## Préparation obligatoire

1. Identifie la décision résiduelle exacte attendue d'Ahmed.
2. Recherche le contexte et vérifie les sources utiles.
3. Résous un seul objet principal exact, puis les objets associés. Pour Odoo, utilise la recherche Bureau Ahmed puis vérifie l'ID choisi ; ne fabrique jamais le reçu de vérification.
4. Compare les solutions réalistes et formule une recommandation argumentée.
5. Réalise ce qui est déjà autorisé et joins les preuves ; sinon explique pourquoi aucune action ne pouvait être faite.
6. Propose qui devrait mettre à jour quel objet, avec l'action, la cible exacte et le résultat attendu.
7. Construis le request pack v1 et valide-le avant soumission.

Lis [references/request-pack.md](references/request-pack.md) pour le contrat détaillé. Pars de [examples/request-pack.sample.json](examples/request-pack.sample.json) lorsque le dossier touche Odoo.

## Résolution Odoo contrôlée

La recherche est volontairement limitée aux noms des projets et tâches des sociétés autorisées. Les documents et approbations ne peuvent être vérifiés que par leur ID exact.

```text
python scripts/submit_request.py odoo-search project.task "fragment distinctif"
python scripts/submit_request.py odoo-verify project.task 1234
```

Recopie sans modification `model`, l'`id` retourné dans `record_id`, `company_id`, `label` et `verification_receipt` dans chaque référence Odoo correspondante. Le reçu est court, lié au demandeur et refusé s'il expire ou si la cible change.

## Soumission

Le token appareil reste uniquement dans `BUREAU_AHMED_DEVICE_TOKEN`. L'URL reste dans `BUREAU_AHMED_API_URL`.

```text
python scripts/submit_request.py validate /chemin/absolu/request.json
python scripts/submit_request.py submit /chemin/absolu/request.json
```

Après succès, rends le `request_id`, le statut de préparation et, s'il existe, le lien privé Telegram. Ne prétends jamais qu'Ahmed a lu ou approuvé la demande.

Pour compléter le même dossier : corrige le pack entier puis utilise `revise`. Pour une simple pièce de conversation ou précision non structurée, utilise `message`.

```text
python scripts/submit_request.py revise REQ-XXXX /chemin/absolu/request.json
python scripts/submit_request.py message REQ-XXXX "Précision factuelle"
```
