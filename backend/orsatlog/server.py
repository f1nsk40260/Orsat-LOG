"""Serveur local ORSAT-LOG (FastAPI) : API REST + WebSocket temps réel + frontend."""

import asyncio
import json
import logging
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, adif, auth, backup, geo, solar, weather
from .db import Database
from .tci import TciClient
from .websdr import WebSdrServer

log = logging.getLogger("orsatlog")

ROOT = Path(__file__).resolve().parents[2]          # dossier du dépôt (~/Orsat-LOG)
FRONTEND_DIST = ROOT / "frontend" / "dist"
LAUNCHER = ROOT / "orsat-log.sh"

db = Database()
_clients: set[WebSocket] = set()


def _broadcast(state, kind="radio"):
    msg = json.dumps({"type": kind, "data": state})
    for ws in list(_clients):
        asyncio.create_task(_safe_send(ws, msg))


async def _safe_send(ws, msg):
    try:
        await ws.send_text(msg)
    except Exception:
        _clients.discard(ws)


_last_radio = {"freq": None, "modulation": None}


def _on_radio(state):
    _broadcast(state)
    # La page (CAT Sync) suit AetherSDR : on recopie seulement un vrai changement de
    # fréquence ou de mode, pas un PTT ou une reconnexion.
    freq, mod = state.get("freq"), state.get("modulation")
    if freq != _last_radio["freq"]:
        websdr.mirror(freq)
    if mod != _last_radio["modulation"] and mod:
        websdr.mirror(freq, mod)
    _last_radio.update(freq=freq, modulation=mod)


tci = TciClient(on_change=_on_radio)
websdr = WebSdrServer(on_change=lambda st: _broadcast(st, "websdr"))


async def _restart_websdr():
    s = db.get_settings()
    if s.get("websdr_enabled") == "1" and not auth.central_mode():
        await websdr.start(s.get("websdr_port") or 40001)
    else:
        await websdr.stop()


def _restart_tci():
    # Serveur central : le TCI du transceiver est sur le PC de l'opérateur, c'est son
    # navigateur qui s'y connecte (frontend/src/tciBrowser.js), pas ce serveur.
    s = db.get_settings()
    if s.get("tci_enabled") == "1" and not auth.central_mode():
        tci.start(s.get("tci_host") or "127.0.0.1", s.get("tci_port") or 50001, s.get("tci_trx") or 0)
    else:
        tci.stop()


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
    _restart_tci()
    await _restart_websdr()
    recorder = asyncio.create_task(_propagation_recorder())
    saver = asyncio.create_task(backup.daily_task(db))
    yield
    recorder.cancel()
    saver.cancel()
    tci.stop()
    await websdr.stop()


app = FastAPI(title="ORSAT-LOG", version=__version__, lifespan=lifespan)


# ---------- accès protégé (mode serveur central) ----------
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
    if not auth.central_mode() or request.url.path in _PUBLIC or _logged_in(request.cookies):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Connexion requise"}, status_code=401)
    return RedirectResponse("login", status_code=303)   # relatif : marche aussi derrière /log


@app.get("/login", response_class=HTMLResponse)
def login_page():
    if not auth.central_mode():
        return RedirectResponse("./", status_code=303)
    err = "" if auth.password_origin() else "Aucun mot de passe défini sur le serveur."
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
    """Mode de fonctionnement, pour l'interface : en central, le navigateur fait lui-même le TCI."""
    return {"version": __version__, "central": auth.central_mode()}


# ---------- réglages ----------
@app.get("/api/settings")
def get_settings():
    return db.get_settings()


@app.put("/api/settings")
async def put_settings(values: dict):
    before = db.get_settings()
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
    if any(before.get(k) != after.get(k) for k in ("tci_host", "tci_port", "tci_trx", "tci_enabled")):
        _restart_tci()
    if any(before.get(k) != after.get(k) for k in ("websdr_port", "websdr_enabled")):
        await _restart_websdr()
    if before.get("weathercloud") != after.get("weathercloud"):
        asyncio.create_task(_record_weather())
    return after


# ---------- mise à jour depuis GitHub ----------
def _git(*args, timeout=30):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300] or "erreur git")
    return r.stdout.strip()


def _check_update():
    current = {"version": __version__, "commit": _git("rev-parse", "--short", "HEAD"),
               "date": _git("log", "-1", "--format=%cd", "--date=format:%d/%m/%Y %H:%M")}
    _git("fetch", "-q", "origin", timeout=60)
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    changes = _git("log", "--format=%s", f"HEAD..{upstream}")
    return {"current": current, "changes": [c for c in changes.splitlines() if c]}


@app.get("/api/update/check")
async def update_check():
    """Version installée + modifications disponibles sur GitHub."""
    try:
        return await asyncio.to_thread(_check_update)
    except Exception as exc:
        raise HTTPException(502, f"Vérification impossible : {exc}")


