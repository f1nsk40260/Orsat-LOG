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
from . import dlayer

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
            mufs, chis, pts = [], [], []
            for x in ends:
                pt = destination(home, float(az), x)
                fof2, m3000, hm, chi = iono(pt)
                mufs.append(mufd_estimate(fof2, m3000, hop, hm) if fof2 and m3000 else None)
                chis.append(chi)
                pts.append((round(pt[0], 1), round(pt[1], 1)))
            cells.append({"az": az, "lo": lo, "hi": hi, "hop": hop, "n": n, "chis": chis, "pts": pts,
                          "muf": None if any(m is None for m in mufs) else min(mufs)})
    return {"cells": cells, "when": when}


# ---------- absorption MESURÉE (dlayer.py) : éruption GOES et fmin des ionosondes ----------
_ctx = {"t": 0.0, "h0": None, "cls": None, "at": None, "fac": {}}


def _abs_ctx():
    """Éruption en cours et facteurs fmin, relus au plus une fois par minute."""
    import time as _t
    if _t.time() - _ctx["t"] > 60:
        try:
            h0, cls = dlayer.haf0()
        except Exception:
            h0, cls = None, None
        if dlayer.state["at"] != _ctx["at"]:
            _ctx["fac"] = {}
        _ctx.update(t=_t.time(), h0=h0, cls=cls, at=dlayer.state["at"])
    return _ctx


def _factor(pt):
    f = _ctx["fac"].get(pt)
    if f is None:
        f = _ctx["fac"][pt] = dlayer.factor_at(pt)
    return f


def dlayer_info():
    """Ce qui a corrigé le modèle (affiché dans le carnet)."""
    ctx = _abs_ctx()
    facs = [st for st in dlayer.state["stations"].values() if st.get("factor") is not None]
    return {"swf_class": ctx["cls"] if ctx["h0"] else None, "haf_mhz": round(ctx["h0"], 1) if ctx["h0"] else None,
            "fmin_stations": len(facs), "fmin_max": max((st["factor"] for st in facs), default=None)}


def _codes(grid, f, ssn):
    ctx = _abs_ctx()
    out = []
    for c in grid["cells"]:
        pts = c.get("pts") or [None] * len(c["chis"])
        tot, measured = 0.0, False
        for x, pt in zip(c["chis"], pts):
            fac = _factor(pt) if pt else 1.0
            swf = 2 * dlayer.swf_db(f, _sec_d(c["hop"]), x, ctx["h0"])
            tot += absorption_db(f, c["hop"], x, ssn) * fac + swf
            measured = measured or swf > 1 or fac >= 1.5
        db = tot * c["n"] / len(c["chis"])
        if c["muf"]:
            out.append((CODE[_cell(f, c["muf"], db)], db))
        elif measured and db > ABSORBED_DB:
            out.append((CODE["absorbed"], db))      # MUF inconnue (ionosonde muette) mais absorption mesurée
        else:
            out.append((CODE[None], None))
    return out


def skip_map(grid, bands, sfi):
    ssn = ssn_from_sfi(sfi)
    return {"az_step": MAP_AZ_STEP, "rings": MAP_RINGS,
            "bands": {b: "".join(code for code, _ in _codes(grid, f, ssn)) for b, f in bands},
            "muf": [None if c["muf"] is None else round(c["muf"], 1) for c in grid["cells"]],
            "when": grid["when"].strftime("%H:%M UTC"), "ssn": round(ssn), "dlayer": dlayer_info()}


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
            "thresholds_db": [WEAK_DB, ABSORBED_DB], "when": grid["when"].strftime("%H:%M UTC"),
            "dlayer": dlayer_info()}



# ---------- écoute du WebSDR : propagation × diagramme de l'antenne de réception ----------
LISTEN_GOOD_DB, LISTEN_FAIR_DB = 0.0, -6.0


def listen_map(grid, bands, sfi, gain_fn, takeoff_fn):
    """Qualité d'écoute par case : là où la bande passe (o/e/w), gain de l'antenne de réception à l'angle
    d'arrivée, diminué de 3 dB en limite de MUF et de 6 dB si l'absorption affaiblit.
    G = bonne (≥ 0 dBi), M = moyenne (≥ −6), P = faible ; c/a/- inchangés (silence, absorbée, pas de mesure)."""
    ssn = ssn_from_sfi(sfi)
    out = {}
    for band, f in bands:
        codes = []
        for c, (code, _db) in zip(grid["cells"], _codes(grid, f, ssn)):
            if code not in "oew":
                codes.append(code)
                continue
            g = gain_fn(band, takeoff_fn(c["hop"])) - (3 if code == "e" else 0) - (6 if code == "w" else 0)
            codes.append("G" if g >= LISTEN_GOOD_DB else "M" if g >= LISTEN_FAIR_DB else "P")
        out[band] = "".join(codes)
    return {"az_step": MAP_AZ_STEP, "rings": MAP_RINGS, "bands": out,
            "muf": [None if c["muf"] is None else round(c["muf"], 1) for c in grid["cells"]],
            "when": grid["when"].strftime("%H:%M UTC"), "ssn": round(ssn), "dlayer": dlayer_info()}



BANNER_SCORE = {"G": 1.0, "M": 0.6, "P": 0.25}


