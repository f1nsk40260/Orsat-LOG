"""Enrichissement des QSO pour l'analyse de propagation.

1. Données QRZ.com (adif_extra) promues en colonnes : locator d'émission du QSO (MY_GRIDSQUARE),
   pays, DXCC, continent, zones CQ / ITU, coordonnées, confirmation (LoTW, QSL, eQSL).
2. Distance / azimut depuis le QTH réel de chaque QSO (F1NSK a émis depuis IN93LR puis IN93KU),
   vers le locator du correspondant, à défaut ses coordonnées.
3. SFI, A et K historiques pour les QSO qui n'en ont pas (contacts venus de QRZ) : archive du
   GFZ Potsdam (Kp, ap, Ap, SN, F10.7 depuis 1932), Matzka et al. (2021), Space Weather,
   https://doi.org/10.1029/2020SW002641 — données CC BY 4.0. K = Kp du créneau de 3 h du QSO,
   A = Ap du jour, SFI = F10.7 observé du jour. Origine notée dans qso.solar_src = 'GFZ'.
"""

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone

from . import __version__, geo
from .db import DATA_DIR

log = logging.getLogger("orsatlog.enrich")

GFZ_URLS = ("https://kp.gfz.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt",
            "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt")
GFZ_FILE = DATA_DIR / "gfz_kp_ap_f107.txt"
GFZ_MAX_AGE = 7 * 86400          # archive relue chaque semaine


# ---------- 1. données QRZ ----------
def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def promote(extra):
    """Champs ADIF de QRZ -> colonnes du carnet."""
    e = extra or {}
    conf = ("LoTW" if e.get("LOTW_QSL_RCVD", "").upper() == "Y" else
            "QSL" if e.get("QSL_RCVD", "").upper() == "Y" else
            "eQSL" if e.get("EQSL_QSL_RCVD", "").upper() == "Y" else "")
    my = (e.get("MY_GRIDSQUARE") or "").strip().upper()
    return {
        "my_gridsquare": my if geo.valid_locator(my) else None,
        "country": (e.get("COUNTRY") or "").strip() or None,
        "dxcc": _int(e.get("DXCC")),
        "cont": (e.get("CONT") or "").strip().upper() or None,
        "cqz": _int(e.get("CQZ")),
        "ituz": _int(e.get("ITUZ")),
        "lat": geo.adif_coord(e.get("LAT")),
        "lon": geo.adif_coord(e.get("LON")),
        "confirmed": conf,
    }


# ---------- 2. géométrie ----------
def origin_of(q, settings):
    """QTH d'où le QSO a été fait / l'écoute entendue."""
    if q.get("kind") == "SWL":
        swl = settings.get("swl_locator", "")
        return swl if geo.valid_locator(swl) else settings.get("locator", "")
    my = q.get("my_gridsquare") or ""
    return my if geo.valid_locator(my) else settings.get("locator", "")


def geometry(q, settings):
    """(distance km, azimut °) ou (None, None)."""
    org = origin_of(q, settings)
    if not geo.valid_locator(org):
        return None, None
    grid = q.get("gridsquare") or ""
    if geo.valid_locator(grid):
        return geo.distance_bearing(org, grid)
    if q.get("lat") is not None and q.get("lon") is not None:
        return geo.distance_bearing(org, (q["lat"], q["lon"]))
    return None, None


