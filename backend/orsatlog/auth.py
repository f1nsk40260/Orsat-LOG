"""Accès protégé du carnet en mode serveur central (run.py --central).

Mot de passe : celui du panneau admin de PhantomSDR-ORSAT, lu (jamais écrit) dans
son admin_config.json (clé password_hash, même format PBKDF2 que admin_server.py).
Chemin : variable ORSATLOG_PASSWORD_FILE, sinon ~/PhantomSDR-Plus/admin_config.json.
À défaut (PC de test sans WebSDR), mot de passe propre au carnet : data/auth.json,
défini par « run.py --set-password ».

Session : cookie signé (HMAC-SHA256, clé data/secret.key), valable 30 jours.
Anti-rafale : 5 échecs en 10 min depuis une même adresse = 10 min de blocage.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from .db import DATA_DIR

COOKIE = "orsatlog_session"
SESSION_DAYS = 30
PBKDF2_ITER = 200_000
ADMIN_CONFIG = Path(os.environ.get("ORSATLOG_PASSWORD_FILE",
                                   Path.home() / "PhantomSDR-Plus" / "admin_config.json"))
OWN_AUTH = DATA_DIR / "auth.json"
SECRET_FILE = DATA_DIR / "secret.key"

MAX_FAILS, WINDOW_S, BLOCK_S = 5, 600, 600
_fails: dict[str, list[float]] = {}
_blocked: dict[str, float] = {}


def central_mode():
    return os.environ.get("ORSATLOG_MODE") == "central"


# --- mot de passe ---
def _stored_hash():
    """(empreinte, origine) : panneau admin ORSAT en priorité, sinon mot de passe propre."""
    for path, origin in ((ADMIN_CONFIG, "panneau admin ORSAT"), (OWN_AUTH, "carnet")):
        try:
            h = json.loads(path.read_text()).get("password_hash", "")
        except (OSError, ValueError):
            continue
        if h:
            return h, origin
    return "", ""


def password_origin():
    return _stored_hash()[1]


def _verify(pwd, stored):
    if stored.startswith("pbkdf2$"):                       # pbkdf2$itérations$sel$empreinte
        try:
            _, it, salt, h = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), int(it))
            return hmac.compare_digest(dk.hex(), h)
        except ValueError:
            return False
    legacy = hashlib.sha256(pwd.encode()).hexdigest()      # ancien format du panneau admin
    return bool(stored) and hmac.compare_digest(legacy, stored)


def check_password(pwd):
    stored, _ = _stored_hash()
    return bool(stored) and _verify(pwd or "", stored)


def set_own_password(pwd):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), PBKDF2_ITER)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OWN_AUTH.write_text(json.dumps({"password_hash": f"pbkdf2${PBKDF2_ITER}${salt}${dk.hex()}"}))
    os.chmod(OWN_AUTH, 0o600)


# --- anti-rafale ---
def blocked_for(ip):
    """Secondes de blocage restantes pour cette adresse (0 = libre)."""
    until = _blocked.get(ip, 0)
    return max(0, int(until - time.time()))


def note_failure(ip):
    now = time.time()
    lst = [t for t in _fails.get(ip, []) if now - t < WINDOW_S] + [now]
    _fails[ip] = lst
    if len(lst) >= MAX_FAILS:
        _blocked[ip] = now + BLOCK_S
        _fails[ip] = []


def note_success(ip):
    _fails.pop(ip, None)
    _blocked.pop(ip, None)


# --- session ---
def _secret():
    try:
        return SECRET_FILE.read_bytes()
    except OSError:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        SECRET_FILE.write_bytes(key)
        os.chmod(SECRET_FILE, 0o600)
        return key


def new_token():
    exp = str(int(time.time()) + SESSION_DAYS * 86400)
    sig = hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def valid_token(token):
    try:
        exp, sig = (token or "").split(".", 1)
        good = hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > time.time()
    except ValueError:
        return False
