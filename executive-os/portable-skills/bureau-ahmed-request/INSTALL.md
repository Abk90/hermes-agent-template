# Installation

Ce dossier suit le format Agent Skills. Installe-le sans le modifier, puis configure les deux variables d'environnement remises individuellement par l'administrateur :

- `BUREAU_AHMED_API_URL` ;
- `BUREAU_AHMED_DEVICE_TOKEN`.

Depuis le dépôt Bureau Ahmed :

```text
python executive-os/scripts/install_portable_skill.py claude-user
python executive-os/scripts/install_portable_skill.py kimi-user
python executive-os/scripts/install_portable_skill.py project --project-root /chemin/du/projet
```

L'installation projet écrit deux copies identiques : `.claude/skills/bureau-ahmed-request` pour Claude Code et `.agents/skills/bureau-ahmed-request` pour Kimi Code.

Invocation manuelle :

- Claude Code : `/bureau-ahmed-request` ;
- Kimi Code : `/skill:bureau-ahmed-request`.

Le token appartient à un appareil et à une personne. Il ne doit pas être copié dans un prompt, un fichier projet, un request pack, une capture ou une conversation Telegram.
