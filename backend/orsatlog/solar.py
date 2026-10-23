"""Indices solaires et géomagnétiques du jour, lus directement à la NOAA SWPC (plus d'intermédiaire).

  - json/f107_cm_flux.json                 SFI (flux à 10,7 cm, Penticton), 3 mesures par jour, du plus récent au plus ancien
  - products/noaa-planetary-k-index.json   Kp officiel par créneau de 3 h + « a_running » (indice a du créneau)
  - json/solar-cycle/swpc_observed_ssn.json nombre de taches observé, un par jour (gros fichier : lu une fois par jour)

A = moyenne des 8 derniers indices a (24 h glissantes). L'état des bandes n'est plus fourni :
la grille « Bandes ouvertes » (kc2g.py, ionosondes mesurées) le remplace.
Format renvoyé inchangé (sfi, a_index, k_index, sunspots, geomagfield, updated) : propagation et fiches QSO.
"""

import json
import logging
import time
import urllib.request

log = logging.getLogger("orsatlog")

BASE = "https://services.swpc.noaa.gov/"
SFI_URL = BASE + "json/f107_cm_flux.json"
KP_URL = BASE + "products/noaa-planetary-k-index.json"
SSN_URL = BASE + "json/solar-cycle/swpc_observed_ssn.json"
CACHE_SECONDS = 15 * 60
SSN_CACHE_SECONDS = 12 * 3600
SOURCE = "noaa"

_cache = {"t": 0.0, "data": None}
_ssn = {"t": 0.0, "value": None, "date": None}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ORSAT-LOG"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def geomag_text(k):
    """Résumé en clair de l'indice K (vocabulaire des échelles NOAA)."""
    if k is None:
        return ""
    if k < 3:
        return "calme"
    if k < 4:
        return "instable"
    if k < 5:
        return "actif"
    return f"tempête G{min(5, int(k) - 4)}"


def _sunspots():
    now = time.time()
    if _ssn["value"] is None or now - _ssn["t"] > SSN_CACHE_SECONDS:
        try:
            rows = [r for r in _get(SSN_URL) if r.get("swpc_ssn") is not None]
            last = max(rows, key=lambda r: r.get("Obsdate") or "")
            _ssn.update(t=now, value=_num(last["swpc_ssn"]), date=(last.get("Obsdate") or "")[:10])
        except Exception as exc:
            log.info("taches solaires NOAA : %s", exc)
            _ssn["t"] = now - SSN_CACHE_SECONDS + 1800      # nouvel essai dans 30 min
    return _ssn["value"]


def _fetch():
    sfi_rows = [r for r in _get(SFI_URL) if r.get("flux") is not None]
    sfi = max(sfi_rows, key=lambda r: r.get("time_tag") or "") if sfi_rows else None
    kp_rows = sorted((r for r in _get(KP_URL) if r.get("Kp") is not None), key=lambda r: r["time_tag"])
    if not kp_rows and not sfi:
        raise ValueError("réponse NOAA vide")
    k = _num(kp_rows[-1]["Kp"]) if kp_rows else None
    a_vals = [r["a_running"] for r in kp_rows[-8:] if r.get("a_running") is not None]
    times = [t for t in ((sfi or {}).get("time_tag"), kp_rows[-1]["time_tag"] if kp_rows else None) if t]
    return {
        "updated": max(times) if times else None,
        "sfi": round(_num(sfi["flux"])) if sfi else None,
        "a_index": round(sum(a_vals) / len(a_vals)) if a_vals else None,
        "k_index": round(k, 1) if k is not None else None,
        "k_time": kp_rows[-1]["time_tag"] if kp_rows else None,
        "sunspots": _sunspots(),
        "xray": None,                   # en direct dans la météo spatiale (spacewx.py)
        "geomagfield": geomag_text(k),
        "conditions": [],
    }


def get_solar():
    """Retourne les dernières données (ou None si indisponibles). Bloquant : appeler via to_thread."""
    now = time.time()
    if _cache["data"] is None or now - _cache["t"] > CACHE_SECONDS:
        try:
            _cache["data"] = _fetch()
            _cache["t"] = now
        except Exception as exc:
            log.warning("indices solaires NOAA : %s", exc)
            # on garde l'ancienne valeur, nouvel essai dans 2 min
            _cache["t"] = now - CACHE_SECONDS + 120
    return _cache["data"]
