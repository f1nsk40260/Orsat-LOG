"""Altitude et fréquences critiques des couches ionosphériques sur une journée (ionosonde GIRO la plus proche).

Mesures (GIRO, valeurs ARTIST, un ionogramme toutes les 5 à 15 min) :
  - F2 : hmF2 (altitude du maximum, km) et foF2 (MHz)
  - F1 : hmF1 et foF1 — n'existe que de jour, surtout en été
  - E  : hmE et foE — vers 100-120 km, forte de jour, presque absente la nuit
  - Es : foEs (E sporadique), altitude prise à celle de la couche E
La couche D ne réfléchit rien : aucune ionosonde ne donne son altitude (60-90 km). On affiche sa présence
selon la hauteur du Soleil au-dessus de la station (cos χ, nulle de nuit) ; son absorption mesurée
(fmin) est déjà donnée par dlayer.py.
"""

import math
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import ionosonde

# même ordre de préférence que dlayer.py : la plus proche du QTH d'abord, les suivantes en secours
STATIONS = [("EB040", "Roquetes", 40.80, 0.50), ("EA036", "El Arenosillo", 37.10, -6.70),
            ("DB049", "Dourbes", 50.10, 4.60), ("RL052", "Chilton", 51.50, -0.60),
            ("RO041", "Rome", 41.90, 12.50)]
CHARS = ["foF2", "hmF2", "foF1", "hmF1", "foE", "hmE", "foEs"]
CORE = ["foF2", "hmF2", "foE", "foEs"]     # repli si GIRO refuse une des caractéristiques
TODAY_TTL = 15 * 60

_cache = {}                  # "AAAAMMJJ" -> (instant du calcul, résultat)


def _parse(text, chars):
    out = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        t = line.split()
        if len(t) < 2 or "T" not in t[0]:
            continue
        vals = []
        for i in range(2, len(t), 2):          # valeur puis indicateur de qualité
            try:
                vals.append(float(t[i]))
            except ValueError:
                vals.append(None)
        vals += [None] * len(chars)
        try:
            ts = datetime.strptime(t[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        row = dict.fromkeys(CHARS)
        row.update(zip(chars, vals[:len(chars)]))
        out.append((ts, row))
    return out


def _fetch(code, start, end):
    rows = _fetch_chars(code, start, end, CHARS)
    return rows or _fetch_chars(code, start, end, CORE)


def _fetch_chars(code, start, end, chars):
    params = urllib.parse.urlencode({"ursiCode": code, "charName": ",".join(chars),
                                     "fromDate": start.strftime("%Y/%m/%d %H:%M:%S"),
                                     "toDate": end.strftime("%Y/%m/%d %H:%M:%S")})
    return _parse(ionosonde._get(f"{ionosonde.GETBEST}?{params}"), chars)


def _ok_h(h, lo, hi):
    return round(h) if h is not None and lo < h < hi else None


def _r(v):
    return round(v, 2) if v else None


def day_layers(day):
    """day = « AAAAMMJJ » (UTC). Bloquant (requête GIRO) : appeler via to_thread."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y%m%d") == day
    hit = _cache.get(day)
    if hit and (not today or time.time() - hit[0] < TODAY_TTL):
        return hit[1]
    start = datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)
    end = min(start + timedelta(days=1), now)
    if end <= start:
        return {"ok": False, "msg": "Jour à venir."}
    from .reach import solar_zenith
    errors = []
    for code, name, lat, lon in STATIONS:
        try:
            rows = _fetch(code, start, end)
        except Exception as exc:
            errors.append(f"{name} : {exc}")
            continue
        pts = []
        for ts, v in rows:
            if v["foF2"] is None and v["foE"] is None and v["foF1"] is None:
                continue
            chi = solar_zenith(lat, lon, ts)
            pts.append({"time": ts.strftime("%H%M"),
                        "f2": [_r(v["foF2"]), _ok_h(v["hmF2"], 150, 600)],
                        "f1": [_r(v["foF1"]), _ok_h(v["hmF1"], 140, 300)],
                        "e": [_r(v["foE"]), _ok_h(v["hmE"], 85, 160)],
                        "es": _r(v["foEs"]),
                        # présence de la couche D (0 la nuit, 1 Soleil au zénith)
                        "d": round(max(0.0, math.cos(math.radians(chi))), 2)})
        if len(pts) < 2:
            errors.append(f"{name} : pas de mesure")
            continue
        res = {"ok": True, "station": name, "code": code, "points": pts}
        _cache[day] = (time.time(), res)
        return res
    return {"ok": False, "msg": "Ionosondes GIRO indisponibles (" + "; ".join(errors) + ")."}