@app.post("/api/update")
def update_run(rebuild: bool = False):
    if auth.central_mode():
        raise HTTPException(400, "Serveur central : la mise à jour se fait sur le serveur (service ORSAT-LOG)")
    """Lance le lanceur (mise à jour + recompilation + redémarrage) dans un processus détaché :
    il ferme cette instance et rouvre l'application à jour."""
    if not LAUNCHER.exists():
        raise HTTPException(500, "Lanceur orsat-log.sh introuvable")
    # rebuild = recompilation complète (comme « orsat-log --rebuild »)
    cmd = ["bash", str(LAUNCHER)] + (["--rebuild"] if rebuild else [])
    subprocess.Popen(cmd, cwd=str(ROOT), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True}


# ---------- radio / solaire ----------
@app.get("/api/radio")
def get_radio():
    return tci.state


# Mode du carnet (ADIF) -> modulation TCI pour recaler la page du WebSDR
_TUNE_MODES = {"USB": "usb", "LSB": "lsb", "CW": "cw", "AM": "am", "FM": "nfm"}


class TuneIn(BaseModel):
    freq: int
    mode: str = ""
    submode: str = ""
    kind: str = ""


@app.post("/api/tune")
async def tune(t: TuneIn):
    """Recale sur une entrée du carnet : une écoute SWL règle la page du WebSDR,
    un QSO (ou un QSO de groupe) règle le transceiver (AetherSDR)."""
    mode = (t.submode or t.mode).upper()
    tci_mode = _TUNE_MODES.get(mode)
    if not tci_mode and mode not in ("", "SSB"):
        tci_mode = "usb"        # modes numériques (FT8, RTTY...) : écoute en USB
    if mode == "SSB":
        tci_mode = "lsb" if t.freq < 10_000_000 else "usb"
    if t.kind == "SWL":
        if not await websdr.tune(t.freq, tci_mode):
            raise HTTPException(409, "Aucune page WebSDR connectée (bouton CAT Sync de la page ORSAT)")
    elif not await tci.tune(t.freq, tci_mode):
        raise HTTPException(409, "Transceiver TCI non connecté (AetherSDR)")
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

    my_loc = db.get_settings().get("locator", "")
    if geo.valid_locator(my_loc) and geo.valid_locator(rec["gridsquare"]):
        rec["distance_km"], rec["bearing"] = geo.distance_bearing(my_loc, rec["gridsquare"])

    sol = await asyncio.to_thread(solar.get_solar) or db.last_snapshot()
    if sol:
        rec["sfi"], rec["a_index"], rec["k_index"] = sol["sfi"], sol["a_index"], sol["k_index"]

    return db.add_qso(rec)


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
    my_loc = db.get_settings().get("locator", "")
    if geo.valid_locator(my_loc) and geo.valid_locator(grid):
        rec["distance_km"], rec["bearing"] = geo.distance_bearing(my_loc, grid)
    return db.update_qso(qso_id, rec)


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
def delete_qso(qso_id: int):
    if not db.delete_qso(qso_id):
        raise HTTPException(404, "QSO introuvable")
    return {"ok": True}


# ---------- sauvegardes ----------
@app.get("/api/backups")
def list_backups():
    return {"items": backup.list_backups(), "keep_days": backup.KEEP_DAYS}


@app.get("/api/backup/download")
def download_backup():
    """Copie fraîche de la base, à garder chez soi."""
    tmp = backup.snapshot_file(db)
    name = f"orsat-log_{datetime.now(timezone.utc):%Y%m%d-%H%M}.db"
    return FileResponse(tmp, filename=name, media_type="application/vnd.sqlite3",
                        background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))


@app.get("/api/backups/{name}")
def get_backup(name: str):
    path = backup.BACKUP_DIR / name
    if not backup.valid_name(name) or not path.is_file():
        raise HTTPException(404, "Sauvegarde introuvable")
    return FileResponse(path, filename=name, media_type="application/vnd.sqlite3")


@app.post("/api/restore")
async def restore(file: UploadFile = File(...)):
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
    s = db.get_settings()
    text = adif.export(db.all_qsos(), s.get("callsign", ""), s.get("locator", ""))
    name = f"orsat-log_{datetime.now(timezone.utc):%Y%m%d}.adi"
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- temps réel ----------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if auth.central_mode() and not _logged_in(ws.cookies):
        await ws.close(code=4401)
        return
    await ws.accept()
    _clients.add(ws)
    await ws.send_text(json.dumps({"type": "radio", "data": tci.state}))
    await ws.send_text(json.dumps({"type": "websdr", "data": websdr.state}))
    try:
        while True:
            await ws.receive_text()  # le client n'envoie rien pour l'instant
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)


# ---------- frontend compilé ----------
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