# ---------- 3. archive solaire GFZ ----------
def _download():
    last = None
    for url in GFZ_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"ORSAT-LOG/{__version__} (F1NSK)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if b"F10.7" not in data[:5000] and b"Kp" not in data[:5000]:
                raise ValueError("contenu inattendu")
            tmp = GFZ_FILE.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(GFZ_FILE)
            log.info("Archive solaire GFZ téléchargée (%d Ko)", len(data) // 1024)
            return True
        except Exception as exc:
            last = exc
    log.warning("Archive solaire GFZ indisponible : %s", last)
    return False


def load_gfz():
    """{AAAAMMJJ: (kp[8], Ap, F10.7obs, SN)} ; valeurs manquantes (-1) -> None."""
    out = {}
    try:
        lines = GFZ_FILE.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        if not line or line.startswith("#"):
            continue
        t = line.split()
        if len(t) < 27:
            continue
        try:
            day = f"{int(t[0]):04d}{int(t[1]):02d}{int(t[2]):02d}"
            kp = [float(x) for x in t[7:15]]
            ap_day = float(t[23])
            sn = float(t[24])
            f107 = float(t[25])
        except ValueError:
            continue
        out[day] = ([k if k >= 0 else None for k in kp],
                    ap_day if ap_day >= 0 else None,
                    f107 if f107 > 0 else None,
                    sn if sn >= 0 else None)
    return out


_cache = {"mtime": None, "table": {}}


def gfz_table():
    """Archive GFZ chargée une fois (rechargée si le fichier a changé)."""
    try:
        m = GFZ_FILE.stat().st_mtime
    except OSError:
        return {}
    if _cache["mtime"] != m:
        _cache.update(mtime=m, table=load_gfz())
    return _cache["table"]


# Cycles solaires (début = minimum, maximum lissé). Cycle 25 : maximum provisoire.
CYCLES = [
    (23, "199608", "200111"),
    (24, "200812", "201404"),
    (25, "201912", "202410"),
]


def cycle_of(qso_date):
    """(numéro du cycle, mois depuis le début, mois par rapport au maximum) pour AAAAMMJJ."""
    ym = qso_date[:6]
    current = None
    for num, start, peak in CYCLES:
        if ym >= start:
            current = (num, start, peak)
    if not current:
        return None
    num, start, peak = current
    months = lambda a, b: (int(b[:4]) - int(a[:4])) * 12 + int(b[4:6]) - int(a[4:6])
    return {"cycle": num, "since_start": months(start, ym), "from_max": months(peak, ym),
            "max_provisional": num == 25}


def solar_for(table, qso_date, time_on):
    row = table.get(qso_date)
    if not row:
        return None
    kp, ap, f107 = row[:3]
    try:
        slot = min(7, int((time_on or "0000")[:2]) // 3)
    except ValueError:
        slot = 0
    k = kp[slot]
    if f107 is None and ap is None and k is None:
        return None
    return {"sfi": round(f107) if f107 is not None else None,
            "a_index": round(ap) if ap is not None else None,
            "k_index": round(k, 2) if k is not None else None,
            "solar_src": "GFZ"}


# ---------- passe complète ----------
def run(db, refresh=True):
    """Complète tout le carnet ; renvoie un résumé. Sans danger à relancer."""
    s = db.get_settings()
    rows = db.all_entries_for_enrich()
    promoted = geo_fixed = solar = 0
    for q in rows:
        change = {}
        if q.get("adif_extra") and q.get("country") is None:
            try:
                extra = json.loads(q["adif_extra"])
            except ValueError:
                extra = {}
            p = promote(extra)
            change.update({k: v for k, v in p.items() if v not in (None, "") or k == "confirmed"})
            change["country"] = p["country"] or ""      # traité une fois pour toutes
            promoted += 1
        merged = {**q, **change}
        d, b = geometry(merged, s)
        if (d, b) != (q.get("distance_km"), q.get("bearing")):
            change.update(distance_km=d, bearing=b)
            geo_fixed += 1
        if change:
            db.update_qso(q["id"], change)
    missing = db.entries_without_solar()
    if missing:
        stale = not GFZ_FILE.exists() or time.time() - GFZ_FILE.stat().st_mtime > GFZ_MAX_AGE
        if refresh and stale:
            _download()
        table = load_gfz()
        for q in missing:
            sol = solar_for(table, q["qso_date"], q["time_on"])
            if sol:
                db.update_qso(q["id"], sol)
                solar += 1
    summary = {"promoted": promoted, "geometry": geo_fixed, "solar": solar,
               "solar_missing": len(missing) - solar,
               "gfz_date": datetime.fromtimestamp(GFZ_FILE.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
               if GFZ_FILE.exists() else ""}
    if promoted or geo_fixed or solar:
        log.info("Enrichissement : %s", summary)
    return summary
