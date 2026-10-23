"""Portée par bande : courte, moyenne ou longue distance, et absorption de jour (estimation).

Plafond — MUF mesurée (ionosondes KC2G), pour cinq tranches de distance (saut représentatif) :
  0–100 km      saut de 100 km  (NVIS, quasi vertical : MUF ≈ foF2), réflexion à 50 km
  100–300 km    saut de 200 km  (NVIS), réflexion à 100 km
  300–900 km    saut de 600 km,  réflexion à 300 km
  900–2500 km   saut de 1500 km, réflexion à 750 km
  ≥ 2500 km     saut de 3000 km, réflexion à 1500 km (au-delà : plusieurs sauts)
L'onde de sol (quelques dizaines de km sur les bandes basses) n'est pas calculée.
MUF(saut) = loi de la sécante étalonnée sur la MUF(3000) de l'ionogramme (ionosonde.mufd_estimate).

Plancher — absorption dans la couche D (MODÈLE, pas une mesure) : formule de George & Bradley
(reprise par l'UIT-R P.533) pour un saut :
    A (dB) = 677,2 · sec(i) · I / ((f + fH)^1,98 + 10,2)
    I = (1 + 0,0037 R) · (cos 0,881 χ)^1,3   ;  χ = angle zénithal du Soleil au point de réflexion,
    R = nombre de taches déduit du SFI, fH = 1,2 MHz (gyrofréquence), i = incidence à 100 km.
La nuit (Soleil sous l'horizon), l'absorption est négligée. Seuils : < 20 dB normale,
20–40 dB affaiblie, > 40 dB absorbée (ordre de grandeur d'une station de 100 W).
"""

import math
from datetime import datetime, timezone

from .ionosonde import mufd_estimate

EARTH_R = 6371.0
F_H = 1.2
D_LAYER_KM = 100.0
WEAK_DB, ABSORBED_DB = 20.0, 40.0
# (clé, saut km, distance du point de réflexion km, borne basse de la tranche km)
RANGES = [("d100", 100, 50, 0), ("d300", 200, 100, 100), ("d900", 600, 300, 300),
          ("d2500", 1500, 750, 900), ("dx", 3000, 1500, 2500)]
RANK = {"open": 3, "edge": 2, "weak": 1, "absorbed": 0, "closed": 0, None: -1}


def ssn_from_sfi(sfi):
    """SFI = 63,7 + 0,728 R + 0,00089 R²  ->  R."""
    if not sfi:
        return 80.0
    a, b, c = 0.00089, 0.728, 63.7 - sfi
    disc = b * b - 4 * a * c
    return max(0.0, (-b + math.sqrt(disc)) / (2 * a)) if disc > 0 else 0.0


