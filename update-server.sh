#!/usr/bin/env bash
# ORSAT-LOG — mise à jour sur le serveur, lancée par le panneau admin du WebSDR
# (rubrique « Carnet ORSAT-LOG ») ou à la main :  bash ~/Orsat-LOG/update-server.sh
# Récupère le code, met à jour les dépendances, recompile l'interface en basse priorité.
# Le redémarrage du service est fait ensuite par le panneau (ou : sudo systemctl restart orsat-log).
set -e
cd "$(dirname "$(readlink -f "$0")")"

if ! command -v npm >/dev/null && [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true
fi
if ! command -v npm >/dev/null; then
    for d in "$HOME"/.nvm/versions/node/*/bin "$HOME/.local/bin" /usr/local/bin; do
        [ -x "$d/npm" ] && export PATH="$d:$PATH"
    done
fi

echo "== Code =="
BEFORE=$(git rev-parse --short HEAD)
git checkout -- frontend/package-lock.json 2>/dev/null || true
git pull --ff-only
AFTER=$(git rev-parse --short HEAD)
[ "$BEFORE" = "$AFTER" ] && echo "Déjà à jour ($AFTER)." || git --no-pager log --format='  %h %s' "$BEFORE..$AFTER"

echo "== Dépendances Python =="
.venv/bin/pip install -q -r requirements.txt && echo "OK"

echo "== Interface (basse priorité) =="
command -v npm >/dev/null || { echo "npm introuvable"; exit 1; }
(cd frontend && nice -n 15 npm install --silent --no-audit --no-fund && nice -n 15 npm run build --silent)
# npm réécrit parfois package-lock.json selon sa version : on le remet, sinon le prochain git pull échoue
git checkout -- frontend/package-lock.json 2>/dev/null || true
echo "OK"
echo "== Terminé ($AFTER) =="
