"""Accès au carnet.

- Opérateur (navigateur) : mot de passe du panneau admin de PhantomSDR-ORSAT, lu (jamais
  écrit) dans son admin_config.json (clé password_hash, même format PBKDF2 que
  admin_server.py). Chemin : ORSATLOG_PASSWORD_FILE, sinon ~/PhantomSDR-Plus/admin_config.json.
  Session : cookie signé (HMAC-SHA256, clé data/secret.key), valable 30 jours.
  Anti-rafale : 5 échecs en 10 min depuis une même adresse = 10 min de blocage.
- Panneau admin (rubrique « Carnet ORSAT-LOG ») : en-tête X-OrsatLog-Admin, clé dérivée de
  password_hash, que le panneau et le carnet lisent tous deux et qu'un visiteur ne connaît pas.
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
ADMIN_HEADER = "x-orsatlog-admin"
SESSION_DAYS = 30
ADMIN_CONFIG = Path(os.environ.get("ORSATLOG_PASSWORD_FILE",
                                   Path.home() / "PhantomSDR-Plus" / "admin_config.json"))
SECRET_FILE = DATA_DIR / "secret.key"

MAX_FAILS, WINDOW_S, BLOCK_S = 5, 600, 600
_fails: dict[str, list[float]] = {}
_blocked: dict[str, float] = {}


# --- mot de passe du panneau admin ---
def _stored_hash():
    try:
        return json.loads(ADMIN_CONFIG.read_text()).get("password_hash", "")
    except (OSError, ValueError):
        return ""


def password_available():
    return bool(_stored_hash())


def check_password(pwd):
    stored = _stored_hash()
    if stored.startswith("pbkdf2$"):                       # pbkdf2$itérations$sel$empreinte
        try:
            _, it, salt, h = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", (pwd or "").encode(), bytes.fromhex(salt), int(it))
            return hmac.compare_digest(dk.hex(), h)
        except ValueError:
            return False
    legacy = hashlib.sha256((pwd or "").encode()).hexdigest()   # ancien format du panneau
    return bool(stored) and hmac.compare_digest(legacy, stored)


def admin_token():
    """Clé partagée avec le panneau admin (vide si le mot de passe est introuvable)."""
    stored = _stored_hash()
    return hmac.new(stored.encode(), b"orsatlog-admin", hashlib.sha256).hexdigest() if stored else ""


def is_admin(headers):
    token = admin_token()
    given = headers.get(ADMIN_HEADER, "")
    return bool(token and given) and hmac.compare_digest(given, token)


# --- anti-rafale ---
def blocked_for(ip):
    """Secondes de blocage restantes pour cette adresse (0 = libre)."""
    return max(0, int(_blocked.get(ip, 0) - time.time()))


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
