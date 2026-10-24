"""Conseil de partenaire pour la réception en diversité du WebSDR (PhantomSDR-ORSAT).

Un bon partenaire entend LES MÊMES ZONES qu'ORSAT, mais par un autre chemin. Pour chaque bande :
  - zones entendues par ORSAT : carte des zones de silence depuis son locator (propagation seule,
    mêmes ionosondes KC2G que le reste du carnet), cases jusqu'à 3000 km ;
  - pour chaque case, le partenaire l'entend-il ? même calcul depuis SON locator, case lue à la
    distance et à l'azimut de ce point vu de chez lui ;
  - recouvrement = part de la zone entendue par ORSAT (pondérée par la surface) que le partenaire
    entend aussi ; × facteur d'éloignement (moins de 100 km : évanouissements liés, inutile ;
    300 km et plus : pleinement indépendants).
La propagation seule est comptée des deux côtés (l'antenne du partenaire est inconnue).

Disponibilité : chaque partenaire est sondé toutes les 10 min (page d'accueil ; /status pour un KiwiSDR).

Calcul ENTIÈREMENT SÉPARÉ de l'indice de performance d'ORSAT : rien n'est écrit en base, rien n'est
réutilisé par reach.performance_index ni par la mesure SNR.
"""

import asyncio
import json
import logging
import math
import re
import ssl
import time
import urllib.error
import urllib.request

from . import auth, geo, kc2g, reach

log = logging.getLogger("orsatlog")

# Liste par défaut, tant que l'opérateur n'a rien enregistré dans le panneau admin de PhantomSDR-ORSAT
DEFAULT = [
    {"id": "rigi", "name": "NovaSDR Rigi", "type": "phantom", "addr": "https://novasdr.rigiremote.ch/", "locator": "JN47FB"},
    {"id": "heppen", "name": "WebSDR Heppen", "type": "uber", "addr": "https://websdr.heppen.be/", "locator": "JO21OC"},
    {"id": "kiwi21051", "name": "KiwiSDR 21051", "type": "kiwi", "addr": "http://21051.proxy2.kiwisdr.com:8073/", "locator": ""},
]
MAX_KM = 3000                     # zones retenues : là où se trouvent les stations qu'on écoute
HEAR = {"o": 1.0, "e": 0.6, "w": 0.4, "a": 0.0, "c": 0.0}
GOOD, FAIR = 55, 30               # conseillé / possible
CHECK_S = 10 * 60
CACHE_S = 10 * 60

health = {}                       # id -> {"online": bool, "msg": str, "ts": float}
_cache = {"t": 0.0, "key": None, "data": None}


def load():
    """Partenaires actifs, lus dans diversity_partners.json de PhantomSDR-ORSAT (même dossier
    qu'admin_config.json) ; liste par défaut si absent."""
    try:
        d = json.loads((auth.ADMIN_CONFIG.parent / "diversity_partners.json").read_text(encoding="utf-8"))
        rows = [p for p in d.get("partners", []) if p.get("enabled", True) and p.get("addr")]
    except (OSError, ValueError, AttributeError):
        rows = DEFAULT
    return [{"id": str(p.get("id")), "name": p.get("name", ""), "type": p.get("type", ""),
             "addr": p.get("addr", ""), "locator": str(p.get("locator") or "").upper()} for p in rows]


def _bearing_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dl = lo2 - lo1
    x = math.sin(dl) * math.cos(la2)
    y = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    brg = (math.degrees(math.atan2(x, y)) + 360) % 360
    c = math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(dl)
    return brg, kc2g.EARTH_R * math.acos(max(-1.0, min(1.0, c)))


def _lookup(codes, rings, step, brg, km):
    """Code de la case de la carte (azimut extérieur, anneaux intérieurs) qui contient ce point."""
    k = next((i for i, r in enumerate(rings) if km <= r), None)
    if k is None:
        return "-"
    a = int(round(brg / step)) % int(360 / step)
    return codes[a * len(rings) + k]


