"""Bandes ouvertes en ce moment, par direction, depuis le QTH : mesures d'ionosondes de KC2G.

Source : https://prop.kc2g.com/api/stations.json (Andrew Rodland KC2G), dernière mesure de
chaque ionosonde du monde (réseaux GIRO, NOAA, INGV, Australian SWS) : foF2, MUF(3000) « mufd »,
foEs, hmF2, indice de confiance « cs » (0–100). Une requête toutes les 15 min.

Calcul, pour chacune des 8 directions :
  - F2 : un saut de 3000 km, point de réflexion à 1500 km du QTH ; MUF = MUF(3000) interpolée
    (pondération 1/d²) entre les ionosondes à moins de 1500 km de ce point.
  - « Proche » : saut de 600 km (Europe de l'Ouest), réflexion au-dessus du QTH,
    loi de la sécante étalonnée sur la mesure (ionosonde.mufd_estimate).
  - Es : un saut de 2000 km, réflexion à 1000 km ; MUF ≈ 5 × foEs (couche E à ~110 km).
Es retenu à partir du 17 m. Une bande est « ouverte » sous 85 % de la MUF, « en limite » jusqu'à 100 %, « fermée » au-dessus.
C'est la limite HAUTE : l'absorption de jour (160 / 80 m) et la puissance ne sont pas comptées.
"""

import json
import logging
import math
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from . import geo
from . import reach
from .ionosonde import mufd_estimate

log = logging.getLogger("orsatlog")

URL = "https://prop.kc2g.com/api/stations.json"
CACHE_SECONDS = 15 * 60
MAX_AGE = timedelta(minutes=90)     # mesure plus ancienne : ignorée
MAX_KM = 1500                       # rayon de recherche autour d'un point de réflexion
MIN_CS = 25                         # confiance minimale de la mesure
EARTH_R = 6371.0
ES_MIN_MHZ = 18.0                   # Es pris en compte à partir du 17 m
CREDIT = "Mesures d'ionosondes via KC2G (prop.kc2g.com) — GIRO, NOAA, INGV, Australian SWS"

DIRS = [("N", 0), ("NE", 45), ("E", 90), ("SE", 135), ("S", 180), ("SO", 225), ("O", 270), ("NO", 315)]
BANDS = [("160m", 1.85), ("80m", 3.65), ("60m", 5.36), ("40m", 7.1), ("30m", 10.12), ("20m", 14.15),
         ("17m", 18.1), ("15m", 21.2), ("12m", 24.94), ("10m", 28.5), ("6m", 50.15)]

