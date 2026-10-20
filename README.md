# ORSAT-LOG

Carnet de trafic radioamateur pour Linux, connecté au transceiver en **TCI**, orienté analyse de la propagation.

## Installation (une seule fois)

```bash
git clone git@github.com:f1nsk40260/Orsat-LOG.git ~/Orsat-LOG
cd ~/Orsat-LOG
chmod +x update.sh
./update.sh
```

Prérequis : Python 3.10+, Node.js/npm, et pour la fenêtre native GTK/WebKit
(Debian/Ubuntu/Mint : `sudo apt install python3-gi gir1.2-webkit2-4.1`).

## Mise à jour et lancement

```bash
~/Orsat-LOG/update.sh
```

Le script récupère le code, installe les dépendances, recompile l'interface,
crée le raccourci « ORSAT-LOG » dans le menu et lance l'application.

Lancement direct : `.venv/bin/python run.py` (options `--browser`, `--server`, `--debug`).

## Développement de l'interface

```bash
.venv/bin/python run.py --server     # backend sur :8740
cd frontend && npm run dev           # interface avec rechargement à chaud
```

Voir [ROADMAP.md](ROADMAP.md) pour l'état du projet.
