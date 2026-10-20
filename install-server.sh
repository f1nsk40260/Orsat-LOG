#!/usr/bin/env bash
# ORSAT-LOG — installation en SERVEUR CENTRAL sur le PC du WebSDR PhantomSDR-ORSAT.
#
#   cd ~/Orsat-LOG && bash install-server.sh [dossier du WebSDR]
#
# Dossier du WebSDR par défaut : ~/PhantomSDR-Plus (celui qui contient admin_config.json).
# Ce que fait le script (relançable sans risque) :
#   1. environnement Python du carnet (.venv) et compilation de l'interface, en basse priorité ;
#   2. service systemd « orsat-log » : démarrage automatique, plafonds mémoire / CPU, pour ne
#      jamais gêner le WebSDR ;
#   3. ajoute log_port à admin_config.json (copie de sécurité faite avant) ;
#   4. redémarre le proxy du WebSDR (coupure de quelques secondes) pour ouvrir /log.
# Mot de passe : celui du panneau admin ORSAT. Adresse : https://<votre-adresse>/log/
set -e
cd "$(dirname "$(readlink -f "$0")")"
DIR="$(pwd)"
PHANTOM="${1:-$HOME/PhantomSDR-Plus}"
CFG="$PHANTOM/admin_config.json"
PORT=8740
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

say() { printf '\n== %s ==\n' "$1"; }
die() { printf '\n[ERREUR] %s\n' "$1" >&2; exit 1; }

[ -f "$CFG" ] || die "admin_config.json introuvable dans $PHANTOM (donnez le dossier du WebSDR en argument)"
# npm vient de nvm sur la plupart des stations, et le terminal du panneau admin ne lit pas
# ~/.bashrc : on charge nvm comme recompile.sh de PhantomSDR, puis on cherche ailleurs.
if ! command -v npm >/dev/null && [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true
fi
if ! command -v npm >/dev/null; then
    for d in "$HOME"/.nvm/versions/node/*/bin "$HOME/.local/bin" /usr/local/bin /snap/bin; do
        [ -x "$d/npm" ] && export PATH="$d:$PATH"
    done
fi
command -v npm >/dev/null || die "npm introuvable (sudo apt install nodejs npm)"
echo "npm : $(command -v npm)"
PYV="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
python3 -c "import ensurepip" 2>/dev/null \
    || die "module venv absent : sudo apt install -y python${PYV}-venv   puis relancez ce script"

say "Environnement Python"
# Un environnement incomplet (essai précédent sans venv) est refait de zéro
[ -x .venv/bin/pip ] || { rm -rf .venv; python3 -m venv .venv; }
# Serveur seulement : pas de fenêtre pywebview sur le serveur
.venv/bin/pip install -q "fastapi>=0.110" "uvicorn>=0.29" "websockets>=12" python-multipart

say "Interface (basse priorité)"
(cd frontend && nice -n 15 npm install --silent && nice -n 15 npm run build --silent)

say "Service systemd orsat-log"
UNIT=/etc/systemd/system/orsat-log.service
$SUDO tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=ORSAT-LOG, carnet de trafic (serveur central, /log du WebSDR)
After=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$DIR
Environment=ORSATLOG_PASSWORD_FILE=$CFG
ExecStart=$DIR/.venv/bin/python $DIR/run.py --central --port $PORT
Restart=always
RestartSec=5
# Ne jamais gêner le WebSDR : priorité basse et plafonds
Nice=10
CPUQuota=30%
MemoryMax=300M

[Install]
WantedBy=multi-user.target
EOF
$SUDO systemctl daemon-reload
$SUDO systemctl enable orsat-log >/dev/null 2>&1
$SUDO systemctl restart orsat-log
sleep 3
systemctl is-active --quiet orsat-log || die "le service ne démarre pas : journalctl -u orsat-log -n 30"
echo "Service actif sur 127.0.0.1:$PORT"

say "admin_config.json : log_port"
if python3 -c "import json,sys; sys.exit(0 if json.load(open('$CFG')).get('log_port') == $PORT else 1)"; then
    echo "déjà en place"
    NEED_PROXY=0
else
    NEED_PROXY=1
    cp -p "$CFG" "$CFG.avant-orsat-log"
    python3 - "$CFG" "$PORT" <<'PY'
import json, os, sys, tempfile
path, port = sys.argv[1], int(sys.argv[2])
cfg = json.load(open(path))
cfg["log_port"] = port
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
with os.fdopen(fd, "w") as f:
    json.dump(cfg, f, indent=2)
os.chmod(tmp, os.stat(path).st_mode & 0o777)
os.replace(tmp, path)
PY
    echo "ajouté (copie de sécurité : $CFG.avant-orsat-log)"
fi

# Le proxy n'est relancé qu'au premier passage (simple mise à jour du carnet : WebSDR intact)
if [ "${NEED_PROXY:-1}" = 0 ] && [ "${FORCE_PROXY:-0}" != 1 ]; then
    say "Proxy du WebSDR : inchangé (déjà relié à /log)"
elif systemctl is-active --quiet phantomsdr-proxy; then
    say "Redémarrage du proxy du WebSDR (quelques secondes de coupure)"
    $SUDO systemctl restart phantomsdr-proxy
    sleep 2
    systemctl is-active --quiet phantomsdr-proxy && echo "proxy relancé" || die "le proxy ne repart pas : journalctl -u phantomsdr-proxy -n 30"
else
    echo "Service phantomsdr-proxy non trouvé : relancez le proxy du WebSDR à la main."
fi

say "Vérification"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/login" || true)
[ "$code" = "200" ] && echo "Carnet : OK" || echo "Carnet : réponse $code (voir journalctl -u orsat-log)"
echo
echo "ORSAT-LOG est en ligne sous /log/ du WebSDR, mot de passe du panneau admin."
