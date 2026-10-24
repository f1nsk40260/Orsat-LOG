"""Mesure réelle de la réception d'ORSAT : bruit de fond, signaux et SNR, bande par bande.

Le carnet se connecte à la chute d'eau du WebSDR (ws://127.0.0.1:<port>/waterfall, port lu dans le
config.toml de PhantomSDR-ORSAT, à côté d'admin_config.json), comme un auditeur sans le son. Toutes les
5 min, pour chaque bande amateur, il demande cette portion du spectre (commande « window »), lit ~3 s de
lignes et calcule :
  - le bruit de fond : 20e centile du spectre moyen (dB) ;
  - les signaux : groupes de cases dépassant le bruit de 10 dB ou plus ; le SNR du meilleur.
Format des lignes (PhantomSDR, compression zstd) : flux zstd → CBOR {frame_num, l, r, data}, data = int8
en dB (20·log10(puissance) + 127) : un SNR se lit par simple soustraction. Aucun décodage, aucun son :
la charge est celle d'un auditeur de plus avec la chute d'eau ouverte, quelques secondes toutes les 5 min.
"""

import asyncio
import json
import logging
import math
import time
import tomllib
from pathlib import Path

from . import auth

log = logging.getLogger("orsatlog")

BANDS = [("160m", 1810, 2000), ("80m", 3500, 3800), ("60m", 5351, 5367), ("40m", 7000, 7200),
         ("30m", 10100, 10150), ("20m", 14000, 14350), ("17m", 18068, 18168), ("15m", 21000, 21450),
         ("12m", 24890, 24990), ("10m", 28000, 29700)]
DWELL_S = 3.0                 # temps d'écoute par bande
SIGNAL_DB = 10.0              # un signal = au moins 10 dB au-dessus du bruit
PERIOD_S = 5 * 60

state = {"last": None, "error": "", "at": None, "url": ""}


def waterfall_url():
    """ws://127.0.0.1:<port>/waterfall, port du [server] de PhantomSDR (config.toml près d'admin_config.json)."""
    port = 9001
    try:
        cfg = tomllib.loads((auth.ADMIN_CONFIG.parent / "config.toml").read_text())
        port = int(cfg.get("server", {}).get("port", port))
    except Exception:
        pass
    return f"ws://127.0.0.1:{port}/waterfall"


def analyse(rows):
    """rows : lignes de dB (même longueur) -> bruit, nombre de signaux, meilleur SNR, occupation %."""
    n = min(len(r) for r in rows)
    if n < 8:
        return None
    mean = []
    for i in range(n):                      # moyenne en puissance sur les lignes, puis retour en dB
        p = sum(10 ** (r[i] / 10) for r in rows) / len(rows)
        mean.append(10 * math.log10(p))
    s = sorted(mean)
    floor = s[int(0.2 * (n - 1))]
    above = [v - floor >= SIGNAL_DB for v in mean]
    groups, best, i = 0, 0.0, 0
    while i < n:
        if above[i]:
            j = i
            while j + 1 < n and (above[j + 1] or (j + 2 < n and above[j + 2])):   # trou d'une case toléré
                j += 1
            groups += 1
            best = max(best, max(mean[i:j + 1]) - floor)
            i = j + 1
        else:
            i += 1
    occ = round(100 * sum(1 for v in mean if v - floor >= 6) / n)
    return {"floor": round(floor - 127, 1), "signals": groups, "best_snr": round(best, 1), "occupancy": occ,
            "bins": n}


async def measure(url=None):
    """Un passage sur toutes les bandes. Renvoie {bande: résultat} (bandes hors du spectre ignorées)."""
    import cbor2
    import websockets
    import zstandard

    url = url or waterfall_url()
    state["url"] = url
    out = {}
    async with websockets.connect(url, max_size=None, open_timeout=10, ping_interval=None) as ws:
        info = None
        t0 = time.monotonic()
        while info is None and time.monotonic() - t0 < 10:
            msg = await asyncio.wait_for(ws.recv(), 10)
            if isinstance(msg, str):
                try:
                    d = json.loads(msg)
                except ValueError:
                    continue
                if "fft_result_size" in d:
                    info = d
        if not info:
            raise RuntimeError("le WebSDR n'a pas envoyé ses paramètres")
        if info.get("waterfall_compression", "zstd") != "zstd":
            raise RuntimeError(f"compression {info.get('waterfall_compression')} non prise en charge")
        size, base, bw = int(info["fft_result_size"]), float(info["basefreq"]), float(info["total_bandwidth"])
        dec = zstandard.ZstdDecompressor().decompressobj()
        for band, lo, hi in BANDS:
            l = int((lo * 1e3 - base) / bw * size)
            r = int((hi * 1e3 - base) / bw * size)
            if l < 0 or r > size or r - l < 4:
                continue
            await ws.send(json.dumps({"cmd": "window", "l": l, "r": r}))
            rows = []
            end = time.monotonic() + DWELL_S
            while time.monotonic() < end:
                try:
                    msg = await asyncio.wait_for(ws.recv(), max(0.1, end - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                if not isinstance(msg, (bytes, bytearray)):
                    continue
                raw = dec.decompress(msg)
                if not raw:
                    continue
                try:
                    pkt = cbor2.loads(raw)
                except Exception:
                    continue
                # lignes de l'ancienne fenêtre encore en route : ignorées
                # (l renvoyé = début arrondi au niveau de réduction : tolérance large, les bandes sont éloignées)
                if abs(int(pkt.get("l", -1)) - l) > max((r - l) * 0.25, 64) or not pkt.get("data"):
                    continue
                rows.append([b - 256 if b > 127 else b for b in pkt["data"]])
            if len(rows) >= 3:
                res = analyse(rows[1:])            # la première ligne peut être incomplète
                if res:
                    out[band] = res
    return out


async def loop(on_result):
    """Mesure toutes les 5 min ; on_result(dict) enregistre. Silencieux si le WebSDR ne répond pas."""
    await asyncio.sleep(45)
    while True:
        try:
            res = await measure()
            state.update(last=res, error="", at=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), ts=time.time())
            if res:
                await on_result(res)
        except Exception as exc:
            state["error"] = str(exc)
            log.info("mesure SNR du WebSDR : %s", exc)
        await asyncio.sleep(PERIOD_S)
