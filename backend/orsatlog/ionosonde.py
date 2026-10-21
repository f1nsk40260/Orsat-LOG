"""Ionosphère mesurée au moment d'un QSO : ionosondes du réseau GIRO (DIDBase).

Source : Lowell GIRO Data Center, https://giro.uml.edu — Reinisch, B. W., and I. A. Galkin,
Global ionospheric radio observatory (GIRO), Earth Planets Space, 63, 377-381 (2011).
Mesures sous licence CC BY-NC-SA 4.0 (usage non commercial, citation de GIRO et de
l'observatoire). Accès vérifié depuis le serveur ORSAT le 21/10/2026 :
  - mesures : GET https://lgdc.uml.edu/fastchar/getbest ?ursiCode=&charName=&fromDate=&toDate=
    réponse texte : lignes « # » puis « 2011-05-02T21:00:05.000Z  CS  val QD  val QD ... »,
    « --- » = valeur absente ;
  - stations : https://lgdc.uml.edu/common/DIDBFastStationList (tableau HTML).
Pas de compte ; requêtes espacées (≥ 1,2 s), sinon le serveur répond 429.

Point de mesure : point de réflexion du trajet (milieu pour un saut unique ≤ 4000 km ; pour un
trajet plus long, points de contrôle à 2000 km de chaque extrémité, méthode CCIR). L'ionosonde
retenue est la plus proche de ce point, à moins de 1500 km, et qui a des mesures à cette heure.
"""

import json
import logging
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import __version__, geo
from .db import DATA_DIR

log = logging.getLogger("orsatlog.ionosonde")

GETBEST = "https://lgdc.uml.edu/fastchar/getbest"
STATION_LIST = "https://lgdc.uml.edu/common/DIDBFastStationList"
STATIONS_FILE = DATA_DIR / "giro_stations.json"
UA = f"ORSAT-LOG/{__version__} (F1NSK)"
MAX_KM = 1500            # ionosonde au plus à cette distance du point de réflexion
WINDOW_H = 2             # mesures sur ±2 h autour du QSO (courbe de la fiche)
EARTH_R = 6371.0

# Stations européennes relevées sur le serveur ORSAT le 21/10/2026 (secours si la liste en ligne
# est indisponible) : code URSI, nom, latitude, longitude.
FALLBACK = [
    ("AT138", "ATHENS", 38.00, 23.50), ("RL052", "CHILTON", 51.50, -0.60),
    ("DB049", "DOURBES", 50.10, 4.60), ("TR170", "EISCAT TROMSO", 69.58, 19.22),
    ("EA036", "EL ARENOSILLO", 37.10, -6.70), ("MO156", "ELEKTROUGLI", 55.76, 38.28),
    ("FF051", "FAIRFORD", 51.70, -1.50), ("GM037", "GIBILMANNA", 37.90, 14.00),
    ("JR055", "JULIUSRUH", 54.60, 13.40), ("KL154", "KALININGRAD", 54.36, 20.12),
    ("KI167", "KIRUNA", 67.86, 20.43), ("MO155", "MOSCOW", 55.47, 37.30),
    ("NI135", "NICOSIA", 35.03, 33.16), ("OL246", "OLSZTYN", 53.80, 20.50),
    ("PQ052", "PRUHONICE", 50.00, 14.60), ("RO041", "ROME", 41.90, 12.50),
    ("EB040", "ROQUETES", 40.80, 0.50), ("RV149", "ROSTOV", 47.24, 39.63),
    ("VT139", "SAN VITO", 40.60, 17.80), ("SO148", "SOPRON", 47.63, 16.72),
    ("LD160", "ST. PETERSBURG", 60.00, 30.70), ("TR169", "TROMSO", 69.60, 19.20),
    ("MZ152", "WARSAW", 52.20, 21.10),
]

_net_lock = threading.Lock()
_last_call = [0.0]


def _get(url, timeout=40):
    """Requête vers GIRO, jamais plus d'une toutes les 1,2 s."""
    with _net_lock:
        wait = 1.2 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        finally:
            _last_call[0] = time.time()


# ---------- stations ----------
def stations():
    """[(code, nom, lat, lon)] : liste GIRO relue chaque semaine, sinon liste de secours."""
    try:
        if STATIONS_FILE.exists() and time.time() - STATIONS_FILE.stat().st_mtime < 7 * 86400:
            return [tuple(s) for s in json.loads(STATIONS_FILE.read_text())]
    except (OSError, ValueError):
        pass
    try:
        html = _get(STATION_LIST)
        rows = re.findall(r'ursiCode=(\w+)">\w+</a></big></td><td[^>]*><big>([^<]+)</big></td>'
                          r'<td[^>]*><big>\s*([-\d.]+)</big></td><td[^>]*><big>\s*([-\d.]+)</big>', html)
        out = []
        for code, name, la, lo in rows:
            lo = float(lo)
            out.append((code, name.strip(), float(la), lo - 360 if lo > 180 else lo))
        if len(out) > 20:
            STATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATIONS_FILE.write_text(json.dumps(out))
            return out
    except Exception as exc:
        log.info("Liste des stations GIRO indisponible (%s) : liste de secours", exc)
    try:
        return [tuple(s) for s in json.loads(STATIONS_FILE.read_text())]
    except (OSError, ValueError):
        return FALLBACK


