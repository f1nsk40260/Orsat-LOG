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


def compute(home, dirs, bands, interp, destination, sfi, when=None):
    """Portée par direction et meilleure direction.
    interp(point, champ) -> (valeur, ionosondes) ; destination(home, az, km) -> point."""
    when = when or datetime.now(timezone.utc)
    ssn = ssn_from_sfi(sfi)
    per_dir = {}
    for name, az in dirs:
        geo_r = {}
        for key, hop, refl, _lo in RANGES:
            pt = destination(home, az, refl)
            fof2, _ = interp(pt, "fof2")
            m3000, _ = interp(pt, "mufd")
            hm, _ = interp(pt, "hmf2")
            muf = m3000 if hop == 3000 else mufd_estimate(fof2, m3000, hop, hm)
            geo_r[key] = {"muf": muf, "chi": solar_zenith(pt[0], pt[1], when), "hop": hop}
        rows = []
        for band, f in bands:
            row = {"band": band}
            for key, *_ in RANGES:
                g = geo_r[key]
                db = absorption_db(f, g["hop"], g["chi"], ssn)
                row[key] = {"state": _cell(f, g["muf"], db),
                            "muf": round(g["muf"], 1) if g["muf"] else None, "db": round(db)}
            rows.append(row)
        per_dir[name] = rows
    # meilleure direction, portée par portée
    best = []
    for i, (band, _f) in enumerate(bands):
        row = {"band": band}
        for key, *_ in RANGES:
            cands = [(RANK[per_dir[n][i][key]["state"]], per_dir[n][i][key]["muf"] or 0, n) for n, _ in dirs]
            r, _m, n = max(cands)
            row[key] = {**per_dir[n][i][key], "dir": n if r >= 0 else None}
        best.append(row)
    for rows in [best, *per_dir.values()]:
        for row in rows:
            # zone de silence : fermée (MUF dépassée) près, ouverte plus loin -> « silence < X km »
            states = [row[k]["state"] for k, *_ in RANGES]
            first = next((i for i, s in enumerate(states) if s in ("open", "edge", "weak")), None)
            row["skip"] = (RANGES[first][3] if first and all(s == "closed" for s in states[:first]) else None)
    return {"best": best, "dirs": per_dir, "ssn": round(ssn),
            "thresholds_db": [WEAK_DB, ABSORBED_DB], "when": when.strftime("%H:%M UTC")}
