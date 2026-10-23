"""ORSAT-LOG, serveur central (FastAPI) : API REST + WebSocket temps réel + interface.

Tourne sur le PC du WebSDR, derrière proxy.py de PhantomSDR-ORSAT (https://<site>/log/).
Les réglages se font dans le panneau admin du WebSDR (rubrique « Carnet ORSAT-LOG »)."""

import asyncio
import json
import logging
import os
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, adif, auth, backup, eibi, enrich, geo, ionosonde, kc2g, qrz, qrzxml, solar, spacewx, weather
from .db import DATA_DIR, Database
from .websdr import Page, WebSdrLink

log = logging.getLogger("orsatlog")

ROOT = Path(__file__).resolve().parents[2]          # dossier du dépôt (~/Orsat-LOG)
FRONTEND_DIST = ROOT / "frontend" / "dist"

db = Database()
# Écoute FT8/WSPR via l'autorun du WebSDR supprimée (v1.13.0) : trop de charge sur le serveur.
# Purge unique des anciennes tables (jusqu'à ~2 Go) puis récupération de la place.
with db._lock:
    if db._con.execute("SELECT 1 FROM sqlite_master WHERE name='heard'").fetchone():
        db._con.executescript("DROP TABLE IF EXISTS heard; DROP TABLE IF EXISTS heard_sum;"
                              "DROP TABLE IF EXISTS heard_spool;")
        db._con.commit()
        db._con.execute("VACUUM")
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
qrz_dir = qrzxml.QrzXml(db)         # annuaire QRZ : photo, nom, QTH d'un indicatif
grid_filler = qrzxml.GridFiller(db, qrz_dir)


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
                    db.add_snapshot(utc_day(now), now.strftime("%H%M%S"), data, source=solar.SOURCE)
        except Exception as exc:
            log.warning("relevé de propagation : %s", exc)
        try:
            sw = await asyncio.to_thread(spacewx.get_spacewx)
            if sw:
                now = datetime.now(timezone.utc)
                db.add_spacewx(utc_day(now), now.strftime("%H%M%S"), sw)
        except Exception as exc:
            log.warning("relevé de météo spatiale : %s", exc)
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


_enrich_state = {"last": "", "summary": {}}


async def _enrich_loop():
    """Enrichissement du carnet (enrich.py) : au démarrage, puis une fois par jour."""
    await asyncio.sleep(30)
    while True:
        await run_enrich()
        await asyncio.sleep(24 * 3600)


async def run_enrich():
    try:
        _enrich_state["summary"] = await asyncio.to_thread(enrich.run, db)
        _enrich_state["last"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception as exc:
        log.warning("enrichissement : %s", exc)


@asynccontextmanager
async def lifespan(app):
    recorder = asyncio.create_task(_propagation_recorder())
    syncer = asyncio.create_task(qrz_sync.loop())
    enricher = asyncio.create_task(_enrich_loop())
    saver = asyncio.create_task(backup.daily_task(db))
    yield
    recorder.cancel()
    saver.cancel()
    syncer.cancel()
    enricher.cancel()


app = FastAPI(title="ORSAT-LOG", version=__version__, lifespan=lifespan)


# ---------- accès protégé ----------
# Pages et appels accessibles sans session : la connexion elle-même.
_PUBLIC = {"/login", "/favicon.ico", "/ecoute", "/ecoute.html", "/api/public/listenmap"}
_PUBLIC_PREFIX = ("/assets/",)      # fichiers compilés de l'interface (aucune donnée du carnet)

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
    if request.url.path in _PUBLIC or request.url.path.startswith(_PUBLIC_PREFIX) or _logged_in(request.cookies):
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
            "websdr_pages": websdr.state["pages"], "clients": len(_clients),
            "enrich": {**db.enrich_stats(), **_enrich_state}}


# ---------- synchronisation QRZ.com (panneau admin) ----------
def _qrz_status():
    s = db.get_settings()
    key = s.get("qrz_api_key", "")
    return {"enabled": s.get("qrz_sync") == "1", "key_set": bool(key),
            "key_hint": ("…" + key[-4:]) if len(key) >= 4 else "",
            "full_done": s.get("qrz_full_done") == "1", "last_pull": s.get("qrz_last_pull", ""),
            "xml_user": s.get("qrz_xml_user", ""), "xml_set": bool(s.get("qrz_xml_password")),
            **qrz_sync.state, **db.qrz_counts(), "journal": list(qrz_sync.journal)[-80:]}


