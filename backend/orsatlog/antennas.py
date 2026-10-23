"""Meilleure antenne par bande et par tranche de distance — comparaison de modèles types (ESTIMATION).

Pour chaque tranche, l'angle de départ nécessaire vient de la géométrie du saut (réflexion F2 à 300 km).
Pour chaque modèle, gain dans la direction favorable de l'antenne, à cet angle, au-dessus d'un sol
moyen (εr = 13, σ = 5 mS/m) :
    G(Δ) = G_espace_libre + 20·log10 |E(Δ)| + 20·log10 |1 + Γ(Δ)·exp(−j·2k·h·sinΔ)| − pertes
  - E(Δ) : diagramme propre de l'élément dans le plan vertical utile (1 pour un dipôle en travers du fil)
  - Γ : coefficient de Fresnel du sol, polarisation horizontale ou verticale selon l'antenne
  - h : hauteur du centre de rayonnement (en m, convertie en longueurs d'onde bande par bande)
C'est le calcul classique « élément + image dans le sol » (méthode des logiciels de type HFTA) : les
valeurs absolues sont approchées, la hiérarchie entre antennes est fiable. Le couplage aux objets voisins,
les pertes de câble et le rendement réel des radians ne sont pas comptés.
"""

import cmath
import math

EARTH_R = 6371.0
H_F2 = 300.0
EPS_R, SIGMA = 13.0, 0.005          # sol moyen

# (id, libellé, polarisation, hauteur du centre en m ou fonction de λ, gain espace libre dBi,
#  diagramme vertical E(Δ en rad, λ), pertes dB, bandes utilisables (MHz min, max), directive ?)
def _flat(_d, _l):
    return 1.0


def _loop_h(d, _l):
    # loop horizontale onde entière ≈ deux dipôles en phase espacés de λ/4 : maximum vers le zénith
    return math.cos(math.pi / 4 * math.cos(d))


def _loop_v(d, _l):
    # delta-loop / quad verticale, polarisation horizontale ≈ deux dipôles superposés à λ/4 : angle bas
    return math.cos(math.pi / 4 * math.sin(d))


def _vert(length_l):
    """Monopôle vertical de longueur donnée (en λ) : diagramme du dipôle 2× plus long."""
    k = math.pi * 2 * length_l

    def e(d, _l):
        c = math.cos(d)
        if c < 1e-3:
            return 0.0
        return abs((math.cos(k * math.sin(d)) - math.cos(k)) / c) / abs(1 - math.cos(k))
    return e


def _beam(q):
    return lambda d, _l: max(0.0, math.cos(d)) ** q


