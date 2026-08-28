# Contrat Request Pack v1

Le serveur impose le schéma JSON `1.0`. L'identité du demandeur ne vient jamais du JSON : elle est injectée à partir du credential appareil vérifié.

## Objet principal

`business_context.context_status` vaut :

- `exact` si l'objet a été résolu sans ambiguïté ;
- `not_applicable` si la demande n'appartient à aucun objet métier ;
- `unresolved` si plusieurs objets ou identités restent possibles.

Un objet Odoo exact exige au minimum :

- `system: "odoo"` ;
- le nom technique exact du modèle, par exemple `project.task` ;
- l'ID numérique positif du record ;
- l'ID exact de la société ;
- un libellé lisible.
- le `verification_receipt` retourné par `odoo-verify`, sans aucune modification.

Une recherche par nom est limitée à `project.project` et `project.task`, dans les sociétés autorisées pour le collaborateur. `documents.document` et `approval.request` exigent un ID déjà connu. Si plusieurs résultats subsistent, le contexte reste `unresolved` : le skill ne choisit pas à la place de la personne.

Le document précis est une preuve ou un objet associé. L'activité doit être proposée sur l'objet qui porte réellement l'action, pas automatiquement sur chaque document.

## Préparation

`preparation` distingue :

- la recherche effectuée et ses sources ;
- les options comparées ;
- la recommandation ;
- le travail déjà terminé dans le mandat ;
- le blocage restant.

Si aucune recherche n'est utile, explique-le dans `no_research_reason`. Si aucune action ne peut être faite avant autorisation, explique-le dans `no_work_reason`.

Une demande de décision doit contenir au moins une option et une recommandation argumentée. Une information P3 peut ne pas en contenir.

## Opérations proposées

Les seuls verbes acceptés en Phase 1 sont :

- `create_activity` ;
- `post_internal_note` ;
- `update_task_fields` ;
- `link_document`.

Chaque proposition contient une cible exacte, l'exécuteur souhaité, le payload envisagé, la justification et `approval_required: true`. Le serveur les enregistre au statut `PROPOSED` et exécute toujours zéro écriture.

Une cible Odoo proposée doit réutiliser le reçu signé de l'objet réellement vérifié. Le serveur refuse un reçu d'une autre personne, société, cible ou libellé.

## Impact et urgence

Le mot « urgent » ne suffit pas. Renseigne l'échéance réelle, la conséquence dans deux heures, la conséquence demain, les personnes bloquées, le montant, l'irréversibilité et les risques humains/légaux/client.

## Idempotence

`submission_id` est stable pour une même soumission. Le client l'utilise comme `Idempotency-Key` par défaut. Réutiliser la même clé avec un contenu différent est refusé.

## Informations interdites

Ne place jamais dans un pack : mot de passe, token, clé API, credential, clé privée ou secret. Les clés JSON qui ressemblent à ces champs sont rejetées par le serveur.
