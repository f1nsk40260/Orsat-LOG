#!/usr/bin/env bash
# ORSAT-LOG — lanceur quotidien.
# À chaque lancement : récupère les dernières modifs, recompile seulement ce qui a changé,
# ferme l'instance déjà ouverte, puis ouvre l'application.
#   orsat-log            lancement normal
#   orsat-log --offline  sans vérifier GitHub
#   orsat-log --rebuild  force la recompilation complète
cd "$(dirname "$(readlink -f "$0")")" || exit 1
DIR="$(pwd)"
LOG_DIR="$HOME/.local/share/orsat-log"
LOG="$LOG_DIR/orsat-log.log"
mkdir -p "$LOG_DIR"

notify() { command -v notify-send >/dev/null && notify-send -a ORSAT-LOG -i "$DIR/assets/orsat-log.svg" "ORSAT-LOG" "$1"; echo "$1"; }

OFFLINE=0; REBUILD=0
for a in "$@"; do
    case "$a" in --offline) OFFLINE=1 ;; --rebuild) REBUILD=1 ;; esac
done

{
echo "===== $(date '+%F %T') ====="

# 1. Mise à jour du code
BEFORE=$(git rev-parse HEAD)
if [ "$OFFLINE" = 0 ]; then
    git pull --ff-only -q || echo "GitHub injoignable : lancement de la version locale."
fi
AFTER=$(git rev-parse HEAD)
# vrai si un des chemins donnés a été modifié par la mise à jour
changed() {
    [ "$BEFORE" = "$AFTER" ] && return 1
    ! git diff --quiet "$BEFORE" "$AFTER" -- "$@"
}

# 2. Dépendances Python (si requirements.txt a changé ou venv absent)
if [ ! -x .venv/bin/python ]; then
    python3 -m venv --system-site-packages .venv
    REBUILD=1
fi
if [ "$REBUILD" = 1 ] || changed requirements.txt; then
    .venv/bin/pip install -q -r requirements.txt
fi

# 3. Interface (si frontend modifié ou jamais compilée)
# Aussi si les sources sont plus récentes que la compilation (code récupéré par un
# « git pull » fait à la main : le lanceur ne voit alors aucun changement).
stale_ui() {
    [ -n "$(find frontend/src frontend/index.html frontend/package.json -newer frontend/dist/index.html -print -quit 2>/dev/null)" ]
}
if [ "$REBUILD" = 1 ] || [ ! -f frontend/dist/index.html ] || changed frontend || stale_ui; then
    if [ "$REBUILD" = 1 ] || [ ! -d frontend/node_modules ] || changed frontend/package.json frontend/package-lock.json; then
        (cd frontend && npm install --silent)
    fi
    (cd frontend && npm run build --silent) || { notify "Échec de compilation de l'interface — voir $LOG"; exit 1; }
fi

if [ "$BEFORE" != "$AFTER" ]; then
    notify "Mise à jour : $(git log -1 --format=%s)"
fi

# 4. Ferme l'instance précédente (sinon le port 8740 est occupé)
pkill -f "$DIR/run.py" && sleep 1
} >>"$LOG" 2>&1

# 5. Lancement
exec .venv/bin/python "$DIR/run.py" >>"$LOG" 2>&1