MODELS = [
    # id, libellé, pol, hauteur (m) ou ("lambda", x), gain fs, E, pertes, (fmin, fmax), directive
    ("dip6", "Dipôle à 6 m", "H", 6, 2.15, _flat, 0.3, (1.8, 54), False),
    ("dip10", "Dipôle à 10 m", "H", 10, 2.15, _flat, 0.3, (1.8, 54), False),
    ("dip15", "Dipôle à 15 m", "H", 15, 2.15, _flat, 0.3, (1.8, 54), False),
    ("dip25", "Dipôle à 25 m", "H", 25, 2.15, _flat, 0.3, (1.8, 54), False),
    ("invv12", "V inversé, sommet 12 m", "H", 9.5, 1.6, _flat, 0.4, (1.8, 54), False),
    ("efhw10", "Long fil / EFHW à 10 m", "H", 10, 2.0, _flat, 0.8, (1.8, 54), False),
    ("nvis3", "Dipôle NVIS à 3 m", "H", 3, 2.15, _flat, 0.8, (1.8, 11), False),
    ("loop7", "Loop onde entière horizontale à 7 m", "H", 7, 3.1, _loop_h, 0.3, (1.8, 54), False),
    ("loop15", "Loop onde entière horizontale à 15 m", "H", 15, 3.1, _loop_h, 0.3, (1.8, 54), False),
    ("delta", "Delta-loop verticale (base 2 m)", "H", ("lambda", 0.12, 2), 3.1, _loop_v, 0.3, (3.5, 54), False),
    # verticales au sol (« Vg ») : gain et diagramme sur sol parfait, puis correction du sol réel |1+Γv|/2
    ("vert14", "Verticale λ/4 au sol (radians)", "Vg", 0, 5.15, _vert(0.25), 1.5, (1.8, 54), False),
    ("vert58", "Verticale 5/8 λ au sol (radians)", "Vg", 0, 8.0, _vert(0.625), 1.5, (3.5, 54), False),
    # verticales surélevées (« V ») : élément en espace libre + image dans le sol réel
    ("gp", "Ground-plane surélevée (base 10 m)", "V", ("lambda", 0.125, 10), 2.15, _vert(0.25), 0.5, (7, 54), False),
    ("magloop", "Loop magnétique (petite, verticale)", "V", 2, 1.76, _beam(1.0), 4.0, (3.5, 30), False),
    ("hexbeam", "Hexbeam 2 él. à 10 m", "H", 10, 5.5, _beam(1.2), 0.3, (14, 54), True),
    ("yagi3_12", "Yagi 3 él. à 12 m", "H", 12, 7.5, _beam(1.5), 0.2, (14, 54), True),
    ("yagi3_20", "Yagi 3 él. à 20 m", "H", 20, 7.5, _beam(1.5), 0.2, (14, 54), True),
    ("yagi5_20", "Yagi 5 él. à 20 m", "H", 20, 10.0, _beam(2.5), 0.2, (14, 54), True),
    ("quad2", "Quad cubique 2 él. à 15 m", "H", 15, 7.0, _beam(1.4), 0.2, (14, 30), True),
]


SHORT = {"dip6": "Dipôle 6 m", "dip10": "Dipôle 10 m", "dip15": "Dipôle 15 m", "dip25": "Dipôle 25 m",
         "invv12": "V inversé 12 m", "efhw10": "EFHW 10 m", "nvis3": "NVIS 3 m", "loop7": "Loop horiz. 7 m",
         "loop15": "Loop horiz. 15 m", "delta": "Delta-loop", "vert14": "Verticale λ/4", "vert58": "Verticale 5/8",
         "gp": "Ground-plane", "magloop": "Loop magn.", "hexbeam": "Hexbeam", "yagi3_12": "Yagi 3 él. 12 m",
         "yagi3_20": "Yagi 3 él. 20 m", "yagi5_20": "Yagi 5 él. 20 m", "quad2": "Quad 2 él."}


def _gamma(delta, lam, pol):
    """Coefficient de réflexion de Fresnel du sol moyen."""
    eps = complex(EPS_R, -60 * SIGMA * lam)
    s, c2 = math.sin(delta), math.cos(delta) ** 2
    root = cmath.sqrt(eps - c2)
    if pol == "H":
        return (s - root) / (s + root)
    return (eps * s - root) / (eps * s + root)


def _height(spec, lam):
    if isinstance(spec, tuple):          # ("lambda", fraction, base en m)
        return spec[1] * lam + spec[2]
    return float(spec)


def gain_dbi(model, freq_mhz, elev_deg):
    _id, _lbl, pol, hspec, g0, efn, loss, (fmin, fmax), _dir = model
    if not fmin <= freq_mhz <= fmax:
        return None
    lam = 299.792458 / freq_mhz
    d = math.radians(max(0.5, elev_deg))
    h = _height(hspec, lam)
    e = efn(d, lam)
    if pol == "Vg":
        ground = abs(1 + _gamma(d, lam, "V")) / 2           # rapport sol réel / sol parfait
    else:
        ground = abs(1 + _gamma(d, lam, pol) * cmath.exp(-1j * 4 * math.pi * h / lam * math.sin(d)))
    if e <= 1e-6 or ground <= 1e-6:
        return -40.0
    return g0 + 20 * math.log10(e) + 20 * math.log10(ground) - loss


