#!/usr/bin/env bash
# ORSAT-LOG — mise à jour depuis GitHub + installation + (re)compilation.
# Usage : ./update.sh          met à jour puis lance l'application
#         ./update.sh --no-run met à jour sans lancer
set -e
cd "$(dirname "$(readlink -f "$0")")"
DIR="$(pwd)"

echo "== Récupération du code =="
git pull --ff-only

echo "== Environnement Python =="
if [ ! -d .venv ]; then
    # --system-site-packages : permet d'utiliser python3-gi (GTK) installé par la distribution
    python3 -m venv --system-site-packages .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== Compilation de l'interface =="
if ! command -v npm >/dev/null; then
    echo "npm introuvable : installe Node.js (paquet nodejs/npm de ta distribution)."
    exit 1
fi
(cd frontend && npm install --silent && npm run build --silent)

echo "== Lanceur =="
chmod +x "$DIR/orsat-log.sh"
# commande « orsat-log » dans le terminal
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/orsat-log.sh" "$HOME/.local/bin/orsat-log"
# icône dans le menu des applications
mkdir -p "$HOME/.local/share/applications"
DESKTOP_FILE="$HOME/.local/share/applications/orsat-log.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=ORSAT-LOG
Comment=Carnet de trafic radioamateur avec TCI
Exec=$DIR/orsat-log.sh
Icon=$DIR/assets/orsat-log.svg
Terminal=false
Categories=HamRadio;Network;
Actions=offline;rebuild;journal;

[Desktop Action offline]
Name=Lancer sans mise à jour
Exec=$DIR/orsat-log.sh --offline

[Desktop Action rebuild]
Name=Recompiler entièrement
Exec=$DIR/orsat-log.sh --rebuild

[Desktop Action journal]
Name=Voir le journal
Exec=xdg-open $HOME/.local/share/orsat-log/orsat-log.log
EOF
chmod +x "$DESKTOP_FILE"
# icône sur le Bureau
BUREAU="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Bureau")"
if [ -d "$BUREAU" ]; then
    cp "$DESKTOP_FILE" "$BUREAU/orsat-log.desktop"
    chmod +x "$BUREAU/orsat-log.desktop"
    gio set "$BUREAU/orsat-log.desktop" metadata::trusted true 2>/dev/null || true
    echo "Icône ORSAT-LOG ajoutée sur le Bureau ($BUREAU)."
fi

# Vérifie le moteur de fenêtre native (pywebview a besoin de GTK/WebKit sous Linux)
if ! .venv/bin/python -c "import gi; gi.require_version('WebKit2', '4.1')" 2>/dev/null \
   && ! .venv/bin/python -c "import gi; gi.require_version('WebKit2', '4.0')" 2>/dev/null; then
    echo
    echo "!! Fenêtre native indisponible (GTK/WebKit manquant) : l'appli s'ouvrira dans le navigateur."
    echo "   Debian/Ubuntu/Mint : sudo apt install python3-gi gir1.2-webkit2-4.1"
    echo "   Fedora             : sudo dnf install python3-gobject webkit2gtk4.1"
    echo "   Arch               : sudo pacman -S python-gobject webkit2gtk-4.1"
fi

echo "== OK =="
if [ "$1" != "--no-run" ]; then
    pkill -f "$DIR/run.py" && sleep 1
    exec .venv/bin/python "$DIR/run.py"
fi
