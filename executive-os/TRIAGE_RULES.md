# Regles de triage P0-P4

Source executable : `src/executive_os/triage.py`. Seuils : `config/executive-os.toml`.

## Qualification minimale

Chaque demande doit identifier le demandeur, le sujet, la decision attendue et la recommandation. Une urgence reclamee exige aussi une echeance, la consequence dans deux heures et la consequence demain. Les achats, fournisseurs et paiements exigent le montant. Un workflow Odoo exige sa reference.

Les champs manquants produisent des questions courtes et la route `clarify`, sauf P0 : la voie humaine directe reste ouverte pendant la clarification.

## Classification

| Niveau | Regle deterministe de depart | Livraison |
|---|---|---|
| P0 | securite humaine, risque legal serieux, crise client majeure imminente, ou decision irreversible imminente avec consequence majeure | voie humaine directe + signal immediat lorsqu'active |
| P1 | echeance dans les 12 h avec consequence majeure, personne/operation bloquee ou montant >= 20 000 DH | FLASH, aujourd'hui |
| P2 | decision normale sans preuve d'interruption immediate | queue executive, batch |
| P3 | information sans decision/action immediate | rattacher/archiver, aucune interruption |
| P4 | idee/opportunite sans action actuelle | backlog |

Les fenetres et montants sont configurables. Un montant >= 100 000 DH ajoute toujours un besoin de jugement explicite d'Ahmed ; il ne transforme pas a lui seul une demande en P0.

## Regle d'urgence

Le mot « urgent » ne suffit jamais. La classification utilise consequence, deadline, irreversibilite, argent, personnes bloquees, client, securite et risque legal. Une petite action n'interrompt pas `NOW` uniquement parce qu'elle prend quelques minutes : elle rejoint `FLASH` ou `COMMS`.

## Routes

1. `answer` : procedure connue et reponse sure.
2. `delegate` : responsable connu et aucune decision d'Ahmed requise.
3. `odoo` : workflow officiel ; Telegram ne le remplace pas.
4. `omnifocus` : Ahmed doit effectuer une action distincte.
5. `executive_queue` : jugement d'Ahmed requis.
6. `archive` : information P3.
7. `backlog` : idee P4.

La route Odoo precede OmniFocus. Une approbation Odoo seule ne cree donc jamais une action OmniFocus.

## Etats techniques

```text
NEW -> QUALIFYING -> READY -> PENDING -> DONE
                         \-> REJECTED
PENDING -> RETRYING -> PENDING/DONE/FAILED
FAILED -> RETRYING/REJECTED
```

Les transitions non prevues sont refusees. Une erreur ou un timeout n'est jamais `DONE`.
