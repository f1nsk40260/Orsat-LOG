"""Absorption de la couche D MESURÉE : corrige le modèle de George & Bradley (soleil calme) de reach.py.

Deux sources :
  1. Éruptions (SWF, « sudden ionospheric disturbance ») — flux X GOES 0,1–0,8 nm en temps réel
     (spacewx.py), modèle D-RAP de la NOAA : fréquence la plus haute absorbée de 1 dB au point
     subsolaire HAF = 10·log10(flux) + 65 MHz (C1 ≈ 5, M1 ≈ 15, X1 ≈ 25 MHz), réduite côté jour par
     cos(χ)^0,75, nulle de nuit ; absorption à f : (HAF / f)^1,5 dB par traversée de la couche D,
     multipliée par la sécante du trajet. Pris en compte à partir de la classe C1.
  2. fmin des ionosondes (GIRO, valeurs ARTIST) — fréquence la plus basse qui revient : elle monte
     quand la couche D absorbe. Pour chaque station proche, fmin du moment comparée à la médiane des
     15 jours précédents à la même demi-heure : facteur (fmin / médiane)² (l'absorption varie
     comme 1/f²), borné 0,5–8, appliqué au modèle autour de la station (pondération 1/d²,
     1500 km au plus). Ionogramme récent de jour SANS aucun écho (ni fmin ni foF2) : black-out,
     facteur maximal. Sans données GIRO : facteur 1, le calcul reste celui du modèle seul.

Le suivi des facteurs dans le temps montre aussi la vitesse de retour à la normale après un événement.
"""

import asyncio
import logging
import math
import statistics
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import ionosonde, spacewx

log = logging.getLogger("orsatlog")

# Ionosondes européennes utiles depuis le sud-ouest de la France (codes URSI, voir ionosonde.FALLBACK)
STATIONS = [("EB040", "Roquetes", 40.80, 0.50), ("EA036", "El Arenosillo", 37.10, -6.70),
            ("DB049", "Dourbes", 50.10, 4.60), ("RO041", "Rome", 41.90, 12.50),
            ("RL052", "Chilton", 51.50, -0.60), ("FF051", "Fairford", 51.70, -1.50),
            ("PQ052", "Pruhonice", 50.00, 14.60), ("GM037", "Gibilmanna", 37.90, 14.00)]
SWF_MIN_FLUX = 1e-6          # classe C1
REF_DAYS = 15
FRESH_MIN = 45               # mesure plus ancienne : ignorée
FACTOR_MIN, FACTOR_MAX = 0.5, 8.0
MAX_KM = 1500
PERIOD_S = 15 * 60

_series = {}                 # code -> {ts(datetime): (cs, fmin, fof2)}
state = {"stations": {}, "at": None, "error": ""}


# ---------- éruptions (GOES, D-RAP) ----------
def haf0():
    """HAF au point subsolaire (MHz) si une éruption ≥ C1 est en cours, sinon None."""
    sw = spacewx.get_spacewx() or {}
    flux = sw.get("xray_flux")
    try:
        flux = float(flux)
    except (TypeError, ValueError):
        return None, None
    if flux < SWF_MIN_FLUX:
        return None, sw.get("xray")
    return 10 * math.log10(flux) + 65, sw.get("xray")


def swf_db(freq, sec, chi_deg, h0):
    """Absorption ajoutée par l'éruption pour UNE traversée de la couche D (dB)."""
    if not h0 or chi_deg >= 90:
        return 0.0
    haf = h0 * math.cos(math.radians(chi_deg)) ** 0.75
    return sec * (haf / freq) ** 1.5


