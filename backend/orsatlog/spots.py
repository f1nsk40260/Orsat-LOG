"""Stations FT8 décodées par la veille cyclique du WebSDR (autorun de PhantomSDR-ORSAT).

Le démon écrit autorun-spots/AAAAMMJJ-HH.jsonl (une ligne par station : t, mode, band, call, grid,
snr, f) dans le dossier de PhantomSDR-ORSAT. Le carnet les relit en lecture seule pour le bandeau
« Indice de performance » : seules les stations dont le locator est valide sont gardées, avec leur
distance au récepteur. Rien n'entre dans le carnet QSO ni dans le journal SWL (donc rien vers QRZ) ;
le démon efface lui-même les fichiers de plus de 3 jours.
"""

import json
import time
from pathlib import Path

from . import auth, geo


def spool_dir():
    return Path(auth.ADMIN_CONFIG).parent / "autorun-spots"


def recent(home_locator, hours=3):
    """{bande: {indicatif: (distance_km, snr)}} des stations localisées décodées depuis `hours` h."""
    if not geo.valid_locator(home_locator or ""):
        return {}
    since = time.time() - hours * 3600
    out = {}
    d = spool_dir()
    for h in range(hours + 1):                      # un fichier par heure UTC
        name = time.strftime("%Y%m%d-%H.jsonl", time.gmtime(time.time() - h * 3600))
        try:
            lines = (d / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                s = json.loads(line)
            except ValueError:
                continue
            grid, call, band = (s.get("grid") or "").upper(), (s.get("call") or "").upper(), s.get("band") or ""
            if s.get("t", 0) < since or not call or not band or not geo.valid_locator(grid):
                continue
            try:
                km, _ = geo.distance_bearing(home_locator, grid)
            except ValueError:
                continue
            out.setdefault(band, {})[call] = (km, s.get("snr"))
    return out