_cache = {"t": 0.0, "stations": None}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "ORSAT-LOG"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.loads(resp.read())
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        st = r.get("station") or {}
        la, lo = _num(st.get("latitude")), _num(st.get("longitude"))
        if la is None or lo is None:
            continue
        lo = lo - 360 if lo > 180 else lo           # KC2G donne 0–360°
        try:
            t = datetime.strptime((r.get("time") or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        cs = _num(r.get("cs"))
        if now - t > MAX_AGE or (cs is not None and 0 <= cs < MIN_CS):
            continue
        out.append({"code": st.get("code"), "name": st.get("name"), "lat": la, "lon": lo,
                    "time": t.strftime("%Y-%m-%dT%H:%MZ"), "age_min": round((now - t).total_seconds() / 60),
                    "fof2": _num(r.get("fof2")), "mufd": _num(r.get("mufd")),
                    "foes": _num(r.get("foes")), "hmf2": _num(r.get("hmf2"))})
    return out


def stations():
    now = time.time()
    if _cache["stations"] is None or now - _cache["t"] > CACHE_SECONDS:
        try:
            _cache["stations"] = _fetch()
            _cache["t"] = now
        except Exception as exc:
            log.warning("ionosondes KC2G : %s", exc)
            _cache["t"] = now - CACHE_SECONDS + 120
    return _cache["stations"]


def destination(origin, bearing_deg, km):
    """Point à `km` du QTH dans la direction donnée (grand cercle)."""
    la1, lo1, b = math.radians(origin[0]), math.radians(origin[1]), math.radians(bearing_deg)
    d = km / EARTH_R
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return (math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180)


def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def _interp(sts, pt, field):
    """Valeur interpolée au point (1/d²) et ionosondes utilisées."""
    near = [(max(_km(pt, (s["lat"], s["lon"])), 50.0), s) for s in sts if s.get(field)]
    near = sorted((x for x in near if x[0] <= MAX_KM), key=lambda x: x[0])[:4]
    if not near:
        return None, []
    w = [1 / d ** 2 for d, _ in near]
    v = sum(wi * s[field] for wi, (_, s) in zip(w, near)) / sum(w)
    return round(v, 1), [{"name": s["name"], "km": round(d), "age_min": s["age_min"]} for d, s in near]


def _state(freq, muf):
    if muf is None:
        return None
    return "open" if freq <= 0.85 * muf else "edge" if freq <= muf else "closed"


_map_cache = {"key": None, "data": None}


def skip_map(locator, sfi=None):
    """Carte azimutale des zones de silence (reach.skip_map), recalculée au plus toutes les 15 min."""
    home = geo.locator_to_latlon(locator) if geo.valid_locator(locator or "") else None
    if not home:
        return {"ok": False, "msg": "Locator du QTH non réglé (panneau admin)."}
    sts = stations()
    if sts is None:
        return {"ok": False, "msg": "Mesures d'ionosondes (KC2G) momentanément indisponibles."}
    key = (locator, _cache["t"], sfi)
    if _map_cache["key"] != key:
        _map_cache["data"] = reach.skip_map(home, BANDS, lambda pt, f: _interp(sts, pt, f), destination, sfi)
        _map_cache["key"] = key
    return {"ok": True, "home": [round(home[0], 3), round(home[1], 3)], **_map_cache["data"]}


def open_bands(locator, sfi=None):
    """Grille bandes × directions. Bloquant : appeler via to_thread."""
    home = geo.locator_to_latlon(locator) if geo.valid_locator(locator or "") else None
    if not home:
        return {"ok": False, "msg": "Locator du QTH non réglé (panneau admin)."}
    sts = stations()
    if sts is None:
        return {"ok": False, "msg": "Mesures d'ionosondes (KC2G) momentanément indisponibles."}
    cols = []
    # proche : saut de 600 km, réflexion au-dessus du QTH
    fof2, used = _interp(sts, home, "fof2")
    m3000, _ = _interp(sts, home, "mufd")
    hm, _ = _interp(sts, home, "hmf2")
    cols.append({"dir": "Proche", "az": None, "muf": mufd_estimate(fof2, m3000, 600, hm),
                 "es": None, "stations": used, "hop_km": 600})
    for name, az in DIRS:
        pt = destination(home, az, 1500)
        muf, used = _interp(sts, pt, "mufd")
        foes, _ = _interp(sts, destination(home, az, 1000), "foes")
        cols.append({"dir": name, "az": az, "muf": muf, "es": round(5 * foes, 1) if foes else None,
                     "stations": used, "point": [round(pt[0], 2), round(pt[1], 2)], "hop_km": 3000})
    rows = []
    for band, f in BANDS:
        cells = []
        for c in cols:
            f2 = _state(f, c["muf"])
            # l'Es ne compte qu'à partir du 17 m : en dessous, c'est la F2 qui décide
            es = _state(f, c["es"]) if c["es"] and f >= ES_MIN_MHZ else None
            # le meilleur des deux modes l'emporte ; on note quand c'est l'Es
            rank = {"open": 2, "edge": 1, "closed": 0, None: -1}
            best, via = (es, "Es") if rank[es] > rank[f2] else (f2, "F2")
            cells.append({"state": best, "via": via if best in ("open", "edge") else None})
        rows.append({"band": band, "freq": f, "cells": cells})
    newest = min((s["age_min"] for s in sts), default=None)
    portee = reach.compute(home, DIRS, BANDS, lambda pt, f: _interp(sts, pt, f), destination, sfi)
    return {"ok": True, "reach": portee, "home": [round(home[0], 2), round(home[1], 2)], "columns": cols, "rows": rows,
            "stations_count": len(sts), "newest_min": newest,
            "computed": datetime.now(timezone.utc).strftime("%H:%M UTC"), "credit": CREDIT}
