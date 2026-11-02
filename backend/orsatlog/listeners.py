"""Nombre d'auditeurs en ligne sur le WebSDR ORSAT, lu côté serveur.

Le carnet reste abonné au flux d'événements de PhantomSDR-ORSAT (ws://127.0.0.1:<port>/events, même
port que la chute d'eau, voir snr.waterfall_candidates). Ce flux envoie à l'ouverture puis à chaque
changement (au moins toutes les 10 s) un JSON {waterfall_clients, signal_clients, ...}.
Auditeurs = signal_clients (personnes qui écoutent le son) : la mesure SNR du carnet, qui n'ouvre que
la chute d'eau, n'y est pas comptée. Indépendant de la page reliée : le compte est connu même quand
l'opérateur n'a pas le WebSDR ouvert.
"""

import asyncio
import json
import logging

from . import snr

log = logging.getLogger("orsatlog")

RETRY_S = 30


def _candidates():
    return [u.rsplit("/waterfall", 1)[0] + "/events" for u in snr.waterfall_candidates()]


_state = {"good": None}


async def _follow(url, on_count):
    import websockets
    async with websockets.connect(url, max_size=None, open_timeout=10) as ws:
        _state["good"] = url
        log.info("auditeurs : abonné à %s", url)
        while True:
            msg = await asyncio.wait_for(ws.recv(), 60)      # silence > 60 s : flux mort, on se reconnecte
            if not isinstance(msg, str) or not msg.strip():
                continue
            try:
                d = json.loads(msg)
            except ValueError:
                continue
            if isinstance(d, dict) and "signal_clients" in d:
                on_count(int(d["signal_clients"]))


async def loop(on_count):
    """on_count(n) : n auditeurs, ou None si le WebSDR ne répond pas."""
    while True:
        good = _state["good"]
        urls = ([good] if good else []) + [u for u in _candidates() if u != good]
        for url in urls:
            try:
                await _follow(url, on_count)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("auditeurs : %s : %s", url, exc)
        on_count(None)
        await asyncio.sleep(RETRY_S)