def solar_zenith(lat, lon, when):
    """Angle zénithal du Soleil (degrés), formule usuelle (déclinaison + équation du temps)."""
    doy = when.timetuple().tm_yday
    g = 2 * math.pi / 365 * (doy - 1 + (when.hour - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    minutes = when.hour * 60 + when.minute + eqt + 4 * lon
    ha = math.radians(minutes / 4 - 180)
    la = math.radians(lat)
    cz = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    return math.degrees(math.acos(max(-1.0, min(1.0, cz))))


def _sec_d(hop_km):
    """sec(i) à la traversée de la couche D pour un saut de cette longueur (Terre sphérique)."""
    theta = min(hop_km, 3800) / (2 * EARTH_R)
    h_f = 300.0
    elev = math.atan((math.cos(theta) - EARTH_R / (EARTH_R + h_f)) / math.sin(theta))
    sin_i = EARTH_R * math.cos(elev) / (EARTH_R + D_LAYER_KM)
    return 1 / math.sqrt(max(1e-4, 1 - sin_i ** 2))


def absorption_db(freq, hop_km, chi_deg, ssn):
    if chi_deg >= 90:
        return 0.0
    i = (1 + 0.0037 * ssn) * math.cos(math.radians(0.881 * chi_deg)) ** 1.3
    return 677.2 * _sec_d(hop_km) * i / ((freq + F_H) ** 1.98 + 10.2)


def _cell(freq, muf, db):
    if muf is None:
        return None
    s = "open" if freq <= 0.85 * muf else "edge" if freq <= muf else "closed"
    if s != "closed" and db is not None:
        if db > ABSORBED_DB:
            s = "absorbed"
        elif db > WEAK_DB and s == "open":
            s = "weak"
    return s


# ---------- calcul unique : grille azimut × distance, dont dérivent la carte ET le tableau ----------
MAP_AZ_STEP = 5                                                       # degrés (tombe sur N, NE, E…)
# bords extérieurs des anneaux, km : fins près du QTH pour le zoom (100/300/900/2500 inclus)
MAP_RINGS = list(range(25, 301, 25)) + list(range(350, 1001, 50)) + list(range(1250, 5001, 250))
MAX_HOP_KM = 3500
CODE = {"open": "o", "edge": "e", "weak": "w", "absorbed": "a", "closed": "c", None: "-"}
STATE_OF = {v: k for k, v in CODE.items()}


def build_grid(home, interp, destination, when=None):
    """Pour chaque azimut et chaque anneau : MUF du trajet (distance réelle = milieu de l'anneau).
    Saut unique jusqu'à 3500 km ; au-delà n sauts égaux, MUF = la plus basse des deux réflexions
    extrêmes, absorption cumulée sur les n sauts."""
    when = when or datetime.now(timezone.utc)
    cache = {}

    def iono(pt):
        k = (round(pt[0], 1), round(pt[1], 1))
        if k not in cache:
            cache[k] = (interp(pt, "fof2")[0], interp(pt, "mufd")[0], interp(pt, "hmf2")[0],
                        solar_zenith(pt[0], pt[1], when))
        return cache[k]

    inner = [0] + MAP_RINGS[:-1]
    cells = []
    for az in range(0, 360, MAP_AZ_STEP):
        for lo, hi in zip(inner, MAP_RINGS):
            d = (lo + hi) / 2
            n = math.ceil(d / MAX_HOP_KM)
            hop = d / n
            ends = [hop / 2] if n == 1 else [hop / 2, d - hop / 2]
            mufs, chis = [], []
            for x in ends:
                fof2, m3000, hm, chi = iono(destination(home, float(az), x))
                mufs.append(mufd_estimate(fof2, m3000, hop, hm) if fof2 and m3000 else None)
                chis.append(chi)
            cells.append({"az": az, "lo": lo, "hi": hi, "hop": hop, "n": n, "chis": chis,
                          "muf": None if any(m is None for m in mufs) else min(mufs)})
    return {"cells": cells, "when": when}


def _codes(grid, f, ssn):
    out = []
    for c in grid["cells"]:
        db = sum(absorption_db(f, c["hop"], x, ssn) for x in c["chis"]) * c["n"] / len(c["chis"]) if c["muf"] else None
        out.append((CODE[_cell(f, c["muf"], db)], db))
    return out


def skip_map(grid, bands, sfi):
    ssn = ssn_from_sfi(sfi)
    return {"az_step": MAP_AZ_STEP, "rings": MAP_RINGS,
            "bands": {b: "".join(code for code, _ in _codes(grid, f, ssn)) for b, f in bands},
            "muf": [None if c["muf"] is None else round(c["muf"], 1) for c in grid["cells"]],
            "when": grid["when"].strftime("%H:%M UTC"), "ssn": round(ssn)}


def compute(grid, dirs, bands, sfi):
    """Portée par bande, lue dans la même grille que la carte : pour chaque direction et chaque
    tranche, l'état qui couvre la plus grande part de la tranche ; zone de silence = bord intérieur
    du premier anneau ouvert, si tout ce qui précède est fermé (MUF dépassée)."""
    ssn = ssn_from_sfi(sfi)
    n = len(MAP_RINGS)
    per_dir = {}
    for name, az in dirs:
        a0 = (az // MAP_AZ_STEP) * n
        rows = []
        for band, f in bands:
            codes = _codes({"cells": grid["cells"][a0:a0 + n]}, f, ssn)
            cells = grid["cells"][a0:a0 + n]
            row = {"band": band}
            for key, _hop, _refl, lo in RANGES:
                hi = next((r[3] for r in RANGES if r[3] > lo), MAP_RINGS[-1])
                idx = [i for i, c in enumerate(cells) if c["lo"] >= lo and c["hi"] <= hi]
                cover = {}
                for i in idx:
                    cover[codes[i][0]] = cover.get(codes[i][0], 0) + cells[i]["hi"] - cells[i]["lo"]
                known = {k: v for k, v in cover.items() if k != "-"}      # sans mesure : ignoré s'il y a mieux
                main = max(known, key=lambda k: (known[k], RANK[STATE_OF[k]])) if known else "-"
                mid = idx[len(idx) // 2] if idx else None
                row[key] = {"state": STATE_OF[main],
                            "muf": round(cells[mid]["muf"], 1) if mid is not None and cells[mid]["muf"] else None,
                            "db": round(codes[mid][1]) if mid is not None and codes[mid][1] is not None else None}
            first = next((i for i, (c, _) in enumerate(codes) if c in "oew"), None)
            row["skip"] = (cells[first]["lo"] if first and all(c == "c" for c, _ in codes[:first]) else None)
            row["_near_open"] = first == 0
            rows.append(row)
        per_dir[name] = rows
    best = []
    for i, (band, _f) in enumerate(bands):
        row = {"band": band}
        for key, *_ in RANGES:
            r, _m, nm = max((RANK[per_dir[d][i][key]["state"]], per_dir[d][i][key]["muf"] or 0, d) for d, _ in dirs)
            row[key] = {**per_dir[nm][i][key], "dir": nm if r >= 0 else None}
        # silence « toutes directions » : plus petite zone de silence, sauf si une direction passe dès le QTH
        skips = [per_dir[d][i]["skip"] for d, _ in dirs if per_dir[d][i]["skip"] is not None]
        near = any(per_dir[d][i]["_near_open"] for d, _ in dirs)
        row["skip"] = min(skips) if skips and not near else None
        best.append(row)
    return {"best": best, "dirs": per_dir, "ssn": round(ssn),
            "thresholds_db": [WEAK_DB, ABSORBED_DB], "when": grid["when"].strftime("%H:%M UTC")}
