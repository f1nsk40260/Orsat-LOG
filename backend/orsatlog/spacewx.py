"""Météo spatiale en direct : NOAA SWPC (Space Weather Prediction Center), données publiques.

Sources JSON (services.swpc.noaa.gov), lues toutes les 15 min par le relevé de propagation :
  - json/planetary_k_index_1m.json        Kp estimé minute par minute ({time_tag, estimated_kp, kp})
  - json/rtsw/rtsw_mag_1m.json            champ magnétique interplanétaire (bt, bz_gsm), du plus récent au plus ancien
  - json/rtsw/rtsw_wind_1m.json           vent solaire (proton_speed, proton_density), idem
  - json/goes/primary/xrays-6-hour.json   flux X GOES (energy « 0.1-0.8nm » = bande longue des classes A..X)
  - json/goes/primary/xray-flares-7-day.json  éruptions (begin_time, max_time, end_time, max_class)
  - products/noaa-scales.json             échelles NOAA R (radio), S (radiations), G (géomagnétique)

Une requête par fichier et par relevé : charge négligeable pour le serveur ORSAT.
"""

import json
import logging
import time
import urllib.request

log = logging.getLogger("orsatlog")

BASE = "https://services.swpc.noaa.gov/"
URLS = {
    "kp": BASE + "json/planetary_k_index_1m.json",
    "mag": BASE + "json/rtsw/rtsw_mag_1m.json",
    "wind": BASE + "json/rtsw/rtsw_wind_1m.json",
    "xray": BASE + "json/goes/primary/xrays-6-hour.json",
    "flares": BASE + "json/goes/primary/xray-flares-7-day.json",
    "scales": BASE + "products/noaa-scales.json",
}
CACHE_SECONDS = 10 * 60
CREDIT = "NOAA Space Weather Prediction Center (SWPC), données publiques"

_cache = {"t": 0.0, "data": None}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ORSAT-LOG"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def xray_class(flux):
    """Flux X 0,1–0,8 nm (W/m²) -> classe « C2.3 »."""
    if not flux or flux <= 0:
        return None
    for letter, base in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)):
        if flux >= base or letter == "A":
            return f"{letter}{flux / base:.1f}"


def flare_rank(cls):
    """« M2.4 » -> 2.4e-5 (pour comparer / filtrer)."""
    if not cls or cls[0] not in "ABCMX":
        return 0.0
    base = {"A": 1e-8, "B": 1e-7, "C": 1e-6, "M": 1e-5, "X": 1e-4}[cls[0]]
    return base * (_num(cls[1:]) or 1.0)


def _iso(t):
    """« 2026-10-22T14:47:00 » ou « …Z » -> (AAAAMMJJ, HHMMSS)."""
    t = (t or "").replace("Z", "")
    return t[:10].replace("-", ""), t[11:19].replace(":", "")


def _rtsw_latest(rows, fields):
    """Dernière mesure valide : la source active (DSCOVR / ACE / IMAP) d'abord."""
    rows = [r for r in rows or [] if all(r.get(f) is not None for f in fields)]
    if not rows:
        return None
    act = [r for r in rows if r.get("active")]
    return max(act or rows, key=lambda r: r.get("time_tag") or "")


def _fetch():
    data = {"updated": None, "credit": CREDIT}
    errors = []

    def take(key):
        try:
            return _get(URLS[key])
        except Exception as exc:
            errors.append(f"{key} : {exc}")
            return None

    kp = take("kp")
    if kp:
        last = max(kp, key=lambda r: r.get("time_tag") or "")
        data["kp"] = _num(last.get("estimated_kp"))
        data["kp_time"] = last.get("time_tag")
        data["updated"] = last.get("time_tag")
    m = _rtsw_latest(take("mag"), ("bz_gsm", "bt"))
    if m:
        data.update(bz=_num(m["bz_gsm"]), bt=_num(m["bt"]), mag_time=m["time_tag"])
    w = _rtsw_latest(take("wind"), ("proton_speed", "proton_density"))
    if w:
        data.update(speed=_num(w["proton_speed"]), density=_num(w["proton_density"]), wind_time=w["time_tag"])
    xr = take("xray")
    if xr:
        long_ = [r for r in xr if r.get("energy") == "0.1-0.8nm" and r.get("flux")]
        if long_:
            last = max(long_, key=lambda r: r["time_tag"])
            data["xray_flux"] = last["flux"]
            data["xray"] = xray_class(last["flux"])
            data["xray_time"] = last["time_tag"]
    fl = take("flares")
    if fl is not None:
        data["flares"] = [
            {"begin": f.get("begin_time"), "max": f.get("max_time"), "end": f.get("end_time"),
             "cls": f.get("max_class") or f.get("begin_class")}
            for f in fl if (f.get("max_class") or f.get("begin_class"))
        ]
    sc = take("scales")
    if sc and isinstance(sc, dict) and "0" in sc:
        now = sc["0"]
        data["scales"] = {k: {"scale": _num((now.get(k) or {}).get("Scale")) or 0,
                              "text": (now.get(k) or {}).get("Text") or ""} for k in ("R", "S", "G")}
    if errors:
        data["errors"] = errors
        log.info("météo spatiale NOAA partielle : %s", "; ".join(errors))
    if len(errors) == len(URLS):
        raise ConnectionError("NOAA SWPC injoignable")
    return data


def get_spacewx():
    """Dernières données (ou None si NOAA est injoignable). Bloquant : appeler via to_thread."""
    now = time.time()
    if _cache["data"] is None or now - _cache["t"] > CACHE_SECONDS:
        try:
            _cache["data"] = _fetch()
            _cache["t"] = now
        except Exception as exc:
            log.warning("météo spatiale : %s", exc)
            _cache["t"] = now - CACHE_SECONDS + 120     # nouvel essai dans 2 min
    return _cache["data"]