@app.get("/api/admin/qrz")
def admin_qrz(request: Request):
    _require_admin(request)
    return _qrz_status()


class QrzIn(BaseModel):
    api_key: str | None = None     # None = inchangée ; "" = effacer
    enabled: bool | None = None
    xml_user: str | None = None    # annuaire QRZ : identifiant (None = inchangé ; "" = effacer)
    xml_password: str | None = None


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
    if cfg.xml_user is not None or cfg.xml_password is not None:
        cur = db.get_settings()
        user = (cfg.xml_user if cfg.xml_user is not None else cur.get("qrz_xml_user", "")).strip()
        pwd = cfg.xml_password if cfg.xml_password else cur.get("qrz_xml_password", "")
        if not user:
            values.update(qrz_xml_user="", qrz_xml_password="")
        else:
            try:      # identifiants essayés avant d'être enregistrés
                sess = await asyncio.to_thread(qrz_dir.login, user, pwd)
            except Exception as exc:
                raise HTTPException(400, f"Annuaire QRZ : {exc}")
            values.update(qrz_xml_user=user, qrz_xml_password=pwd)
            qrz_sync.note("Annuaire QRZ : connexion vérifiée" + (f" — {sess['message']}" if sess.get("message") else "."))
        qrz_dir.forget()
    if cfg.enabled is not None:
        values["qrz_sync"] = "1" if cfg.enabled else "0"
        qrz_sync.note("Synchronisation automatique " + ("activée." if cfg.enabled else "désactivée."))
    if values:
        db.set_settings(values)
    if qrz_sync.enabled():
        qrz_sync.poke()
    return _qrz_status()


@app.get("/api/admin/gridfill")
def admin_gridfill(request: Request):
    """Locators manquants des QSO enregistrés : nombre et avancement de la recherche QRZ."""
    _require_admin(request)
    return {**grid_filler.count(), "state": grid_filler.state}


@app.post("/api/admin/gridfill")
async def admin_gridfill_run(request: Request):
    _require_admin(request)
    if not db.get_settings().get("qrz_xml_password"):
        raise HTTPException(400, "Annuaire QRZ non réglé (identifiant et mot de passe QRZ.com)")
    if not grid_filler.state["running"]:
        asyncio.create_task(asyncio.to_thread(grid_filler.run))
    return {**grid_filler.count(), "state": grid_filler.state}


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
        s.pop("qrz_xml_password", None)
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


def recompute():
    """Recalcule distance et azimut de toutes les entrées (après un changement de locator).
    Un QSO garde son propre QTH d'émission (my_gridsquare) : seuls ceux qui n'en ont pas, et les
    écoutes SWL, suivent le locator des réglages."""
    n = 0
    s = db.get_settings()
    for q in db.all_qsos():
        d, b = enrich.geometry(q, s)
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


@app.get("/api/spacewx")
async def get_spacewx():
    """Météo spatiale en direct (NOAA SWPC) : Kp estimé, vent solaire, Bz, X, échelles R/S/G."""
    data = await asyncio.to_thread(spacewx.get_spacewx)
    if not data:
        return {"ok": False, "msg": "NOAA SWPC momentanément injoignable."}
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    big = [f for f in data.get("flares") or [] if (f.get("max") or f.get("begin") or "") >= since
           and spacewx.flare_rank(f.get("cls")) >= 1e-6]
    return {"ok": True, **{k: v for k, v in data.items() if k != "flares"}, "flares_24h": big}


@app.get("/api/skipmap")
async def get_skip_map():
    """Carte azimutale des zones de silence + correspondants du jour (positions connues)."""
    s = db.get_settings()
    sol = await asyncio.to_thread(solar.get_solar) or db.last_snapshot() or {}
    data = await asyncio.to_thread(kc2g.skip_map, s.get("locator", ""), sol.get("sfi"))
    if data.get("ok"):
        pts = []
        for q in db.day_qsos(utc_day()):
            ll = None
            if geo.valid_locator(q.get("gridsquare") or ""):
                ll = geo.locator_to_latlon(q["gridsquare"])
            elif q.get("lat") is not None and q.get("lon") is not None:
                ll = (q["lat"], q["lon"])
            if ll:
                pts.append({"call": q["call"], "band": q.get("band"), "kind": q.get("kind"),
                            "session": q.get("session_name"), "lat": ll[0], "lon": ll[1],
                            "km": q.get("distance_km"), "time": q.get("time_on")})
        data["stations"] = pts
    return data