def listen_probability(lmap, radius_km=800):
    """Probabilité de réception par bande dans un disque autour du récepteur : moyenne, pondérée par la
    surface des cases, des scores bonne 1 / moyenne 0,6 / faible 0,25 / silence ou absorbée 0.
    Les cases sans mesure sont écartées ; None si aucune case n'est mesurée."""
    rings = lmap["rings"]
    inner = [0] + rings[:-1]
    n = len(rings)
    out = {}
    for band, codes in lmap["bands"].items():
        tot = acc = 0.0
        for i, code in enumerate(codes):
            k = i % n
            lo, hi = inner[k], min(rings[k], radius_km)
            if lo >= radius_km or code == "-":
                continue
            w = hi * hi - lo * lo                 # surface de la portion d'anneau (même angle pour toutes)
            tot += w
            acc += w * BANNER_SCORE.get(code, 0.0)
        out[band] = None if tot == 0 else round(100 * acc / tot)
    return out



# ---------- indice de performance (IP) du WebSDR, par bande ----------
# Tranches de distance à poids égal : une bande ouverte seulement en DX garde une note honnête.
IP_TRANCHES = [("d100", 0, 100, "loc"), ("d300", 100, 300, "loc"), ("d900", 300, 900, "reg"),
               ("d2500", 900, 2500, "eu"), ("dx", 2500, 5000, "dx")]
IP_PRED_W, IP_MEAS_W = 0.4, 0.6          # poids prévision / mesure réelle (quand elle est récente)


def measure_score(m):
    """Mesure réelle d'une bande -> 0..100 : meilleur SNR (6 dB -> 0, 30 dB -> 70) + nombre de signaux (10 -> 30)."""
    if not m or not m.get("signals"):
        return 0.0
    snr = max(0.0, min(1.0, ((m.get("best_snr") or 0) - 6) / 24))
    return 70 * snr + 30 * min(1.0, m["signals"] / 10)


def observed_score(n, snr=None):
    """Stations localisées entendues dans une tranche -> note, orientée phonie (SSB).
    snr : SNR FT8 représentatif de la tranche (dB, bande de 2,5 kHz), None = contact du carnet (pas de
    SNR : compté comme pleinement exploitable). Le FT8 passe jusqu'à −24 dB, une SSB confortable demande
    environ +5 dB : −24 dB -> 15, −10 -> 56, 0 -> 85, +5 et plus -> 100. Avec 1 ou 2 stations : 60 au plus."""
    if not n:
        return 0
    q = 100 if snr is None else max(15, min(100, round(15 + (snr + 24) * 85 / 29)))
    return min(q, 60) if n < 3 else q


def performance_index(lmap, measured=None, heard=None):
    """Par bande : {ip, pred, meas, zone, tranches{clé: 0..100|None}}.
    note d'une tranche = score des cases pondéré par la surface (bonne 1, moyenne 0,6, faible 0,25,
    silence/absorbée 0) ; pred = 0,7 × meilleure tranche + 0,3 × moyenne des tranches ;
    zone = tranche la mieux notée (≥ 50).
    ip = 0,4·pred + 0,6·mesure si une mesure récente existe, sinon pred.
    heard : {bande: {tranches: {clé: nb de stations localisées}}} (carnet + veille FT8). Une tranche
    où des stations ont été entendues est relevée à observed_score() ; l'absence de station n'abaisse
    jamais une tranche (zone de silence, personne n'émet). tranches_iono garde la prévision seule."""
    rings = lmap["rings"]
    inner = [0] + rings[:-1]
    n = len(rings)
    out = {}
    for band, codes in lmap["bands"].items():
        acc = {t[0]: [0.0, 0.0] for t in IP_TRANCHES}
        for i, code in enumerate(codes):
            k = i % n
            lo, hi = inner[k], rings[k]
            if code == "-":
                continue
            for key, tlo, thi, _z in IP_TRANCHES:
                a, b = max(lo, tlo), min(hi, thi)
                if b > a:
                    w = b * b - a * a
                    acc[key][0] += w
                    acc[key][1] += w * BANNER_SCORE.get(code, 0.0)
        tr = {k: (round(100 * v[1] / v[0]) if v[0] else None) for k, v in acc.items()}
        tr_iono = dict(tr)
        hb = (heard or {}).get(band) or {}
        for k, nb in (hb.get("tranches") or {}).items():
            o = observed_score(nb, (hb.get("snr") or {}).get(k))
            if k in tr and o and (tr[k] is None or o > tr[k]):
                tr[k] = o
        known = [v for v in tr.values() if v is not None]
        # une bande ne s'ouvre jamais sur toutes les distances (zone de silence) : la meilleure tranche
        # compte pour 70 %, l'étendue (moyenne des tranches) pour 30 %
        pred = round(0.7 * max(known) + 0.3 * sum(known) / len(known)) if known else None
        best = max(((tr[k], z) for k, _a, _b, z in IP_TRANCHES if tr[k] is not None), default=(None, None))
        zone = best[1] if best[0] is not None and best[0] >= 50 else None
        m = (measured or {}).get(band)
        meas = round(measure_score(m)) if m is not None else None
        if pred is None and meas is None:
            ip = None
        elif meas is None:
            ip = pred
        elif pred is None:
            ip = meas
        else:
            ip = round(IP_PRED_W * pred + IP_MEAS_W * meas)
        out[band] = {"ip": ip, "pred": pred, "meas": meas, "zone": zone, "tranches": tr,
                     "tranches_iono": tr_iono, "corrected": tr != tr_iono}
    return out