def overlap(home, hmap, phome, pmap):
    """{bande: recouvrement 0..1 ou None (bande fermée à ORSAT ou sans mesure)}."""
    rings, step = hmap["rings"], hmap["az_step"]
    inner = [0] + rings[:-1]
    n = len(rings)
    pts = []                                              # points des cases d'ORSAT vus du partenaire
    for i in range(len(hmap["muf"])):
        k = i % n
        lo, hi = inner[k], rings[k]
        if lo >= MAX_KM:
            pts.append(None)
            continue
        pt = kc2g.destination(home, float((i // n) * step), (lo + hi) / 2)
        pts.append((hi * hi - lo * lo, _bearing_km(phome, pt)))
    out = {}
    for band, codes in hmap["bands"].items():
        pcodes = pmap["bands"].get(band, "")
        tot = acc = 0.0
        for code, p in zip(codes, pts):
            if p is None or code not in HEAR:
                continue
            o = HEAR[code]
            if o == 0:
                continue
            pc = _lookup(pcodes, pmap["rings"], pmap["az_step"], *p[1])
            if pc not in HEAR:
                continue                                  # pas de mesure de ce côté : case écartée
            tot += p[0] * o
            acc += p[0] * o * HEAR[pc]
        out[band] = None if tot == 0 else acc / tot
    return out


def compute(orsat_locator, sfi):
    """Bloquant (appeler via to_thread). Mis en cache 10 min."""
    parts = load()
    key = (orsat_locator, tuple((p["id"], p["locator"]) for p in parts), kc2g._cache["t"])
    if _cache["data"] and _cache["key"] == key and time.time() - _cache["t"] < CACHE_S:
        return _attach_health(_cache["data"])
    hmap = kc2g.skip_map(orsat_locator, sfi)
    if not hmap.get("ok"):
        return hmap
    home = hmap["home"]
    res = {}
    best = {}
    for p in parts:
        r = {"name": p["name"], "dist_km": None, "bands": {}}
        if geo.valid_locator(p["locator"]):
            pmap = kc2g.skip_map(p["locator"], sfi)
            if pmap.get("ok"):
                brg, d = _bearing_km(home, pmap["home"])
                r["dist_km"] = round(d)
                far = max(0.0, min(1.0, (d - 100) / 200))
                for band, v in overlap(home, hmap, pmap["home"], pmap).items():
                    r["bands"][band] = None if v is None else round(100 * v * far)
        res[p["id"]] = r
    for band, _f in kc2g.BANDS:
        sc = [(r["bands"].get(band), pid) for pid, r in res.items() if r["bands"].get(band) is not None]
        if sc:
            s, pid = max(sc)
            if s >= FAIR:
                best[band] = pid
    data = {"ok": True, "when": hmap["when"], "good": GOOD, "fair": FAIR, "partners": res, "best": best}
    _cache.update(t=time.time(), key=key, data=data)
    return _attach_health(data)


def _attach_health(data):
    out = dict(data)
    out["partners"] = {pid: dict(r, online=health.get(pid, {}).get("online"), status=health.get(pid, {}).get("msg", ""))
                       for pid, r in data["partners"].items()}
    # un partenaire hors ligne n'est jamais conseillé
    out["best"] = {b: pid for b, pid in data["best"].items() if health.get(pid, {}).get("online") is not False}
    return out


def check(p):
    """Le partenaire répond-il ? True / False et un mot d'explication."""
    m = re.match(r"^(https?|wss?)://([^/?#]+)", p["addr"].strip(), re.I)
    if not m:
        return False, "adresse invalide"
    scheme = {"ws": "http", "wss": "https"}.get(m.group(1).lower(), m.group(1).lower())
    url = f"{scheme}://{m.group(2)}/" + ("status" if p["type"] == "kiwi" else "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ORSAT-diversity-check"})
        with urllib.request.urlopen(req, timeout=10, context=ssl.create_default_context()) as r:
            body = r.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return (e.code < 500 and e.code != 404), f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)[:120]
    if p["type"] == "kiwi" and "offline=yes" in body:
        return False, "se déclare hors ligne"
    return True, "en ligne"


async def health_loop():
    await asyncio.sleep(20)
    while True:
        for p in load():
            try:
                ok, msg = await asyncio.to_thread(check, p)
            except Exception as exc:
                ok, msg = False, str(exc)[:120]
            health[p["id"]] = {"online": ok, "msg": msg, "ts": time.time()}
        await asyncio.sleep(CHECK_S)
