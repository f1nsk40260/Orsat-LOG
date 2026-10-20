"""Serveur local ORSAT-LOG (FastAPI) : API REST + WebSocket temps réel + frontend."""

import asyncio
import json
import logging
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, adif, geo, solar, weather
from .db import Database
from .tci import TciClient

log = logging.getLogger("orsatlog")

ROOT = Path(__file__).resolve().parents[2]          # dossier du dépôt (~/Orsat-LOG)
FRONTEND_DIST = ROOT / "frontend" / "dist"
LAUNCHER = ROOT / "orsat-log.sh"

db = Database()
_clients: set[WebSocket] = set()


def _broadcast(state):
    msg = json.dumps({"type": "radio", "data": state})
    for ws in list(_clients):
        asyncio.create_task(_safe_send(ws, msg))


async def _safe_send(ws, msg):
    try:
        await ws.send_text(msg)
    except Exception:
        _clients.discard(ws)


tci = TciClient(on_change=_broadcast)


def _restart_tci():
    s = db.get_settings()
    if s.get("tci_enabled") == "1":
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
    recorder = asyncio.create_task(_propagation_recorder())
    yield
    recorder.cancel()
    tci.stop()


app = FastAPI(title="ORSAT-LOG", version=__version__, lifespan=lifespan)


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
def update_run():
    """Lance le lanceur (mise à jour + recompilation + redémarrage) dans un processus détaché :
    il ferme cette instance et rouvre l'application à jour."""
    if not LAUNCHER.exists():
        raise HTTPException(500, "Lanceur orsat-log.sh introuvable")
    subprocess.Popen(["bash", str(LAUNCHER)], cwd=str(ROOT), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True}


# ---------- radio / solaire ----------
@app.get("/api/radio")
def get_radio():
    return tci.state


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


@app.get("/api/export/adif", response_class=PlainTextResponse)
def export_adif():
    s = db.get_settings()
    text = adif.export(db.all_qsos(), s.get("callsign", ""), s.get("locator", ""))
    name = f"orsat-log_{datetime.now(timezone.utc):%Y%m%d}.adi"
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- temps réel ----------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    await ws.send_text(json.dumps({"type": "radio", "data": tci.state}))
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
