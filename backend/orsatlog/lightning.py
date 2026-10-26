"""Foudre en temps réel (réseau Blitzortung.org) : orages proches et lointains, pour le QRN des bandes basses.

Le carnet écoute le flux public de la carte Blitzortung (WebSocket wss://wsN.blitzortung.org, message
d'ouverture {"a":111}). Chaque message est un impact, en JSON compressé LZW (même décodage que la carte).
Rien de brut n'est stocké : les impacts sont comptés à la volée par tranche de 5 min
  - total mondial (le bruit des orages tropicaux remonte la nuit sur 160/80 m) ;
  - à moins de 500 km et à moins de 2000 km de la station ;
  - en 8 secteurs (N, NE, E...) pour les moins de 2000 km ;
  - l'impact le plus proche (distance, azimut).
Les impacts des 30 dernières minutes à moins de 3000 km restent en mémoire pour la carte et le bandeau.
Données Blitzortung : usage privé et non commercial, source à citer (« Blitzortung.org »).
"""

import asyncio
import json
import logging
import math
import time
from collections import deque

log = logging.getLogger("orsatlog.lightning")

SERVERS = ["wss://ws1.blitzortung.org/", "wss://ws7.blitzortung.org/", "wss://ws8.blitzortung.org/"]
ORIGIN = "https://map.blitzortung.org"
BUCKET_S = 5 * 60
RECENT_S = 30 * 60
RECENT_KM = 3000
RECENT_MAX = 20000
NEAR_KM, FAR_KM = 500, 2000
SECTORS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]

state = {"enabled": True, "connected": False, "server": "", "error": "", "last_ts": None, "since": None}
_recent = deque(maxlen=RECENT_MAX)        # (ts, lat, lon, km, az)
_world = deque()                          # horodatages de tous les impacts des 15 dernières minutes (comptage)
_bucket = None


def decode(data):
    """Décodage LZW du flux de la carte Blitzortung (reprise fidèle de sa fonction JavaScript)."""
    if not data:
        return ""
    dico, out = {}, []
    c = f = data[0]
    out.append(c)
    code = 256
    for ch in data[1:]:
        n = ord(ch)
        if n < 256:
            a = ch
        else:
            a = dico.get(n, f + c)
        out.append(a)
        c = a[0]
        dico[code] = f + c
        code += 1
        f = a
    return "".join(out)


def _dist_az(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return km, (math.degrees(math.atan2(y, x)) + 360) % 360


def _sector(az):
    return int(((az + 22.5) % 360) // 45)


def _new_bucket(start):
    return {"start": start, "total": 0, "n500": 0, "n2000": 0, "sectors": [0] * 8, "near_km": None, "near_az": None}


def _add(lat, lon, center, now):
    """Compte un impact dans la tranche courante et la mémoire récente."""
    global _bucket
    _world.append(now)
    _bucket["total"] += 1
    if not center:
        return
    km, az = _dist_az(center[0], center[1], lat, lon)
    if km <= FAR_KM:
        _bucket["n2000"] += 1
        _bucket["sectors"][_sector(az)] += 1
        if km <= NEAR_KM:
            _bucket["n500"] += 1
    if _bucket["near_km"] is None or km < _bucket["near_km"]:
        _bucket["near_km"], _bucket["near_az"] = round(km), round(az)
    if km <= RECENT_KM:
        _recent.append((now, round(lat, 2), round(lon, 2), round(km), round(az)))


async def _connect(url):
    import websockets
    kw = dict(max_size=None, open_timeout=15, ping_interval=30, ping_timeout=30)
    try:
        return await websockets.connect(url, additional_headers={"Origin": ORIGIN}, **kw)
    except TypeError:                                   # websockets < 14
        return await websockets.connect(url, extra_headers={"Origin": ORIGIN}, **kw)


async def loop(get_center, on_bucket, is_enabled):
    """Écoute permanente. get_center() -> (lat, lon) ou None ; on_bucket(dict) enregistre une tranche
    de 5 min terminée ; is_enabled() lit le réglage (coupure possible sans redémarrer)."""
    global _bucket
    await asyncio.sleep(20)
    _bucket = _new_bucket(int(time.time()) // BUCKET_S * BUCKET_S)
    turn = 0
    while True:
        if not is_enabled():
            state.update(enabled=False, connected=False)
            await asyncio.sleep(60)
            continue
        state["enabled"] = True
        url = SERVERS[turn % len(SERVERS)]
        turn += 1
        try:
            ws = await _connect(url)
            async with ws:
                await ws.send('{"a":111}')
                state.update(connected=True, server=url, error="", since=time.time())
                log.info("Blitzortung : relié à %s", url)
                while is_enabled():
                    msg = await asyncio.wait_for(ws.recv(), 120)   # plus rien depuis 2 min : serveur suivant
                    now = time.time()
                    await _roll(now, on_bucket)
                    try:
                        d = json.loads(decode(msg if isinstance(msg, str) else msg.decode("utf-8", "replace")))
                        lat, lon = float(d["lat"]), float(d["lon"])
                    except (ValueError, KeyError, TypeError):
                        continue
                    state["last_ts"] = now
                    _add(lat, lon, get_center(), now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.update(connected=False, error=f"{url} : {exc}")
            log.info("Blitzortung : %s", state["error"])
        state["connected"] = False
        await asyncio.sleep(10)


async def _roll(now, on_bucket):
    """Ferme la tranche de 5 min écoulée et l'enregistre."""
    global _bucket
    start = int(now) // BUCKET_S * BUCKET_S
    if start == _bucket["start"]:
        return
    done, _bucket = _bucket, _new_bucket(start)
    try:
        await on_bucket(done)
    except Exception as exc:
        log.warning("Blitzortung : enregistrement : %s", exc)


def live(window_s=15 * 60):
    """Résumé des 15 dernières minutes : comptages, secteurs, orage le plus proche, cellules pour la carte."""
    now = time.time()
    while _world and now - _world[0] > window_s:
        _world.popleft()
    while _recent and now - _recent[0][0] > RECENT_S:
        _recent.popleft()
    pts = [p for p in _recent if now - p[0] <= window_s]
    sectors = [0] * 8
    n500 = n2000 = 0
    nearest = None
    cells = {}
    for ts, lat, lon, km, az in pts:
        if km <= FAR_KM:
            n2000 += 1
            sectors[_sector(az)] += 1
            if km <= NEAR_KM:
                n500 += 1
        if nearest is None or km < nearest[0]:
            nearest = (km, az)
    # cellules orageuses (carré de 0,5°) sur 30 min, pour la carte
    for ts, lat, lon, km, az in _recent:
        k = (math.floor(lat * 2) / 2, math.floor(lon * 2) / 2)
        c = cells.setdefault(k, [0, 0])
        c[0] += 1
        c[1] = max(c[1], ts)
    return {
        "ok": True,
        "status": {k: state[k] for k in ("enabled", "connected", "server", "error")},
        "window_min": window_s // 60,
        "world": len(_world),
        "n500": n500, "n2000": n2000,
        "sectors": dict(zip(SECTORS, sectors)),
        "nearest": {"km": nearest[0], "az": nearest[1], "dir": SECTORS[_sector(nearest[1])]} if nearest else None,
        "cells": [{"lat": k[0] + 0.25, "lon": k[1] + 0.25, "n": v[0], "age_min": round((now - v[1]) / 60)}
                  for k, v in cells.items()],
        "last_strike_s": round(now - state["last_ts"]) if state["last_ts"] else None,
    }