# ---------- géométrie ----------
def _interp(a, b, f):
    """Point à la fraction f du grand cercle de a vers b (degrés)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = 2 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2
                                + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))
    if d == 0:
        return a
    A, B = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
    x = A * math.cos(la1) * math.cos(lo1) + B * math.cos(la2) * math.cos(lo2)
    y = A * math.cos(la1) * math.sin(lo1) + B * math.cos(la2) * math.sin(lo2)
    z = A * math.sin(la1) + B * math.sin(la2)
    return (math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x)))


def reflection_points(origin, target, dist_km):
    """[(libellé, (lat, lon), longueur du saut km)]."""
    if dist_km <= 4000:
        return [("milieu du trajet", _interp(origin, target, 0.5), dist_km)]
    hops = math.ceil(dist_km / 4000)
    hop = dist_km / hops
    f = (hop / 2) / dist_km
    return [("1er saut (côté émission)", _interp(origin, target, f), hop),
            ("dernier saut (côté correspondant)", _interp(origin, target, 1 - f), hop)]


def _km(a, b):
    return geo.distance_bearing(a, b)[0]


def mufd_estimate(fof2, muf3000, hop_km, hmf2=None):
    """MUF pour la longueur réelle du saut, à partir de la MUF(3000) mesurée : loi de la sécante
    sur Terre sphérique, étalonnée sur la mesure à 3000 km (même ionogramme)."""
    if not (fof2 and muf3000 and hop_km):
        return None
    h = hmf2 if hmf2 and 150 < hmf2 < 600 else 300.0

    def sec_i(d):
        theta = min(d, 3800) / (2 * EARTH_R)
        elev = math.atan((math.cos(theta) - EARTH_R / (EARTH_R + h)) / math.sin(theta))
        sin_i = EARTH_R * math.cos(elev) / (EARTH_R + h)
        return 1 / math.sqrt(max(1e-6, 1 - sin_i ** 2))

    k = muf3000 / (fof2 * sec_i(3000))
    return round(k * fof2 * sec_i(hop_km), 2)


# ---------- mesures ----------
def _parse(text):
    """Lignes de getbest -> [{ts, cs, fof2, mufd, foes}] (None si « --- »)."""
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
        vals += [None] * 3
        try:
            ts = datetime.strptime(t[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            cs = int(t[1])
        except ValueError:
            continue
        out.append({"ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "cs": cs,
                    "fof2": vals[0], "mufd": vals[1], "foes": vals[2]})
    return out


def fetch(code, start, end):
    params = urllib.parse.urlencode({"ursiCode": code, "charName": "foF2,MUF(D),foEs",
                                     "fromDate": start.strftime("%Y/%m/%d %H:%M:%S"),
                                     "toDate": end.strftime("%Y/%m/%d %H:%M:%S")})
    return _parse(_get(f"{GETBEST}?{params}"))


def nearest(series, when):
    best = None
    for m in series:
        if m["fof2"] is None and m["mufd"] is None:
            continue
        dt = abs((datetime.strptime(m["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - when).total_seconds())
        if best is None or dt < best[0]:
            best = (dt, m)
    return (best[1], round(best[0] / 60)) if best and best[0] <= 45 * 60 else (None, None)


def for_qso(q, origin_ll, target_ll):
    """Ionosphère au(x) point(s) de réflexion du QSO. Peut prendre quelques secondes."""
    if not (origin_ll and target_ll):
        return {"ok": False, "msg": "Position du correspondant inconnue : pas de point de réflexion."}
    t = (q.get("time_on") or "000000").ljust(6, "0")
    when = datetime.strptime(q["qso_date"] + t, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    dist = q.get("distance_km") or _km(origin_ll, target_ll)
    freq = (q.get("freq") or 0) / 1e6 or None
    sts = stations()
    points = []
    for label, pt, hop in reflection_points(origin_ll, target_ll, dist):
        cands = sorted(((_km(pt, (s[2], s[3])), s) for s in sts), key=lambda x: x[0])
        cands = [c for c in cands if c[0] <= MAX_KM][:3]
        res = {"label": label, "point": pt, "hop_km": round(hop), "station": None}
        tried = []
        for km, (code, name, la, lo) in cands:
            try:
                series = fetch(code, when - timedelta(hours=WINDOW_H), when + timedelta(hours=WINDOW_H))
            except Exception as exc:
                tried.append(f"{name} : injoignable ({exc})")
                continue
            m, dt_min = nearest(series, when)
            if not m:
                tried.append(f"{name} : pas de mesure à cette heure")
                continue
            res.update(station={"code": code, "name": name.title(), "lat": la, "lon": lo, "km": km},
                       measure=m, dt_min=dt_min,
                       series=[{k: s[k] for k in ("ts", "fof2", "mufd", "foes")} for s in series],
                       muf_hop=mufd_estimate(m["fof2"], m["mufd"], hop))
            break
        if not res["station"]:
            res["net_error"] = bool(tried) and all("injoignable" in x for x in tried)
            res["msg"] = ("Aucune ionosonde à moins de %d km de ce point." % MAX_KM if not cands
                          else "Ionosondes proches sans mesure exploitable : " + " ; ".join(tried))
        points.append(res)
    return {"ok": True, "freq_mhz": freq, "when": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "points": points,
            "credit": "GIRO / DIDBase, Lowell GIRO Data Center (Reinisch & Galkin, 2011), CC BY-NC-SA 4.0"}