def takeoff_deg(d_km):
    """Angle de départ d'un saut de d km (réflexion F2 à 300 km), un seul saut jusqu'à 3500 km."""
    n = max(1, math.ceil(d_km / 3500))
    theta = (d_km / n) / (2 * EARTH_R)
    return math.degrees(math.atan((math.cos(theta) - EARTH_R / (EARTH_R + H_F2)) / math.sin(theta)))


def best_for(freq_mhz, lo_km, hi_km):
    """Classement des modèles pour une tranche : gain moyen (puissance) sur les angles de la tranche."""
    # DX (> 2500 km) : sauts les plus longs possibles, donc les angles bas (2 à 8°) ;
    # sinon : bas, milieu et haut de la tranche
    dists = [2500, 3000, 3500] if lo_km >= 2500 else [max(lo_km, 25), (max(lo_km, 25) + hi_km) / 2, hi_km]
    angles = [takeoff_deg(x) for x in dists]
    ranked = []
    for m in MODELS:
        gs = [gain_dbi(m, freq_mhz, a) for a in angles]
        if any(g is None for g in gs):
            continue
        p = sum(10 ** (g / 10) for g in gs) / len(gs)
        ranked.append({"id": m[0], "name": m[1], "short": SHORT.get(m[0], m[1]),
                       "dbi": round(10 * math.log10(p), 1), "directive": m[8]})
    ranked.sort(key=lambda r: -r["dbi"])
    return {"angles": [round(a) for a in angles], "ranked": ranked}


def table(bands, ranges):
    """bands = [(nom, MHz)], ranges = [(clé, lo, hi)] -> meilleures antennes par bande et tranche."""
    out = []
    for band, f in bands:
        row = {"band": band}
        for key, lo, hi in ranges:
            r = best_for(f, lo, hi)
            row[key] = {"angles": r["angles"], "top": r["ranked"][:8]}
        out.append(row)
    return {"rows": out, "models": [{"id": m[0], "name": m[1], "short": SHORT.get(m[0], m[1]),
                                     "directive": m[8]} for m in MODELS]}


_TABLE = {}


def cached_table(bands, ranges):
    """Le classement ne dépend que de la bande et de la tranche : calculé une fois."""
    key = (tuple(bands), tuple(ranges))
    if key not in _TABLE:
        _TABLE[key] = table(bands, ranges)
    return _TABLE[key]


# ---------- antenne du WebSDR ORSAT : diagramme NEC réel ----------
# websdr_loop.json : loop horizontale 80 m (trapèze) à 6 m sur sable, alimentée dans un angle (balun 4:1),
# NEC-2 avec sol de Sommerfeld ; désadaptation calculée par rapport à 200 Ω.
# « avg » = gain moyenné sur l'azimut par degré d'élévation ; « grid » = [élévation][azimut tous les 5°]
# (orientation de la loop encore inconnue : on utilise la moyenne).
_WEBSDR = None


def websdr_pattern():
    global _WEBSDR
    if _WEBSDR is None:
        import json
        from pathlib import Path
        _WEBSDR = json.loads((Path(__file__).with_name("websdr_loop.json")).read_text())
    return _WEBSDR


def websdr_gain(band, elev_deg):
    """Gain de réception (dBi, moyenne azimut) de la loop du WebSDR ; bande sans calcul -> la plus proche."""
    pat = websdr_pattern()["bands"]
    if band not in pat:
        mhz = {"6m": 50.0}.get(band)
        band = min(pat, key=lambda b: abs(pat[b]["mhz"] - (mhz or 0)))
    e = max(0, min(90, int(round(elev_deg))))
    # pénalité de rapport signal/bruit due à la désadaptation (nulle tant que le bruit extérieur domine)
    return pat[band]["avg"][e] - pat[band].get("snr_penalty_db", 0.0)