# ---------- fmin des ionosondes (GIRO) ----------
def _parse(text):
    out = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        t = line.split()
        if len(t) < 2 or "T" not in t[0]:
            continue
        vals = []
        for i in range(2, len(t), 2):
            try:
                vals.append(float(t[i]))
            except ValueError:
                vals.append(None)
        vals += [None, None]
        try:
            ts = datetime.strptime(t[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            cs = int(t[1])
        except ValueError:
            continue
        out[ts] = (cs, vals[0], vals[1])
    return out


def _fetch(code, start, end):
    params = urllib.parse.urlencode({"ursiCode": code, "charName": "fmin,foF2",
                                     "fromDate": start.strftime("%Y/%m/%d %H:%M:%S"),
                                     "toDate": end.strftime("%Y/%m/%d %H:%M:%S")})
    return _parse(ionosonde._get(f"{ionosonde.GETBEST}?{params}"))


def _evaluate(code, name, lat, lon, now):
    s = _series.get(code) or {}
    recent = [ts for ts in s if now - ts <= timedelta(minutes=FRESH_MIN)]
    if not recent:
        return {"name": name, "lat": lat, "lon": lon, "factor": None, "note": "pas de mesure récente"}
    ts = max(recent)
    cs, fmin, fof2 = s[ts]
    from .reach import solar_zenith
    day = solar_zenith(lat, lon, ts) < 90
    if fmin is None and fof2 is None:
        if day and cs is not None and cs >= 0:
            return {"name": name, "lat": lat, "lon": lon, "factor": FACTOR_MAX, "fmin": None, "ts": ts.isoformat(),
                    "note": "aucun écho de jour : black-out"}
        return {"name": name, "lat": lat, "lon": lon, "factor": None, "note": "ionogramme sans valeur"}
    if fmin is None:
        return {"name": name, "lat": lat, "lon": lon, "factor": None, "note": "fmin absente"}
    # référence : même demi-heure (±15 min) des 15 jours précédents
    ref = []
    for d in range(1, REF_DAYS + 1):
        t0 = ts - timedelta(days=d)
        ref += [v[1] for t, v in s.items() if abs((t - t0).total_seconds()) <= 15 * 60 and v[1]]
    if len(ref) < 5:
        return {"name": name, "lat": lat, "lon": lon, "factor": None, "fmin": fmin, "ts": ts.isoformat(),
                "note": "historique insuffisant pour la référence"}
    med = statistics.median(ref)
    if not day:
        f = 1.0                                   # de nuit, pas de couche D : pas de correction
    else:
        f = max(FACTOR_MIN, min(FACTOR_MAX, (fmin / med) ** 2))
    return {"name": name, "lat": lat, "lon": lon, "factor": round(f, 2), "fmin": fmin,
            "ref": round(med, 2), "ts": ts.isoformat(), "note": "" if day else "nuit"}


def refresh():
    """Bloquant. Premier passage : 16 jours d'historique par station ; ensuite les 3 dernières heures."""
    now = datetime.now(timezone.utc)
    errors = []
    for code, name, lat, lon in STATIONS:
        start = now - (timedelta(hours=3) if _series.get(code) else timedelta(days=REF_DAYS + 1))
        try:
            got = _fetch(code, start, now)
            s = _series.setdefault(code, {})
            s.update(got)
            for ts in [t for t in s if now - t > timedelta(days=REF_DAYS + 2)]:
                del s[ts]
        except Exception as exc:
            errors.append(f"{name} : {exc}")
        state["stations"][code] = _evaluate(code, name, lat, lon, now)
    state["at"] = now.strftime("%Y-%m-%d %H:%M UTC")
    state["error"] = "; ".join(errors)
    if errors:
        log.info("fmin GIRO : %s", state["error"])


def factor_at(pt):
    """Facteur multiplicatif de l'absorption au point (lat, lon) : 1 sans mesure proche."""
    num = den = 0.0
    for st in state["stations"].values():
        if st.get("factor") is None:
            continue
        la1, lo1, la2, lo2 = map(math.radians, (pt[0], pt[1], st["lat"], st["lon"]))
        c = math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(lo2 - lo1)
        d = 6371.0 * math.acos(max(-1.0, min(1.0, c)))
        if d > MAX_KM:
            continue
        w = 1.0 / max(d, 50.0) ** 2
        num += w * st["factor"]
        den += w
    return num / den if den else 1.0


def summary():
    """Pour la météo spatiale : éruption en cours et facteurs par station."""
    h0, cls = haf0()
    return {"swf": {"class": cls, "haf_mhz": round(h0, 1) if h0 else None},
            "fmin": {"at": state["at"], "error": state["error"],
                     "stations": [dict(v, code=k) for k, v in state["stations"].items()]}}


async def loop():
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.to_thread(refresh)
        except Exception as exc:
            state["error"] = str(exc)
            log.info("fmin GIRO : %s", exc)
        await asyncio.sleep(PERIOD_S)