# ---------- images satellite pour la carte des zones de silence ----------
# Sentinel-2 cloudless 2017 (EOX IT Services, données Copernicus modifiées, CC BY 4.0), tuiles Web Mercator.
# Le carnet les télécharge et les garde : la page reste en même origine, une zone vue ne se recharge pas.
SAT_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2017_3857/default/g/{z}/{y}/{x}.jpg"
SAT_DIR = DATA_DIR / "tiles"


def _sat_tile(z, y, x):
    path = SAT_DIR / str(z) / str(y) / f"{x}.jpg"
    if not path.exists():
        import urllib.request
        req = urllib.request.Request(SAT_URL.format(z=z, y=y, x=x), headers={"User-Agent": "ORSAT-LOG"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(body)
        tmp.replace(path)
    return path


@app.get("/api/sattile/{z}/{y}/{x}.jpg")
async def sat_tile(z: int, y: int, x: int):
    if not (0 <= z <= 14 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(400, "Tuile hors limites")
    try:
        path = await asyncio.to_thread(_sat_tile, z, y, x)
    except Exception as exc:
        raise HTTPException(502, f"Image satellite indisponible : {exc}")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=2592000"})


def _listen_map():
    s = db.get_settings()
    sol = solar.get_solar() or db.last_snapshot() or {}
    loc = s.get("swl_locator") or s.get("locator", "")
    return kc2g.listen_map(loc, sol.get("sfi"))


@app.get("/api/listenmap")
async def get_listen_map():
    """Zone d'écoute efficace du WebSDR en ce moment."""
    return await asyncio.to_thread(_listen_map)


@app.get("/api/public/listenmap")
async def get_public_listen_map():
    """Même carte, sans connexion, pour la page publique « écoute » (aucune donnée du carnet)."""
    return await asyncio.to_thread(_listen_map)


@app.get("/api/openbands")
async def get_open_bands():
    """Bandes ouvertes maintenant par direction depuis le QTH (ionosondes KC2G)."""
    sol = await asyncio.to_thread(solar.get_solar) or db.last_snapshot() or {}
    return await asyncio.to_thread(kc2g.open_bands, db.get_settings().get("locator", ""), sol.get("sfi"))


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


@app.get("/api/qsos/{qso_id}/context")
def qso_context(qso_id: int):
    """Tout ce qu'il faut pour la fiche d'un QSO : conditions solaires et géomagnétiques du jour
    (archive GFZ), SFI des 7 jours autour, position dans le cycle solaire, QTH d'émission,
    autres QSO du jour sur la bande, historique avec la station."""
    q = db.get_qso(qso_id)
    if not q:
        raise HTTPException(404, "Entrée introuvable")
    q.pop("adif_extra", None)
    s = db.get_settings()
    table = enrich.gfz_table()
    from datetime import date as _date, timedelta as _td
    d0 = _date(int(q["qso_date"][:4]), int(q["qso_date"][4:6]), int(q["qso_date"][6:8]))
    day = table.get(q["qso_date"])
    week = []
    for i in range(-7, 8):
        k = (d0 + _td(days=i)).strftime("%Y%m%d")
        row = table.get(k)
        week.append({"day": k, "sfi": row[2] if row else None, "ap": row[1] if row else None,
                     "kp_max": max([x for x in row[0] if x is not None], default=None) if row else None})
    try:
        slot = min(7, int((q["time_on"] or "00")[:2]) // 3)
    except ValueError:
        slot = 0
    origin = enrich.origin_of(q, s)
    origin_ll = geo.locator_to_latlon(origin) if geo.valid_locator(origin) else None
    target_ll = None
    if geo.valid_locator(q.get("gridsquare") or ""):
        target_ll = geo.locator_to_latlon(q["gridsquare"])
    elif q.get("lat") is not None and q.get("lon") is not None:
        target_ll = (q["lat"], q["lon"])
    return {
        "qso": q,
        "origin": origin, "origin_ll": origin_ll, "target_ll": target_ll,
        "solar": {"kp": day[0] if day else None, "ap": day[1] if day else None,
                  "sfi": day[2] if day else None, "sn": day[3] if day else None,
                  "slot": slot, "source": "GFZ" if day else None},
        "week": week,
        "cycle": enrich.cycle_of(q["qso_date"]),
        "snapshot": db.snapshots_around(q["qso_date"], q["time_on"]),
        "same_day_band": db.same_day_band(q["qso_date"], q.get("band"), qso_id),
        "same_call": db.same_call(q["call"], qso_id) if q.get("kind") == "QSO" else [],
        "spacewx": _spacewx_for(q),
    }


def _spacewx_for(q):
    """Météo spatiale au moment du QSO : relevé NOAA le plus proche et éruptions de -3 h à +30 min.
    Disponible pour les QSO postérieurs à la mise en service des relevés (v1.14)."""
    t = (q.get("time_on") or "000000").ljust(6, "0")
    try:
        when = datetime.strptime(q["qso_date"] + t, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    since = db.flares_since()
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    if not since or when.strftime(fmt) < since:
        return {"covered": False, "since": since}
    flares = db.flares_between((when - timedelta(hours=3)).strftime(fmt), (when + timedelta(minutes=30)).strftime(fmt))
    for f in flares:
        peak = datetime.strptime((f.get("peak") or f["begin"])[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        f["minutes"] = round((peak - when).total_seconds() / 60)       # négatif = avant le QSO
    return {"covered": True, "near": db.spacewx_near(q["qso_date"], q.get("time_on")),
            "flares": [f for f in flares if spacewx.flare_rank(f.get("cls")) >= 1e-6]}


@app.get("/api/qsos/{qso_id}/iono")
def qso_iono(qso_id: int, refresh: bool = False):
    """Ionosphère mesurée (ionosondes GIRO) au point de réflexion du trajet, à l'heure du QSO.
    Interrogée à la première ouverture de la fiche puis mémorisée (fonction synchrone : FastAPI
    l'exécute hors de la boucle, le carnet reste réactif pendant l'attente)."""
    q = db.get_qso(qso_id)
    if not q:
        raise HTTPException(404, "Entrée introuvable")
    origin = enrich.origin_of(q, db.get_settings())
    origin_ll = geo.locator_to_latlon(origin) if geo.valid_locator(origin) else None
    target_ll = None
    if geo.valid_locator(q.get("gridsquare") or ""):
        target_ll = geo.locator_to_latlon(q["gridsquare"])
    elif q.get("lat") is not None and q.get("lon") is not None:
        target_ll = (q["lat"], q["lon"])
    key = f"{q['qso_date']}{q.get('time_on') or ''}|{origin_ll}|{target_ll}|{q.get('freq')}"
    if not refresh:
        hit = db.iono_get(qso_id, key)
        if hit:
            return hit
    res = ionosonde.for_qso(q, origin_ll, target_ll)
    # QSO de moins de 6 h : les ionosondes n'ont pas encore tout publié (courbe +2 h incomplète),
    # on ne fige pas le résultat, la fiche réinterrogera GIRO à la prochaine ouverture.
    recent = (datetime.now(timezone.utc) - datetime.strptime(res.get("when", "2000-01-01T00:00:00Z"),
              "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() < 6 * 3600
    res["provisional"] = recent
    if res.get("ok") and not recent and not any(p.get("net_error") for p in res["points"]):
        db.iono_put(qso_id, key, res)
    return res


@app.get("/api/eibi")
def eibi_lookup(freq: int, date: str = "", time: str = ""):
    """Stations de la grille EiBi sur cette fréquence (Hz) à cette date / heure UTC (maintenant
    par défaut) : identification des écoutes SWL et position de l'émetteur."""
    now = datetime.now(timezone.utc)
    return eibi.lookup(freq, date or now.strftime("%Y%m%d"), time or now.strftime("%H%M"))


@app.get("/api/qrz/lookup/{call}")
def qrz_lookup(call: str):
    """Annuaire QRZ : photo, prénom, nom et QTH d'un indicatif (gardé 30 jours)."""
    try:
        return {"ok": True, **qrz_dir.lookup(call)}
    except Exception as exc:
        return {"ok": False, "msg": str(exc)}


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

    settings = db.get_settings()
    if kind == "QSO" and geo.valid_locator(settings.get("locator", "")):
        rec["my_gridsquare"] = settings["locator"].upper()     # QTH d'émission du jour
    rec["distance_km"], rec["bearing"] = enrich.geometry({**rec, "kind": kind}, settings)

    sol = await asyncio.to_thread(solar.get_solar) or db.last_snapshot()
    if sol:
        rec["sfi"], rec["a_index"], rec["k_index"] = sol["sfi"], sol["a_index"], sol["k_index"]
        rec["solar_src"] = solar.SOURCE

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
    old = db.get_qso(qso_id)
    rec["distance_km"], rec["bearing"] = enrich.geometry(
        {**rec, "kind": kind, "my_gridsquare": old.get("my_gridsquare"),
         "lat": None if grid else old.get("lat"), "lon": None if grid else old.get("lon")},
        db.get_settings())
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


def _gfz_day(day):
    """Indices officiels du jour (archive GFZ Potsdam) : pour les jours d'avant les relevés du
    carnet, et pour comparer avec eux. None si la date n'est pas (encore) dans l'archive."""
    row = enrich.gfz_table().get(day)
    if not row:
        return None
    return {"kp": row[0], "ap": row[1], "sfi": row[2], "sn": row[3]}


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
        "archive": _gfz_day(day),
        "weather": db.day_weather(day),
        "spacewx": db.day_spacewx(day),
        "flares": [f for f in db.flares_between(f"{day[:4]}-{day[4:6]}-{day[6:]}T00:00:00Z",
                                                f"{day[:4]}-{day[4:6]}-{day[6:]}T23:59:59Z")
                   if spacewx.flare_rank(f.get("cls")) >= 1e-6],
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


# ---------- analyse du carnet : où et quand la station passe le mieux ----------
_BAND_ORDER = ["2190m", "630m", "160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m",
               "6m", "4m", "2m", "70cm", "23cm", "13cm"]
_SECTORS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


def _bucket_stats(rows):
    km = sorted(r["distance_km"] for r in rows if r["distance_km"])
    n = len(rows)
    return {"n": n, "with_km": len(km),
            "median_km": km[len(km) // 2] if km else None, "max_km": km[-1] if km else None,
            "dx_pct": round(100 * sum(k > 3000 for k in km) / len(km)) if km else None}


@app.get("/api/analysis")
def analysis(kind: str = "QSO", band: str = ""):
    """Statistiques du carnet croisées avec Kp, SFI, heure et direction."""
    if kind not in ("QSO", "SWL"):
        raise HTTPException(400, "kind = QSO ou SWL")
    rows = db.analysis_rows(kind)
    bands = sorted({r["band"] for r in rows if r["band"]},
                   key=lambda b: _BAND_ORDER.index(b) if b in _BAND_ORDER else 99)
    sel = [r for r in rows if not band or (r["band"] or "") == band]

    def hour(r):
        try:
            return int((r["time_on"] or "")[:2])
        except ValueError:
            return None

    kp_b = [("0–1", 0, 2), ("2", 2, 3), ("3", 3, 4), ("4", 4, 5), ("5 et +", 5, 10)]
    sfi_b = [("< 90", 0, 90), ("90–120", 90, 120), ("120–150", 120, 150), ("150–200", 150, 200), ("≥ 200", 200, 999)]
    by_kp = [{"label": l, **_bucket_stats([r for r in sel if r["k_index"] is not None and a <= r["k_index"] < b])}
             for l, a, b in kp_b]
    by_sfi = [{"label": l, **_bucket_stats([r for r in sel if r["sfi"] is not None and a <= r["sfi"] < b])}
              for l, a, b in sfi_b]
    by_hour = [{"hour": h, **_bucket_stats([r for r in sel if hour(r) == h])} for h in range(24)]
    sector = lambda r: None if r["bearing"] is None else int(((r["bearing"] % 360) + 22.5) // 45) % 8
    by_dir = [{"label": _SECTORS[i], **_bucket_stats([r for r in sel if sector(r) == i])} for i in range(8)]
    grid = [{"band": b, "hours": [sum(1 for r in rows if r["band"] == b and hour(r) == h) for h in range(24)]}
            for b in bands]
    return {"kind": kind, "band": band, "bands": bands, "total": _bucket_stats(sel),
            "missing_solar": sum(1 for r in sel if r["k_index"] is None),
            "by_kp": by_kp, "by_sfi": by_sfi, "by_hour": by_hour, "by_dir": by_dir, "band_hour": grid}


@app.get("/ecoute", include_in_schema=False)
def public_listen_page():
    """Page publique « où le WebSDR entend bien en ce moment » (à afficher depuis la page du WebSDR)."""
    return FileResponse(FRONTEND_DIST / "ecoute.html")


# ---------- frontend compilé ----------
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
