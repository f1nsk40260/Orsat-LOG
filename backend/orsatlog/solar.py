"""Données solaires (SFI, A, K...) depuis hamqsl.com, mises en cache 15 min."""

import time
import urllib.request
import xml.etree.ElementTree as ET

SOURCE_URL = "https://www.hamqsl.com/solarxml.php"
CACHE_SECONDS = 15 * 60

_cache = {"t": 0.0, "data": None}


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _fetch():
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "ORSAT-LOG"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        root = ET.fromstring(resp.read())
    sd = root.find("solardata")
    if sd is None:
        raise ValueError("réponse solaire inattendue")
    get = lambda tag: (sd.findtext(tag) or "").strip()
    conditions = [
        {"band": b.get("name"), "time": b.get("time"), "state": (b.text or "").strip()}
        for b in sd.findall("calculatedconditions/band")
    ]
    return {
        "updated": get("updated"),
        "sfi": _num(get("solarflux")),
        "a_index": _num(get("aindex")),
        "k_index": _num(get("kindex")),
        "sunspots": _num(get("sunspots")),
        "xray": get("xray"),
        "geomagfield": get("geomagfield"),
        "conditions": conditions,
    }


def get_solar():
    """Retourne les dernières données (ou None si indisponibles). Bloquant : appeler via to_thread."""
    now = time.time()
    if _cache["data"] is None or now - _cache["t"] > CACHE_SECONDS:
        try:
            _cache["data"] = _fetch()
            _cache["t"] = now
        except Exception:
            # on garde l'ancienne valeur, nouvel essai dans 2 min
            _cache["t"] = now - CACHE_SECONDS + 120
    return _cache["data"]
