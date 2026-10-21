"""ORSAT-LOG, serveur central (FastAPI) : API REST + WebSocket temps réel + interface.

Tourne sur le PC du WebSDR, derrière proxy.py de PhantomSDR-ORSAT (https://<site>/log/).
Les réglages se font dans le panneau admin du WebSDR (rubrique « Carnet ORSAT-LOG »)."""

import asyncio
import json
import logging
import os
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, adif, auth, backup, geo, qrz, solar, weather
from .db import Database
from .websdr import Page, WebSdrLink

log = logging.getLogger("orsatlog")

ROOT = Path(__file__).resolve().parents[2]          # dossier du dépôt (~/Orsat-LOG)
FRONTEND_DIST = ROOT / "frontend" / "dist"

db = Database()
_clients: set[WebSocket] = set()


def _broadcast(state, kind):
    msg = json.dumps({"type": kind, "data": state})
    for ws in list(_clients):
        asyncio.create_task(_safe_send(ws, msg))


async def _safe_send(ws, msg):
    try:
        await ws.send_text(msg)
    except Exception:
        _clients.discard(ws)


websdr = WebSdrLink(on_change=lambda st: _broadcast(st, "websdr"))
qrz_sync = qrz.QrzSync(db)


def utc_day(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y%m%d")


async def _propagation_recorder():
    """Relève la propagation toutes les 15 min ; enregistre un point à chaque nouvelle
    publication de la source, et au moins un point par heure (page du jour bien remplie)."""
    while True:
        try:
            data = await asyncio.to_thread(solar.get_solar)
            if data:
                now = datetime.now(timezone.utc)
                last = db.last_snapshot()
                new_hour = (not last or last["day"] != utc_day(now)
                            or last["time"][:2] != now.strftime("%H"))
                if not last or last.get("source_time") != data.get("updated") or new_hour:
                    db.add_snapshot(utc_day(now), now.strftime("%H%M%S"), data)
        except Exception as exc:
            log.warning("relevé de propagation : %s", exc)
        try:
            await _record_weather()
        except Exception as exc:
            log.warning("relevé météo : %s", exc)
        await asyncio.sleep(15 * 60)


async def _record_weather():
    """Enregistre la mesure de la station si elle est nouvelle (heure de mesure différente)."""
    data = await asyncio.to_thread(weather.get_weather, db.get_settings().get("weathercloud", ""))
    if not data or not data.get("epoch"):
        return
    last = db.last_weather()
    if last and last.get("epoch") == data["epoch"]:
        return
    at = datetime.fromtimestamp(data["epoch"], timezone.utc)
    db.add_weather(utc_day(at), at.strftime("%H%M%S"), data)


@asynccontextmanager
async def lifespan(app):
    recorder = asyncio.create_task(_propagation_recorder())
    syncer = asyncio.create_task(qrz_sync.loop())
    saver = asyncio.create_task(backup.daily_task(db))
    yield
    recorder.cancel()
    saver.cancel()
    syncer.cancel()


app = FastAPI(title="ORSAT-LOG", version=__version__, lifespan=lifespan)


# ---------- accès protégé ----------
# Pages et appels accessibles sans session : la connexion elle-même.
_PUBLIC = {"/login", "/favicon.ico"}

_LOGIN_HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ORSAT-LOG — connexion</title>
<style>
:root{color-scheme:dark}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d0d0f;
color:#e6e2d3;font-family:system-ui,sans-serif}
form{width:min(340px,calc(100vw - 32px));padding:26px 24px;border:1px solid rgba(207,181,59,.35);border-radius:10px;
background:rgba(28,28,32,.9);box-shadow:0 0 24px rgba(207,181,59,.12)}
h1{margin:0 0 4px;color:rgb(207,181,59);letter-spacing:.12em;font-size:1.4rem}h1 small{color:#8f8a78;font-size:.9rem}
p{color:#8f8a78;font-size:.85rem;margin:0 0 18px}label{display:block;font-size:.75rem;letter-spacing:.08em;
text-transform:uppercase;color:#8f8a78;margin-bottom:6px}
input{box-sizing:border-box;width:100%;font:inherit;color:#e6e2d3;background:rgba(0,0,0,.45);
border:1px solid rgba(207,181,59,.3);border-radius:5px;padding:9px 10px}
input:focus{outline:none;border-color:rgb(207,181,59)}
button{margin-top:16px;width:100%;padding:10px;font:inherit;font-weight:600;border-radius:6px;cursor:pointer;
border:1px solid rgb(207,181,59);color:#111;background:linear-gradient(180deg,#e2c95a,rgb(207,181,59))}
.err{color:#d65050;font-size:.85rem;margin-top:12px;min-height:1em}
</style></head><body>
<form method="post" action="login">
<h1>ORSAT<small>-LOG</small></h1><p>Carnet de trafic — accès réservé</p>
<label for="pw">Mot de passe</label><input id="pw" name="password" type="password" autocomplete="current-password" autofocus>
<button type="submit">Ouvrir le carnet</button><div class="err">__ERR__</div>
</form></body></html>"""


def _client_ip(request):
    """Adresse du visiteur ; derrière proxy.py (boucle locale), celle qu'il transmet."""
    ip = request.client.host if request.client else ""
    if ip in ("127.0.0.1", "::1"):
        fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        ip = fwd or request.headers.get("x-real-ip", "") or ip
    return ip


def _logged_in(cookies):
    return auth.valid_token(cookies.get(auth.COOKIE, ""))


@app.middleware("http")
async def _require_login(request: Request, call_next):
    if request.url.path in _PUBLIC or _logged_in(request.cookies):
        return await call_next(request)
    if request.url.path.startswith("/api/") and auth.is_admin(request.headers):
        return await call_next(request)                  # panneau admin du WebSDR
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Connexion requise"}, status_code=401)
    return RedirectResponse("login", status_code=303)   # relatif : marche aussi derrière /log


@app.get("/login", response_class=HTMLResponse)
def login_page():
    err = "" if auth.password_available() else "Mot de passe du panneau admin introuvable sur le serveur."
    return _LOGIN_HTML.replace("__ERR__", err)


@app.post("/login")
def login(request: Request, password: str = Form("")):
    ip = _client_ip(request)
    wait = auth.blocked_for(ip)
    if wait:
        return HTMLResponse(_LOGIN_HTML.replace("__ERR__", f"Trop d'essais : réessayez dans {wait // 60 + 1} min."),
                            status_code=429)
    if not auth.check_password(password):
        auth.note_failure(ip)
        log.warning("Connexion refusée depuis %s", ip)
        return HTMLResponse(_LOGIN_HTML.replace("__ERR__", "Mot de passe incorrect."), status_code=401)
    auth.note_success(ip)
    log.info("Connexion depuis %s", ip)
    resp = RedirectResponse("./", status_code=303)
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie(auth.COOKIE, auth.new_token(), max_age=auth.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=https)
    return resp


@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/api/info")
def info():
    """Sondé par la page du WebSDR pour savoir si ce navigateur a une session au carnet."""
    return {"version": __version__, "central": True}


# ---------- panneau admin du WebSDR (en-tête X-OrsatLog-Admin) ----------
def _require_admin(request: Request):
    if not auth.is_admin(request.headers):
        raise HTTPException(403, "Réservé au panneau admin")


@app.get("/api/admin/status")
def admin_status(request: Request):
    _require_admin(request)
    import subprocess
    def git(*a):
        r = subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    from .db import DB_PATH
    st = db.stats()
    return {"version": __version__, "commit": git("log", "-1", "--format=%h"),
            "commit_subject": git("log", "-1", "--format=%s"),
            "commit_date": git("log", "-1", "--format=%cI"),
            "db_size": DB_PATH.stat().st_size if DB_PATH.exists() else 0, **st,
            "websdr_pages": websdr.state["pages"], "clients": len(_clients)}


# ---------- synchronisation QRZ.com (panneau admin) ----------
def _qrz_status():
    s = db.get_settings()
    key = s.get("qrz_api_key", "")
    return {"enabled": s.get("qrz_sync") == "1", "key_set": bool(key),
            "key_hint": ("…" + key[-4:]) if len(key) >= 4 else "",
            "full_done": s.get("qrz_full_done") == "1", "last_pull": s.get("qrz_last_pull", ""),
            **qrz_sync.state, **db.qrz_counts(), "journal": list(qrz_sync.journal)[-80:]}


@app.get("/api/admin/qrz")
def admin_qrz(request: Request):
    _require_admin(request)
    return _qrz_status()


class QrzIn(BaseModel):
    api_key: str | None = None     # None = inchangée ; "" = effacer
    enabled: bool | None = None


@app.post("/api/admin/qrz")
async def admin_qrz_set(cfg: QrzIn, request: Request):
    _require_admin(request)
    values = {}
    if cfg.api_key is not None:
        key = cfg.api_key.strip()
        if key:
            try:      # la clé est essayée avant d'être enregistrée
                await asyncio.to_thread(qrz_sync.test_key, key)
            except qrz.QrzError as exc:
                raise HTTPException(400, f"Clé QRZ refusée : {exc}")
            qrz_sync.note("Clé QRZ vérifiée et enregistrée.")
        if key != db.get_settings().get("qrz_api_key", ""):
            values.update(qrz_api_key=key, qrz_full_done="0", qrz_last_pull="")
    if cfg.enabled is not None:
        values["qrz_sync"] = "1" if cfg.enabled else "0"
        qrz_sync.note("Synchronisation automatique " + ("activée." if cfg.enabled else "désactivée."))
    if values:
        db.set_settings(values)
    if qrz_sync.enabled():
        qrz_sync.poke()
    return _qrz_status()


@app.post("/api/admin/qrz/run")
async def admin_qrz_run(request: Request, full: bool = False):
    """Synchroniser maintenant (full=true : relire tout le logbook QRZ)."""
    _require_admin(request)
    if not db.get_settings().get("qrz_api_key"):
        raise HTTPException(400, "Aucune clé QRZ enregistrée")
    asyncio.create_task(qrz_sync.run(full=full))
    await asyncio.sleep(0.2)
    return _qrz_status()


@app.post("/api/admin/restart")
def admin_restart(request: Request):
    """Redémarrage par systemd (Restart=always), après une mise à jour."""
    _require_admin(request)
    asyncio.get_event_loop().call_later(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM))
    return {"ok": True}


# ---------- réglages ----------
@app.get("/api/settings")
def get_settings(request: Request):
    s = db.get_settings()
    if not auth.is_admin(request.headers):
        s.pop("qrz_api_key", None)        # la clé QRZ ne sort jamais vers les navigateurs
    return s


@app.put("/api/settings")
async def put_settings(values: dict, request: Request):
    _require_admin(request)            # réglages : panneau admin uniquement
    before = db.get_settings()
    if values.get("swl_locator") and not geo.valid_locator(values["swl_locator"]):
        raise HTTPException(400, "Locator du WebSDR invalide")
    if "swl_locator" in values:
        values["swl_locator"] = values["swl_locator"].strip().upper()
    if values.get("locator") and not geo.valid_locator(values["locator"]):
        raise HTTPException(400, "Locator invalide")
    if "callsign" in values:
        values["callsign"] = values["callsign"].strip().upper()
    if "locator" in values:
        values["locator"] = values["locator"].strip().upper()
    if "weathercloud" in values:   # on accepte l'adresse complète de la station
        values["weathercloud"] = weather.parse_code(values["weathercloud"])
    db.set_settings(values)
    after = db.get_settings()
    if any(before.get(k) != after.get(k) for k in ("locator", "swl_locator")):
        recompute()                       # distances et azimuts de tout le carnet
    if before.get("weathercloud") != after.get("weathercloud"):
        asyncio.create_task(_record_weather())
    return after


def _origin_locator(kind):
    """Point de départ des distances : la station émettrice pour un QSO, le récepteur
    WebSDR pour une écoute SWL (à défaut, la station)."""
    s = db.get_settings()
    if kind == "SWL" and geo.valid_locator(s.get("swl_locator", "")):
        return s["swl_locator"]
    return s.get("locator", "")


def recompute():
    """Recalcule distance et azimut de toutes les entrées (après un changement de locator)."""
    n = 0
    for q in db.all_qsos():
        my_loc = _origin_locator(q.get("kind"))
        d = b = None
        if geo.valid_locator(my_loc) and geo.valid_locator(q.get("gridsquare") or ""):
            d, b = geo.distance_bearing(my_loc, q["gridsquare"])
        if (d, b) != (q.get("distance_km"), q.get("bearing")):
            db.update_qso(q["id"], {"distance_km": d, "bearing": b})
            n += 1
    return {"updated": n}


# Mode du carnet (ADIF) -> modulation TCI pour recaler la page du WebSDR
_TUNE_MODES = {"USB": "usb", "LSB": "lsb", "CW": "cw", "AM": "am", "FM": "nfm"}


class TuneIn(BaseModel):
    freq: int
    mode: str = ""
    submode: str = ""
    kind: str = ""


class MirrorIn(BaseModel):
    freq: int | None = None
    modulation: str = ""


@app.post("/api/websdr/mirror")
async def websdr_mirror(m: MirrorIn):
    """AetherSDR (suivi par le navigateur de l'opérateur) a changé de fréquence ; la page
    WebSDR l'a suivi par CAT Sync sans le relayer au carnet."""
    websdr.mirror(m.freq, m.modulation)
    return {"ok": True}


@app.post("/api/tune")
async def tune(t: TuneIn):
    """Recale la page du WebSDR sur une écoute SWL du carnet. (Un QSO règle AetherSDR
    directement depuis le navigateur de l'opérateur : frontend/src/tciBrowser.js.)"""
    mode = (t.submode or t.mode).upper()
    tci_mode = _TUNE_MODES.get(mode)
    if not tci_mode and mode not in ("", "SSB"):
        tci_mode = "usb"        # modes numériques (FT8, RTTY...) : écoute en USB
    if mode == "SSB":
        tci_mode = "lsb" if t.freq < 10_000_000 else "usb"
    if not await websdr.tune(t.freq, tci_mode):
        raise HTTPException(409, "Aucune page WebSDR reliée (ouvrez https://orsat.ddns.net dans ce navigateur)")
    return {"ok": True}


@app.get("/api/weather")
async def get_weather():
    data = await asyncio.to_thread(weather.get_weather, db.get_settings().get("weathercloud", ""))
    return {"data": data, "error": weather.last_error()}


@app.get("/api/solar")
async def get_solar():
    return await asyncio.to_thread(solar.get_solar)


# ---------- QSO ----------
class QsoIn(BaseModel):
    kind: str = "QSO"             # QSO = contact réalisé, SWL = écoute
    session_id: int | None = None # rattachement à un QSO de groupe
    call: str
    qso_date: str | None = None   # AAAAMMJJ, défaut = maintenant UTC
    time_on: str | None = None    # HHMMSS
    freq: int | None = None       # Hz
    mode: str = ""
    submode: str = ""
    rst_sent: str = ""
    rst_rcvd: str = ""
    name: str = ""
    qth: str = ""
    gridsquare: str = ""
    comment: str = ""


@app.get("/api/qsos")
def list_qsos(limit: int = 200):
    return db.list_qsos(limit)


@app.get("/api/worked/{call}")
def worked(call: str):
    return db.worked_before(call)


@app.post("/api/qsos")
async def add_qso(q: QsoIn):
    kind = "SWL" if q.kind.upper() == "SWL" else "QSO"
    # en SWL la station entendue peut être un nom (« Radio Romania ») : on garde la casse
    call = q.call.strip() if kind == "SWL" else q.call.strip().upper()
    if not call:
        raise HTTPException(400, "Station entendue obligatoire" if kind == "SWL" else "Indicatif obligatoire")
    now = datetime.now(timezone.utc)
    rec = q.model_dump()
    if q.session_id is not None:
        if not db.get_session(q.session_id):
            raise HTTPException(404, "QSO de groupe introuvable")
        kind = "QSO"
    rec["kind"] = kind
    rec["call"] = call
    if kind == "SWL":
        rec["rst_sent"] = ""
    rec["qso_date"] = q.qso_date or now.strftime("%Y%m%d")
    rec["time_on"] = q.time_on or now.strftime("%H%M%S")
    rec["mode"] = q.mode.strip().upper()
    rec["submode"] = q.submode.strip().upper()
    rec["gridsquare"] = q.gridsquare.strip().upper()
    rec["band"] = geo.band_of(q.freq, swl=kind == "SWL")

    my_loc = _origin_locator(kind)
    if geo.valid_locator(my_loc) and geo.valid_locator(rec["gridsquare"]):
        rec["distance_km"], rec["bearing"] = geo.distance_bearing(my_loc, rec["gridsquare"])

    sol = await asyncio.to_thread(solar.get_solar) or db.last_snapshot()
    if sol:
        rec["sfi"], rec["a_index"], rec["k_index"] = sol["sfi"], sol["a_index"], sol["k_index"]

    if kind == "QSO":
        rec["qrz_state"] = "pending"           # à envoyer vers QRZ.com
    saved = db.add_qso(rec)
    if kind == "QSO":
        qrz_sync.poke()
    return saved


class QsoEdit(BaseModel):
    """Entrée complète, telle que corrigée dans le formulaire d'édition."""
    kind: str = "QSO"
    session_id: int | None = None
    call: str
    qso_date: str                 # AAAAMMJJ
    time_on: str                  # HHMM ou HHMMSS (UTC)
    freq: int | None = None
    mode: str = ""
    submode: str = ""
    rst_sent: str = ""
    rst_rcvd: str = ""
    name: str = ""
    qth: str = ""
    gridsquare: str = ""
    comment: str = ""
    sfi: float | None = None
    a_index: float | None = None
    k_index: float | None = None


@app.put("/api/qsos/{qso_id}")
def update_qso(qso_id: int, q: QsoEdit):
    """Corrige une entrée. Bande, distance et azimut sont recalculés."""
    if not db.get_qso(qso_id):
        raise HTTPException(404, "Entrée introuvable")
    kind = "SWL" if q.kind.upper() == "SWL" else "QSO"
    call = q.call.strip() if kind == "SWL" else q.call.strip().upper()
    if not call:
        raise HTTPException(400, "Station entendue obligatoire" if kind == "SWL" else "Indicatif obligatoire")
    d = q.qso_date.replace("-", "").strip()
    try:
        datetime.strptime(d, "%Y%m%d")
    except ValueError:
        raise HTTPException(400, "Date invalide")
    t = q.time_on.replace(":", "").strip()
    if len(t) == 4:
        t += "00"
    if len(t) != 6 or not t.isdigit() or int(t[:2]) > 23 or int(t[2:4]) > 59 or int(t[4:]) > 59:
        raise HTTPException(400, "Heure UTC invalide (HH:MM ou HH:MM:SS)")
    grid = q.gridsquare.strip().upper()
    if grid and not geo.valid_locator(grid):
        raise HTTPException(400, "Locator invalide")
    if q.freq is not None and q.freq <= 0:
        raise HTTPException(400, "Fréquence invalide")
    session_id = q.session_id if kind == "QSO" else None
    if session_id is not None and not db.get_session(session_id):
        session_id = None

    rec = q.model_dump()
    rec.update(kind=kind, call=call, qso_date=d, time_on=t, gridsquare=grid, session_id=session_id,
               mode=q.mode.strip().upper(), submode=q.submode.strip().upper(),
               band=geo.band_of(q.freq, swl=kind == "SWL"), distance_km=None, bearing=None)
    if kind == "SWL":
        rec["rst_sent"] = ""
    my_loc = _origin_locator(kind)
    if geo.valid_locator(my_loc) and geo.valid_locator(grid):
        rec["distance_km"], rec["bearing"] = geo.distance_bearing(my_loc, grid)
    old = db.get_qso(qso_id)
    if kind == "QSO":
        rec["qrz_state"] = "pending"           # correction à renvoyer vers QRZ.com
    elif old.get("qrz_logid"):
        # Devenu une écoute : jamais envoyé ; il reste chez QRZ (pas de suppression automatique)
        rec["qrz_state"] = ""
        qrz_sync.note(f"{old['call']} {old['qso_date']} passé en SWL : il reste dans le logbook QRZ "
                      f"(n° {old['qrz_logid']}), à supprimer à la main si besoin.")
    saved = db.update_qso(qso_id, rec)
    if kind == "QSO":
        qrz_sync.poke()
    return saved


# ---------- QSO de groupe ----------
def _hhmm(v, field):
    v = (v or "").replace(":", "").strip()
    if v == "":
        return ""
    if len(v) != 4 or not v.isdigit() or int(v[:2]) > 23 or int(v[2:]) > 59:
        raise HTTPException(400, f"{field} : heure attendue au format HH:MM")
    return v


class SessionIn(BaseModel):
    name: str | None = None
    time_start: str | None = None   # HH:MM ou HHMM (UTC)
    time_end: str | None = None
    freq: int | None = None
    mode: str | None = None
    submode: str | None = None
    animator: str | None = None     # indicatif de l'animateur
    comment: str | None = None


def _clean_session(s: SessionIn):
    data = {k: v for k, v in s.model_dump().items() if v is not None}
    if "name" in data:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise HTTPException(400, "Nom du QSO de groupe obligatoire")
    if "time_start" in data:
        data["time_start"] = _hhmm(data["time_start"], "Début")
    if "time_end" in data:
        data["time_end"] = _hhmm(data["time_end"], "Fin")
    for k in ("mode", "submode", "animator"):
        if k in data:
            data[k] = data[k].strip().upper()
    return data


def _check_slot(start, end):
    if start and end and end < start:
        raise HTTPException(400, "L'heure de fin est avant l'heure de début")


@app.get("/api/sessions/names")
def session_names():
    """Noms déjà utilisés (pour retrouver un QSO quotidien) avec les réglages de la dernière fois."""
    return db.session_names()


@app.get("/api/sessions/regulars")
def session_regulars(name: str):
    return db.regulars(name.strip())


@app.post("/api/sessions")
def create_session(s: SessionIn):
    data = _clean_session(s)
    if not data.get("name"):
        raise HTTPException(400, "Nom du QSO de groupe obligatoire")
    now = datetime.now(timezone.utc)
    data.setdefault("time_start", now.strftime("%H%M"))
    if not data["time_start"]:
        data["time_start"] = now.strftime("%H%M")
    _check_slot(data["time_start"], data.get("time_end"))
    sess = db.create_session(utc_day(now), data)
    # le nom et ses réglages restent dans la liste (sans effacer un horaire habituel par un champ vide)
    db.upsert_template(sess["name"], {k: v for k, v in sess.items() if v not in (None, "")})
    return sess


@app.get("/api/sessions/{sid}")
def get_session(sid: int):
    s = db.get_session(sid)
    if not s:
        raise HTTPException(404, "QSO de groupe introuvable")
    s["participants"] = db.session_qsos(sid)
    return s


@app.put("/api/sessions/{sid}")
def update_session(sid: int, s: SessionIn):
    cur = db.get_session(sid)
    if not cur:
        raise HTTPException(404, "QSO de groupe introuvable")
    data = _clean_session(s)
    _check_slot(data.get("time_start", cur["time_start"]), data.get("time_end", cur["time_end"]))
    sess = db.update_session(sid, data)
    if any(k in data for k in ("name", "time_start", "freq", "mode", "animator")):
        db.upsert_template(sess["name"], {k: v for k, v in sess.items() if k != "time_end" or v})
    return sess


@app.post("/api/templates")
def save_template(s: SessionIn):
    """Préenregistre un nom de QSO de groupe (sans ouvrir de session)."""
    data = _clean_session(s)
    if not data.get("name"):
        raise HTTPException(400, "Nom du QSO de groupe obligatoire")
    _check_slot(data.get("time_start"), data.get("time_end"))
    db.upsert_template(data.pop("name"), data)
    return db.session_names()


@app.delete("/api/templates/{name}")
def delete_template(name: str):
    """Retire un nom de la liste (les sessions déjà tenues sont conservées)."""
    if not db.delete_template(name):
        raise HTTPException(404, "Nom introuvable")
    return db.session_names()


@app.delete("/api/sessions/{sid}")
def delete_session(sid: int):
    if not db.delete_session(sid):
        raise HTTPException(404, "QSO de groupe introuvable")
    return {"ok": True}


# ---------- agenda ----------
def _check_day(day):
    if len(day) != 8 or not day.isdigit():
        raise HTTPException(400, "Date attendue au format AAAAMMJJ")


@app.get("/api/today")
def today():
    return {"day": utc_day()}


@app.get("/api/day/{day}")
def get_day(day: str):
    """Page d'agenda : activité, relevés de propagation et notes d'un jour UTC."""
    _check_day(day)
    entries = db.day_qsos(day)
    bands = {}
    for e in entries:
        if e["band"]:
            bands[e["band"]] = bands.get(e["band"], 0) + 1
    return {
        "day": day,
        "entries": entries,
        "propagation": db.day_snapshots(day),
        "weather": db.day_weather(day),
        "note": db.get_note(day),
        "sessions": db.day_sessions(day),
        "stats": {
            "qso": sum(e["kind"] == "QSO" for e in entries),
            "swl": sum(e["kind"] == "SWL" for e in entries),
            "bands": bands,
            "max_km": max((e["distance_km"] or 0 for e in entries), default=0),
        },
    }


class NoteIn(BaseModel):
    text: str = ""


@app.put("/api/day/{day}/note")
def put_note(day: str, n: NoteIn):
    _check_day(day)
    db.set_note(day, n.text)
    return {"ok": True}


@app.get("/api/month/{month}")
def get_month(month: str):
    """Jours actifs d'un mois AAAAMM (pour le calendrier)."""
    if len(month) != 6 or not month.isdigit():
        raise HTTPException(400, "Mois attendu au format AAAAMM")
    return db.month_activity(month)


@app.delete("/api/qsos/{qso_id}")
async def delete_qso(qso_id: int, qrz_too: bool = False):
    """Supprime une entrée. qrz_too=true : aussi dans le logbook QRZ.com (définitif),
    seulement si l'opérateur l'a confirmé."""
    q = db.get_qso(qso_id)
    if not q:
        raise HTTPException(404, "QSO introuvable")
    if qrz_too and q.get("kind") == "QSO" and q.get("qrz_logid"):
        try:
            await asyncio.to_thread(qrz_sync.delete_remote, q["qrz_logid"])
        except qrz.QrzError as exc:
            raise HTTPException(502, f"Suppression chez QRZ impossible ({exc}) : rien n'a été supprimé")
    elif q.get("kind") == "QSO" and q.get("qrz_logid"):
        db.qrz_ignore(q)          # gardé chez QRZ : la synchronisation ne le reprendra plus
    db.delete_qso(qso_id)
    return {"ok": True}


# ---------- sauvegardes ----------
@app.get("/api/backups")
def list_backups(request: Request):
    _require_admin(request)
    return {"items": backup.list_backups(), "keep_days": backup.KEEP_DAYS}


@app.get("/api/backup/download")
def download_backup(request: Request):
    _require_admin(request)
    """Copie fraîche de la base, à garder chez soi."""
    tmp = backup.snapshot_file(db)
    name = f"orsat-log_{datetime.now(timezone.utc):%Y%m%d-%H%M}.db"
    return FileResponse(tmp, filename=name, media_type="application/vnd.sqlite3",
                        background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))


@app.get("/api/backups/{name}")
def get_backup(name: str, request: Request):
    _require_admin(request)
    path = backup.BACKUP_DIR / name
    if not backup.valid_name(name) or not path.is_file():
        raise HTTPException(404, "Sauvegarde introuvable")
    return FileResponse(path, filename=name, media_type="application/vnd.sqlite3")


@app.post("/api/restore")
async def restore(request: Request, file: UploadFile = File(...)):
    _require_admin(request)
    """Remplace la base par une sauvegarde. La base actuelle est d'abord sauvegardée."""
    tmp = backup.DATA_DIR / "restore-upload.tmp"
    try:
        with open(tmp, "wb") as f:
            while chunk := await file.read(1 << 20):
                f.write(chunk)
        if not await asyncio.to_thread(backup.check_logbook_file, tmp):
            raise HTTPException(400, "Ce fichier n'est pas une sauvegarde ORSAT-LOG valide")
        before = f"orsatlog-{datetime.now(timezone.utc):%Y%m%d-%H%M}.db"
        await asyncio.to_thread(backup.make_backup, db, before)
        await asyncio.to_thread(db.restore_from, tmp)
        log.info("Base restaurée depuis %s (ancienne base gardée : %s)", file.filename, before)
        return {"ok": True, "previous": before}
    finally:
        tmp.unlink(missing_ok=True)


@app.get("/api/export/adif", response_class=PlainTextResponse)
def export_adif():
    """Carnet de trafic (QSO et QSO de groupe) : le seul destiné à QRZ.com / LoTW."""
    s = db.get_settings()
    text = adif.export(db.traffic_qsos(), s.get("callsign", ""), s.get("locator", ""), kind="QSO")
    name = f"orsat-log_trafic_{datetime.now(timezone.utc):%Y%m%d}.adi"
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/export/adif-swl", response_class=PlainTextResponse)
def export_adif_swl():
    """Journal d'écoute (SWL), à part : jamais envoyé vers QRZ.com."""
    s = db.get_settings()
    text = adif.export(db.listening_qsos(), s.get("callsign", ""), s.get("locator", ""),
                       s.get("swl_locator", "") or s.get("locator", ""), kind="SWL")
    name = f"orsat-log_ecoutes_{datetime.now(timezone.utc):%Y%m%d}.adi"
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- temps réel ----------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if not _logged_in(ws.cookies):
        await ws.close(code=4401)
        return
    await ws.accept()
    _clients.add(ws)
    await ws.send_text(json.dumps({"type": "websdr", "data": websdr.state}))
    try:
        while True:
            await ws.receive_text()  # le client n'envoie rien pour l'instant
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)


@app.websocket("/tci")
async def tci_page(ws: WebSocket):
    """La page du WebSDR s'y relie et parle TCI (voir websdr.py)."""
    if not _logged_in(ws.cookies):
        await ws.close(code=4401)
        return
    await ws.accept()
    await websdr.on_page(Page(ws))


# ---------- frontend compilé ----------
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
